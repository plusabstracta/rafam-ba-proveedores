import sqlite3

import pytest

from src.retry_store import (
    REASON_BACKEND_REJECTED,
    REASON_DEPENDENCY_MISSING,
    REASON_VALIDATION_CLIENT,
    STATUS_PENDING,
    STATUS_PERMANENT,
    RetryStore,
)


@pytest.fixture
def store(tmp_path):
    s = RetryStore(db_path=str(tmp_path / "state.db"), max_attempts=3)
    yield s
    s.close()


class TestRetryStore:
    def test_enqueue_new_item_is_pending(self, store):
        store.enqueue("gastos", "2026-1001", REASON_VALIDATION_CLIENT, "importe negativo")
        items = store.list_items("gastos")
        assert len(items) == 1
        assert items[0].external_id == "2026-1001"
        assert items[0].status == STATUS_PENDING
        assert items[0].attempts == 1

    def test_enqueue_existing_increments_attempts(self, store):
        store.enqueue("gastos", "x", REASON_DEPENDENCY_MISSING)
        store.enqueue("gastos", "x", REASON_DEPENDENCY_MISSING)
        items = store.list_items("gastos")
        assert items[0].attempts == 2

    def test_promotes_to_permanent_after_max_attempts(self, store):
        for _ in range(3):
            store.enqueue("orden_pago", "op-1", REASON_BACKEND_REJECTED, "rechazo server")
        items = store.list_items("orden_pago")
        assert items[0].status == STATUS_PERMANENT
        # Permanent rows are no longer reinjected as pending.
        assert store.pending_external_ids("orden_pago") == set()

    def test_resolve_removes_item(self, store):
        store.enqueue("gastos", "y", REASON_VALIDATION_CLIENT)
        store.resolve("gastos", "y")
        assert store.list_items("gastos") == []

    def test_pending_external_ids_only_returns_pending(self, store):
        store.enqueue("gastos", "a", REASON_DEPENDENCY_MISSING)
        for _ in range(3):
            store.enqueue("gastos", "b", REASON_DEPENDENCY_MISSING)
        pending = store.pending_external_ids("gastos")
        assert pending == {"a"}

    def test_counts_by_entity(self, store):
        store.enqueue("gastos", "a", REASON_DEPENDENCY_MISSING)
        store.enqueue("retenciones", "r", REASON_VALIDATION_CLIENT)
        counts = store.counts_by_entity()
        assert counts["gastos"][STATUS_PENDING] == 1
        assert counts["retenciones"][STATUS_PENDING] == 1

    def test_shared_connection_participates_in_transaction(self, tmp_path):
        # Conexion inyectada: el commit lo controla el owner del batch (F2).
        conn = sqlite3.connect(str(tmp_path / "shared.db"))
        conn.row_factory = sqlite3.Row
        store = RetryStore(conn=conn)
        store.enqueue("gastos", "z", REASON_VALIDATION_CLIENT)
        # Sin commit del owner, otra conexion no deberia ver la fila.
        other = sqlite3.connect(str(tmp_path / "shared.db"))
        other.row_factory = sqlite3.Row
        rows = other.execute("SELECT COUNT(*) AS n FROM retry_queue").fetchone()
        assert rows["n"] == 0
        conn.commit()
        rows = other.execute("SELECT COUNT(*) AS n FROM retry_queue").fetchone()
        assert rows["n"] == 1
        conn.close()
        other.close()
