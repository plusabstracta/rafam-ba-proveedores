#!/usr/bin/env python3
"""update_field_mapping.py — Regenera docs/field_mapping.md desde el esquema real.

Combina las columnas reales leídas desde la base de datos con el mapeo
RAFAM→Paxapos definido en PAXAPOS_MAPPINGS (fuente de verdad en este script).

Columnas presentes en la DB pero **ausentes** en PAXAPOS_MAPPINGS aparecen
como *(completar)* en la tabla generada, facilitando la detección de gaps.

Configurar el backend via variables de entorno (o .env):
    DB_BACKEND=sqlite   # default — usa state/dev_rafam.db (cargar antes con load_csv_to_sqlite.py)
    DB_BACKEND=oracle   # usa Oracle RAFAM (requiere DB_HOST, DB_USER, DB_PASSWORD)

Uso:
    python scripts/update_field_mapping.py
    python scripts/update_field_mapping.py --dry-run   # imprime en stdout, no escribe
    python scripts/update_field_mapping.py --db state/other.db   # SQLite custom
"""

from __future__ import annotations

import argparse
import os
import sys  # noqa: F401 — kept for stderr writes
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect as sa_inspect  # noqa: E402
from sqlalchemy.engine import Engine

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

DOCS_DIR = REPO_ROOT / "docs"
OUTPUT_MD = DOCS_DIR / "field_mapping.md"
SCHEMA = "OWNER_RAFAM"


def _create_engine(backend: str, db_path: str | None) -> Engine:
    """Build a SQLAlchemy engine for the requested backend.

    oracledb is imported lazily so that SQLite mode works in environments
    where the Oracle Instant Client is not installed.
    """
    if backend == "sqlite":
        path = db_path or str(REPO_ROOT / "state" / "dev_rafam.db")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(f"sqlite+pysqlite:///{path}", future=True)

    if backend != "oracle":
        raise ValueError(f"DB_BACKEND no soportado: '{backend}'. Usar oracle|sqlite")

    import oracledb  # noqa: PLC0415 — intentional lazy import

    host = os.getenv("DB_HOST", "10.10.91.241")
    port = int(os.getenv("DB_PORT", 1521))
    service = os.getenv("DB_SERVICE", "BDRAFAM")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    if not user or not password:
        raise ValueError("Faltan DB_USER / DB_PASSWORD para Oracle")
    oracle_client_dir = os.getenv("ORACLE_CLIENT_DIR")
    oracledb.init_oracle_client(lib_dir=oracle_client_dir or None)
    url = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service}"
    return create_engine(url, future=True)


# ─── Mapeo RAFAM → Paxapos ────────────────────────────────────────────────────
# Fuente de verdad para las columnas mapeadas. Editar aquí al confirmar nuevos campos.
# Formato por tabla: lista de (COLUMNA_RAFAM, tabla_paxapos, col_paxapos, transformacion).
# Las columnas presentes en la DB pero AUSENTES aquí aparecen como *(completar)*.

