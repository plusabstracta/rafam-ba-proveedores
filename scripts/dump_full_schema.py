"""
dump_full_schema.py — Dump COMPLETO del esquema RAFAM configurado en .env.

A diferencia de explore_schema.py / generate_rafam_context.py (que filtran
por tablas relevantes), este script extrae **toda** la base disponible en el
backend configurado por RAFAM_SOURCE_BACKEND:

    - Todas las tablas
    - Todas las vistas disponibles
    - Todas las columnas
    - Todas las PKs y FKs
    - Todos los indices
    - Conteo de filas por tabla (opcional, exacto y puede tardar)

Sale en dos formatos:
    - output/rafam_context/full_schema.json   (machine-readable, para usar
      en otros scripts del proyecto)
    - output/rafam_context/full_schema.md     (human-readable, para commitear
      y revisar en PRs)

Uso:
    python scripts/dump_full_schema.py
    python scripts/dump_full_schema.py --schema OWNER_RAFAM --out-dir output/rafam_context
    python scripts/dump_full_schema.py --row-counts

Variables de entorno:
    RAFAM_SOURCE_BACKEND=oracle|sqlite
    RAFAM_SOURCE_* segun el backend elegido (ver README.md)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "output" / "rafam_context"

load_dotenv(REPO_ROOT / ".env")

sys.path.insert(0, str(REPO_ROOT))

from src.db import create_source_engine  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="OWNER_RAFAM", help="Owner del schema a dumpear")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directorio de salida (default: output/rafam_context)",
    )
    parser.add_argument(
        "--no-views",
        action="store_true",
        help="No incluir vistas (ALL_VIEWS) — acelera el dump si no las necesitas",
    )
    parser.add_argument(
        "--no-indexes",
        action="store_true",
        help="No incluir indices",
    )
    parser.add_argument(
        "--row-counts",
        action="store_true",
        help="Contar filas exactas con SELECT COUNT(*) por tabla (puede tardar mucho)",
    )
    return parser.parse_args()


# ─── Introspeccion de schema ────────────────────────────────────────────────

def _effective_schema(engine: Engine, requested_schema: str) -> str | None:
    if engine.dialect.name == "sqlite":
        return None
    return requested_schema.upper()


def _qualified_name(engine: Engine, table_name: str, schema: str | None) -> str:
    preparer = engine.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    if schema:
        return f"{preparer.quote_schema(schema)}.{quoted_table}"
    return quoted_table


def _safe_inspect_call(default: Any, callback):
    try:
        return callback()
    except SQLAlchemyError as exc:
        print(f"[warn] introspeccion parcial: {exc}", file=sys.stderr)
        return default


def _fetch_oracle_table_metadata(engine: Engine, schema: str | None) -> dict[str, dict[str, Any]]:
    if engine.dialect.name != "oracle" or not schema:
        return {}

    query = text(
        """
        SELECT TABLE_NAME, NUM_ROWS, LAST_ANALYZED, TABLESPACE_NAME
        FROM ALL_TABLES
        WHERE OWNER = :owner
        """,
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"owner": schema}).mappings().all()

    return {
        str(row["table_name" if "table_name" in row else "TABLE_NAME"]): {
            "num_rows": int(row["num_rows" if "num_rows" in row else "NUM_ROWS"])
            if row["num_rows" if "num_rows" in row else "NUM_ROWS"] is not None
            else None,
            "last_analyzed": row[
                "last_analyzed" if "last_analyzed" in row else "LAST_ANALYZED"
            ].isoformat()
            if row["last_analyzed" if "last_analyzed" in row else "LAST_ANALYZED"]
            else None,
            "tablespace": row["tablespace_name" if "tablespace_name" in row else "TABLESPACE_NAME"],
        }
        for row in rows
    }


def _fetch_exact_row_count(engine: Engine, table_name: str, schema: str | None) -> int | None:
    qualified_name = _qualified_name(engine, table_name, schema)
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(f"SELECT COUNT(*) FROM {qualified_name}")).scalar_one())
    except SQLAlchemyError as exc:
        print(f"[warn] no se pudo contar {qualified_name}: {exc}", file=sys.stderr)
        return None


def fetch_tables(engine: Engine, schema: str | None, include_row_counts: bool) -> list[dict[str, Any]]:
    inspector = sa_inspect(engine)
    table_names = _safe_inspect_call([], lambda: inspector.get_table_names(schema=schema))
    oracle_metadata = _fetch_oracle_table_metadata(engine, schema)
    tables: list[dict[str, Any]] = []

    for table_name in sorted(table_names):
        metadata = oracle_metadata.get(table_name, {})
        table = {
            "name": table_name,
            "num_rows": metadata.get("num_rows"),
            "row_count_source": "oracle_statistics" if metadata.get("num_rows") is not None else None,
            "last_analyzed": metadata.get("last_analyzed"),
            "tablespace": metadata.get("tablespace"),
        }
        if include_row_counts:
            table["num_rows"] = _fetch_exact_row_count(engine, table_name, schema)
            table["row_count_source"] = "exact_count"
        tables.append(table)

    return tables


def fetch_views(engine: Engine, schema: str | None) -> list[dict[str, Any]]:
    inspector = sa_inspect(engine)
    view_names = _safe_inspect_call([], lambda: inspector.get_view_names(schema=schema))
    views: list[dict[str, Any]] = []

    for view_name in sorted(view_names):
        definition = _safe_inspect_call(
            "",
            lambda view_name=view_name: inspector.get_view_definition(view_name, schema=schema) or "",
        )
        views.append({"name": view_name, "text_length": len(definition), "text": definition})

    return views


def fetch_columns(engine: Engine, tables: list[dict[str, Any]], schema: str | None) -> dict[str, list[dict]]:
    inspector = sa_inspect(engine)
    columns: dict[str, list[dict]] = {}

    for table in tables:
        table_name = table["name"]
        raw_columns = _safe_inspect_call(
            [],
            lambda table_name=table_name: inspector.get_columns(table_name, schema=schema),
        )
        columns[table_name] = [
            {
                "name": column["name"],
                "type": str(column.get("type", "")),
                "nullable": bool(column.get("nullable", True)),
                "position": position,
                "default": str(column.get("default") or "").strip() or None,
            }
            for position, column in enumerate(raw_columns, start=1)
        ]

    return columns


def fetch_constraints(
    engine: Engine,
    tables: list[dict[str, Any]],
    schema: str | None,
) -> tuple[dict[str, list[str]], dict[str, list[dict[str, Any]]]]:
    inspector = sa_inspect(engine)
    primary_keys: dict[str, list[str]] = {}
    foreign_keys: dict[str, list[dict[str, Any]]] = {}

    for table in tables:
        table_name = table["name"]
        pk = _safe_inspect_call(
            {},
            lambda table_name=table_name: inspector.get_pk_constraint(table_name, schema=schema),
        )
        primary_keys[table_name] = list(pk.get("constrained_columns") or [])

        raw_fks = _safe_inspect_call(
            [],
            lambda table_name=table_name: inspector.get_foreign_keys(table_name, schema=schema),
        )
        foreign_keys[table_name] = [
            {
                "constraint": fk.get("name") or "",
                "ref_owner": fk.get("referred_schema") or schema or "",
                "ref_table": fk.get("referred_table") or "",
                "columns": list(fk.get("constrained_columns") or []),
                "ref_columns": list(fk.get("referred_columns") or []),
            }
            for fk in raw_fks
        ]

    return primary_keys, foreign_keys


def fetch_indexes(
    engine: Engine,
    tables: list[dict[str, Any]],
    schema: str | None,
) -> dict[str, list[dict[str, Any]]]:
    inspector = sa_inspect(engine)
    indexes: dict[str, list[dict[str, Any]]] = {}

    for table in tables:
        table_name = table["name"]
        raw_indexes = _safe_inspect_call(
            [],
            lambda table_name=table_name: inspector.get_indexes(table_name, schema=schema),
        )
        indexes[table_name] = [
            {
                "name": index.get("name") or "",
                "unique": bool(index.get("unique")),
                "columns": list(index.get("column_names") or []),
            }
            for index in raw_indexes
        ]

    return indexes


# ─── Renderers ───────────────────────────────────────────────────────────────

def write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[json] {path} ({path.stat().st_size:,} bytes)")


def write_markdown(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = data["schema"]
    backend = data["backend"]
    tables = data["tables"]
    views = data.get("views", [])
    columns = data["columns"]
    pks = data["primary_keys"]
    fks = data["foreign_keys"]
    indexes = data.get("indexes", {})

    lines: list[str] = []
    lines.append(f"# Esquema completo RAFAM — `{schema}`")
    lines.append("")
    lines.append(f"> Generado por `scripts/dump_full_schema.py` el {data['generated_at']}")
    lines.append(f"> Backend: `{backend}`")
    lines.append(f"> **No editar manualmente** — regenerar ejecutando el script.")
    lines.append("")
    lines.append(f"- Tablas: **{len(tables)}**")
    lines.append(f"- Vistas: **{len(views)}**")
    lines.append("")

    lines.append("## Indice de tablas")
    lines.append("")
    for t in tables:
        lines.append(f"- [{t['name']}](#{t['name'].lower()})")
    lines.append("")

    if views:
        lines.append("## Indice de vistas")
        lines.append("")
        for v in views:
            lines.append(f"- [{v['name']}](#view-{v['name'].lower()})")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Tablas
    for t in tables:
        name = t["name"]
        lines.append(f"## {name}")
        lines.append("")
        meta = []
        if t.get("num_rows") is not None:
            label = "exacto" if t.get("row_count_source") == "exact_count" else "estimado"
            meta.append(f"**Rows ({label}):** {t['num_rows']:,}")
        if t.get("tablespace"):
            meta.append(f"**Tablespace:** `{t['tablespace']}`")
        if t.get("last_analyzed"):
            meta.append(f"**Ultimo analisis:** `{t['last_analyzed']}`")
        if meta:
            lines.append("  ".join(meta))
            lines.append("")

        pk_cols = pks.get(name, [])
        if pk_cols:
            lines.append(f"**PK:** `{'`, `'.join(pk_cols)}`")
        else:
            lines.append("**PK:** *(no encontrada)*")
        lines.append("")

        fk_list = fks.get(name, [])
        if fk_list:
            lines.append("**FKs:**")
            lines.append("")
            for fk in fk_list:
                cols = ", ".join(f"`{c}`" for c in fk["columns"])
                ref_cols = ", ".join(f"`{c}`" for c in fk["ref_columns"])
                lines.append(
                    f"- ({cols}) → `{fk['ref_owner']}.{fk['ref_table']}` ({ref_cols})"
                )
            lines.append("")

        cols = columns.get(name, [])
        if cols:
            lines.append("| Columna | Tipo | Nulo | Default |")
            lines.append("|---------|------|------|---------|")
            for c in cols:
                nullable = "✓" if c["nullable"] else "✗"
                default = c.get("default") or ""
                # Escapar pipes en default
                default = str(default).replace("|", "\\|")
                lines.append(
                    f"| `{c['name']}` | `{c['type']}` | {nullable} | {default} |"
                )
            lines.append("")

        idx_list = indexes.get(name, [])
        if idx_list:
            lines.append("**Indices:**")
            lines.append("")
            for idx in idx_list:
                u = " (UNIQUE)" if idx["unique"] else ""
                cols_str = ", ".join(idx["columns"])
                lines.append(f"- `{idx['name']}`{u}: ({cols_str})")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Vistas
    if views:
        lines.append("# Vistas")
        lines.append("")
        for v in views:
            lines.append(f"## VIEW {v['name']} <a id=\"view-{v['name'].lower()}\"></a>")
            lines.append("")
            lines.append("```sql")
            lines.append(v["text"].rstrip())
            lines.append("```")
            lines.append("")
            lines.append("---")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[md]   {path} ({path.stat().st_size:,} bytes)")


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    out_dir: Path = args.out_dir
    requested_schema: str = args.schema.upper()
    engine = create_source_engine()
    schema = _effective_schema(engine, requested_schema)
    display_schema = schema or "default"
    backend = engine.dialect.name

    print(f"[conn] backend={backend} schema={display_schema}")
    print("[fetch] tables...")
    tables = fetch_tables(engine, schema, args.row_counts)
    print(f"        {len(tables)} tablas")

    print("[fetch] columns...")
    columns = fetch_columns(engine, tables, schema)
    print(f"        {sum(len(v) for v in columns.values())} columnas en {len(columns)} tablas")

    print("[fetch] constraints (PK/FK)...")
    pks, fks = fetch_constraints(engine, tables, schema)
    print(f"        {len(pks)} PKs, {sum(len(v) for v in fks.values())} FKs")

    indexes: dict = {}
    if not args.no_indexes:
        print("[fetch] indexes...")
        indexes = fetch_indexes(engine, tables, schema)
        print(f"        {sum(len(v) for v in indexes.values())} indices en {len(indexes)} tablas")

    views: list[dict] = []
    if not args.no_views:
        print("[fetch] views (puede tardar)...")
        views = fetch_views(engine, schema)
        print(f"        {len(views)} vistas")

    data = {
        "schema": display_schema,
        "backend": backend,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "tables": tables,
        "views": views,
        "columns": columns,
        "primary_keys": pks,
        "foreign_keys": fks,
        "indexes": indexes,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(data, out_dir / "full_schema.json")
    write_markdown(data, out_dir / "full_schema.md")

    print("\n[done] subir a git:")
    print(f"  - {out_dir / 'full_schema.json'}")
    print(f"  - {out_dir / 'full_schema.md'}")


if __name__ == "__main__":
    main()
