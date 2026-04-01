"""
Tests de mapeo para MigratorExporter — sin llamadas HTTP reales.

Validan que _map_solic_gasto, _map_ped_item, _map_oc_item y
_write_batch_orden_pago construyen los payloads correctos.
"""
from unittest.mock import patch

import pytest

from src.exporter import MigratorExporter


# ─── Fixture: MigratorExporter sin HTTP ──────────────────────────────────────

@pytest.fixture
def exporter():
    """MigratorExporter con lookups mockeados para tests unitarios."""
    with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
        mock_lookups.return_value = {
            "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
            "tipos_factura": [
                {"id": "2", "name": "Factura A", "codename": "factura_a"},
                {"id": "3", "name": "Factura B", "codename": "factura_b"},
            ],
            "tipos_de_pago": [
                {"id": "4", "name": "Transferencia"}
            ],
        }
        with patch.dict("os.environ", {
            "MIGRATOR_BASE_URL": "https://example.com",
            "MIGRATOR_TENANT": "test",
            "MIGRATOR_API_KEY": "key",
            "MIGRATOR_DEFAULT_UNIDAD_ID": "1",
            "MIGRATOR_DEFAULT_TIPO_PAGO_ID": "4",
        }):
            exp = MigratorExporter(dry_run=True)
    return exp


# ─── solic_gastos ─────────────────────────────────────────────────────────────

class TestMapSolicGasto:

    def test_mapea_campos_basicos(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "500",
            "FECH_SOLIC": "2026-03-10 00:00:00",
            "IMPORTE_TOT": "1210.50",
            "ESTADO_SOLIC": "C",
            "TIPO_DOC": "factura_a",
            "NRO_DOC": "42",
            "OBSERVACIONES": "Factura de papelería",
        }
        result = exporter._map_solic_gasto(raw)
        assert result is not None
        assert result["external_id"] == {"rafam_ref": "SG-2026-1-500"}
        assert result["Gasto"]["fecha"] == "2026-03-10"
        assert result["Gasto"]["importe_total"] == 1210.50
        assert result["Gasto"]["tipo_factura_id"] == 2
        assert result["Gasto"]["factura_nro"] == "00000042"
        assert result["Gasto"]["observacion"] == "Factura de papelería"

    def test_excluye_anuladas(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "501",
            "FECH_SOLIC": "2026-03-10", "IMPORTE_TOT": "100",
            "ESTADO_SOLIC": "A",
        }
        assert exporter._map_solic_gasto(raw) is None

    def test_sin_fecha_retorna_none(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "502",
            "FECH_SOLIC": "", "IMPORTE_TOT": "100", "ESTADO_SOLIC": "C",
        }
        assert exporter._map_solic_gasto(raw) is None

    def test_sin_importe_retorna_none(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "503",
            "FECH_SOLIC": "2026-03-10", "IMPORTE_TOT": None, "ESTADO_SOLIC": "C",
        }
        assert exporter._map_solic_gasto(raw) is None

    def test_tipo_doc_sin_match_usa_default(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "504",
            "FECH_SOLIC": "2026-03-10", "IMPORTE_TOT": "50",
            "ESTADO_SOLIC": "C", "TIPO_DOC": "DESCONOCIDO",
        }
        result = exporter._map_solic_gasto(raw)
        # default es None cuando MIGRATOR_DEFAULT_TIPO_FACTURA_ID no está seteado
        assert result is not None
        assert "tipo_factura_id" not in result["Gasto"]

    def test_nro_doc_cero_no_se_incluye(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "505",
            "FECH_SOLIC": "2026-03-10", "IMPORTE_TOT": "50",
            "ESTADO_SOLIC": "C", "NRO_DOC": "0",
        }
        result = exporter._map_solic_gasto(raw)
        assert result is not None
        assert "factura_nro" not in result["Gasto"]


# ─── _format_date_only ────────────────────────────────────────────────────────

class TestFormatDateOnly:

    def test_datetime_string_recorta_hora(self, exporter):
        assert exporter._format_date_only("2026-03-10 14:30:00") == "2026-03-10"

    def test_solo_fecha(self, exporter):
        assert exporter._format_date_only("2026-03-10") == "2026-03-10"

    def test_vacio_devuelve_string_vacio(self, exporter):
        assert exporter._format_date_only("") == ""
        assert exporter._format_date_only(None) == ""


# ─── orden_pago grouping ──────────────────────────────────────────────────────

