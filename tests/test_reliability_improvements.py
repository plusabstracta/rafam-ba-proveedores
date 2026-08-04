"""Tests de las mejoras de fiabilidad de la sincronizacion.

1. Reinyeccion de la cola de reintentos para proveedores y solic_gastos
   (antes solo orden_pago/retenciones: una fila rechazada quedaba pending
   para siempre, invisible).
2. Expansion de SGs con multiples comprobantes (antes se omitian del
   enriquecimiento).
3. Snapshot de la cola de reintentos en el historial de corridas y su
   agregacion para el mail diario (antes el mail siempre decia "sin
   pendientes").
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

from src.models import Checkpoint, EntityConfig
from src.run_history import aggregate_runs, load_runs, record_run
from src.source_repository import SourceRepository


# ─── 1. Reinyeccion de retry keys en las queries ─────────────────────────────

@pytest.fixture
def engine_proveedores():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE PROVEEDORES (
                COD_PROV INTEGER PRIMARY KEY,
                RAZON_SOCIAL TEXT,
                FECHA_ULT_COMP DATETIME
            )
        """))
        conn.execute(text("INSERT INTO PROVEEDORES VALUES (1, 'Viejo', '2026-01-01')"))
        conn.execute(text("INSERT INTO PROVEEDORES VALUES (2, 'Nuevo', '2026-06-01')"))
        conn.execute(text("INSERT INTO PROVEEDORES VALUES (3, 'Rechazado', '2026-01-15')"))
        conn.commit()
    return engine


class TestRetryReinjectionProveedores:
    CFG = {"proveedores": EntityConfig(
        name="proveedores", table_name="PROVEEDORES", ts_field="FECHA_ULT_COMP",
    )}

    def _rows(self, engine, checkpoint, retry_keys=None):
        from datetime import datetime
        with engine.connect() as conn:
            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", self.CFG):
                stmt = repo.build_statement("proveedores", checkpoint, retry_keys)
                return conn.execute(stmt).fetchall()

    def test_sin_retry_keys_el_cursor_excluye_viejos(self):
        from datetime import datetime
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE PROVEEDORES (COD_PROV INTEGER PRIMARY KEY, RAZON_SOCIAL TEXT, FECHA_ULT_COMP DATETIME)"))
            for cod, fecha in ((1, "2026-01-01"), (2, "2026-06-01"), (3, "2026-01-15")):
                conn.execute(text(f"INSERT INTO PROVEEDORES VALUES ({cod}, 'P{cod}', '{fecha}')"))
            conn.commit()
        cp = Checkpoint(entity="proveedores", last_ts=datetime(2026, 5, 1))
        rows = self._rows(engine, cp)
        assert {r[0] for r in rows} == {2}

    def test_retry_keys_reinyectan_proveedores_viejos(self):
        from datetime import datetime
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE PROVEEDORES (COD_PROV INTEGER PRIMARY KEY, RAZON_SOCIAL TEXT, FECHA_ULT_COMP DATETIME)"))
            for cod, fecha in ((1, "2026-01-01"), (2, "2026-06-01"), (3, "2026-01-15")):
                conn.execute(text(f"INSERT INTO PROVEEDORES VALUES ({cod}, 'P{cod}', '{fecha}')"))
            conn.commit()
        cp = Checkpoint(entity="proveedores", last_ts=datetime(2026, 5, 1))
        # El proveedor 3 fue rechazado por el receptor y quedo encolado:
        # aunque su FECHA_ULT_COMP este detras del watermark, debe re-entrar.
        rows = self._rows(engine, cp, retry_keys={"3"})
        assert {r[0] for r in rows} == {2, 3}

    def test_retry_keys_invalidas_se_ignoran(self):
        from datetime import datetime
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE PROVEEDORES (COD_PROV INTEGER PRIMARY KEY, RAZON_SOCIAL TEXT, FECHA_ULT_COMP DATETIME)"))
            conn.execute(text("INSERT INTO PROVEEDORES VALUES (2, 'P2', '2026-06-01')"))
            conn.commit()
        cp = Checkpoint(entity="proveedores", last_ts=datetime(2026, 5, 1))
        rows = self._rows(engine, cp, retry_keys={"no-numerico", ""})
        assert {r[0] for r in rows} == {2}