PAXAPOS_MAPPINGS: dict[str, list[tuple[str, str, str, str]]] = {
    "PROVEEDORES": [
        ("COD_PROV",       "proveedores", "id_externo",       "ninguna"),
        ("RAZON_SOCIAL",   "proveedores", "razon_social",     "trim()"),
        ("FANTASIA",       "proveedores", "name",             "trim(); fallback a RAZON_SOCIAL"),
        ("CUIT",           "proveedores", "cuit",             "_normalize_cuit()"),
        ("COD_IVA",        "proveedores", "iva_condicion_id", "mapeo IVA_MAP (RINS/MONOT/EXEN/CF/NGAN/RNI)"),
        ("COD_ESTADO",     "proveedores", "estado",           "mapeo de código"),
        ("EMAIL",          "proveedores", "mail",             "trim()"),
        ("CALLE_POSTAL",   "proveedores", "domicilio",        "_join_address(CALLE_POSTAL, NRO_POSTAL)"),
        ("NRO_POSTAL",     "proveedores", "domicilio",        "parte de _join_address (ver CALLE_POSTAL)"),
        ("CALLE_LEGAL",    "proveedores", "domicilio",        "_join_address(CALLE_LEGAL, NRO_LEGAL) — fallback"),
        ("NRO_LEGAL",      "proveedores", "domicilio",        "parte de _join_address (ver CALLE_LEGAL)"),
        ("LOCA_POSTAL",    "proveedores", "localidad",        "_first_non_empty(LOCA_POSTAL, LOCA_LEGAL)"),
        ("LOCA_LEGAL",     "proveedores", "localidad",        "_first_non_empty fallback"),
        ("PROV_POSTAL",    "proveedores", "provincia",        "_first_non_empty(PROV_POSTAL, PROV_LEGAL)"),
        ("PROV_LEGAL",     "proveedores", "provincia",        "_first_non_empty fallback"),
        ("COD_POSTAL",     "proveedores", "codigo_postal",    "_first_non_empty(COD_POSTAL, COD_LEGAL)"),
        ("COD_LEGAL",      "proveedores", "codigo_postal",    "_first_non_empty fallback"),
        ("NRO_PAIS_TE1",   "proveedores", "telefono",         "_build_phone(NRO_PAIS_TE1, NRO_INTE_TE1, NRO_TELE_TE1)"),
        ("NRO_INTE_TE1",   "proveedores", "telefono",         "parte de _build_phone (ver NRO_PAIS_TE1)"),
        ("NRO_TELE_TE1",   "proveedores", "telefono",         "parte de _build_phone (ver NRO_PAIS_TE1)"),
        ("NRO_PAIS_TE2",   "proveedores", "telefono",         "_build_phone — segundo teléfono (fallback)"),
        ("NRO_INTE_TE2",   "proveedores", "telefono",         "parte de _build_phone segundo"),
        ("NRO_TELE_TE2",   "proveedores", "telefono",         "parte de _build_phone segundo"),
        ("NRO_PAIS_TE3",   "proveedores", "telefono",         "_build_phone — tercer teléfono (fallback)"),
        ("NRO_INTE_TE3",   "proveedores", "telefono",         "parte de _build_phone tercero"),
        ("NRO_TELE_TE3",   "proveedores", "telefono",         "parte de _build_phone tercero"),
        ("TE_CELULAR",     "proveedores", "telefono",         "_first_non_empty fallback celular"),
        ("FECHA_ALTA",     "proveedores", "created_at",       "ninguna"),
        ("FECHA_ULT_COMP", "proveedores", "updated_at",       "ninguna"),
    ],
    "JURISDICCIONES": [
        ("JURISDICCION",  "jurisdicciones", "id_externo",    "ninguna"),
        ("DENOMINACION",  "jurisdicciones", "nombre",        "trim()"),
        ("SELECCIONABLE", "jurisdicciones", "seleccionable", "ninguna"),
        ("VIGENTE_DESDE", "jurisdicciones", "vigente_desde", "ninguna"),
        ("VIGENTE_HASTA", "jurisdicciones", "vigente_hasta", "ninguna"),
    ],
    "PEDIDOS": [
        ("EJERCICIO",    "pedidos", "ejercicio",      "ninguna"),
        ("NUM_PED",      "pedidos", "numero_pedido",  "ninguna"),
        ("JURISDICCION", "pedidos", "jurisdiccion_id","lookup por id_externo (FK → JURISDICCIONES)"),
        ("FECH_EMI",     "pedidos", "fecha",          "ninguna"),
        ("COSTO_TOT",    "pedidos", "importe_total",  "ninguna"),
        ("PED_ESTADO",   "pedidos", "estado",         "mapeo de código"),
        ("OBSERVACIONES","pedidos", "observaciones",  "trim()"),
    ],
    "PED_ITEMS": [
        ("EJERCICIO",    "pedido_items", "ejercicio",       "parte de FK → PEDIDOS"),
        ("NUM_PED",      "pedido_items", "pedido_id",       "lookup por ejercicio+numero_pedido (FK → PEDIDOS)"),
        ("ORDEN",        "pedido_items", "nro_item",        "ninguna"),
        ("JURISDICCION", "pedido_items", "jurisdiccion_id", "lookup por id_externo (FK → JURISDICCIONES)"),
        ("DESCRIP_BIE",  "pedido_items", "descripcion",     "trim()"),
        ("CANTIDAD",     "pedido_items", "cantidad",        "ninguna"),
        ("COSTO_UNI",    "pedido_items", "precio_unitario", "ninguna"),
    ],
    "SOLIC_GASTOS": [
        ("EJERCICIO",    "solicitudes_gasto", "ejercicio",         "ninguna"),
        ("DELEG_SOLIC",  "solicitudes_gasto", "deleg_solic",       "ninguna"),
        ("NRO_SOLIC",    "solicitudes_gasto", "numero_solicitud",  "ninguna"),
        ("NRO_PED",      "solicitudes_gasto", "pedido_id",         "lookup ejercicio+numero_pedido (FK → PEDIDOS; NRO_PED → NUM_PED)"),
        ("JURISDICCION", "solicitudes_gasto", "jurisdiccion_id",   "lookup por id_externo (FK → JURISDICCIONES)"),
        ("OP_COD_PROV",  "solicitudes_gasto", "proveedor_id",      "lookup por id_externo (FK → PROVEEDORES)"),
        ("FECH_SOLIC",   "solicitudes_gasto", "fecha",             "ninguna"),
        ("IMPORTE_TOT",  "solicitudes_gasto", "importe",           "ninguna"),
        ("ESTADO_SOLIC", "solicitudes_gasto", "estado",            "mapeo de código"),
    ],
    "ORDEN_COMPRA": [
        ("EJERCICIO",   "ordenes_compra", "ejercicio",       "ninguna"),
        ("UNI_COMPRA",  "ordenes_compra", "uni_compra",      "ninguna"),
        ("NRO_OC",      "ordenes_compra", "numero_oc",       "ninguna"),
        ("COD_PROV",    "ordenes_compra", "proveedor_id",    "lookup por id_externo (FK → PROVEEDORES)"),
        ("CUIT",        "ordenes_compra", "cuit_proveedor",  "ninguna (desnormalizado)"),
        ("FECH_OC",     "ordenes_compra", "fecha",           "ninguna"),
        ("IMPORTE_TOT", "ordenes_compra", "importe_total",   "ninguna"),
        ("ESTADO_OC",   "ordenes_compra", "estado",          "N→pendiente, A→anulada"),
    ],
    "OC_ITEMS": [
        ("EJERCICIO",      "oc_items", "ejercicio",       "parte de FK → ORDEN_COMPRA"),
        ("UNI_COMPRA",     "oc_items", "uni_compra",      "parte de FK → ORDEN_COMPRA"),
        ("NRO_OC",         "oc_items", "orden_compra_id", "lookup por clave compuesta (FK → ORDEN_COMPRA)"),
        ("DELEG_SOLIC",    "oc_items", "deleg_solic",     "parte de FK → SOLIC_GASTOS"),
        ("NRO_SOLIC",      "oc_items", "solic_gasto_id",  "lookup por clave compuesta (FK → SOLIC_GASTOS)"),
        ("ITEM_OC",        "oc_items", "nro_item",        "ninguna"),
        ("COD_PROV",       "oc_items", "proveedor_id",    "lookup por id_externo (FK → PROVEEDORES)"),
        ("SG_JURISDICCION","oc_items", "jurisdiccion_id", "lookup por id_externo (FK → JURISDICCIONES)"),
        ("DESCRIPCION",    "oc_items", "descripcion",     "trim()"),
        ("CANTIDAD",       "oc_items", "cantidad",        "ninguna"),
        ("IMP_UNITARIO",   "oc_items", "precio_unitario", "ninguna"),
    ],
    "ORDEN_PAGO": [
        ("EJERCICIO",           "ordenes_pago", "ejercicio",              "ninguna"),
        ("NRO_OP",              "ordenes_pago", "numero_op",              "ninguna"),
        ("COD_PROV",            "ordenes_pago", "proveedor_id",           "lookup por id_externo (FK → PROVEEDORES)"),
        ("JURISDICCION",        "ordenes_pago", "jurisdiccion_id",        "lookup por id_externo (FK → JURISDICCIONES)"),
        ("SG_DELEG_SOLIC",      "ordenes_pago", "deleg_solic",            "parte de FK → SOLIC_GASTOS"),
        ("SG_NRO_SOLIC",        "ordenes_pago", "solic_gasto_id",         "lookup por clave compuesta (FK → SOLIC_GASTOS)"),
        ("RECO_DEU_COMPRA_EJER","ordenes_pago", "orden_compra_ejercicio", "parte de FK → ORDEN_COMPRA"),
        ("RECO_DEU_COMPRA",     "ordenes_pago", "orden_compra_id",        "lookup por clave compuesta (FK → ORDEN_COMPRA; confirmar UNI_COMPRA)"),
        ("FECH_OP",             "ordenes_pago", "fecha",                  "ninguna"),
        ("IMPORTE_TOTAL",       "ordenes_pago", "importe",                "ninguna"),
        ("IMPORTE_LIQUIDO",     "ordenes_pago", "importe_liquido",        "ninguna"),
        ("ESTADO_OP",           "ordenes_pago", "estado",                 "C→pagada, A→anulada, N→pendiente"),
    ],
}

