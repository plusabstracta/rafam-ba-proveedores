from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine

from src.checkpoint_store import CheckpointStore
from src.models import Checkpoint, EntityConfig
from src.source_repository import SourceRepository
from src.sync_engine import SyncEngine


@pytest.fixture
def store(tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test_checkpoint.db'}"
    return CheckpointStore(db_url=db_url)


@pytest.fixture
def configs() -> dict[str, EntityConfig]:
    return {
        "proveedores": EntityConfig(
            name="proveedores",
            table_name="PROVEEDORES",
            ts_field="FECHA_MODIFICACION",
        ),
        "pedidos": EntityConfig(
            name="pedidos",
            table_name="PEDIDOS",
            id_field="NRO_PEDIDO",
            ts_field="FECHA_PEDIDO",
        ),
    }


@pytest.fixture
def engine(store: CheckpointStore, configs) -> SyncEngine:
    return SyncEngine(store, configs)


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

    def test_reset_removes_checkpoint(self, store):
        store.save(Checkpoint(entity="proveedores", last_id=99))
        store.reset("proveedores")

        assert store.get("proveedores").is_fresh


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

    def test_mark_error_preserves_cursor(self, engine):
        ts = datetime(2026, 3, 9, 18, 0, 0)
        engine.mark_success("proveedores", last_id=100, last_ts=ts, count=5)
        engine.mark_error("proveedores", "ORA-00942: table or view does not exist")

        cp = engine.get_checkpoint("proveedores")
        assert cp.last_id == 100
        assert cp.last_ts == ts
        assert "error" in cp.status.lower()


class TestExtractCursorValues:

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


class TestSourceRepository:

    def test_incremental_filter_uses_checkpoint_ts(self):
        # PROVEEDORES uses ts_field="FECHA_ULT_COMP" (see config.py)
        db = create_engine("sqlite+pysqlite:///:memory:", future=True)
        metadata = MetaData()
        proveedores = Table(
            "PROVEEDORES",
            metadata,
            Column("COD_PROV", Integer),
            Column("FECHA_ULT_COMP", DateTime),
            Column("RAZON_SOCIAL", String),
        )
        metadata.create_all(db)

        now = datetime.now(timezone.utc)
        older = now.replace(year=2025)

        with db.begin() as conn:
            conn.execute(
                proveedores.insert(),
                [
                    {"COD_PROV": 1, "FECHA_ULT_COMP": older, "RAZON_SOCIAL": "Viejo"},
                    {"COD_PROV": 2, "FECHA_ULT_COMP": now, "RAZON_SOCIAL": "Nuevo"},
                ],
            )

        cp = Checkpoint(entity="proveedores", last_ts=older, last_run=older)

        with db.connect() as conn:
            repo = SourceRepository(conn, schema="OWNER_RAFAM")
            stmt = repo.build_statement("proveedores", cp)
            rows = repo.execute(stmt).all()

        assert len(rows) == 1
        assert rows[0].COD_PROV == 2

    def test_incremental_filter_full_load_ignores_checkpoint(self):
        """Entidades full_load devuelven todos los registros sin importar el checkpoint."""
        db = create_engine("sqlite+pysqlite:///:memory:", future=True)
        metadata = MetaData()
        # solic_gastos NO es full_load pero tiene ts_field; ped_items sí es full_load
        # Usamos solic_gastos con full_load=True para aislar el comportamiento
        from src.models import EntityConfig as EC
        from unittest.mock import patch

        solic_gastos_tbl = Table(
            "SOLIC_GASTOS",
            metadata,
            Column("EJERCICIO", Integer),
            Column("DELEG_SOLIC", Integer),
            Column("NRO_SOLIC", Integer),
            Column("FECH_SOLIC", DateTime),
        )
        orden_pago_tbl = Table(
            "ORDEN_PAGO",
            metadata,
            Column("EJERCICIO", Integer),
            Column("NRO_OP", Integer),
            Column("NRO_CANCE", Integer),
            Column("COD_PROV", Integer),
        )
        metadata.create_all(db)

        now = datetime.now(timezone.utc)
        with db.begin() as conn:
            conn.execute(solic_gastos_tbl.insert(), [
                {"EJERCICIO": 2024, "DELEG_SOLIC": 1, "NRO_SOLIC": 1, "FECH_SOLIC": now.replace(year=2024)},
                {"EJERCICIO": 2025, "DELEG_SOLIC": 1, "NRO_SOLIC": 2, "FECH_SOLIC": now.replace(year=2025)},
            ])

        # Parchamos ENTITY_CONFIGS para inyectar full_load=True en solic_gastos
        full_load_cfg = EC(name="solic_gastos", table_name="SOLIC_GASTOS", full_load=True)
        cp = Checkpoint(entity="solic_gastos", last_ts=now.replace(year=2024), last_run=now)

        with patch("src.source_repository.ENTITY_CONFIGS", {"solic_gastos": full_load_cfg}):
            with db.connect() as conn:
                repo = SourceRepository(conn, schema="OWNER_RAFAM")
                stmt = repo.build_statement("solic_gastos", cp)
                rows = repo.execute(stmt).all()

        assert len(rows) == 2  # full_load: ignora el checkpoint y devuelve todo