class TestRetryReinjectionSolicGastos:
    CFG = {"solic_gastos": EntityConfig(
        name="solic_gastos", table_name="SOLIC_GASTOS", ts_field="FECH_SOLIC",
    )}

    @pytest.fixture
    def engine_sg(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE SOLIC_GASTOS (
                    EJERCICIO INTEGER, DELEG_SOLIC INTEGER, NRO_SOLIC INTEGER,
                    FECH_SOLIC DATETIME, ESTADO_SOLIC TEXT, IMPORTE_TOT REAL,
                    PRIMARY KEY (EJERCICIO, DELEG_SOLIC, NRO_SOLIC)
                )
            """))
            conn.execute(text("""
                CREATE TABLE OC_ITEMS (
                    EJERCICIO INTEGER, UNI_COMPRA INTEGER, NRO_OC INTEGER, ITEM_OC INTEGER,
                    DELEG_SOLIC INTEGER, NRO_SOLIC INTEGER,
                    PRIMARY KEY (EJERCICIO, UNI_COMPRA, NRO_OC, ITEM_OC)
                )
            """))
            conn.execute(text("""
                CREATE TABLE ORDEN_COMPRA (
                    EJERCICIO INTEGER, UNI_COMPRA INTEGER, NRO_OC INTEGER, COD_PROV INTEGER,
                    PRIMARY KEY (EJERCICIO, UNI_COMPRA, NRO_OC)
                )
            """))
            conn.execute(text("INSERT INTO SOLIC_GASTOS VALUES (2026, 1, 100, '2026-01-10', 'C', 500)"))
            conn.execute(text("INSERT INTO SOLIC_GASTOS VALUES (2026, 1, 200, '2026-06-10', 'C', 900)"))
            conn.commit()
        return engine

    def test_retry_keys_reinyectan_sgs_viejas(self, engine_sg):
        from datetime import datetime
        cp = Checkpoint(entity="solic_gastos", last_ts=datetime(2026, 5, 1))
        key = json.dumps({"deleg_solic": 1, "ejercicio": 2026, "nro_solic": 100}, sort_keys=True)
        with engine_sg.connect() as conn:
            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", self.CFG):
                sin_retry = conn.execute(repo.build_statement("solic_gastos", cp)).fetchall()
                con_retry = conn.execute(
                    repo.build_statement("solic_gastos", cp, {key})
                ).fetchall()
        assert {r[2] for r in sin_retry} == {200}
        assert {r[2] for r in con_retry} == {100, 200}

    def test_retry_key_con_nro_comprob_extra_tambien_matchea(self, engine_sg):
        """Las claves de gastos expandidos por comprobante llevan nro_comprob
        extra; el parser debe tolerarlo (ignora el campo)."""
        from datetime import datetime
        cp = Checkpoint(entity="solic_gastos", last_ts=datetime(2026, 5, 1))
        key = json.dumps(
            {"deleg_solic": 1, "ejercicio": 2026, "nro_comprob": "0001-5", "nro_solic": 100},
            sort_keys=True,
        )
        with engine_sg.connect() as conn:
            repo = SourceRepository(conn)
            with patch.dict("src.config.ENTITY_CONFIGS", self.CFG):
                rows = conn.execute(repo.build_statement("solic_gastos", cp, {key})).fetchall()
        assert {r[2] for r in rows} == {100, 200}


# ─── 2. fetch_cta_comprob_for_sgs (expansion multi-comprobante) ──────────────

class TestFetchCtaComprobForSgs:
    @pytest.fixture
    def engine_cc(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE REG_COMP (
                    EJERCICIO INTEGER, NRO_REG_COMP INTEGER,
                    DELEG_SOLIC INTEGER, NRO_SOLIC INTEGER,
                    UNI_COMPRA INTEGER, NRO_OC INTEGER, COD_PROV INTEGER,
                    PRIMARY KEY (EJERCICIO, NRO_REG_COMP)
                )
            """))
            conn.execute(text("""
                CREATE TABLE CTA_COMPROB (
                    EJERCICIO INTEGER, NRO_REG_COMP INTEGER, TIPO TEXT,
                    NRO_COMPROB TEXT, COD_PROV INTEGER,
                    IMPORTE_COMPR REAL, IMPORTE_SIN_IVA REAL,
                    FECH_COMPROB DATETIME, FECH_VENCIM DATETIME
                )
            """))
            # SG (2026,1,100) con DOS comprobantes via el mismo REG_COMP
            conn.execute(text("INSERT INTO REG_COMP VALUES (2026, 900, 1, 100, 1, 50, 77)"))
            conn.execute(text(
                "INSERT INTO CTA_COMPROB VALUES (2026, 900, 'FA', '0001-11', 77, 1000, 900, '2026-03-01', '2026-04-01')"
            ))
            conn.execute(text(
                "INSERT INTO CTA_COMPROB VALUES (2026, 900, 'FA', '0001-22', 77, 2000, 1800, '2026-03-05', '2026-04-05')"
            ))
            conn.commit()
        return engine

    def test_devuelve_todos_los_comprobantes_por_sg(self, engine_cc):
        with engine_cc.connect() as conn:
            repo = SourceRepository(conn)
            out = repo.fetch_cta_comprob_for_sgs([(2026, 1, 100)])
        assert out is not None
        comps = out.get((2026, 1, 100), [])
        assert {c["CTA_NRO_COMPROB"] for c in comps} == {"0001-11", "0001-22"}
        by_nro = {c["CTA_NRO_COMPROB"]: c for c in comps}
        assert by_nro["0001-11"]["CTA_IMPORTE_COMPR"] == 1000
        assert by_nro["0001-22"]["CTA_IMPORTE_NETO"] == 1800

    def test_sg_inexistente_devuelve_vacio(self, engine_cc):
        with engine_cc.connect() as conn:
            repo = SourceRepository(conn)
            out = repo.fetch_cta_comprob_for_sgs([(2026, 9, 999)])
        assert out == {}


