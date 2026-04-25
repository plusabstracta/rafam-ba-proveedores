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


def _available_tables(inspector: Any, backend: str) -> set[str]:
    """Return uppercase table names visible to the current connection."""
    try:
        schema = SCHEMA if backend == "oracle" else None
        return {t.upper() for t in inspector.get_table_names(schema=schema)}
    except Exception as exc:
        print(f"[ERROR] No se pudo listar tablas: {exc}", file=sys.stderr)
        sys.exit(1)


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


def _build_markdown(all_columns: dict[str, list[dict[str, str]]], backend: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_label = (
        f"Oracle `{SCHEMA}`" if backend == "oracle"
        else "SQLite dev (snapshots CSV)"
    )

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
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

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
    args = parser.parse_args()

    if args.db:
        os.environ["SQLITE_DB_PATH"] = str(Path(args.db).resolve())

    backend = os.getenv("DB_BACKEND", "sqlite").lower()
    db_path = os.getenv("SQLITE_DB_PATH") if backend == "sqlite" else None
    print(f"[INFO] Leyendo esquema desde {backend.upper()}...")

    engine = _create_engine(backend, db_path)
    inspector = sa_inspect(engine)

    available = _available_tables(inspector, backend)
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

    md = _build_markdown(all_columns, backend)

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
