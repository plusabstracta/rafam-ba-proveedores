"""Tests del mapper de clasificaciones (clasificador por objeto del gasto RAFAM).

Validan normalizacion (mojibake + limite de 150), jerarquia de 4 niveles,
dedup de colisiones (3.3.6.0) y armado del payload `clasificaciones`.
"""

from datetime import datetime

from sqlalchemy import create_engine, text

from main import OFFICIAL_ENTITIES
from src.entity_link_store import EntityLinkStore
from src.mappers.clasificaciones import (
    ClasificacionesMapper,
    build_nodes,
    clean_text,
    code_str,
    nivel,
    parent_code,
    persist_links,
    truncate_name,
)
from src.models import Checkpoint
from src.source_repository import SourceRepository

COLUMNS = ["INCISO", "PAR_PRIN", "PAR_PARC", "PAR_SUBP", "DENOMINACION"]


def test_clasificaciones_corren_antes_que_proveedores():
    assert OFFICIAL_ENTITIES[:2] == ("clasificaciones", "proveedores")


def test_query_clasificaciones_es_completa_atemporal_y_ordenada():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE GASTOS (
                INCISO INTEGER,
                PAR_PRIN INTEGER,
                PAR_PARC INTEGER,
                PAR_SUBP INTEGER,
                DENOMINACION TEXT,
                EJERCICIO INTEGER
            )
        """))
        conn.execute(text("""
            INSERT INTO GASTOS VALUES
                (2, 1, 1, 0, 'Productos alimenticios', 2021),
                (2, 0, 0, 0, 'Bienes de consumo', 2021),
                (2, 1, 1, 0, 'Productos alimenticios', 2021),
                (3, 3, 2, 0, 'Alquiler de maquinaria', 2026)
        """))

        repo = SourceRepository(conn)
        old_checkpoint = Checkpoint(
            entity="clasificaciones",
            last_run=datetime(2026, 1, 1),
        )
        result = repo.fetch_entity("clasificaciones", old_checkpoint)

        assert list(result.keys()) == COLUMNS
        assert result.fetchall() == [
            (2, 0, 0, 0, "Bienes de consumo"),
            (2, 1, 1, 0, "Productos alimenticios"),
            (3, 3, 2, 0, "Alquiler de maquinaria"),
        ]


# ── Normalizacion ──────────────────────────────────────────────────────────

def test_clean_text_corrige_mojibake_desagues():
    assert clean_text("Mantenimiento y limpieza de desag³es") == (
        "Mantenimiento y limpieza de desagües"
    )


def test_clean_text_colapsa_espacios():
    assert clean_text("  Gastos   en   personal   ") == "Gastos en personal"


def test_truncate_name_no_toca_cortos():
    assert truncate_name("Agua", 50) == "Agua"


def test_truncate_name_corta_por_palabra_a_50():
    largo = (
        "Transferencias al Sector Público Nacional, al Sector Público "
        "Provincial y al Sector Público Municipal para financiar gastos corrientes"
    )
    out = truncate_name(largo, 50)
    assert len(out) <= 50
    assert not out.endswith(" ")
    # No parte una palabra por la mitad (el ultimo token esta completo)
    assert largo.startswith(out)


# ── Codigos y jerarquia ────────────────────────────────────────────────────

def test_code_str():
    assert code_str(1, 1, 6, 1) == "1.1.6.1"


def test_parent_code_por_nivel():
    assert parent_code(1, 0, 0, 0) is None          # inciso = raiz
    assert parent_code(1, 1, 0, 0) == "1.0.0.0"     # principal -> inciso
    assert parent_code(1, 1, 6, 0) == "1.1.0.0"     # parcial -> principal
    assert parent_code(1, 1, 6, 1) == "1.1.6.0"     # subparcial -> parcial


def test_nivel_por_profundidad():
    assert nivel(1, 0, 0, 0) == 1
    assert nivel(1, 1, 0, 0) == 2
    assert nivel(1, 1, 6, 0) == 3
    assert nivel(1, 1, 6, 1) == 4


# ── build_nodes ────────────────────────────────────────────────────────────

def test_build_nodes_resuelve_colision_1_1_6_con_subparcial():
    rows = [
        (1, 1, 6, 0, "Contribuciones patronales"),
        (1, 1, 6, 1, "al IPS"),
        (1, 1, 6, 2, "AL IOMA"),
        (1, 1, 6, 3, "Aporte a la Aseguradora de Riesgos de Trabajo"),
    ]
    nodes, discarded = build_nodes(COLUMNS, rows)
    assert discarded == []
    by_code = {n["code"]: n for n in nodes}
    assert by_code["1.1.6.0"]["name"] == "Contribuciones patronales"
    assert by_code["1.1.6.1"]["parent_code"] == "1.1.6.0"
    assert by_code["1.1.6.2"]["name"] == "AL IOMA"
    assert by_code["1.1.6.3"]["nivel"] == 4


def test_build_nodes_dedup_3_3_6_0_canonica_y_log():
    rows = [
        (3, 3, 6, 0, "Mantenimiento y Limpieza"),
        (3, 3, 6, 0, "Mantenimiento y limpieza de desagues"),
        (3, 3, 6, 0, "Mantenimiento y limpieza de desag³es"),
    ]
    nodes, discarded = build_nodes(COLUMNS, rows)
    assert len(nodes) == 1
    assert nodes[0]["code"] == "3.3.6.0"
    assert nodes[0]["name"] == "Mantenimiento y Limpieza"
    # Las otras dos denominaciones quedan registradas como descartadas
    assert len(discarded) == 2
    assert {d["kept"] for d in discarded} == {"Mantenimiento y Limpieza"}


def test_build_nodes_ordena_padres_antes_que_hijos():
    rows = [
        (1, 1, 6, 3, "Aporte a la ART"),
        (1, 0, 0, 0, "Gastos en personal"),
        (1, 1, 6, 0, "Contribuciones patronales"),
        (1, 1, 0, 0, "Personal permanente"),
    ]
    nodes, _ = build_nodes(COLUMNS, rows)
    order = [n["code"] for n in nodes]
    assert order == ["1.0.0.0", "1.1.0.0", "1.1.6.0", "1.1.6.3"]


def test_build_nodes_ignora_filas_sin_inciso():
    rows = [
        (None, 0, 0, 0, "basura"),
        (2, 0, 0, 0, "Bienes de consumo"),
    ]
    nodes, _ = build_nodes(COLUMNS, rows)
    assert [n["code"] for n in nodes] == ["2.0.0.0"]


def test_build_nodes_respeta_largo_real_de_account_clasificaciones():
    largo = (
        "Transferencias al Sector Público Nacional, al Sector Público "
        "Provincial y al Sector Público Municipal para financiar gastos corrientes"
    )
    rows = [(5, 3, 0, 0, largo)]
    nodes, _ = build_nodes(COLUMNS, rows)
    assert len(nodes[0]["name"]) <= 150
    assert len(nodes[0]["name"]) > 50
    assert nodes[0]["denominacion"] == clean_text(largo)  # denominacion full preservada


# ── Mapper + persist ───────────────────────────────────────────────────────

def _link_store():
    return EntityLinkStore(db_path=":memory:")


def test_build_payload_arma_seccion_clasificaciones_con_parent_external_id():
    store = _link_store()
    mapper = ClasificacionesMapper(link_store=store)
    rows = [
        (1, 0, 0, 0, "Gastos en personal"),
        (1, 1, 0, 0, "Personal permanente"),
        (1, 1, 6, 0, "Contribuciones patronales"),
        (1, 1, 6, 1, "al IPS"),
    ]
    payload, raw_by_key = mapper.build_payload(
        COLUMNS, rows, dry_run=True, payload_options={}
    )
    assert payload is not None
    clasifs = payload["clasificaciones"]
    assert [c["external_id"]["codigo"] for c in clasifs] == [
        "1.0.0.0", "1.1.0.0", "1.1.6.0", "1.1.6.1",
    ]
    # Raiz sin parent; hijos con parent_external_id
    assert "parent_external_id" not in clasifs[0]
    assert clasifs[3]["parent_external_id"] == {"codigo": "1.1.6.0"}
    assert set(raw_by_key.keys()) == {"1.0.0.0", "1.1.0.0", "1.1.6.0", "1.1.6.1"}
    store.close()


def test_persist_links_guarda_codigo_a_id_remoto():
    store = _link_store()
    mapper = ClasificacionesMapper(link_store=store)
    rows = [(2, 0, 0, 0, "Bienes de consumo")]
    payload, raw_by_key = mapper.build_payload(
        COLUMNS, rows, dry_run=False, payload_options={}
    )
    parsed = {
        "results": {
            "clasificaciones": [
                {"success": True, "external_id": {"codigo": "2.0.0.0"}, "id": 42},
            ]
        }
    }
    persist_links(parsed, raw_by_key, store)
    assert store.get_remote_id("clasificacion", "2.0.0.0") == "42"
    link = store.get_link("clasificacion", "2.0.0.0")
    assert link["denominacion"] == "Bienes de consumo"
    assert link["nivel"] == "1"
    store.close()


def test_build_payload_inyecta_id_en_upsert_y_parent_id_migrado():
    store = _link_store()
    # Simular que el padre ya fue migrado antes.
    store.save_link(entity="clasificacion", source_key="1.1.6.0", remote_id="10")
    store.save_link(entity="clasificacion", source_key="1.1.6.1", remote_id="11")
    mapper = ClasificacionesMapper(link_store=store)
    rows = [(1, 1, 6, 1, "al IPS")]
    payload, _ = mapper.build_payload(COLUMNS, rows, dry_run=True, payload_options={})
    row = payload["clasificaciones"][0]
    assert row["Clasificacion"]["id"] == 11         # upsert del propio nodo
    assert row["parent_id"] == 10                   # parent ya migrado inyectado
    store.close()