# ─── Claves primarias ─────────────────────────────────────────────────────────
PK_DEFINITIONS: dict[str, list[str]] = {
    "JURISDICCIONES": ["JURISDICCION"],
    "PROVEEDORES":    ["COD_PROV"],
    "PEDIDOS":        ["EJERCICIO", "NUM_PED"],
    "PED_ITEMS":      ["EJERCICIO", "NUM_PED", "ORDEN"],
    "SOLIC_GASTOS":   ["EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC"],
    "ORDEN_COMPRA":   ["EJERCICIO", "UNI_COMPRA", "NRO_OC"],
    "OC_ITEMS":       ["EJERCICIO", "UNI_COMPRA", "NRO_OC", "ITEM_OC"],
    "ORDEN_PAGO":     ["EJERCICIO", "NRO_OP"],
}

# ─── Relaciones FK ────────────────────────────────────────────────────────────
# Incluye relaciones lógicas confirmadas por análisis de CSV + diccionario Oracle.
# "note" se muestra en la columna extra de la tabla generada.
FK_RELATIONSHIPS: list[dict[str, Any]] = [
    {"child": "PEDIDOS",      "child_cols": ["JURISDICCION"],
     "parent": "JURISDICCIONES", "parent_cols": ["JURISDICCION"]},
    {"child": "PED_ITEMS",    "child_cols": ["EJERCICIO", "NUM_PED"],
     "parent": "PEDIDOS",        "parent_cols": ["EJERCICIO", "NUM_PED"]},
    {"child": "PED_ITEMS",    "child_cols": ["JURISDICCION"],
     "parent": "JURISDICCIONES", "parent_cols": ["JURISDICCION"]},
    {"child": "SOLIC_GASTOS", "child_cols": ["EJERCICIO", "NRO_PED"],
     "parent": "PEDIDOS",        "parent_cols": ["EJERCICIO", "NUM_PED"],
     "note": "NRO_PED → NUM_PED (nombres distintos en cada tabla)"},
    {"child": "SOLIC_GASTOS", "child_cols": ["JURISDICCION"],
     "parent": "JURISDICCIONES", "parent_cols": ["JURISDICCION"]},
    {"child": "SOLIC_GASTOS", "child_cols": ["OP_COD_PROV"],
     "parent": "PROVEEDORES",    "parent_cols": ["COD_PROV"]},
    {"child": "ORDEN_COMPRA", "child_cols": ["COD_PROV"],
     "parent": "PROVEEDORES",    "parent_cols": ["COD_PROV"]},
    {"child": "OC_ITEMS",     "child_cols": ["EJERCICIO", "UNI_COMPRA", "NRO_OC"],
     "parent": "ORDEN_COMPRA",   "parent_cols": ["EJERCICIO", "UNI_COMPRA", "NRO_OC"]},
    {"child": "OC_ITEMS",     "child_cols": ["EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC"],
     "parent": "SOLIC_GASTOS",   "parent_cols": ["EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC"]},
    {"child": "OC_ITEMS",     "child_cols": ["COD_PROV"],
     "parent": "PROVEEDORES",    "parent_cols": ["COD_PROV"]},
    {"child": "OC_ITEMS",     "child_cols": ["SG_JURISDICCION"],
     "parent": "JURISDICCIONES", "parent_cols": ["JURISDICCION"]},
    {"child": "ORDEN_PAGO",   "child_cols": ["COD_PROV"],
     "parent": "PROVEEDORES",    "parent_cols": ["COD_PROV"]},
    {"child": "ORDEN_PAGO",   "child_cols": ["JURISDICCION"],
     "parent": "JURISDICCIONES", "parent_cols": ["JURISDICCION"]},
    {"child": "ORDEN_PAGO",   "child_cols": ["EJERCICIO", "SG_DELEG_SOLIC", "SG_NRO_SOLIC"],
     "parent": "SOLIC_GASTOS",   "parent_cols": ["EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC"]},
    {"child": "ORDEN_PAGO",   "child_cols": ["RECO_DEU_COMPRA_EJER", "RECO_DEU_COMPRA"],
     "parent": "ORDEN_COMPRA",   "parent_cols": ["EJERCICIO", "NRO_OC"],
     "note": "confirmar UNI_COMPRA"},
]

