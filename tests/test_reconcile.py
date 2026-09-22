import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from src.entity_link_store import EntityLinkStore
from src.reconcile import RECONCILE_TARGETS, ReconcileTarget, format_report, has_drift, reconcile
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


class TestReconcileTargetsIncluyeGastosYRetenciones:
    """Antes del fix `main.py reconcile` no podia detectar drift silencioso en
    solic_gastos ni retenciones -- quedaban fuera de RECONCILE_TARGETS."""

    def test_gastos_y_retenciones_estan_registrados(self):
        by_label = {t.label: t for t in RECONCILE_TARGETS}
        assert "gastos" in by_label
        assert "retenciones" in by_label

    def test_gastos_apunta_a_solic_gastos(self):
        target = next(t for t in RECONCILE_TARGETS if t.label == "gastos")
        assert target.source_table == "SOLIC_GASTOS"
        assert target.link_entity == "gasto"
        assert target.retry_entity == "solic_gastos"
        assert target.distinct_fields == ["EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC"]

    def test_retenciones_cuenta_op_con_deducciones_no_todas_las_op(self):
        """El universo de origen NO puede ser ORDEN_PAGO completa (la mayoria
        de las OP no tiene deducciones y jamas genera link/retry) -- tiene que
        ser distinct(EJERCICIO, NRO_OP) de ORDEN_PAGO_DEDUC, si no cualquier OP
        sin retenciones aparece como drift permanente (falso positivo)."""
        target = next(t for t in RECONCILE_TARGETS if t.label == "retenciones")
        assert target.source_table == "ORDEN_PAGO_DEDUC"
        assert target.link_entity == "retenciones"
        assert target.retry_entity == "retenciones"
        assert target.distinct_fields == ["EJERCICIO", "NRO_OP"]

    def test_retenciones_no_marca_drift_por_op_sin_deducciones(self, link_store, retry_store):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        metadata = MetaData()
        op_deduc = Table(
            "ORDEN_PAGO_DEDUC",
            metadata,
            Column("EJERCICIO", Integer),
            Column("NRO_OP", Integer),
            Column("CODIGO_DEDUC", String),
        )
        metadata.create_all(engine)
        conn = engine.connect()
        # Una sola OP con deduccion (aunque en RAFAM existan muchas OP sin
        # deducciones, esas NUNCA deberian contar como universo de origen aca).
        conn.execute(op_deduc.insert(), [{"EJERCICIO": 2026, "NRO_OP": 1, "CODIGO_DEDUC": "3"}])
        conn.commit()
        repo = SourceRepository(conn)

        link_store.save_link("retenciones", '{"ejercicio": 2026, "nro_op": 1}', "9001")
        target = next(t for t in RECONCILE_TARGETS if t.label == "retenciones")

        rows = reconcile(repo, link_store, retry_store, targets=[target])
        assert rows[0].source_count == 1
        assert rows[0].migrated_count == 1
        assert rows[0].drift == 0
        conn.close()