class TestWriteBatchOrdenPago:

    def _make_exporter(self):
        with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
            mock_lookups.return_value = {
                "unidades_de_medida": [],
                "tipos_factura": [],
                "tipos_de_pago": [{"id": "4", "name": "Transferencia"}],
            }
            with patch.dict("os.environ", {
                "MIGRATOR_BASE_URL": "https://example.com",
                "MIGRATOR_TENANT": "test",
                "MIGRATOR_API_KEY": "key",
                "MIGRATOR_DEFAULT_TIPO_PAGO_ID": "4",
            }):
                return MigratorExporter(dry_run=True)

    def test_agrupa_por_nro_op(self):
        exp = self._make_exporter()

        # Pre-poblar link_store con gastos (simula sync previo de solic_gastos)
        import json
        exp._link_store.save_link(
            entity="gasto",
            source_key=json.dumps({"rafam_ref": "SG-2026-1-100"}, sort_keys=True),
            remote_id="501",
        )
        exp._link_store.save_link(
            entity="gasto",
            source_key=json.dumps({"rafam_ref": "SG-2026-1-200"}, sort_keys=True),
            remote_id="502",
        )

        columns = [
            "EJERCICIO", "NRO_OP", "FECH_OP", "ESTADO_OP",
            "IMPORTE_TOTAL", "CONCEPTO", "NRO_CANCE",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "FECH_CONFIRM", "LUG_EMI", "CODIGO_FF", "JURISDICCION",
            "CODIGO_UE", "COD_PROV", "TIPO_OP", "TIPO_DOC", "NRO_DOC",
            "ANIO_DOC", "CONFIRMADO", "CANT_IMPRES", "FECH_ANUL",
            "MOTIVO_ANUL", "OBSERVACIONES", "COD_EMP",
            "IMPORTE_BONIFICACION", "IMPORTE_DEDUCCIONES", "ASIENTO",
            "ASIENTO_ANUL", "MONTO_SIN_IVA", "DEUDA", "BLOQUEADA",
            "RECURSO", "PERCIBIDO", "NO_PAGADO", "PAGADO",
            "RECO_DEU_ORDEN", "RECO_DEU_EJERCICIO", "RECO_DEU_COMPRA",
            "RECO_DEU_COMPRA_EJER", "F931", "SICORE",
        ]

        def row(nro_op, sg_deleg, sg_nro, estado="C", importe="500"):
            vals = {
                "EJERCICIO": "2026", "NRO_OP": str(nro_op),
                "FECH_OP": "2026-03-10 00:00:00",
                "ESTADO_OP": estado, "IMPORTE_TOTAL": importe,
                "CONCEPTO": "Pago servicios", "NRO_CANCE": str(sg_nro),
                "SG_DELEG_SOLIC": str(sg_deleg), "SG_NRO_SOLIC": str(sg_nro),
                "FECH_CONFIRM": "2026-03-11 00:00:00",
            }
            return tuple(vals.get(c, "") for c in columns)

        rows = [
            row(1001, 1, 100),
            row(1002, 1, 200),
            row(1003, None, None, estado="N"),  # sin gasto → omitida
        ]

        sent_payloads = []

        def fake_post(url, payload):
            sent_payloads.append(payload)
            return {"stats": {"ordenes_pago": {"ok": 2, "error": 0}}}

        exp._post_json = fake_post
        exp.write_batch("orden_pago", columns, rows)

        assert len(sent_payloads) == 1
        ops = sent_payloads[0]["ordenes_pago"]
        # 1001 y 1002 tienen gasto; 1003 no tiene (SG_DELEG_SOLIC=None)
        assert len(ops) == 2
        ids = {op["external_id"]["nro_op"] for op in ops}
        assert ids == {1001, 1002}
        # verificar que gasto_ids se resolvió a IDs numéricos de Paxapos
        for op in ops:
            assert len(op["gasto_ids"]) == 1
            assert isinstance(op["gasto_ids"][0], int)

    def test_op_anulada_no_se_envia(self):
        exp = self._make_exporter()
        columns = [
            "EJERCICIO", "NRO_OP", "FECH_OP", "ESTADO_OP",
            "IMPORTE_TOTAL", "CONCEPTO", "NRO_CANCE",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "FECH_CONFIRM", "LUG_EMI", "CODIGO_FF", "JURISDICCION",
            "CODIGO_UE", "COD_PROV", "TIPO_OP", "TIPO_DOC", "NRO_DOC",
            "ANIO_DOC", "CONFIRMADO", "CANT_IMPRES", "FECH_ANUL",
            "MOTIVO_ANUL", "OBSERVACIONES", "COD_EMP",
            "IMPORTE_BONIFICACION", "IMPORTE_DEDUCCIONES", "ASIENTO",
            "ASIENTO_ANUL", "MONTO_SIN_IVA", "DEUDA", "BLOQUEADA",
            "RECURSO", "PERCIBIDO", "NO_PAGADO", "PAGADO",
            "RECO_DEU_ORDEN", "RECO_DEU_EJERCICIO", "RECO_DEU_COMPRA",
            "RECO_DEU_COMPRA_EJER", "F931", "SICORE",
        ]
        vals = {
            "EJERCICIO": "2026", "NRO_OP": "999",
            "FECH_OP": "2026-03-10", "ESTADO_OP": "A",
            "IMPORTE_TOTAL": "100", "NRO_CANCE": "50",
            "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": "50",
            "FECH_CONFIRM": "",
        }
        rows = [tuple(vals.get(c, "") for c in columns)]

        sent = []
        exp._post_json = lambda url, p: sent.append(p) or {"stats": {"ordenes_pago": {"ok": 0}}}
        exp.write_batch("orden_pago", columns, rows)
        assert sent == []  # no se envió nada


# ─── tipo_factura lookup ──────────────────────────────────────────────────────

class TestResolveTipoFacturaId:

    def test_match_por_codename(self, exporter):
        assert exporter._resolve_tipo_factura_id("factura_a") == 2

    def test_match_por_name(self, exporter):
        assert exporter._resolve_tipo_factura_id("Factura B") == 3

    def test_sin_match_retorna_default(self, exporter):
        # default es None cuando MIGRATOR_DEFAULT_TIPO_FACTURA_ID no está seteado
        assert exporter._resolve_tipo_factura_id("ORDSE") is None

    def test_none_retorna_default(self, exporter):
        assert exporter._resolve_tipo_factura_id(None) is None
