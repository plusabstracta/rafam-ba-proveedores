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
        store.enqueue("gastos", "x", REASON_BACKEND_REJECTED)
        store.enqueue("gastos", "x", REASON_BACKEND_REJECTED)
        items = store.list_items("gastos")
        assert items[0].attempts == 2

    def test_dependency_missing_no_incrementa_attempts(self, store):
        """Esperar una dependencia no es un fallo: re-encolar por
        dependency_missing no debe acercar la fila a 'permanent' (con el cron
        cada 10 min, una OP quedaba permanent en <2h aunque su OC pudiera
        confirmarse dias despues)."""
        for _ in range(20):
            store.enqueue("orden_pago", "op-espera", REASON_DEPENDENCY_MISSING)
        items = store.list_items("orden_pago")
        assert items[0].attempts == 1
        assert items[0].status == STATUS_PENDING
        assert store.pending_external_ids("orden_pago") == {"op-espera"}

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
            store.enqueue("gastos", "b", REASON_BACKEND_REJECTED)
        pending = store.pending_external_ids("gastos")
        assert pending == {"a"}

    def test_counts_by_entity(self, store):
        store.enqueue("gastos", "a", REASON_DEPENDENCY_MISSING)
        store.enqueue("retenciones", "r", REASON_VALIDATION_CLIENT)
        counts = store.counts_by_entity()
        assert counts["gastos"][STATUS_PENDING] == 1
        assert counts["retenciones"][STATUS_PENDING] == 1

    def test_requeue_devuelve_permanent_a_pending(self, store):
        """core#406: cuando el receptor arregla el motivo del rechazo, las filas
        que ya agotaron los intentos tienen que poder volver a la cola; si no,
        quedan 'permanent' y no se reinyectan nunca mas."""
        for _ in range(3):
            store.enqueue("ordenes_compra", "oc-98", REASON_BACKEND_REJECTED, "cantidad <= 0")
        assert store.list_items("ordenes_compra")[0].status == STATUS_PERMANENT
        assert store.pending_external_ids("ordenes_compra") == set()

        assert store.requeue(entity="ordenes_compra") == 1

        item = store.list_items("ordenes_compra")[0]
        assert item.status == STATUS_PENDING
        assert item.attempts == 0
        assert store.pending_external_ids("ordenes_compra") == {"oc-98"}

    def test_requeue_respeta_filtros_y_no_toca_pending(self, store):
        for _ in range(3):
            store.enqueue("ordenes_compra", "oc-98", REASON_BACKEND_REJECTED)
        for _ in range(3):
            store.enqueue("gastos", "g-1", REASON_BACKEND_REJECTED)
        store.enqueue("gastos", "g-2", REASON_BACKEND_REJECTED)

        assert store.requeue(entity="gastos", external_id="g-1") == 1
        assert store.list_items("ordenes_compra")[0].status == STATUS_PERMANENT

        gastos = {i.external_id: i for i in store.list_items("gastos")}
        assert gastos["g-1"].status == STATUS_PENDING and gastos["g-1"].attempts == 0
        assert gastos["g-2"].attempts == 1  # la pending no se toca

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