class TestSolicGastosMultiComprobante:
    def _mapper(self, source_repo):
        from src.mappers.solic_gastos import SolicGastosMapper

        class _Lookup:
            def resolve_tipo_factura_id(self, _v):
                return 2

        class _LinkStore:
            def __init__(self):
                self.links = {}

            def get_sent_oc_gasto_refs(self):
                return {"SG-2026-1-100"}

            def get_all_links(self, _entity):
                return [{
                    "source_key": json.dumps(
                        {"ejercicio": 2026, "nro_oc": 50, "uni_compra": 1}, sort_keys=True
                    ),
                    "remote_id": "700",
                    "gasto_refs": "SG-2026-1-100",
                }]

            def get_remote_id(self, _entity, _key):
                return "42"

            def get_link(self, _entity, _key):
                return None

        resolver_response = {
            "success": True,
            "gastos": [
                {
                    "id": 91,
                    "pedido_id": 700,
                    "proveedor_id": 42,
                    "factura_nro": "11",
                    "punto_de_venta": "0001",
                    "empty_fields": ["importe_neto"],
                },
                {
                    "id": 92,
                    "pedido_id": 700,
                    "proveedor_id": 42,
                    "factura_nro": "22",
                    "punto_de_venta": "0001",
                    "empty_fields": ["importe_neto"],
                },
            ],
        }
        return SolicGastosMapper(
            link_store=_LinkStore(),
            lookup_resolver=_Lookup(),
            resolve_gastos_fn=lambda pedido_ids, comprobantes: resolver_response,
            source_repo=source_repo,
        )

    COLUMNS = [
        "EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC", "FECH_SOLIC", "ESTADO_SOLIC",
        "IMPORTE_TOT", "CTA_COMPROB_COUNT", "CTA_NRO_COMPROB", "CTA_TIPO_COMPROB",
        "CTA_FECH_COMPROB", "CTA_FECH_VENCIM", "CTA_IMPORTE_COMPR",
        "CTA_IMPORTE_NETO", "CTA_IMPORTE_SIN_IVA", "OC_COD_PROV",
    ]

    def _row(self):
        vals = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "100",
            "FECH_SOLIC": "2026-03-01", "ESTADO_SOLIC": "C", "IMPORTE_TOT": "3000",
            # 2 comprobantes: la fila agregada solo trae el MIN()
            "CTA_COMPROB_COUNT": "2", "CTA_NRO_COMPROB": "0001-11",
            "CTA_TIPO_COMPROB": "FA", "CTA_FECH_COMPROB": "2026-03-01",
            "CTA_IMPORTE_COMPR": "1000", "OC_COD_PROV": "77",
        }
        return tuple(vals.get(c, "") for c in self.COLUMNS)

    def test_sg_multi_comprobante_se_expande_y_enriquece(self):
        class _FakeRepo:
            def fetch_cta_comprob_for_sgs(self, keys):
                assert keys == [(2026, 1, 100)]
                return {(2026, 1, 100): [
                    {
                        "CTA_NRO_COMPROB": "0001-11", "CTA_TIPO_COMPROB": "FA",
                        "CTA_FECH_COMPROB": "2026-03-01", "CTA_FECH_VENCIM": "2026-04-01",
                        "CTA_IMPORTE_COMPR": 1000, "CTA_IMPORTE_NETO": 900,
                        "CTA_IMPORTE_SIN_IVA": 900,
                    },
                    {
                        "CTA_NRO_COMPROB": "0001-22", "CTA_TIPO_COMPROB": "FA",
                        "CTA_FECH_COMPROB": "2026-03-05", "CTA_FECH_VENCIM": "2026-04-05",
                        "CTA_IMPORTE_COMPR": 2000, "CTA_IMPORTE_NETO": 1800,
                        "CTA_IMPORTE_SIN_IVA": 1800,
                    },
                ]}

        mapper = self._mapper(_FakeRepo())
        payload, raw_by_sk = mapper.build_payload(
            self.COLUMNS, [self._row()], dry_run=False, payload_options={},
        )
        assert payload is not None
        gastos = payload["gastos"]
        # Un enriquecimiento por comprobante, cada uno contra su gasto_id
        assert {g["Gasto"]["id"] for g in gastos} == {91, 92}
        assert all(g["Gasto"]["merge"] == "fill_empty" for g in gastos)
        by_id = {g["Gasto"]["id"]: g for g in gastos}
        assert by_id[91]["Gasto"]["importe_neto"] == 900
        assert by_id[92]["Gasto"]["importe_neto"] == 1800
        # external_id extendido con nro_comprob para no colisionar en links
        exts = [g["external_id"] for g in gastos]
        assert {e["nro_comprob"] for e in exts} == {"0001-11", "0001-22"}
        assert all(e["ejercicio"] == 2026 and e["nro_solic"] == 100 for e in exts)

    def test_sin_source_repo_no_expande_y_no_rompe(self):
        mapper = self._mapper(None)
        payload, _ = mapper.build_payload(
            self.COLUMNS, [self._row()], dry_run=False, payload_options={},
        )
        assert payload is None