# ─── Secciones del documento (en orden de aparición) ─────────────────────────
SECTIONS: list[dict[str, Any]] = [
    {"num": 1, "title": "Proveedores",          "tables": ["PROVEEDORES"]},
    {"num": 2, "title": "Jurisdicciones",        "tables": ["JURISDICCIONES"]},
    {"num": 3, "title": "Pedidos",               "tables": ["PEDIDOS", "PED_ITEMS"]},
    {"num": 4, "title": "Solicitudes de gasto",  "tables": ["SOLIC_GASTOS"]},
    {"num": 5, "title": "Órdenes de compra",     "tables": ["ORDEN_COMPRA", "OC_ITEMS"]},
    {"num": 6, "title": "Órdenes de pago",       "tables": ["ORDEN_PAGO"]},
]


# ─── Schema inspection ────────────────────────────────────────────────────────

def _get_columns(inspector: Any, table: str, backend: str) -> list[dict[str, str]]:
    """Return [{name, type}] for *table*. Returns [] on error."""
    try:
        schema = SCHEMA if backend == "oracle" else None
        cols = inspector.get_columns(table, schema=schema)
        return [{"name": str(c["name"]).upper(), "type": str(c["type"])} for c in cols]
    except Exception as exc:
        print(f"[WARN] {table}: no se pudo leer columnas — {exc}", file=sys.stderr)
        return []


def _available_tables(inspector: Any, backend: str, engine: Any = None) -> set[str]:
    """Return uppercase table names visible to the current connection."""
    from sqlalchemy import text as sa_text

    try:
        schema = SCHEMA if backend == "oracle" else None
        tables = {t.upper() for t in inspector.get_table_names(schema=schema)}
    except Exception as exc:
        print(f"[ERROR] No se pudo listar tablas via inspector: {exc}", file=sys.stderr)
        tables = set()

    if not tables and backend == "oracle" and engine is not None:
        # Fallback: query ALL_TABLES directly (handles restricted privileges)
        print("[INFO] get_table_names vacio — intentando ALL_TABLES directamente...", file=sys.stderr)
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    sa_text("SELECT table_name FROM all_tables WHERE owner = :s"),
                    {"s": SCHEMA},
                )
                tables = {row[0].upper() for row in result}
        except Exception as exc2:
            print(f"[ERROR] No se pudo listar tablas via ALL_TABLES: {exc2}", file=sys.stderr)
            sys.exit(1)

    if not tables:
        print(f"[ERROR] No se encontraron tablas para el schema '{SCHEMA}'.", file=sys.stderr)
        sys.exit(1)

    return tables


# ─── Markdown builders ────────────────────────────────────────────────────────

def _entity_rows(table: str, columns: list[dict[str, str]], backend: str) -> list[str]:
    """Generate markdown table rows for a single RAFAM table."""
    mapping: dict[str, tuple[str, str, str]] = {
        rafam: (pax_table, pax_col, transform)
        for rafam, pax_table, pax_col, transform in PAXAPOS_MAPPINGS.get(table, [])
    }
    pks = set(PK_DEFINITIONS.get(table, []))
    db_col_names = {c["name"] for c in columns}

    # Warn about mapped columns missing from the DB
    for rafam_col in mapping:
        if rafam_col not in db_col_names:
            print(
                f"[WARN] {table}.{rafam_col}: en PAXAPOS_MAPPINGS pero NO en la DB -- revisar",
                file=sys.stderr,
            )

    rows: list[str] = []
    for col in columns:
        name = col["name"]
        col_type = col["type"]
        # Only show type for Oracle (SQLite is all TEXT — no value)
        type_suffix = (
            f" *(tipo: `{col_type}`)*"
            if backend == "oracle" and col_type and col_type.upper() != "TEXT"
            else ""
        )
        pk_marker = "[PK] " if name in pks else ""
        display_name = f"{pk_marker}`{name}`{type_suffix}"

        if name in mapping:
            pax_table, pax_col, transform = mapping[name]
            rows.append(f"| {table} | {display_name} | {pax_table} | {pax_col} | {transform} |")
        else:
            rows.append(f"| {table} | {display_name} | *(completar)* | *(completar)* | *(completar)* |")

    return rows


