import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "trace_oc_flow_dev_rafam.py"
SPEC = importlib.util.spec_from_file_location("trace_oc_flow_dev_rafam", SCRIPT_PATH)
trace_oc_flow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trace_oc_flow)


def _make_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE ORDEN_COMPRA (
                EJERCICIO INTEGER,
                UNI_COMPRA INTEGER,
                NRO_OC INTEGER,
                COD_PROV INTEGER,
                NRO_ADJUD INTEGER,
                ESTADO_OC TEXT,
                CONFIRMADO TEXT,
                FECH_OC TEXT,
                FECH_CONFIRM TEXT,
                IMPORTE_TOT REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE OC_ITEMS (
                EJERCICIO INTEGER,
                UNI_COMPRA INTEGER,
                NRO_OC INTEGER,
                ITEM_OC INTEGER,
                CANTIDAD REAL,
                IMP_UNITARIO REAL,
                IMPORTE_EJER REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE REG_COMP (
                EJERCICIO INTEGER,
                NRO_REG_COMP INTEGER,
                UNI_COMPRA INTEGER,
                NRO_OC INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE CTA_COMPROB (
                EJERCICIO INTEGER,
                TIPO TEXT,
                NRO_COMPROB TEXT,
                COD_PROV INTEGER,
                NRO_REG_COMP INTEGER,
                IMPORTE_COMPR REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE ORDEN_PAGO_IMPUT (
                EJERCICIO INTEGER,
                NRO_OP INTEGER,
                NRO_REG_COMP INTEGER,
                TIPO_COMPROB TEXT,
                NRO_COMPROB TEXT,
                COD_PROV INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE ORDEN_PAGO (
                EJERCICIO INTEGER,
                NRO_OP INTEGER,
                ESTADO_OP TEXT,
                CONFIRMADO TEXT,
                FECH_CONFIRM TEXT,
                IMPORTE_TOTAL REAL
            )
        """))

        for nro_oc in range(1, 9):
            conn.execute(text("""
                INSERT INTO ORDEN_COMPRA VALUES
                (2026, 1, :nro_oc, 99, :nro_oc, 'R', 'S', '2026-01-01', '2026-01-02', 100)
            """), {"nro_oc": nro_oc})
            conn.execute(text("""
                INSERT INTO OC_ITEMS VALUES (2026, 1, :nro_oc, 1, 1, 100, 100)
            """), {"nro_oc": nro_oc})

        # OC 1: sin REG_COMP.
        for nro_oc in range(2, 9):
            conn.execute(text("""
                INSERT INTO REG_COMP VALUES (2026, :nro_reg_comp, 1, :nro_oc)
            """), {"nro_reg_comp": 1000 + nro_oc, "nro_oc": nro_oc})

        # OC 2: REG_COMP sin CTA_COMPROB.
        # OC 3: CTA_COMPROB sin OPI.
        for nro_oc in range(3, 9):
            conn.execute(text("""
                INSERT INTO CTA_COMPROB VALUES
                (2026, 'FAB', :nro_comprob, 99, :nro_reg_comp, 100)
            """), {
                "nro_comprob": f"0001-0000000{nro_oc}",
                "nro_reg_comp": 1000 + nro_oc,
            })

        # OC 4: OPI sin cabecera ORDEN_PAGO.
        for nro_oc in range(4, 9):
            conn.execute(text("""
                INSERT INTO ORDEN_PAGO_IMPUT VALUES
                (2026, :nro_op, :nro_reg_comp, 'FAB', :nro_comprob, 99)
            """), {
                "nro_op": 2000 + nro_oc,
                "nro_reg_comp": 1000 + nro_oc,
                "nro_comprob": f"0001-0000000{nro_oc}",
            })

        # OC 5: OP no confirmada.
        conn.execute(text("""
            INSERT INTO ORDEN_PAGO VALUES (2026, 2005, 'N', 'N', NULL, 100)
        """))
        # OC 6: OP confirmada pero importe invalido.
        conn.execute(text("""
            INSERT INTO ORDEN_PAGO VALUES (2026, 2006, 'C', 'S', '2026-01-10', 0)
        """))
        # OC 7: OP canonica valida.
        conn.execute(text("""
            INSERT INTO ORDEN_PAGO VALUES (2026, 2007, 'C', 'S', '2026-01-10', 100)
        """))
        # OC 8: OP estado N pero confirmada, con fecha e importe valido.
        conn.execute(text("""
            INSERT INTO ORDEN_PAGO VALUES (2026, 2008, 'N', 'S', '2026-01-10', 100)
        """))
    return engine


def test_audit_rows_classifies_oc_without_canonical_op():
    engine = _make_engine()
    with engine.connect() as conn:
        rows = trace_oc_flow._audit_rows(conn)

    motives = {row["NRO_OC"]: row["motivo_sin_op"] for row in rows}
    assert motives == {
        1: "sin_reg_comp",
        2: "sin_cta_comprob",
        3: "sin_opi",
        4: "sin_orden_pago",
        5: "op_no_confirmada",
        6: "op_importe_invalido",
        7: "con_op_canonica",
        8: "op_no_confirmada",
    }


def test_filter_rows_lists_only_oc_without_canonical_op_by_default():
    engine = _make_engine()
    with engine.connect() as conn:
        rows = trace_oc_flow._audit_rows(conn)

    filtered = trace_oc_flow._filter_rows(
        rows,
        include_with_op=False,
        motives=None,
        priority=None,
        limit=None,
    )

    assert [row["NRO_OC"] for row in filtered] == [1, 2, 3, 4, 5, 6, 8]