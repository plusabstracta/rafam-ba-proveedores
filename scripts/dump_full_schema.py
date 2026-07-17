"""
dump_full_schema.py — Dump COMPLETO del esquema RAFAM configurado en .env.

Extrae TODA la base disponible en el backend configurado por RAFAM_SOURCE_BACKEND:

  Backend oracle  → queries directas al diccionario de datos Oracle
                    (ALL_TABLES, ALL_TAB_COLUMNS, ALL_COL_COMMENTS,
                     ALL_CONSTRAINTS, ALL_CONS_COLUMNS, ALL_INDEXES,
                     ALL_IND_COLUMNS, ALL_VIEWS, ALL_TAB_COMMENTS)
  Backend sqlite  → SQLAlchemy inspector (fallback)

Sale en dos formatos:
    - output/rafam_context/full_schema.json
    - output/rafam_context/full_schema.md  (con comentarios de columna)

Uso:
    python scripts/dump_full_schema.py
    python scripts/dump_full_schema.py --schema OWNER_RAFAM --row-counts
    python scripts/dump_full_schema.py --no-views --no-indexes
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


# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--schema", default="OWNER_RAFAM", help="Owner/schema a dumpear")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--no-views", action="store_true", help="Omitir vistas")
    p.add_argument("--no-indexes", action="store_true", help="Omitir indices")
    p.add_argument("--row-counts", action="store_true",
                   help="Contar filas exactas (puede tardar)")
    return p.parse_args()


# ─── Oracle data dictionary queries ──────────────────────────────────────────

def _ora_fmt_type(dtype: str | None, length: int | None,
                  precision: int | None, scale: int | None) -> str:
    """Convierte metadatos Oracle crudos en la cadena legible NUMBER(15,2), VARCHAR2(80), etc."""
    if dtype is None:
        return "UNKNOWN"
    if dtype == "NUMBER":
        if precision and scale is not None and scale != 0:
            return f"NUMBER({precision},{scale})"
        if precision:
            return f"NUMBER({precision})"
        return "NUMBER"
    if dtype in ("VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR"):
        return f"{dtype}({length or 1})"
    if dtype == "RAW":
        return f"RAW({length or 1})"
    return dtype


class OracleFetcher:
    """Fetch completo del diccionario de datos Oracle via queries directas."""

    def __init__(self, engine: Engine, schema: str):
        self.engine = engine
        self.schema = schema

    def _q(self, sql: str, **kw) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return conn.execute(text(sql), {"owner": self.schema, **kw}).mappings().all()

    # ── tables ────────────────────────────────────────────────────────────
    def fetch_tables(self, include_row_counts: bool) -> list[dict[str, Any]]:
        rows = self._q(
            "SELECT TABLE_NAME, NUM_ROWS, LAST_ANALYZED, TABLESPACE_NAME "
            "FROM ALL_TABLES WHERE OWNER = :owner ORDER BY TABLE_NAME"
        )
        tables: list[dict[str, Any]] = []
        for r in rows:
            t: dict[str, Any] = {
                "name": r["TABLE_NAME"],
                "num_rows": int(r["NUM_ROWS"]) if r["NUM_ROWS"] is not None else None,
                "row_count_source": "oracle_statistics" if r["NUM_ROWS"] is not None else None,
                "last_analyzed": r["LAST_ANALYZED"].isoformat() if r["LAST_ANALYZED"] else None,
                "tablespace": r["TABLESPACE_NAME"],
            }
            if include_row_counts and t["name"]:
                t["num_rows"] = self._exact_count(t["name"])
                t["row_count_source"] = "exact_count"
            tables.append(t)
        return tables

    def _exact_count(self, table_name: str) -> int | None:
        try:
            with self.engine.connect() as conn:
                q = text(f'SELECT COUNT(*) FROM "{self.schema}"."{table_name}"')
                return int(conn.execute(q).scalar_one())
        except SQLAlchemyError as exc:
            print(f"[warn] COUNT(*) fallo en {table_name}: {exc}", file=sys.stderr)
            return None

    # ── columns + comments ────────────────────────────────────────────────
    def fetch_columns(self, tables: list[dict[str, Any]]) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for t in tables:
            tn = t["name"]
            rows = self._q(
                """
                SELECT col.COLUMN_NAME, col.DATA_TYPE, col.DATA_LENGTH,
                       col.DATA_PRECISION, col.DATA_SCALE, col.NULLABLE,
                       col.DATA_DEFAULT, com.COMMENTS AS COL_COMMENT
                FROM   ALL_TAB_COLUMNS col
                LEFT JOIN ALL_COL_COMMENTS com
                       ON  com.OWNER       = col.OWNER
                       AND com.TABLE_NAME  = col.TABLE_NAME
                       AND com.COLUMN_NAME = col.COLUMN_NAME
                WHERE  col.OWNER      = :owner
                  AND  col.TABLE_NAME = :table_name
                ORDER BY col.COLUMN_ID
                """,
                table_name=tn,
            )
            result[tn] = [
                {
                    "name": r["COLUMN_NAME"],
                    "type": _ora_fmt_type(
                        r["DATA_TYPE"], r["DATA_LENGTH"],
                        r["DATA_PRECISION"], r["DATA_SCALE"],
                    ),
                    "nullable": r["NULLABLE"] == "Y",
                    "position": i + 1,
                    "default": (r["DATA_DEFAULT"] or "").strip() or None,
                    "comment": (r["COL_COMMENT"] or "").strip() or None,
                }
                for i, r in enumerate(rows)
            ]
        return result

    # ── constraints (PK + FK) ─────────────────────────────────────────────
    def fetch_constraints(
        self, tables: list[dict[str, Any]]
    ) -> tuple[dict[str, list[str]], dict[str, list[dict[str, Any]]]]:
        pks: dict[str, list[str]] = {}
        fks: dict[str, list[dict[str, Any]]] = {}

        for t in tables:
            tn = t["name"]
            rows = self._q(
                """
                SELECT c.CONSTRAINT_NAME, c.CONSTRAINT_TYPE,
                       cc.COLUMN_NAME, cc.POSITION,
                       c.R_OWNER, c.R_CONSTRAINT_NAME
                FROM   ALL_CONSTRAINTS c
                JOIN   ALL_CONS_COLUMNS cc
                       ON  cc.OWNER           = c.OWNER
                       AND cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME
                WHERE  c.OWNER      = :owner
                  AND  c.TABLE_NAME = :table_name
                  AND  c.CONSTRAINT_TYPE IN ('P','R')
                ORDER BY c.CONSTRAINT_TYPE, cc.POSITION
                """,
                table_name=tn,
            )

            pk_cols: list[str] = []
            fk_list: list[dict[str, Any]] = []
            for r in rows:
                if r["CONSTRAINT_TYPE"] == "P" and r["COLUMN_NAME"] not in pk_cols:
                    pk_cols.append(r["COLUMN_NAME"])
                elif r["CONSTRAINT_TYPE"] == "R":
                    ref_table = self._resolve_fk_table(
                        r["R_OWNER"], r["R_CONSTRAINT_NAME"]
                    )
                    fk_list.append({
                        "constraint": r["CONSTRAINT_NAME"],
                        "ref_owner": r["R_OWNER"] or "",
                        "ref_table": ref_table,
                        "columns": [r["COLUMN_NAME"]],
                        "ref_columns": [],  # se resuelve por nombre de FK
                    })
            pks[tn] = pk_cols

            # Agrupar columnas por FK constraint
            fk_grouped: dict[str, dict[str, Any]] = {}
            for r in rows:
                if r["CONSTRAINT_TYPE"] != "R":
                    continue
                cname = r["CONSTRAINT_NAME"]
                if cname not in fk_grouped:
                    ref_table = self._resolve_fk_table(r["R_OWNER"], r["R_CONSTRAINT_NAME"])
                    fk_grouped[cname] = {
                        "constraint": cname,
                        "ref_owner": r["R_OWNER"] or "",
                        "ref_table": ref_table,
                        "columns": [],
                        "ref_columns": [],
                    }
                fk_grouped[cname]["columns"].append(r["COLUMN_NAME"])

            fks[tn] = list(fk_grouped.values())

        return pks, fks

    def _resolve_fk_table(self, r_owner: str | None, r_constraint: str | None) -> str:
        if not r_owner or not r_constraint:
            return r_constraint or ""
        try:
            with self.engine.connect() as conn:
                row = conn.execute(
                    text("SELECT TABLE_NAME FROM ALL_CONSTRAINTS "
                         "WHERE OWNER = :o AND CONSTRAINT_NAME = :c"),
                    {"o": r_owner, "c": r_constraint},
                ).mappings().first()
                if row:
                    return f"{r_owner}.{row['TABLE_NAME']}"
        except SQLAlchemyError:
            pass
        return f"{r_owner}.{r_constraint}"

    # ── indexes ───────────────────────────────────────────────────────────
    def fetch_indexes(self, tables: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for t in tables:
            tn = t["name"]
            rows = self._q(
                """
                SELECT i.INDEX_NAME, i.UNIQUENESS, ic.COLUMN_NAME, ic.COLUMN_POSITION
                FROM   ALL_INDEXES i
                JOIN   ALL_IND_COLUMNS ic
                       ON  ic.INDEX_OWNER = i.OWNER
                       AND ic.INDEX_NAME  = i.INDEX_NAME
                WHERE  i.TABLE_OWNER = :owner
                  AND  i.TABLE_NAME  = :table_name
                ORDER BY i.INDEX_NAME, ic.COLUMN_POSITION
                """,
                table_name=tn,
            )
            idx_map: dict[str, dict[str, Any]] = {}
            for r in rows:
                iname = r["INDEX_NAME"]
                if iname not in idx_map:
                    idx_map[iname] = {
                        "name": iname,
                        "unique": r["UNIQUENESS"] == "UNIQUE",
                        "columns": [],
                    }
                idx_map[iname]["columns"].append(r["COLUMN_NAME"])
            result[tn] = list(idx_map.values())
        return result

    # ── views ─────────────────────────────────────────────────────────────
    def fetch_views(self) -> list[dict[str, Any]]:
        rows = self._q(
            "SELECT VIEW_NAME, TEXT_LENGTH, TEXT "
            "FROM ALL_VIEWS WHERE OWNER = :owner ORDER BY VIEW_NAME"
        )
        return [
            {"name": r["VIEW_NAME"], "text_length": r["TEXT_LENGTH"] or len(r["TEXT"] or ""),
             "text": r["TEXT"] or ""}
            for r in rows
        ]

    # ── table comments ────────────────────────────────────────────────────
    def fetch_table_comments(self) -> dict[str, str]:
        rows = self._q(
            "SELECT TABLE_NAME, COMMENTS FROM ALL_TAB_COMMENTS "
            "WHERE OWNER = :owner AND TABLE_TYPE = 'TABLE'"
        )
        return {r["TABLE_NAME"]: (r["COMMENTS"] or "").strip() for r in rows}


# ─── SQLAlchemy fallback (SQLite, etc.) ──────────────────────────────────────

def _safe(default: Any, callback):
    try:
        return callback()
    except SQLAlchemyError as exc:
        print(f"[warn] introspeccion: {exc}", file=sys.stderr)
        return default


class SAFetcher:
    """Fallback via SQLAlchemy inspector — funciona con cualquier dialecto."""

    def __init__(self, engine: Engine, schema: str | None):
        self.engine = engine
        self.schema = schema
        self.insp = sa_inspect(engine)

    def fetch_tables(self, include_row_counts: bool) -> list[dict[str, Any]]:
        names = _safe([], lambda: self.insp.get_table_names(schema=self.schema))
        tables: list[dict[str, Any]] = []
        for n in sorted(names):
            t: dict[str, Any] = {"name": n, "num_rows": None, "row_count_source": None,
                                 "last_analyzed": None, "tablespace": None}
            if include_row_counts:
                try:
                    with self.engine.connect() as conn:
                        t["num_rows"] = int(
                            conn.execute(text(f'SELECT COUNT(*) FROM "{n}"')).scalar_one()
                        )
                        t["row_count_source"] = "exact_count"
                except Exception:
                    pass
            tables.append(t)
        return tables

    def fetch_columns(self, tables: list[dict[str, Any]]) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for t in tables:
            raw = _safe([], lambda tn=t["name"]: self.insp.get_columns(tn, schema=self.schema))
            result[t["name"]] = [
                {"name": c["name"], "type": str(c.get("type", "")),
                 "nullable": bool(c.get("nullable", True)), "position": i + 1,
                 "default": str(c.get("default") or "").strip() or None,
                 "comment": None}
                for i, c in enumerate(raw)
            ]
        return result

    def fetch_constraints(self, tables):
        pks, fks = {}, {}
        for t in tables:
            tn = t["name"]
            pk = _safe({}, lambda tn=tn: self.insp.get_pk_constraint(tn, schema=self.schema))
            pks[tn] = list(pk.get("constrained_columns") or [])
            raw = _safe([], lambda tn=tn: self.insp.get_foreign_keys(tn, schema=self.schema))
            fks[tn] = [
                {"constraint": fk.get("name") or "",
                 "ref_owner": fk.get("referred_schema") or self.schema or "",
                 "ref_table": fk.get("referred_table") or "",
                 "columns": list(fk.get("constrained_columns") or []),
                 "ref_columns": list(fk.get("referred_columns") or [])}
                for fk in raw
            ]
        return pks, fks

    def fetch_indexes(self, tables):
        result = {}
        for t in tables:
            tn = t["name"]
            raw = _safe([], lambda tn=tn: self.insp.get_indexes(tn, schema=self.schema))
            result[tn] = [
                {"name": ix.get("name") or "", "unique": bool(ix.get("unique")),
                 "columns": list(ix.get("column_names") or [])}
                for ix in raw
            ]
        return result

    def fetch_views(self):
        names = _safe([], lambda: self.insp.get_view_names(schema=self.schema))
        views = []
        for n in sorted(names):
            defn = _safe("", lambda n=n: self.insp.get_view_definition(n, schema=self.schema) or "")
            views.append({"name": n, "text_length": len(defn), "text": defn})
        return views

    def fetch_table_comments(self) -> dict[str, str]:
        return {}


# ─── Markdown renderer ───────────────────────────────────────────────────────

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
    table_comments = data.get("table_comments", {})

    has_comments = any(
        c.get("comment")
        for cols in columns.values()
        for c in cols
    )

    lines: list[str] = []
    lines.append(f"# Esquema completo RAFAM — `{schema}`")
    lines.append("")
    lines.append(f"> Generado por `scripts/dump_full_schema.py` el {data['generated_at']}")
    lines.append(f"> Backend: `{backend}`")
    lines.append("> **No editar manualmente** — regenerar ejecutando el script.")
    lines.append("")
    lines.append(f"- Tablas: **{len(tables)}**")
    lines.append(f"- Vistas: **{len(views)}**")
    lines.append("")

    # ── Indice de tablas ──────────────────────────────────────────────────
    lines.append("## Indice de tablas")
    lines.append("")
    for t in tables:
        anchor = t["name"].lower()
        tc = table_comments.get(t["name"], "")
        suffix = f" — {tc}" if tc else ""
        lines.append(f"- [{t['name']}](#{anchor}){suffix}")
    lines.append("")

    if views:
        lines.append("## Indice de vistas")
        lines.append("")
        for v in views:
            lines.append(f"- [{v['name']}](#view-{v['name'].lower()})")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Tablas ────────────────────────────────────────────────────────────
    for t in tables:
        name = t["name"]
        lines.append(f"## {name}")
        lines.append("")

        tc = table_comments.get(name, "")
        if tc:
            lines.append(f"> {tc}")
            lines.append("")

        meta: list[str] = []
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
                cols_str = ", ".join(f"`{c}`" for c in fk["columns"])
                ref = fk.get("ref_table", "")
                ref_cols = ", ".join(f"`{c}`" for c in fk["ref_columns"]) if fk["ref_columns"] else ""
                suffix = f" ({ref_cols})" if ref_cols else ""
                lines.append(f"- ({cols_str}) → `{ref}`{suffix}")
            lines.append("")

        cols = columns.get(name, [])
        if cols:
            if has_comments:
                lines.append("| # | Columna | Tipo | Nulo | Default | Comentario |")
                lines.append("|---|---------|------|------|---------|------------|")
            else:
                lines.append("| # | Columna | Tipo | Nulo | Default |")
                lines.append("|---|---------|------|------|---------|")

            for c in cols:
                nullable = "✓" if c["nullable"] else "✗"
                default = str(c.get("default") or "").replace("|", "\\|")
                comment = (c.get("comment") or "").replace("|", "\\|").replace("\n", " ")
                if has_comments:
                    lines.append(
                        f"| {c['position']} | `{c['name']}` | `{c['type']}` | {nullable} | {default} | {comment} |"
                    )
                else:
                    lines.append(
                        f"| {c['position']} | `{c['name']}` | `{c['type']}` | {nullable} | {default} |"
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

    # ── Vistas ────────────────────────────────────────────────────────────
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


def write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[json] {path} ({path.stat().st_size:,} bytes)")


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    out_dir: Path = args.out_dir
    requested_schema = args.schema.upper()
    engine = create_source_engine()
    backend = engine.dialect.name
    schema = requested_schema if backend != "sqlite" else None
    display_schema = schema or "default"

    print(f"[conn] backend={backend} schema={display_schema}")

    # Elegir fetcher segun dialecto
    if backend == "oracle":
        fetcher = OracleFetcher(engine, schema)  # type: ignore[arg-type]
    else:
        fetcher = SAFetcher(engine, schema)

    print("[fetch] tables...")
    tables = fetcher.fetch_tables(args.row_counts)
    print(f"        {len(tables)} tablas")

    print("[fetch] columns + comments...")
    columns = fetcher.fetch_columns(tables)
    total_cols = sum(len(v) for v in columns.values())
    with_comment = sum(1 for cols in columns.values() for c in cols if c.get("comment"))
    print(f"        {total_cols} columnas, {with_comment} con comentario")

    print("[fetch] constraints (PK/FK)...")
    pks, fks = fetcher.fetch_constraints(tables)
    print(f"        {sum(len(v) for v in pks.values() if v)} PKs, {sum(len(v) for v in fks.values())} FKs")

    indexes: dict = {}
    if not args.no_indexes:
        print("[fetch] indexes...")
        indexes = fetcher.fetch_indexes(tables)
        print(f"        {sum(len(v) for v in indexes.values())} indices")

    views: list[dict] = []
    if not args.no_views:
        print("[fetch] views...")
        views = fetcher.fetch_views()
        print(f"        {len(views)} vistas")

    table_comments = fetcher.fetch_table_comments()
    if table_comments:
        print(f"[meta]  {sum(1 for v in table_comments.values() if v)} tablas con comentario")

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
        "table_comments": table_comments,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(data, out_dir / "full_schema.json")
    write_markdown(data, out_dir / "full_schema.md")

    print(f"\n[done] archivos generados en {out_dir}/")


if __name__ == "__main__":
    main()
