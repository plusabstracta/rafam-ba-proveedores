"""
Tests para:
1. Filtro EJERCICIO >= RAFAM_EJERCICIO_MIN sólo para OCs
2. Flujo OC → OP: 4 OCs enviadas → siguiente corrida detecta y envía OPs vinculadas

Usa SQLite in-memory para simular tablas RAFAM.
"""
import json
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, create_engine, text

from src.models import Checkpoint, EntityConfig
from src.source_repository import SourceRepository


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def engine_with_data():
    """SQLite in-memory con tablas ORDEN_COMPRA, OC_ITEMS, SOLIC_GASTOS,
    ORDEN_PAGO, ORDEN_PAGO_IMPUT, REG_COMP, CTA_COMPROB y PROVEEDORES con
    datos de ej 2025 y 2026."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE PROVEEDORES (
                COD_PROV INTEGER PRIMARY KEY,
                RAZON_SOCIAL TEXT,
                CUIT TEXT,
                FECHA_ULT_COMP DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE ORDEN_COMPRA (
                EJERCICIO INTEGER,
                UNI_COMPRA INTEGER,
                NRO_OC INTEGER,
                COD_PROV INTEGER,
                FECH_OC DATETIME,
                FECH_CONFIRM DATETIME,
                OBSERVACIONES TEXT,
                ESTADO_OC TEXT,
                IMPORTE_TOT REAL,
                FECH_ANUL DATETIME,
                PRIMARY KEY (EJERCICIO, UNI_COMPRA, NRO_OC)
            )
        """))
        conn.execute(text("""
            CREATE TABLE OC_ITEMS (
                EJERCICIO INTEGER,
                UNI_COMPRA INTEGER,
                NRO_OC INTEGER,
                ITEM_OC INTEGER,
                DESCRIPCION TEXT,
                CANTIDAD REAL,
                PRECIO_UNI REAL,
                DELEG_SOLIC INTEGER,
                NRO_SOLIC INTEGER,
                PRIMARY KEY (EJERCICIO, UNI_COMPRA, NRO_OC, ITEM_OC)
            )
        """))
        conn.execute(text("""
            CREATE TABLE SOLIC_GASTOS (
                EJERCICIO INTEGER,
                DELEG_SOLIC INTEGER,
                NRO_SOLIC INTEGER,
                JURISDICCION INTEGER,
                FECH_SOLIC DATETIME,
                ESTADO_SOLIC TEXT,
                IMPORTE_TOT REAL,
                OBSERVACIONES TEXT,
                PRIMARY KEY (EJERCICIO, DELEG_SOLIC, NRO_SOLIC)
            )
        """))
        conn.execute(text("""
            CREATE TABLE ORDEN_PAGO (
                EJERCICIO INTEGER,
                NRO_OP INTEGER,
                COD_PROV INTEGER,
                ESTADO_OP TEXT,
                CONFIRMADO TEXT,
                FECH_CONFIRM DATETIME,
                IMPORTE_TOTAL REAL,
                NRO_CANCE INTEGER,
                CONCEPTO TEXT,
                PRIMARY KEY (EJERCICIO, NRO_OP)
            )
        """))
        conn.execute(text("""
            CREATE TABLE REG_COMP (
                EJERCICIO INTEGER,
                NRO_REG_COMP INTEGER,
                DELEG_SOLIC INTEGER,
                NRO_SOLIC INTEGER,
                UNI_COMPRA INTEGER,
                NRO_OC INTEGER,
                COD_PROV INTEGER,
                PRIMARY KEY (EJERCICIO, NRO_REG_COMP)
            )
        """))
        conn.execute(text("""
            CREATE TABLE CTA_COMPROB (
                EJERCICIO INTEGER,
                TIPO TEXT,
                NRO_COMPROB TEXT,
                COD_PROV INTEGER,
                NRO_REG_COMP INTEGER,
                IMPORTE_COMPR REAL,
                IMPORTE_SIN_IVA REAL,
                FECH_COMPROB DATETIME,
                FECH_VENCIM DATETIME,
                PRIMARY KEY (EJERCICIO, TIPO, NRO_COMPROB, COD_PROV)
            )
        """))
        conn.execute(text("""
            CREATE TABLE ORDEN_PAGO_IMPUT (
                EJERCICIO INTEGER,
                NRO_OP INTEGER,
                NRO_REG_COMP INTEGER,
                TIPO_COMPROB TEXT,
                NRO_COMPROB TEXT,
                COD_PROV INTEGER,
                PRIMARY KEY (EJERCICIO, NRO_OP, NRO_REG_COMP, TIPO_COMPROB, NRO_COMPROB, COD_PROV)
            )
        """))

        # ── Proveedores ──
        conn.execute(text("INSERT INTO PROVEEDORES VALUES (100, 'Prov A', '20111111111', '2026-01-01')"))
        conn.execute(text("INSERT INTO PROVEEDORES VALUES (200, 'Prov B', '20222222222', '2026-01-01')"))

        # ── OCs ejercicio 2025 (deben ser filtradas) ──
        conn.execute(text("""
            INSERT INTO ORDEN_COMPRA VALUES
            (2025, 1, 1, 100, '2025-06-01', '2025-06-05', 'OC vieja', 'R', 50000, NULL)
        """))
        conn.execute(text("""
            INSERT INTO OC_ITEMS VALUES
            (2025, 1, 1, 1, 'Item viejo', 10, 5000, 1, 100)
        """))

        # ── 4 OCs ejercicio 2026 (deben ser procesadas) ──
        for nro_oc in range(1, 5):
            conn.execute(text(f"""
                INSERT INTO ORDEN_COMPRA VALUES
                (2026, 1, {nro_oc}, 100, '2026-03-0{nro_oc}', '2026-03-0{nro_oc}', 'OC nueva {nro_oc}', 'R', {10000 * nro_oc}, NULL)
            """))
            conn.execute(text(f"""
                INSERT INTO OC_ITEMS VALUES
                (2026, 1, {nro_oc}, 1, 'Item {nro_oc}', {nro_oc}, {1000 * nro_oc}, 1, {200 + nro_oc})
            """))
            conn.execute(text(f"""
                INSERT INTO SOLIC_GASTOS VALUES
                (2026, 1, {200 + nro_oc}, 10, '2026-03-0{nro_oc}', 'C', {10000 * nro_oc}, 'Gasto {nro_oc}')
            """))
            # REG_COMP + CTA_COMPROB: bridge OC ↔ SG ↔ CC
            conn.execute(text(f"""
                INSERT INTO REG_COMP VALUES
                (2026, {300 + nro_oc}, 1, {200 + nro_oc}, 1, {nro_oc}, 100)
            """))
            conn.execute(text(f"""
                INSERT INTO CTA_COMPROB VALUES
                (2026, 'FA', 'CC-2026-{nro_oc}', 100, {300 + nro_oc},
                 {10000 * nro_oc}, {10000 * nro_oc}, '2026-04-0{nro_oc}', '2026-05-0{nro_oc}')
            """))

        # ── 4 OPs ejercicio 2026 (vinculadas a las 4 OCs) ──
        for nro_oc in range(1, 5):
            estado_op = "N" if nro_oc == 4 else "C"
            conn.execute(text(f"""
                INSERT INTO ORDEN_PAGO VALUES
                (2026, {500 + nro_oc}, 100, '{estado_op}', 'S', '2026-04-0{nro_oc}', {10000 * nro_oc}, {200 + nro_oc}, 'Pago OC {nro_oc}')
            """))
            # ORDEN_PAGO_IMPUT: bridge real OP ↔ CC
            conn.execute(text(f"""
                INSERT INTO ORDEN_PAGO_IMPUT VALUES
                (2026, {500 + nro_oc}, {300 + nro_oc}, 'FA', 'CC-2026-{nro_oc}', 100)
            """))

        # ── OP ejercicio 2025 (debe ser filtrada) ──
        conn.execute(text("""
            INSERT INTO ORDEN_PAGO VALUES
            (2025, 999, 100, 'C', 'S', '2025-07-01', 50000, 100, 'Pago viejo')
        """))

        conn.commit()
    return engine


