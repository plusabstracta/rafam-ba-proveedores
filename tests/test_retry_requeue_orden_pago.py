"""Cobertura de la recuperacion de OPs salteadas (cola de reintentos).

Antes de estos fixes una OP salteada por dependencia faltante se perdia para
siempre: el watermark del checkpoint avanzaba igual y la fila no volvia a entrar
en la query. Ademas la cola nunca drenaba porque `_record_batch_outcomes` habia
quedado sin invocar.
"""

from __future__ import annotations

import datetime
import json
from unittest.mock import patch

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, and_, select

from src.config import ENTITY_CONFIGS
from src.exporter import MigratorExporter
from src.models import Checkpoint, EntityConfig
from src.retry_store import RetryStore
from src.source_repository import SourceRepository


def _op_key(ejercicio: int, nro_op: int) -> str:
    return json.dumps({"ejercicio": ejercicio, "nro_op": nro_op}, sort_keys=True)


def _orden_pago_table() -> Table:
    return Table(
        "ORDEN_PAGO",
        MetaData(),
        Column("EJERCICIO", Integer),
        Column("NRO_OP", Integer),
        Column("FECH_CONFIRM", DateTime),
        Column("ESTADO_OP", String),
    )


class TestPendingReprocessConfig:
    def test_orden_pago_reprocesa_estado_confirmado(self):
        # El filtro base de la query exige ESTADO_OP='C'. Con 'N' la clausula de
        # reproceso era inalcanzable y la ventana de 30 dias nunca aplicaba.
        assert ENTITY_CONFIGS["orden_pago"].pending_state_value == "C"
        assert ENTITY_CONFIGS["retenciones"].pending_state_value == "C"


class TestOpRetryFilter:
    def test_agrupa_por_ejercicio_y_descarta_claves_invalidas(self):
        repo = SourceRepository.__new__(SourceRepository)
        table = _orden_pago_table()
        keys = {_op_key(2026, 10), _op_key(2026, 11), _op_key(2025, 7), "no-json"}

        sql = str(
            select(table)
            .where(repo._op_retry_filter(table, keys))
            .compile(compile_kwargs={"literal_binds": True})
        )

        assert '"EJERCICIO" = 2026' in sql
        assert '"NRO_OP" IN (10, 11)' in sql
        assert '"EJERCICIO" = 2025' in sql
        assert '"NRO_OP" IN (7)' in sql

    def test_sin_claves_no_agrega_filtro(self):
        repo = SourceRepository.__new__(SourceRepository)
        table = _orden_pago_table()
        assert repo._op_retry_filter(table, None) is None
        assert repo._op_retry_filter(table, set()) is None

    def test_se_orea_con_el_cursor_y_se_andea_con_el_filtro_base(self):
        repo = SourceRepository.__new__(SourceRepository)
        table = _orden_pago_table()
        cfg = EntityConfig(
            name="orden_pago",
            table_name="ORDEN_PAGO",
            ts_field="FECH_CONFIRM",
            pending_state_field="ESTADO_OP",
            pending_state_value="C",
            pending_reprocess_days=30,
        )
        cp = Checkpoint(
            entity="orden_pago",
            last_ts=datetime.datetime(2026, 7, 20),
            last_run=datetime.datetime(2026, 7, 20),
        )

        retry_filter = repo._op_retry_filter(table, {_op_key(2026, 10)})
        stmt = repo._apply_incremental_filters(
            select(table), table, cfg, cp, extra_filters=[retry_filter]
        )
        stmt = stmt.where(and_(table.c.ESTADO_OP == "C"))
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        # La OP encolada entra aunque su FECH_CONFIRM sea anterior al watermark.
        assert '"NRO_OP" IN (10)' in sql
        assert 'FECH_CONFIRM" >= ' in sql


