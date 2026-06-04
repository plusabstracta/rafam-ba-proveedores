import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from src.entity_link_store import EntityLinkStore
from src.reconcile import ReconcileTarget, format_report, has_drift, reconcile
from src.retry_store import REASON_DEPENDENCY_MISSING, RetryStore
from src.source_repository import SourceRepository


@pytest.fixture
def source_repo():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    metadata = MetaData()
    proveedores = Table(
        "PROVEEDORES",
        metadata,
        Column("COD_PROV", Integer, primary_key=True),
        Column("NOMBRE", String),
    )
    metadata.create_all(engine)
    conn = engine.connect()
    conn.execute(
        proveedores.insert(),
        [{"COD_PROV": i, "NOMBRE": f"prov{i}"} for i in range(1, 6)],
    )
    conn.commit()
    repo = SourceRepository(conn)
    yield repo
    conn.close()


@pytest.fixture
def link_store(tmp_path):
    s = EntityLinkStore(db_path=str(tmp_path / "links.db"))
    yield s
    s.close()


@pytest.fixture
def retry_store(tmp_path):
    s = RetryStore(db_path=str(tmp_path / "retry.db"))
    yield s
    s.close()


_TARGET = [ReconcileTarget("proveedores", "PROVEEDORES", None, "proveedores", "proveedores", False)]


class TestReconcile:
    def test_no_drift_when_all_migrated(self, source_repo, link_store, retry_store):
        for i in range(1, 6):
            link_store.save_link("proveedores", str(i), str(100 + i))
        rows = reconcile(source_repo, link_store, retry_store, targets=_TARGET)
        assert rows[0].source_count == 5
        assert rows[0].migrated_count == 5
        assert rows[0].drift == 0
        assert not has_drift(rows)

    def test_pending_retry_counts_against_drift(self, source_repo, link_store, retry_store):
        for i in range(1, 4):
            link_store.save_link("proveedores", str(i), str(100 + i))
        retry_store.enqueue("proveedores", "4", REASON_DEPENDENCY_MISSING)
        retry_store.enqueue("proveedores", "5", REASON_DEPENDENCY_MISSING)
        rows = reconcile(source_repo, link_store, retry_store, targets=_TARGET)
        # 3 migrados + 2 pendientes = 5 origen → sin drift (nada perdido).
        assert rows[0].drift == 0

    def test_detects_silent_drift(self, source_repo, link_store, retry_store):
        link_store.save_link("proveedores", "1", "101")
        rows = reconcile(source_repo, link_store, retry_store, targets=_TARGET)
        # 1 migrado, 0 en cola, 5 origen → 4 perdidas silenciosas.
        assert rows[0].drift == 4
        assert has_drift(rows)

    def test_format_report_renders(self, source_repo, link_store, retry_store):
        rows = reconcile(source_repo, link_store, retry_store, targets=_TARGET)
        report = format_report(rows)
        assert "Entidad" in report
        assert "proveedores" in report
