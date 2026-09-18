"""OP cuyo proveedor no esta migrado + CUIT con digito verificador invalido.

Caso real (sep-2026, OP 2026-6915): el proveedor 51114 tenia FECHA_ULT_COMP
NULL (nunca compro, cobra por OP directa) asi que el cursor incremental de
proveedores no lo traia nunca; la OP se enviaba sin proveedor_id y el receptor
la rechazaba ("No se puede auto-crear gasto sin proveedor_id") hasta agotar
max_attempts. Ademas su CUIT era 00-00000000-0.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, select

from src.exporter import MigratorExporter
from src.gateway_mapper import map_proveedor_migrator_row
from src.retry_store import RetryStore
from src.source_repository import SourceRepository
from src.utils import is_valid_cuit


def _op_key(ejercicio: int, nro_op: int) -> str:
    return json.dumps({"ejercicio": ejercicio, "nro_op": nro_op}, sort_keys=True)


class TestIsValidCuit:
    @pytest.mark.parametrize("cuit", ["20123456786", "30123456781", "27005483552"])
    def test_acepta_digito_verificador_correcto(self, cuit):
        assert is_valid_cuit(cuit) is True

    @pytest.mark.parametrize(
        "cuit",
        [
            "27005483551",  # COD_PROV 34 en RAFAM: deberia terminar en 2
            "27060773003",  # COD_PROV 110: deberia terminar en 4
            "20053087752",  # COD_PROV 262: deberia terminar en 3
            "00000000000",  # pasa el modulo 11 pero no identifica a nadie
            "2012345678",   # 10 digitos
            "",
            None,
        ],
    )
    def test_rechaza_invalidos(self, cuit):
        assert is_valid_cuit(cuit) is False


class TestProveedorCuitInvalido:
    def test_cuit_invalido_se_envia_sin_cuit(self):
        result = map_proveedor_migrator_row({
            "COD_PROV": "51114",
            "RAZON_SOCIAL": "ALOISI ENRIQUE PASCUAL",
            "CUIT": "00-00000000-0",
        })
        assert result is not None
        assert "cuit" not in result["Proveedor"]
        assert "tipo_documento_id" not in result["Proveedor"]

    def test_cuit_valido_se_conserva(self):
        result = map_proveedor_migrator_row({
            "COD_PROV": "7",
            "RAZON_SOCIAL": "Prov SA",
            "CUIT": "20-12345678-6",
        })
        assert result["Proveedor"]["cuit"] == "20123456786"
        assert result["Proveedor"]["tipo_documento_id"] == 1


class TestProveedoresRetryFilter:
    def test_reinyecta_por_cod_prov_sin_depender_del_cursor(self):
        repo = SourceRepository.__new__(SourceRepository)
        table = Table(
            "PROVEEDORES", MetaData(),
            Column("COD_PROV", Integer), Column("RAZON_SOCIAL", String),
        )
        sql = str(
            select(table)
            .where(repo._proveedores_retry_filter(table, {"51114", "34"}))
            .compile(compile_kwargs={"literal_binds": True})
        )
        assert '"COD_PROV" IN (34, 51114)' in sql


class TestOrdenPagoProveedorSinLink:
    COLUMNS = [
        "EJERCICIO", "NRO_OP", "ESTADO_OP", "CONFIRMADO", "FECH_CONFIRM",
        "IMPORTE_TOTAL", "CONCEPTO", "COD_PROV",
        "SG_DELEG_SOLIC", "SG_NRO_SOLIC", "OPI_NRO_COMPROB",
        "SG_OC_EJERCICIO", "SG_OC_NRO", "SG_OC_UNI_COMPRA",
    ]

    def _make_exporter(self, tmp_path, retry_store):
        with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
            mock_lookups.return_value = {
                "unidades_de_medida": [],
                "tipos_factura": [],
                "tipos_de_pago": [{"id": "4", "name": "Transferencia"}],
            }
            with patch.dict("os.environ", {
                "PAXAPOS_URL": "https://example.com",
                "PAXAPOS_TENANT": "test",
                "PAXAPOS_API_KEY": "key",
                "PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID": "4",
                "LOCAL_STATE_DB_PATH": str(tmp_path / "state.db"),
            }):
                exporter = MigratorExporter(dry_run=False)
        exporter.attach_retry_store(retry_store)
        return exporter

    def _row(self, **overrides):
        vals = {
            "EJERCICIO": "2026",
            "NRO_OP": "6915",
            "ESTADO_OP": "C",
            "CONFIRMADO": "S",
            "FECH_CONFIRM": "2026-09-16 00:00:00",
            "IMPORTE_TOTAL": "28301399.56",
            "CONCEPTO": "Pago",
            "COD_PROV": "51114",
            "SG_DELEG_SOLIC": "1",
            "SG_NRO_SOLIC": "100",
            "OPI_NRO_COMPROB": "2020-16590000",
        }
        vals.update(overrides)
        return tuple(vals.get(c, "") for c in self.COLUMNS)

    def test_op_sin_proveedor_migrado_no_se_envia_y_encola_ambos(self, tmp_path):
        retry_store = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter = self._make_exporter(tmp_path, retry_store)
        sent = []
        exporter._post_json = lambda url, payload: sent.append(payload) or {"stats": {}}

        exporter.write_batch("orden_pago", self.COLUMNS, [self._row()])

        assert sent == []
        op_items = retry_store.list_items("orden_pago")
        assert [i.reason_detail for i in op_items] == ["provider_not_migrated"]
        assert op_items[0].reason_code == "dependency_missing"
        # El proveedor queda en SU cola con str(COD_PROV): es la clave que
        # _proveedores_retry_filter reinyecta en la query de PROVEEDORES.
        assert retry_store.pending_external_ids("proveedores") == {"51114"}
        retry_store.close()

    def test_op_se_envia_cuando_el_proveedor_ya_tiene_link(self, tmp_path):
        retry_store = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter = self._make_exporter(tmp_path, retry_store)
        retry_store.enqueue("orden_pago", _op_key(2026, 6915), "dependency_missing", "esperando proveedor",
                            reason_detail="provider_not_migrated")
        exporter._link_store.save_link("proveedores", "51114", remote_id="900")
        sent = []
        exporter._post_json = lambda url, payload: sent.append(payload) or {
            "stats": {"ordenes_pago": {"ok": 1, "error": 0}},
            "results": {"ordenes_pago": [
                {"success": True, "external_id": {"ejercicio": 2026, "nro_op": 6915}, "id": 5555}
            ]},
        }

        exporter.write_batch("orden_pago", self.COLUMNS, [self._row()])

        assert len(sent) == 1
        assert sent[0]["ordenes_pago"][0]["proveedor_id"] == 900
        assert retry_store.pending_external_ids("orden_pago") == set()
        assert retry_store.pending_external_ids("proveedores") == set()
        retry_store.close()

    def test_op_sin_ningun_cod_prov_conserva_comportamiento(self, tmp_path):
        """Sin COD_PROV en la fila no hay proveedor que esperar: se envia como antes."""
        retry_store = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter = self._make_exporter(tmp_path, retry_store)
        sent = []
        exporter._post_json = lambda url, payload: sent.append(payload) or {"stats": {}}

        exporter.write_batch("orden_pago", self.COLUMNS, [self._row(COD_PROV="")])

        assert len(sent) == 1
        assert "proveedor_id" not in sent[0]["ordenes_pago"][0]
        assert retry_store.list_items("orden_pago") == []
        retry_store.close()