class TestOrdenPagoEnqueue:
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
            "NRO_OP": "1001",
            "ESTADO_OP": "C",
            "CONFIRMADO": "S",
            "FECH_CONFIRM": "2026-03-11 00:00:00",
            "IMPORTE_TOTAL": "500",
            "CONCEPTO": "Pago",
            "COD_PROV": "555",
            "SG_DELEG_SOLIC": "1",
            "SG_NRO_SOLIC": "100",
            "OPI_NRO_COMPROB": "0001-00000100",
        }
        vals.update(overrides)
        return tuple(vals.get(c, "") for c in self.COLUMNS)

    def test_op_sin_oc_migrada_queda_encolada(self, tmp_path):
        retry_store = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter = self._make_exporter(tmp_path, retry_store)
        exporter._post_json = lambda url, payload: {"stats": {}}

        # La OC canonica EXISTE en RAFAM (SG_OC_*) pero aun no esta migrada en
        # el link store: la OP se saltea y queda encolada para la proxima
        # corrida (dependencia legitima, independiente de RAFAM_MIGRAR_OP_SIN_OC).
        row = self._row(SG_OC_EJERCICIO="2026", SG_OC_UNI_COMPRA="1", SG_OC_NRO="88")
        exporter.write_batch("orden_pago", self.COLUMNS, [row])

        assert _op_key(2026, 1001) in retry_store.pending_external_ids("orden_pago")
        retry_store.close()

    def test_op_gasto_directo_sin_oc_se_envia_con_flag(self, tmp_path):
        """OP con factura imputada pero sin OC en REG_COMP (gasto directo):
        con RAFAM_MIGRAR_OP_SIN_OC=true (default) se envia sin pedido_id y NO
        queda encolada."""
        retry_store = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter = self._make_exporter(tmp_path, retry_store)
        exporter._link_store.save_link("proveedores", "555", remote_id="42")
        sent = []
        exporter._post_json = lambda url, payload: sent.append(payload) or {
            "stats": {"ordenes_pago": {"ok": 1, "error": 0}}
        }

        exporter.write_batch("orden_pago", self.COLUMNS, [self._row()])

        assert len(sent) == 1
        op = sent[0]["ordenes_pago"][0]
        assert "pedido_id" not in op
        assert op["gasto_nro_comprobante"] == "0001-00000100"
        assert retry_store.pending_external_ids("orden_pago") == set()
        retry_store.close()

    def test_op_gasto_directo_sin_oc_se_omite_sin_flag(self, tmp_path, monkeypatch):
        """Con RAFAM_MIGRAR_OP_SIN_OC=false se conserva el comportamiento
        historico: omitir y encolar."""
        monkeypatch.setenv("RAFAM_MIGRAR_OP_SIN_OC", "false")
        retry_store = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter = self._make_exporter(tmp_path, retry_store)
        sent = []
        exporter._post_json = lambda url, payload: sent.append(payload) or {"stats": {}}

        exporter.write_batch("orden_pago", self.COLUMNS, [self._row()])

        assert sent == []
        assert _op_key(2026, 1001) in retry_store.pending_external_ids("orden_pago")
        retry_store.close()

    def test_op_ya_migrada_y_sin_cambios_se_saca_de_la_cola(self, tmp_path):
        retry_store = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter = self._make_exporter(tmp_path, retry_store)
        exporter._post_json = lambda url, payload: {"stats": {}}

        sk = _op_key(2026, 1001)
        retry_store.enqueue("orden_pago", sk, "dependency_missing", "pendiente")
        exporter._link_store.save_link(
            "orden_pago",
            sk,
            "9001",
            estado_op="C",
            confirmado="S",
            fech_confirm="2026-03-11",
            importe_total="500",
        )

        exporter.write_batch("orden_pago", self.COLUMNS, [self._row()])

        assert sk not in retry_store.pending_external_ids("orden_pago")
        retry_store.close()


class TestRecordBatchOutcomesWiring:
    def test_write_batch_resuelve_la_cola_con_la_respuesta(self, tmp_path):
        """`_record_batch_outcomes` habia quedado huerfano: la cola no drenaba."""
        retry_store = RetryStore(db_path=str(tmp_path / "retry.db"))
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
                "LOCAL_STATE_DB_PATH": str(tmp_path / "state.db"),
            }):
                exporter = MigratorExporter(dry_run=False)
        exporter.attach_retry_store(retry_store)

        sk = _op_key(2026, 1001)
        retry_store.enqueue("orden_pago", sk, "dependency_missing", "pendiente")

        exporter._last_parsed = {
            "results": {
                "ordenes_pago": [
                    {"success": True, "external_id": {"ejercicio": 2026, "nro_op": 1001}}
                ]
            }
        }
        exporter._record_batch_outcomes("orden_pago", exporter._last_parsed)

        assert sk not in retry_store.pending_external_ids("orden_pago")
        retry_store.close()

    def test_write_batch_encola_filas_rechazadas_por_el_receptor(self, tmp_path):
        retry_store = RetryStore(db_path=str(tmp_path / "retry.db"))
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
                "LOCAL_STATE_DB_PATH": str(tmp_path / "state.db"),
            }):
                exporter = MigratorExporter(dry_run=False)
        exporter.attach_retry_store(retry_store)

        parsed = {
            "errors": [
                {
                    "section": "ordenes_pago",
                    "external_id": {"ejercicio": 2026, "nro_op": 2002},
                    "message": "gasto no encontrado",
                }
            ]
        }
        exporter._record_batch_outcomes("orden_pago", parsed)

        assert _op_key(2026, 2002) in retry_store.pending_external_ids("orden_pago")
        retry_store.close()