def _build_markdown(
    all_columns: dict[str, list[dict[str, str]]],
    backend: str,
    engine: Any | None = None,
    include_samples: bool = True,
) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_label = (
        f"Oracle `{SCHEMA}`" if backend == "oracle"
        else "SQLite dev (snapshots CSV)"
    )
    schema_prefix = f"{SCHEMA}." if backend == "oracle" else ""

    lines: list[str] = [
        "# Mapeo de campos RAFAM → Paxapos",
        "",
        f"> Generado automáticamente por `scripts/update_field_mapping.py` el {ts}  ",
        f"> Fuente de columnas: {source_label}  ",
        "> Para actualizar el mapeo: editar `PAXAPOS_MAPPINGS` en el script y re-ejecutar.",
        "",
        "---",
        "",
    ]

    for section in SECTIONS:
        num = section["num"]
        title = section["title"]
        tables: list[str] = section["tables"]

        lines += [f"## {num}. {title}", ""]
        lines += [
            "| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |",
            "|-------------|-------------|---------------|---------------|----------------|",
        ]
        for table in tables:
            cols = all_columns.get(table, [])
            if not cols:
                lines.append(
                    f"| {table} | *(sin columnas — "
                    "verificar que la DB está cargada)* | | | |"
                )
            else:
                lines.extend(_entity_rows(table, cols, backend))
        lines += ["", "---", ""]

    # Section 7: relationships
    lines += [
        "## 7. Relaciones entre tablas (claves foráneas)",
        "",
        "### 7.1 Claves primarias",
        "",
        "| Tabla | Clave primaria |",
        "|-------|----------------|",
    ]
    for table, pks in PK_DEFINITIONS.items():
        pk_str = " + ".join(f"`{p}`" for p in pks)
        lines.append(f"| {table} | {pk_str} |")

    lines += [
        "",
        "### 7.2 Tabla de FKs",
        "",
        "| Tabla hija | Columna(s) FK | Tabla padre | Columna(s) referenciada | Nota |",
        "|------------|---------------|-------------|-------------------------|------|",
    ]
    for fk in FK_RELATIONSHIPS:
        child_cols = " + ".join(f"`{c}`" for c in fk["child_cols"])
        parent_cols = " + ".join(f"`{c}`" for c in fk["parent_cols"])
        note = fk.get("note", "")
        lines.append(
            f"| {fk['child']} | {child_cols} | {fk['parent']} | {parent_cols} | {note} |"
        )

    lines += ["", "---", ""]

    # Section 8: inferred relations
    lines.extend(_build_inferred_relations_section(all_columns))

    # Section 9: business flow queries
    lines.extend(_build_flow_queries_section(backend, schema_prefix))

    # Section 10: provider consistency queries
    lines.extend(_build_provider_analysis_section(backend, schema_prefix))

    # Section 11: real sample data (requires live connection)
    if include_samples and engine is not None:
        lines.extend(_build_sample_data_section(engine, backend, schema_prefix))

    return "\n".join(lines)


# ─── Column-based FK inference ────────────────────────────────────────────────

# Column names that act as join keys across tables.
# Each entry: (col_name, [(table_a, alias_a), (table_b, alias_b), ...])
# If a column appears in ≥2 of the listed tables it's flagged as an inferred FK.
_JOIN_CANDIDATES: list[tuple[str, list[str]]] = [
    ("EJERCICIO",    ["PEDIDOS", "PED_ITEMS", "SOLIC_GASTOS", "ORDEN_COMPRA", "OC_ITEMS", "ORDEN_PAGO"]),
    ("COD_PROV",     ["PROVEEDORES", "ORDEN_COMPRA", "OC_ITEMS", "ORDEN_PAGO"]),
    ("JURISDICCION", ["JURISDICCIONES", "PEDIDOS", "PED_ITEMS", "SOLIC_GASTOS", "ORDEN_PAGO"]),
    ("NRO_OC",       ["ORDEN_COMPRA", "OC_ITEMS"]),
    ("NRO_SOLIC",    ["SOLIC_GASTOS", "OC_ITEMS", "ORDEN_PAGO"]),
    ("NUM_PED",      ["PEDIDOS", "PED_ITEMS"]),
    ("UNI_COMPRA",   ["ORDEN_COMPRA", "OC_ITEMS"]),
    ("DELEG_SOLIC",  ["SOLIC_GASTOS", "OC_ITEMS"]),
]