# ─── Tests: Filtro EJERCICIO >= 2026 ─────────────────────────────────────────

class TestEjercicioMinFilter:

    def test_oc_items_excluye_2025(self, engine_with_data):
        cfg = EntityConfig(
            name="oc_items",
            table_name="OC_ITEMS",
            full_load=True,
            ejercicio_min=2026,
        )
        cp = Checkpoint(entity="oc_items")

        with engine_with_data.connect() as conn:
            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"oc_items": cfg}):
                stmt = repo.build_statement("oc_items", cp)
                rows = conn.execute(stmt).fetchall()

        ejercicios = {r[0] for r in rows}  # EJERCICIO es la primera columna de OC_ITEMS
        assert 2025 not in ejercicios, "OCs de 2025 no deben aparecer con ejercicio_min=2026"
        assert 2026 in ejercicios, "OCs de 2026 deben aparecer"

    def test_oc_items_sin_filtro_incluye_2025(self, engine_with_data):
        cfg = EntityConfig(
            name="oc_items",
            table_name="OC_ITEMS",
            full_load=True,
        )
        cp = Checkpoint(entity="oc_items")

        with engine_with_data.connect() as conn:
            repo = SourceRepository(conn)
            # Monkey-patch config to remove ejercicio_min
            with patch.dict("src.config.ENTITY_CONFIGS", {"oc_items": cfg}):
                stmt = repo.build_statement("oc_items", cp)
                rows = conn.execute(stmt).fetchall()

        ejercicios = {r[0] for r in rows}
        assert 2025 in ejercicios, "Sin filtro, OCs de 2025 deben aparecer"
        assert 2026 in ejercicios

    def test_orden_pago_no_aplica_ejercicio_min(self, engine_with_data):
        cfg = EntityConfig(
            name="orden_pago",
            table_name="ORDEN_PAGO",
            ts_field="FECH_CONFIRM",
            pending_state_field="ESTADO_OP",
            pending_state_value="N",
            pending_reprocess_days=30,
        )
        cp = Checkpoint(entity="orden_pago")

        with engine_with_data.connect() as conn:
            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"orden_pago": cfg}):
                stmt = repo.build_statement("orden_pago", cp)
                rows = conn.execute(stmt).fetchall()

        ej_idx = 0  # EJERCICIO is first column in ORDEN_PAGO
        ejercicios = set()
        for r in rows:
            ejercicios.add(r[ej_idx])

        assert 2025 in ejercicios, "RAFAM_EJERCICIO_MIN no debe filtrar OPs"
        assert 2026 in ejercicios, "OPs de 2026 deben aparecer"

    def test_orden_pago_expone_importes_crudos_cta(self, engine_with_data):
        cfg = EntityConfig(
            name="orden_pago",
            table_name="ORDEN_PAGO",
            ts_field="FECH_CONFIRM",
            pending_state_field="ESTADO_OP",
            pending_state_value="N",
            pending_reprocess_days=30,
        )
        cp = Checkpoint(entity="orden_pago")

        with engine_with_data.connect() as conn:
            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"orden_pago": cfg}):
                stmt = repo.build_statement("orden_pago", cp)
                rows = conn.execute(stmt).mappings().all()

        row = next(r for r in rows if r["EJERCICIO"] == 2026 and r["NRO_OP"] == 501)
        assert row["CTA_IMPORTE_COMPR"] == 10000
        assert row["CTA_IMPORTE_NETO"] == 10000
        assert row["CTA_IMPORTE_SIN_IVA"] == 10000

    def test_solic_gastos_prefiere_importe_liquido_cta(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE SOLIC_GASTOS (
                    EJERCICIO INTEGER,
                    DELEG_SOLIC INTEGER,
                    NRO_SOLIC INTEGER,
                    FECH_SOLIC DATETIME,
                    ESTADO_SOLIC TEXT,
                    IMPORTE_TOT REAL,
                    PRIMARY KEY (EJERCICIO, DELEG_SOLIC, NRO_SOLIC)
                )
            """))
            conn.execute(text("""
                CREATE TABLE OC_ITEMS (
                    EJERCICIO INTEGER,
                    UNI_COMPRA INTEGER,
                    NRO_OC INTEGER,
                    ITEM_OC INTEGER,
                    DELEG_SOLIC INTEGER,
                    NRO_SOLIC INTEGER
                )
            """))
            conn.execute(text("""
                CREATE TABLE ORDEN_COMPRA (
                    EJERCICIO INTEGER,
                    UNI_COMPRA INTEGER,
                    NRO_OC INTEGER,
                    COD_PROV INTEGER
                )
            """))
            conn.execute(text("""
                CREATE TABLE REG_COMP (
                    EJERCICIO INTEGER,
                    NRO_REG_COMP INTEGER,
                    DELEG_SOLIC INTEGER,
                    NRO_SOLIC INTEGER
                )
            """))
            conn.execute(text("""
                CREATE TABLE CTA_COMPROB (
                    EJERCICIO INTEGER,
                    NRO_REG_COMP INTEGER,
                    TIPO TEXT,
                    NRO_COMPROB TEXT,
                    FECH_COMPROB DATETIME,
                    FECH_VENCIM DATETIME,
                    IMPORTE_COMPR REAL,
                    IMPORTE_LIQUIDO REAL,
                    IMPORTE_NETO REAL,
                    IMPORTE_SIN_IVA REAL
                )
            """))
            conn.execute(text("""
                INSERT INTO SOLIC_GASTOS VALUES
                (2026, 1, 10, '2026-04-01', 'C', 1210)
            """))
            conn.execute(text("""
                INSERT INTO OC_ITEMS VALUES
                (2026, 1, 5, 1, 1, 10)
            """))
            conn.execute(text("""
                INSERT INTO ORDEN_COMPRA VALUES
                (2026, 1, 5, 100)
            """))
            conn.execute(text("""
                INSERT INTO REG_COMP VALUES
                (2026, 77, 1, 10)
            """))
            conn.execute(text("""
                INSERT INTO CTA_COMPROB VALUES
                (2026, 77, 'FA', '0001-00000077', '2026-04-02', '2026-05-02',
                 1210, 700, 800, 900)
            """))
            conn.commit()

            cfg = EntityConfig(
                name="solic_gastos",
                table_name="SOLIC_GASTOS",
                ts_field="FECH_SOLIC",
                pending_state_field="ESTADO_SOLIC",
                pending_state_value="N",
                pending_reprocess_days=30,
            )
            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"solic_gastos": cfg}):
                stmt = repo.build_statement("solic_gastos", Checkpoint(entity="solic_gastos"))
                rows = conn.execute(stmt).mappings().all()

        assert rows[0]["CTA_IMPORTE_COMPR"] == 1210
        assert rows[0]["CTA_IMPORTE_NETO"] == 700
        assert rows[0]["CTA_IMPORTE_SIN_IVA"] == 900

    def test_4_ocs_2026_procesadas(self, engine_with_data):
        """Con ejercicio_min=2026, exactamente 4 OCs distintas deben retornar."""
        cfg = EntityConfig(
            name="oc_items",
            table_name="OC_ITEMS",
            full_load=True,
            ejercicio_min=2026,
        )
        cp = Checkpoint(entity="oc_items")

        with engine_with_data.connect() as conn:
            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"oc_items": cfg}):
                stmt = repo.build_statement("oc_items", cp)
                rows = conn.execute(stmt).fetchall()

        # Agrupar por (EJERCICIO, UNI_COMPRA, NRO_OC) — las 3 primeras columnas de OC_ITEMS
        oc_keys = {(r[0], r[1], r[2]) for r in rows}
        assert len(oc_keys) == 4, f"Deben ser 4 OCs, encontradas: {oc_keys}"

    def test_oc_items_no_incluye_oc_historica_por_op_historica(self, engine_with_data):
        """Una OP historica no debe arrastrar OCs anteriores al minimo."""
        cfg = EntityConfig(
            name="oc_items",
            table_name="OC_ITEMS",
            full_load=True,
            ejercicio_min=2026,
        )
        cp = Checkpoint(entity="oc_items")

        with engine_with_data.connect() as conn:
            conn.execute(text("""
                INSERT INTO REG_COMP VALUES
                (2025, 900, 1, 100, 1, 1, 100)
            """))
            conn.execute(text("""
                INSERT INTO CTA_COMPROB VALUES
                (2025, 'FA', 'CC-2025-1', 100, 900,
                 50000, 50000, '2025-06-10', '2025-07-10')
            """))
            conn.execute(text("""
                INSERT INTO ORDEN_PAGO_IMPUT VALUES
                (2025, 999, 900, 'FA', 'CC-2025-1', 100)
            """))
            conn.commit()

            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"oc_items": cfg}):
                stmt = repo.build_statement("oc_items", cp)
                rows = conn.execute(stmt).fetchall()

        oc_keys = {(r[0], r[1], r[2]) for r in rows}
        assert (2025, 1, 1) not in oc_keys
        assert (2026, 1, 1) in oc_keys

    def test_oc_items_incluye_oc_vieja_referenciada_por_op_en_alcance(self, engine_with_data):
        """Una OC anterior al minimo se trae si una OP confirmada actual la necesita."""
        cfg = EntityConfig(
            name="oc_items",
            table_name="OC_ITEMS",
            full_load=True,
            ejercicio_min=2026,
        )
        cp = Checkpoint(entity="oc_items")

        with engine_with_data.connect() as conn:
            conn.execute(text("""
                INSERT INTO REG_COMP VALUES
                (2025, 900, 1, 100, 1, 1, 100)
            """))
            conn.execute(text("""
                INSERT INTO CTA_COMPROB VALUES
                (2025, 'FA', 'CC-2025-1', 100, 900,
                 50000, 50000, '2025-06-10', '2025-07-10')
            """))
            conn.execute(text("""
                INSERT INTO ORDEN_PAGO VALUES
                (2025, 998, 100, 'C', 'S', '2026-01-15', 50000, 100, 'Pago viejo confirmado en 2026')
            """))
            conn.execute(text("""
                INSERT INTO ORDEN_PAGO_IMPUT VALUES
                (2025, 998, 900, 'FA', 'CC-2025-1', 100)
            """))
            conn.commit()

            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"oc_items": cfg}):
                stmt = repo.build_statement("oc_items", cp)
                rows = conn.execute(stmt).fetchall()

        oc_keys = {(r[0], r[1], r[2]) for r in rows}
        assert (2025, 1, 1) in oc_keys
        assert (2026, 1, 1) in oc_keys

    def test_orden_pago_aplica_ejercicio_min_pero_incluye_confirmada_reciente(self, engine_with_data):
        cfg = EntityConfig(
            name="orden_pago",
            table_name="ORDEN_PAGO",
            ts_field="FECH_CONFIRM",
            pending_state_field="ESTADO_OP",
            pending_state_value="N",
            pending_reprocess_days=30,
            ejercicio_min=2026,
        )
        cp = Checkpoint(entity="orden_pago")

        with engine_with_data.connect() as conn:
            conn.execute(text("""
                INSERT INTO ORDEN_PAGO VALUES
                (2025, 888, 100, 'C', 'S', '2026-01-15 00:00:00', 15000, 100, 'Pago viejo confirmado en 2026')
            """))
            conn.execute(text("""
                INSERT INTO ORDEN_PAGO_IMPUT VALUES
                (2025, 888, 900, 'FA', 'CC-2025-1', 100)
            """))
            conn.commit()

            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"orden_pago": cfg}):
                stmt = repo.build_statement("orden_pago", cp)
                rows = conn.execute(stmt).fetchall()

        op_keys = {(r[0], r[1]) for r in rows}
        assert (2025, 888) in op_keys, "La OP de 2025 confirmada en 2026 debe ser incluida"
        assert (2026, 501) in op_keys
        assert (2025, 999) not in op_keys, "La OP de 2025 confirmada en 2025 no debe ser incluida"

    def test_oc_items_aplica_ejercicio_min_pero_incluye_confirmada_reciente(self, engine_with_data):
        cfg = EntityConfig(
            name="oc_items",
            table_name="OC_ITEMS",
            full_load=True,
            ejercicio_min=2026,
        )
        cp = Checkpoint(entity="oc_items")

        with engine_with_data.connect() as conn:
            conn.execute(text("""
                INSERT INTO ORDEN_COMPRA VALUES
                (2025, 1, 88, 100, '2025-06-01', '2026-01-15 00:00:00', 'OC vieja confirmada en 2026', 'R', 50000, NULL)
            """))
            conn.execute(text("""
                INSERT INTO OC_ITEMS VALUES
                (2025, 1, 88, 1, 'Item viejo confirmado en 2026', 10, 5000, 1, 100)
            """))
            conn.commit()

            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"oc_items": cfg}):
                stmt = repo.build_statement("oc_items", cp)
                rows = conn.execute(stmt).fetchall()

        oc_keys = {(r[0], r[1], r[2]) for r in rows}
        assert (2025, 1, 88) in oc_keys, "La OC de 2025 confirmada en 2026 debe ser incluida"
        assert (2025, 1, 1) not in oc_keys, "La OC de 2025 no confirmada en 2026 no debe ser incluida"


# ─── Tests: Flujo OC → OP ────────────────────────────────────────────────────

class TestOcToOpFlow:
    """Verifica que el flujo OC→OP funciona:
    1. Se procesan 4 OCs de 2026
    2. Las OPs vinculadas confirmadas (via ORDEN_PAGO_IMPUT) son encontradas
    3. Cada OP tiene OPI_NRO_COMPROB que vincula al gasto de la OC
    """

    def test_ops_vinculadas_a_ocs_encontradas(self, engine_with_data):
        """Las OPs confirmadas de 2026 vinculadas a OCs deben retornar con OPI_NRO_COMPROB."""
        cfg = EntityConfig(
            name="orden_pago",
            table_name="ORDEN_PAGO",
            ts_field="FECH_CONFIRM",
            pending_state_field="ESTADO_OP",
            pending_state_value="N",
            pending_reprocess_days=30,
            ejercicio_min=2026,
        )
        cp = Checkpoint(entity="orden_pago")

        with engine_with_data.connect() as conn:
            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"orden_pago": cfg}):
                stmt = repo.build_statement("orden_pago", cp)
                result = conn.execute(stmt)
                columns = list(result.keys())
                rows = result.fetchall()

        # Debe haber 3 OPs confirmadas; las OPs N quedan fuera del envio.
        op_keys = {(r[columns.index("EJERCICIO")], r[columns.index("NRO_OP")]) for r in rows}
        assert len(op_keys) == 3, f"Deben ser 3 OPs confirmadas, encontradas: {op_keys}"
        estados = {r[columns.index("ESTADO_OP")] for r in rows}
        assert estados == {"C"}

        # Cada OP debe tener OPI_NRO_COMPROB (bridge ORDEN_PAGO_IMPUT)
        assert "OPI_NRO_COMPROB" in columns, "La columna OPI_NRO_COMPROB debe estar presente"
        cc_nro_idx = columns.index("OPI_NRO_COMPROB")
        cc_nros = {r[cc_nro_idx] for r in rows}
        assert None not in cc_nros, "Todas las OPs deben tener OPI_NRO_COMPROB"
        assert len(cc_nros) == 3, f"Deben ser 3 OPI_NRO_COMPROB distintos, encontrados: {cc_nros}"

    def test_op_tiene_datos_del_gasto_vinculado(self, engine_with_data):
        """Cada OP debe traer SG_DELEG_SOLIC y SG_NRO_SOLIC del LEFT JOIN."""
        cfg = EntityConfig(
            name="orden_pago",
            table_name="ORDEN_PAGO",
            ts_field="FECH_CONFIRM",
            pending_state_field="ESTADO_OP",
            pending_state_value="N",
            pending_reprocess_days=30,
            ejercicio_min=2026,
        )
        cp = Checkpoint(entity="orden_pago")

        with engine_with_data.connect() as conn:
            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"orden_pago": cfg}):
                stmt = repo.build_statement("orden_pago", cp)
                result = conn.execute(stmt)
                columns = list(result.keys())
                rows = result.fetchall()

        assert "SG_DELEG_SOLIC" in columns
        assert "SG_NRO_SOLIC" in columns

        sg_deleg_idx = columns.index("SG_DELEG_SOLIC")
        sg_nro_idx = columns.index("SG_NRO_SOLIC")
        for r in rows:
            assert r[sg_deleg_idx] is not None, "SG_DELEG_SOLIC no debe ser NULL"
            assert r[sg_nro_idx] is not None, "SG_NRO_SOLIC no debe ser NULL"

    def test_op_no_usa_nro_cance_para_vincular_oc(self, engine_with_data):
        """Si NRO_CANCE apunta a otra SG, la OP no debe heredar esa OC.

        Caso real: la OP paga OPI.NRO_REG_COMP=236 por $1.750 sin OC, pero
        ORDEN_PAGO.NRO_CANCE=372 apunta a una solicitud con OC 370 por $780.000.
        El statement debe respetar el REG_COMP imputado por OPI y dejar SG_OC_* nulo.
        """
        cfg = EntityConfig(
            name="orden_pago",
            table_name="ORDEN_PAGO",
            ts_field="FECH_CONFIRM",
            pending_state_field="ESTADO_OP",
            pending_state_value="N",
            pending_reprocess_days=30,
            ejercicio_min=2026,
        )
        cp = Checkpoint(entity="orden_pago")

        with engine_with_data.connect() as conn:
            conn.execute(text("""
                INSERT INTO ORDEN_COMPRA VALUES
                (2026, 1, 370, 200, '2026-01-20', '2026-01-20', 'OC de otra solicitud', 'R', 780000, NULL)
            """))
            conn.execute(text("""
                INSERT INTO OC_ITEMS VALUES
                (2026, 1, 370, 1, 'Publicidad radial', 12, 65000, 1, 372)
            """))
            conn.execute(text("""
                INSERT INTO SOLIC_GASTOS VALUES
                (2026, 1, 372, 10, '2026-01-19', 'C', 780000, 'Solicitud de otra OC')
            """))
            conn.execute(text("""
                INSERT INTO REG_COMP VALUES
                (2026, 514, 1, 372, 1, 370, 200)
            """))
            conn.execute(text("""
                INSERT INTO REG_COMP VALUES
                (2026, 236, NULL, NULL, NULL, NULL, 100)
            """))
            conn.execute(text("""
                INSERT INTO CTA_COMPROB VALUES
                (2026, 'TKT', '0021-00100640', 100, 236, 1750, 1750, '2026-01-22', '2026-01-22')
            """))
            conn.execute(text("""
                INSERT INTO ORDEN_PAGO VALUES
                (2026, 245, 100, 'C', 'S', '2026-01-22', 1750, 372, 'Reg.Comp. 236')
            """))
            conn.execute(text("""
                INSERT INTO ORDEN_PAGO_IMPUT VALUES
                (2026, 245, 236, 'TKT', '0021-00100640', 100)
            """))
            conn.commit()

            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", {"orden_pago": cfg}):
                stmt = repo.build_statement("orden_pago", cp).where(text("ORDEN_PAGO.NRO_OP = 245"))
                result = conn.execute(stmt)
                columns = list(result.keys())
                row = result.fetchone()

        assert row is not None
        mapping = row._mapping
        assert mapping["OPI_NRO_REG_COMP"] == 236
        assert mapping["OPI_NRO_COMPROB"] == "0021-00100640"
        assert mapping["SG_DELEG_SOLIC"] is None
        assert mapping["SG_NRO_SOLIC"] is None
        assert mapping["SG_OC_EJERCICIO"] is None
        assert mapping["SG_OC_UNI_COMPRA"] is None
        assert mapping["SG_OC_NRO"] is None
        assert "SG_OC_NRO" in columns

    def test_cc_nro_coincide_entre_oc_y_op(self, engine_with_data):
        """El CC_NRO que trae la OC debe ser el mismo que trae la OP vinculada."""
        oc_cfg = EntityConfig(
            name="oc_items",
            table_name="OC_ITEMS",
            full_load=True,
            ejercicio_min=2026,
        )
        op_cfg = EntityConfig(
            name="orden_pago",
            table_name="ORDEN_PAGO",
            ts_field="FECH_CONFIRM",
            pending_state_field="ESTADO_OP",
            pending_state_value="N",
            pending_reprocess_days=30,
            ejercicio_min=2026,
        )

        with engine_with_data.connect() as conn:
            repo = SourceRepository(conn)

            # Obtener CC_NROs de las OCs
            with patch.dict("src.config.ENTITY_CONFIGS", {"oc_items": oc_cfg}):
                oc_stmt = repo.build_statement("oc_items", Checkpoint(entity="oc_items"))
                oc_result = conn.execute(oc_stmt)
                oc_cols = list(oc_result.keys())
                oc_rows = oc_result.fetchall()

            oc_cc_nros = set()
            if "OC_CC_NRO" in oc_cols:
                idx = oc_cols.index("OC_CC_NRO")
                oc_cc_nros = {r[idx] for r in oc_rows if r[idx] is not None}

            # Obtener CC_NROs de las OPs
            with patch.dict("src.config.ENTITY_CONFIGS", {"orden_pago": op_cfg}):
                op_stmt = repo.build_statement("orden_pago", Checkpoint(entity="orden_pago"))
                op_result = conn.execute(op_stmt)
                op_cols = list(op_result.keys())
                op_rows = op_result.fetchall()

            op_cc_nros = set()
            if "OPI_NRO_COMPROB" in op_cols:
                idx = op_cols.index("OPI_NRO_COMPROB")
                op_cc_nros = {r[idx] for r in op_rows if r[idx] is not None}

        # Los CC del bridge OPI deben coincidir con los CC asociados a OCs
        assert oc_cc_nros, "Las OCs deben tener OC_CC_NRO"
        assert op_cc_nros, "Las OPs deben tener OPI_NRO_COMPROB"
        assert op_cc_nros <= oc_cc_nros, (
            f"Todos los OPI_NRO_COMPROB de OPs deben existir en OCs.\n"
            f"OC OC_CC_NROs: {oc_cc_nros}\n"
            f"OP OPI_NRO_COMPROBs: {op_cc_nros}"
        )

    def test_incremental_segunda_corrida_detecta_ops_nuevas(self, engine_with_data):
        """Simula 2 corridas:
        1. Primera corrida: procesa OCs (checkpoint avanza)
        2. Segunda corrida: procesa OPs (detecta las nuevas)
        """
        op_cfg = EntityConfig(
            name="orden_pago",
            table_name="ORDEN_PAGO",
            ts_field="FECH_CONFIRM",
            pending_state_field="ESTADO_OP",
            pending_state_value="N",
            pending_reprocess_days=30,
            ejercicio_min=2026,
        )

        with engine_with_data.connect() as conn:
            repo = SourceRepository(conn)

            # Primera corrida: checkpoint fresco → trae todas las OPs confirmadas 2026
            cp_fresh = Checkpoint(entity="orden_pago")
            with patch.dict("src.config.ENTITY_CONFIGS", {"orden_pago": op_cfg}):
                stmt1 = repo.build_statement("orden_pago", cp_fresh)
                rows1 = conn.execute(stmt1).fetchall()
            assert len(rows1) == 3, "Primera corrida debe traer 3 OPs confirmadas"

            # Simular checkpoint avanzado (última FECH_CONFIRM procesada)
            cp_advanced = Checkpoint(
                entity="orden_pago",
                last_ts=datetime(2026, 4, 4),  # después de las 4 OPs originales
                last_run=datetime(2026, 4, 5),
                records_sent=4,
            )

            # Segunda corrida sin datos nuevos → debe estar vacía
            with patch.dict("src.config.ENTITY_CONFIGS", {"orden_pago": op_cfg}):
                stmt2 = repo.build_statement("orden_pago", cp_advanced)
                rows2 = conn.execute(stmt2).fetchall()
            assert len(rows2) == 0, "Sin OPs nuevas, la segunda corrida debe estar vacía"

            # Agregar una OP nueva (simula nueva OP para una 5ta OC)
            conn.execute(text("""
                INSERT INTO ORDEN_PAGO VALUES
                (2026, 600, 200, 'C', 'S', '2026-05-01', 25000, 300, 'Pago nuevo')
            """))
            conn.commit()

            # Tercera corrida: debe detectar la OP nueva
            with patch.dict("src.config.ENTITY_CONFIGS", {"orden_pago": op_cfg}):
                stmt3 = repo.build_statement("orden_pago", cp_advanced)
                rows3 = conn.execute(stmt3).fetchall()
            assert len(rows3) == 1, "La tercera corrida debe detectar la OP nueva"
