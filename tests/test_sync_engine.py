"""
Unit tests for SyncEngine and CheckpointStore.
Oracle is fully mocked — no real DB connection required.

Run:
    pytest tests/
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.checkpoint_store import CheckpointStore
from src.models import Checkpoint, EntityConfig
from src.sync_engine import SyncEngine


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(db_path=tmp_path / "test_checkpoint.db")


@pytest.fixture
def configs() -> dict[str, EntityConfig]:
    return {
        "proveedores": EntityConfig(
            name="proveedores",
            base_query="SELECT * FROM OWNER_RAFAM.PROVEEDORES",
            ts_field="FECHA_MODIFICACION",
        ),
        "pedidos": EntityConfig(
            name="pedidos",
            base_query="SELECT * FROM OWNER_RAFAM.PEDIDOS",
            id_field="NRO_PEDIDO",
            ts_field="FECHA_PEDIDO",
        ),
        "orden_pago": EntityConfig(
            name="orden_pago",
            base_query="SELECT * FROM OWNER_RAFAM.ORDEN_PAGO",
            ts_field="FECHA_OP",
            extra_condition="ESTADO_OP = 'N' AND FECHA_OP > SYSDATE - 30",
        ),
        "jurisdicciones": EntityConfig(
            name="jurisdicciones",
            base_query="SELECT * FROM OWNER_RAFAM.JURISDICCIONES",
            full_load=True,
        ),
    }


@pytest.fixture
def engine(store: CheckpointStore, configs) -> SyncEngine:
    return SyncEngine(store, configs)


# ─── CheckpointStore ─────────────────────────────────────────────────────────

class TestCheckpointStore:

    def test_get_returns_fresh_checkpoint_for_unknown_entity(self, store):
        cp = store.get("proveedores")
        assert cp.entity == "proveedores"
        assert cp.is_fresh
        assert cp.last_id is None
        assert cp.last_ts is None
        assert cp.status == "ok"

    def test_save_and_get_roundtrip(self, store):
        ts = datetime(2026, 3, 9, 18, 0, 0)
        store.save(Checkpoint(entity="proveedores", last_id=42, last_ts=ts, records_sent=10))

        loaded = store.get("proveedores")
        assert loaded.last_id == 42
        assert loaded.last_ts == ts
        assert loaded.records_sent == 10
        assert loaded.status == "ok"

    def test_save_upserts_existing(self, store):
        store.save(Checkpoint(entity="proveedores", last_id=10))
        store.save(Checkpoint(entity="proveedores", last_id=20))

        assert store.get("proveedores").last_id == 20

    def test_reset_removes_checkpoint(self, store):
        store.save(Checkpoint(entity="proveedores", last_id=99))
        store.reset("proveedores")

        assert store.get("proveedores").is_fresh

    def test_all_checkpoints_returns_all_saved(self, store):
        store.save(Checkpoint(entity="a", last_id=1))
        store.save(Checkpoint(entity="b", last_id=2))

        all_cp = store.all_checkpoints()
        assert len(all_cp) == 2
        assert {cp.entity for cp in all_cp} == {"a", "b"}

    def test_reset_nonexistent_entity_is_noop(self, store):
        store.reset("nonexistent")  # must not raise


# ─── SyncEngine.build_incremental_query ──────────────────────────────────────

class TestBuildIncrementalQuery:

    def test_fresh_entity_returns_base_query_unchanged(self, engine):
        sql, params = engine.build_incremental_query(
            "proveedores", "SELECT * FROM OWNER_RAFAM.PROVEEDORES"
        )
        assert sql == "SELECT * FROM OWNER_RAFAM.PROVEEDORES"
        assert params == []

    def test_full_load_entity_always_returns_base_query(self, engine):
        # Even with a saved checkpoint, full_load entities skip the WHERE clause
        engine._store.save(
            Checkpoint(entity="jurisdicciones", last_id=100, last_run=datetime.now(timezone.utc))
        )
        sql, params = engine.build_incremental_query(
            "jurisdicciones", "SELECT * FROM OWNER_RAFAM.JURISDICCIONES"
        )
        assert "WHERE" not in sql.upper()
        assert params == []

    def test_incremental_ts_only_cursor(self, engine):
        ts = datetime(2026, 3, 9, 18, 0, 0)
        engine._store.save(
            Checkpoint(entity="proveedores", last_ts=ts, last_run=ts)
        )
        sql, params = engine.build_incremental_query(
            "proveedores", "SELECT * FROM OWNER_RAFAM.PROVEEDORES"
        )

        assert "WHERE" in sql.upper()
        assert "FECHA_MODIFICACION" in sql
        assert len(params) == 1
        assert params[0] == ts

    def test_incremental_id_and_ts_cursor(self, engine):
        ts = datetime(2026, 3, 9, 18, 0, 0)
        engine._store.save(
            Checkpoint(entity="pedidos", last_id=500, last_ts=ts, last_run=ts)
        )
        sql, params = engine.build_incremental_query(
            "pedidos", "SELECT * FROM OWNER_RAFAM.PEDIDOS"
        )

        assert "NRO_PEDIDO" in sql
        assert "FECHA_PEDIDO" in sql
        assert len(params) == 2
        assert params[0] == 500
        assert params[1] == ts

    def test_extra_condition_is_included(self, engine):
        ts = datetime(2026, 3, 9, 18, 0, 0)
        engine._store.save(
            Checkpoint(entity="orden_pago", last_ts=ts, last_run=ts)
        )
        sql, params = engine.build_incremental_query(
            "orden_pago", "SELECT * FROM OWNER_RAFAM.ORDEN_PAGO"
        )

        assert "ESTADO_OP" in sql
        assert "SYSDATE" in sql

    def test_unknown_entity_returns_base_query(self, engine):
        sql, params = engine.build_incremental_query(
            "tabla_inexistente", "SELECT * FROM OWNER_RAFAM.ALGO"
        )
        assert sql == "SELECT * FROM OWNER_RAFAM.ALGO"
        assert params == []


# ─── SyncEngine.mark_success / mark_error ────────────────────────────────────

class TestMarkSuccessAndError:

    def test_mark_success_saves_checkpoint(self, engine):
        ts = datetime(2026, 3, 9, 18, 0, 0)
        engine.mark_success("proveedores", last_id=500, last_ts=ts, count=42)

        cp = engine.get_checkpoint("proveedores")
        assert cp.last_id == 500
        assert cp.last_ts == ts
        assert cp.records_sent == 42
        assert cp.status == "ok"
        assert cp.last_run is not None

    def test_mark_success_does_not_regress_cursor_when_no_new_values(self, engine):
        ts = datetime(2026, 3, 9, 18, 0, 0)
        engine.mark_success("proveedores", last_id=100, last_ts=ts, count=5)
        # Second run returns 0 rows — last_id/last_ts are None
        engine.mark_success("proveedores", last_id=None, last_ts=None, count=0)

        cp = engine.get_checkpoint("proveedores")
        assert cp.last_id == 100   # preserved from previous run
        assert cp.last_ts == ts    # preserved from previous run

    def test_mark_error_preserves_cursor(self, engine):
        ts = datetime(2026, 3, 9, 18, 0, 0)
        engine.mark_success("proveedores", last_id=100, last_ts=ts, count=5)
        engine.mark_error("proveedores", "ORA-00942: table or view does not exist")

        cp = engine.get_checkpoint("proveedores")
        assert cp.last_id == 100   # cursor NOT advanced
        assert cp.last_ts == ts    # cursor NOT advanced
        assert "error" in cp.status.lower()

    def test_mark_error_on_fresh_entity_keeps_fresh_cursor(self, engine):
        engine.mark_error("proveedores", "connection refused")

        cp = engine.get_checkpoint("proveedores")
        assert cp.last_id is None
        assert cp.last_ts is None
        assert "error" in cp.status.lower()

    def test_reset_checkpoint_makes_entity_fresh(self, engine):
        ts = datetime(2026, 3, 9, 18, 0, 0)
        engine.mark_success("proveedores", last_id=200, last_ts=ts, count=50)
        engine.reset_checkpoint("proveedores")

        assert engine.get_checkpoint("proveedores").is_fresh


# ─── SyncEngine.extract_cursor_values ────────────────────────────────────────

class TestExtractCursorValues:

    def test_returns_none_none_for_empty_rows(self, engine):
        last_id, last_ts = engine.extract_cursor_values([], [], "proveedores")
        assert last_id is None
        assert last_ts is None

    def test_extracts_max_ts(self, engine):
        ts_old = datetime(2026, 1, 1)
        ts_new = datetime(2026, 3, 9, 18, 0, 0)
        columns = ["COD_PROV", "FECHA_MODIFICACION"]
        rows = [(1, ts_old), (2, ts_new), (3, None)]

        _, last_ts = engine.extract_cursor_values(columns, rows, "proveedores")
        assert last_ts == ts_new

    def test_extracts_max_id(self, engine):
        columns = ["NRO_PEDIDO", "FECHA_PEDIDO"]
        rows = [(100, None), (200, None), (150, None)]

        last_id, _ = engine.extract_cursor_values(columns, rows, "pedidos")
        assert last_id == 200

    def test_unknown_entity_returns_none_none(self, engine):
        columns = ["COL_A", "COL_B"]
        rows = [(1, datetime(2026, 1, 1))]
        last_id, last_ts = engine.extract_cursor_values(columns, rows, "nonexistent")
        assert last_id is None
        assert last_ts is None

    def test_column_name_matching_is_case_insensitive(self, engine):
        # Oracle returns column names in uppercase; verify the engine handles both
        ts = datetime(2026, 3, 9)
        columns = ["cod_prov", "fecha_modificacion"]  # lowercase
        rows = [(1, ts)]

        _, last_ts = engine.extract_cursor_values(columns, rows, "proveedores")
        assert last_ts == ts