# ─── 3. Cola de reintentos en el historial / mail diario ─────────────────────

class TestRetryCountsEnHistorial:
    def test_record_y_aggregate_propagan_retry_counts(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAFAM_RUN_HISTORY_PATH", str(tmp_path / "hist.jsonl"))
        base = {
            "hostname": "vm1",
            "start_time": "2026-08-04 10:00:00",
            "end_time": "2026-08-04 10:05:00",
            "duration_formatted": "00:05:00",
            "success": True,
            "error_msg": None,
        }
        record_run(
            {**base, "retry_counts_start": {"orden_pago": {"pending": 5}},
             "retry_counts_end": {"orden_pago": {"pending": 3}}},
            [],
        )
        record_run(
            {**base, "start_time": "2026-08-04 11:00:00",
             "retry_counts_start": {"orden_pago": {"pending": 3}},
             "retry_counts_end": {"orden_pago": {"pending": 7}, "proveedores": {"pending": 1}}},
            [],
        )

        runs = load_runs("2026-08-04")
        assert len(runs) == 2
        summary, _metrics = aggregate_runs(runs, "2026-08-04")
        # Estado del dia: inicio de la primera corrida, fin de la ultima.
        assert summary["retry_counts_start"] == {"orden_pago": {"pending": 5}}
        assert summary["retry_counts_end"] == {
            "orden_pago": {"pending": 7}, "proveedores": {"pending": 1},
        }