def _infer_relations(
    all_columns: dict[str, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    """Return inferred FK relations based on shared column names across tables."""
    col_to_tables: dict[str, list[str]] = {}
    for table, cols in all_columns.items():
        for col in cols:
            col_to_tables.setdefault(col["name"], []).append(table)

    results: list[dict[str, Any]] = []
    seen: set[frozenset[str]] = set()

    for col_name, candidate_tables in _JOIN_CANDIDATES:
        tables_with_col = [t for t in candidate_tables if col_name in col_to_tables.get(col_name, []) or
                           col_name in {c["name"] for c in all_columns.get(t, [])}]
        if len(tables_with_col) < 2:
            continue
        for i, t_a in enumerate(tables_with_col):
            for t_b in tables_with_col[i + 1:]:
                key = frozenset({f"{t_a}.{col_name}", f"{t_b}.{col_name}"})
                if key in seen:
                    continue
                seen.add(key)
                results.append({"col": col_name, "table_a": t_a, "table_b": t_b})

    return results


def _build_inferred_relations_section(
    all_columns: dict[str, list[dict[str, str]]],
) -> list[str]:
    inferred = _infer_relations(all_columns)

    lines: list[str] = [
        "## 8. Relaciones inferidas por coincidencia de columnas",
        "",
        "> Columnas con el mismo nombre presentes en 2 o mas tablas — indican joins posibles.",
        "> Complementa la seccion 7 (FKs declaradas).",
        "",
        "| Columna compartida | Tabla A | Tabla B |",
        "|--------------------|---------|---------|",
    ]
    for rel in inferred:
        lines.append(f"| `{rel['col']}` | {rel['table_a']} | {rel['table_b']} |")

    lines += ["", "---", ""]
    return lines


# ─── Business flow queries ────────────────────────────────────────────────────

# Parametrizable JOIN chains. Each entry has:
#   title    — section heading
#   desc     — what this query shows
#   sql      — the query (parameterized with {schema} and {limit})
#   sqlite   — simplified version that omits schema prefix

_FLOW_QUERIES: list[dict[str, str]] = [
    {
        "title": "Pedido completo con sus items",
        "desc": "Navega PEDIDOS → PED_ITEMS para ver las lineas de cada solicitud interna.",
        "sql": (
            "SELECT\n"
            "  p.EJERCICIO,\n"
            "  p.NUM_PED,\n"
            "  p.FECH_EMI,\n"
            "  p.PED_ESTADO,\n"
            "  p.COSTO_TOT,\n"
            "  pi.ORDEN        AS item_nro,\n"
            "  pi.DESCRIP_BIE  AS descripcion,\n"
            "  pi.CANTIDAD,\n"
            "  pi.COSTO_UNI\n"
            "FROM {schema}PEDIDOS  p\n"
            "JOIN {schema}PED_ITEMS pi ON  pi.EJERCICIO = p.EJERCICIO\n"
            "                         AND pi.NUM_PED   = p.NUM_PED\n"
            "ORDER BY p.EJERCICIO DESC, p.NUM_PED DESC, pi.ORDEN\n"
            "{limit}"
        ),
    },
    {
        "title": "Flujo completo: Pedido → Solicitud de gasto → OC → OP",
        "desc": (
            "Recorre el ciclo de compra completo desde el pedido original "
            "hasta el pago efectivo. Util para auditar una compra de punta a punta."
        ),
        "sql": (
            "SELECT\n"
            "  p.EJERCICIO,\n"
            "  p.NUM_PED,\n"
            "  p.FECH_EMI          AS fecha_pedido,\n"
            "  p.PED_ESTADO        AS estado_pedido,\n"
            "  sg.NRO_SOLIC,\n"
            "  sg.FECH_SOLIC       AS fecha_solic,\n"
            "  sg.ESTADO_SOLIC,\n"
            "  sg.IMPORTE_TOT      AS importe_sg,\n"
            "  oc.NRO_OC,\n"
            "  oc.FECH_OC          AS fecha_oc,\n"
            "  oc.ESTADO_OC,\n"
            "  oc.IMPORTE_TOT      AS importe_oc,\n"
            "  oc.COD_PROV         AS prov_oc,\n"
            "  op.NRO_OP,\n"
            "  op.FECH_OP          AS fecha_pago,\n"
            "  op.ESTADO_OP,\n"
            "  op.IMPORTE_TOTAL    AS importe_pago,\n"
            "  op.COD_PROV         AS prov_op\n"
            "FROM      {schema}PEDIDOS      p\n"
            "JOIN      {schema}SOLIC_GASTOS sg ON  sg.EJERCICIO = p.EJERCICIO\n"
            "                                  AND sg.NRO_PED   = p.NUM_PED\n"
            "LEFT JOIN {schema}ORDEN_COMPRA oc ON  oc.EJERCICIO = sg.EJERCICIO\n"
            "LEFT JOIN {schema}ORDEN_PAGO   op ON  op.EJERCICIO       = sg.EJERCICIO\n"
            "                                  AND op.SG_DELEG_SOLIC  = sg.DELEG_SOLIC\n"
            "                                  AND op.SG_NRO_SOLIC    = sg.NRO_SOLIC\n"
            "ORDER BY p.EJERCICIO DESC, p.NUM_PED, sg.NRO_SOLIC\n"
            "{limit}"
        ),
    },
    {
        "title": "OC con todos sus items y proveedor",
        "desc": "Detalle de lineas de cada Orden de Compra junto con razon social del proveedor.",
        "sql": (
            "SELECT\n"
            "  oc.EJERCICIO,\n"
            "  oc.UNI_COMPRA,\n"
            "  oc.NRO_OC,\n"
            "  oc.FECH_OC,\n"
            "  oc.ESTADO_OC,\n"
            "  oc.IMPORTE_TOT,\n"
            "  pr.RAZON_SOCIAL,\n"
            "  oi.ITEM_OC,\n"
            "  oi.DESCRIPCION,\n"
            "  oi.CANTIDAD,\n"
            "  oi.IMP_UNITARIO\n"
            "FROM {schema}ORDEN_COMPRA oc\n"
            "JOIN {schema}PROVEEDORES  pr ON pr.COD_PROV   = oc.COD_PROV\n"
            "JOIN {schema}OC_ITEMS     oi ON  oi.EJERCICIO  = oc.EJERCICIO\n"
            "                             AND oi.UNI_COMPRA = oc.UNI_COMPRA\n"
            "                             AND oi.NRO_OC     = oc.NRO_OC\n"
            "ORDER BY oc.EJERCICIO DESC, oc.NRO_OC, oi.ITEM_OC\n"
            "{limit}"
        ),
    },
    {
        "title": "Ordenes de pago por proveedor",
        "desc": "Resumen de pagos agrupados por proveedor y estado.",
        "sql": (
            "SELECT\n"
            "  pr.COD_PROV,\n"
            "  pr.RAZON_SOCIAL,\n"
            "  op.ESTADO_OP,\n"
            "  COUNT(*)                    AS cant_op,\n"
            "  SUM(op.IMPORTE_TOTAL)       AS total_pagado\n"
            "FROM {schema}ORDEN_PAGO  op\n"
            "JOIN {schema}PROVEEDORES pr ON pr.COD_PROV = op.COD_PROV\n"
            "GROUP BY pr.COD_PROV, pr.RAZON_SOCIAL, op.ESTADO_OP\n"
            "ORDER BY total_pagado DESC\n"
            "{limit}"
        ),
    },
]

_LIMIT_ORACLE = "FETCH FIRST {n} ROWS ONLY"
_LIMIT_SQLITE = "LIMIT {n}"


def _render_query(sql_template: str, schema_prefix: str, backend: str, limit: int = 10) -> str:
    limit_clause = (
        (_LIMIT_ORACLE if backend == "oracle" else _LIMIT_SQLITE).format(n=limit)
    )
    return sql_template.format(schema=schema_prefix, limit=limit_clause)


def _build_flow_queries_section(backend: str, schema_prefix: str) -> list[str]:
    lines: list[str] = [
        "## 9. Flujo de negocio — queries de ejemplo",
        "",
        "> Queries que recorren el ciclo de compra completo.",
        "> Compatible con Oracle y SQLite (sustituir prefijo de schema segun entorno).",
        "",
    ]
    for q in _FLOW_QUERIES:
        sql = _render_query(q["sql"], schema_prefix, backend, limit=10)
        lines += [
            f"### {q['title']}",
            "",
            q["desc"],
            "",
            "```sql",
            sql,
            "```",
            "",
        ]

    lines += ["---", ""]
    return lines


# ─── Provider consistency analysis ───────────────────────────────────────────

_PROVIDER_CONSISTENCY_QUERIES: list[dict[str, str]] = [
    {
        "title": "OC_ITEMS donde COD_PROV difiere de su ORDEN_COMPRA",
        "desc": (
            "Detecta items de OC cuyo proveedor registrado no coincide con "
            "el proveedor de la cabecera de la OC. Puede indicar datos inconsistentes."
        ),
        "sql": (
            "SELECT\n"
            "  oi.EJERCICIO,\n"
            "  oi.UNI_COMPRA,\n"
            "  oi.NRO_OC,\n"
            "  oi.ITEM_OC,\n"
            "  oi.COD_PROV       AS prov_item,\n"
            "  oc.COD_PROV       AS prov_oc,\n"
            "  oi.DESCRIPCION\n"
            "FROM {schema}OC_ITEMS     oi\n"
            "JOIN {schema}ORDEN_COMPRA oc ON  oc.EJERCICIO  = oi.EJERCICIO\n"
            "                             AND oc.UNI_COMPRA = oi.UNI_COMPRA\n"
            "                             AND oc.NRO_OC     = oi.NRO_OC\n"
            "WHERE oi.COD_PROV != oc.COD_PROV\n"
            "ORDER BY oi.EJERCICIO DESC, oi.NRO_OC\n"
            "{limit}"
        ),
    },
    {
        "title": "ORDEN_PAGO donde COD_PROV difiere de la ORDEN_COMPRA asociada",
        "desc": (
            "Detecta ordenes de pago cuyo proveedor no coincide con el proveedor "
            "de la OC referenciada (RECO_DEU_COMPRA). Puede indicar reasignaciones o errores de carga."
        ),
        "sql": (
            "SELECT\n"
            "  op.EJERCICIO,\n"
            "  op.NRO_OP,\n"
            "  op.COD_PROV             AS prov_op,\n"
            "  op.RECO_DEU_COMPRA      AS nro_oc_ref,\n"
            "  op.RECO_DEU_COMPRA_EJER AS ejer_oc_ref,\n"
            "  oc.COD_PROV             AS prov_oc,\n"
            "  oc.IMPORTE_TOT          AS importe_oc,\n"
            "  op.IMPORTE_TOTAL        AS importe_pago\n"
            "FROM {schema}ORDEN_PAGO   op\n"
            "JOIN {schema}ORDEN_COMPRA oc ON  oc.EJERCICIO = op.RECO_DEU_COMPRA_EJER\n"
            "                             AND oc.NRO_OC    = op.RECO_DEU_COMPRA\n"
            "WHERE op.COD_PROV != oc.COD_PROV\n"
            "ORDER BY op.EJERCICIO DESC, op.NRO_OP\n"
            "{limit}"
        ),
    },
    {
        "title": "Proveedores referenciados en OC pero ausentes en PROVEEDORES",
        "desc": (
            "Detecta COD_PROV usados en ORDEN_COMPRA que no tienen registro "
            "en la tabla maestra PROVEEDORES. Indica posibles datos huerfanos."
        ),
        "sql": (
            "SELECT DISTINCT\n"
            "  oc.COD_PROV,\n"
            "  COUNT(*) AS cant_oc\n"
            "FROM {schema}ORDEN_COMPRA oc\n"
            "WHERE NOT EXISTS (\n"
            "  SELECT 1 FROM {schema}PROVEEDORES pr WHERE pr.COD_PROV = oc.COD_PROV\n"
            ")\n"
            "GROUP BY oc.COD_PROV\n"
            "ORDER BY cant_oc DESC\n"
            "{limit}"
        ),
    },
    {
        "title": "Proveedores referenciados en ORDEN_PAGO pero ausentes en PROVEEDORES",
        "desc": "Mismo analisis para ORDEN_PAGO.COD_PROV.",
        "sql": (
            "SELECT DISTINCT\n"
            "  op.COD_PROV,\n"
            "  COUNT(*) AS cant_op\n"
            "FROM {schema}ORDEN_PAGO op\n"
            "WHERE NOT EXISTS (\n"
            "  SELECT 1 FROM {schema}PROVEEDORES pr WHERE pr.COD_PROV = op.COD_PROV\n"
            ")\n"
            "GROUP BY op.COD_PROV\n"
            "ORDER BY cant_op DESC\n"
            "{limit}"
        ),
    },
]


def _build_provider_analysis_section(backend: str, schema_prefix: str) -> list[str]:
    lines: list[str] = [
        "## 10. Analisis de consistencia del proveedor",
        "",
        "> Detecta divergencias de COD_PROV entre tablas relacionadas.",
        "> Ejecutar contra Oracle o SQLite con datos reales para obtener resultados.",
        "",
    ]
    for q in _PROVIDER_CONSISTENCY_QUERIES:
        sql = _render_query(q["sql"], schema_prefix, backend, limit=20)
        lines += [
            f"### {q['title']}",
            "",
            q["desc"],
            "",
            "```sql",
            sql,
            "```",
            "",
        ]
    lines += ["---", ""]
    return lines


# ─── Real sample data ─────────────────────────────────────────────────────────

_SAMPLE_QUERIES: list[dict[str, str]] = [
    {
        "title": "Muestra de PROVEEDORES",
        "sql": "SELECT * FROM {schema}PROVEEDORES ORDER BY COD_PROV {limit}",
        "cols": ["COD_PROV", "RAZON_SOCIAL", "CUIT", "COD_IVA", "COD_ESTADO", "FECHA_ALTA"],
    },
    {
        "title": "Muestra de PEDIDOS recientes",
        "sql": "SELECT * FROM {schema}PEDIDOS ORDER BY EJERCICIO DESC, NUM_PED DESC {limit}",
        "cols": ["EJERCICIO", "NUM_PED", "FECH_EMI", "JURISDICCION", "COSTO_TOT", "PED_ESTADO"],
    },
    {
        "title": "Muestra de ORDEN_COMPRA recientes",
        "sql": "SELECT * FROM {schema}ORDEN_COMPRA ORDER BY EJERCICIO DESC, NRO_OC DESC {limit}",
        "cols": ["EJERCICIO", "UNI_COMPRA", "NRO_OC", "FECH_OC", "COD_PROV", "ESTADO_OC", "IMPORTE_TOT"],
    },
    {
        "title": "Muestra de ORDEN_PAGO recientes",
        "sql": "SELECT * FROM {schema}ORDEN_PAGO ORDER BY EJERCICIO DESC, NRO_OP DESC {limit}",
        "cols": ["EJERCICIO", "NRO_OP", "FECH_OP", "COD_PROV", "ESTADO_OP", "IMPORTE_TOTAL", "IMPORTE_LIQUIDO"],
    },
    {
        "title": "Muestra de SOLIC_GASTOS recientes",
        "sql": "SELECT * FROM {schema}SOLIC_GASTOS ORDER BY EJERCICIO DESC, NRO_SOLIC DESC {limit}",
        "cols": ["EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC", "NRO_PED", "FECH_SOLIC", "ESTADO_SOLIC", "IMPORTE_TOT"],
    },
]


def _run_sample_query(
    conn: Any,
    sql_template: str,
    cols: list[str],
    schema_prefix: str,
    backend: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Execute a sample query and return rows as dicts (only specified cols)."""
    from sqlalchemy import text as sa_text

    col_list = ", ".join(cols)
    sql = sql_template.replace("SELECT *", f"SELECT {col_list}")

    if backend == "oracle":
        # Use ROWNUM subquery for Oracle pre-12c compatibility
        # (FETCH FIRST requires Oracle 12c+)
        inner = sql.replace("{limit}", "").format(schema=schema_prefix).rstrip()
        rendered = f"SELECT * FROM ({inner}) WHERE ROWNUM <= {limit}"
    else:
        rendered = _render_query(sql, schema_prefix, backend, limit=limit)

    try:
        result = conn.execute(sa_text(rendered))
        keys = list(result.keys())
        return [dict(zip(keys, row)) for row in result.fetchall()]
    except Exception as exc:
        return [{"error": str(exc)}]


def _rows_to_markdown_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["*(sin resultados)*", ""]
    if "error" in rows[0]:
        return [f"> **Error al ejecutar:** `{rows[0]['error']}`", ""]

    headers = list(rows[0].keys())
    sep = "|".join("---" for _ in headers)
    head = "|".join(headers)
    lines = [f"| {head} |", f"| {sep} |"]
    for row in rows:
        cells = " | ".join(str(v) if v is not None else "" for v in row.values())
        lines.append(f"| {cells} |")
    lines.append("")
    return lines


def _build_sample_data_section(
    engine: Any,
    backend: str,
    schema_prefix: str,
) -> list[str]:
    lines: list[str] = [
        "## 11. Datos reales de muestra",
        "",
        "> Primeras filas de cada tabla clave (hasta 8 registros).",
        "> Util para validar el comportamiento del sistema y confirmar mappings.",
        "",
    ]

    with engine.connect() as conn:
        for q in _SAMPLE_QUERIES:
            lines.append(f"### {q['title']}")
            lines.append("")
            rows = _run_sample_query(conn, q["sql"], q["cols"], schema_prefix, backend)
            lines.extend(_rows_to_markdown_table(rows))

    lines += ["---", ""]
    return lines

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenera docs/field_mapping.md desde el esquema real de la DB"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Imprimir en stdout en vez de escribir docs/field_mapping.md",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="Ruta al SQLite (sobreescribe SQLITE_DB_PATH). Solo para DB_BACKEND=sqlite.",
    )
    parser.add_argument(
        "--no-samples",
        action="store_true",
        help="Omitir la seccion 11 (datos reales de muestra). Util para correr rapido.",
    )
    args = parser.parse_args()

    if args.db:
        os.environ["SQLITE_DB_PATH"] = str(Path(args.db).resolve())

    backend = os.getenv("DB_BACKEND", "sqlite").lower()
    db_path = os.getenv("SQLITE_DB_PATH") if backend == "sqlite" else None
    print(f"[INFO] Leyendo esquema desde {backend.upper()}...")

    engine = _create_engine(backend, db_path)
    inspector = sa_inspect(engine)

    available = _available_tables(inspector, backend, engine=engine)
    all_tables = {t for sec in SECTIONS for t in sec["tables"]}
    missing = all_tables - available

    if missing:
        print(f"[WARN] Tablas no encontradas: {', '.join(sorted(missing))}", file=sys.stderr)
        if backend == "sqlite":
            print(
                "   -> Ejecutar primero: python scripts/load_csv_to_sqlite.py",
                file=sys.stderr,
            )

    all_columns: dict[str, list[dict[str, str]]] = {}
    for table in sorted(all_tables):
        if table in available:
            cols = _get_columns(inspector, table, backend)
            all_columns[table] = cols
            print(f"  [OK] {table}: {len(cols)} columnas")
        else:
            all_columns[table] = []

    include_samples = not args.no_samples
    md = _build_markdown(all_columns, backend, engine=engine, include_samples=include_samples)

    if args.dry_run:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        print("\n" + "-" * 60 + "\n")
        print(md)
    else:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_MD.write_text(md, encoding="utf-8")
        print(f"[OK] Escrito -> {OUTPUT_MD}")


if __name__ == "__main__":
    main()
