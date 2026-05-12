"""
dump_full_schema.py — Dump COMPLETO del esquema Oracle OWNER_RAFAM.

A diferencia de explore_schema.py / generate_rafam_context.py (que filtran
por tablas relevantes), este script extrae **todo** el schema:

    - Todas las tablas (ALL_TABLES)
    - Todas las vistas (ALL_VIEWS) con su SQL
    - Todas las columnas (ALL_TAB_COLUMNS)
    - Todas las PKs y FKs (ALL_CONSTRAINTS / ALL_CONS_COLUMNS)
    - Todos los indices (ALL_INDEXES / ALL_IND_COLUMNS)
    - Conteo de filas por tabla (best effort, NUM_ROWS de estadisticas)

Sale en dos formatos:
    - output/rafam_context/full_schema.json   (machine-readable, para usar
      en otros scripts del proyecto)
    - output/rafam_context/full_schema.md     (human-readable, para commitear
      y revisar en PRs)

Uso:
    python scripts/dump_full_schema.py
    python scripts/dump_full_schema.py --schema OWNER_RAFAM --out-dir output/rafam_context

Variables de entorno requeridas (.env):
    RAFAM_SOURCE_HOST
    RAFAM_SOURCE_PORT
    RAFAM_SOURCE_SERVICE
    RAFAM_SOURCE_USER
    RAFAM_SOURCE_PASSWORD
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import oracledb
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "output" / "rafam_context"

# Inicializar Oracle Instant Client a nivel de módulo (ANTES de cualquier intento de conexión)
load_dotenv(REPO_ROOT / ".env")
try:
    lib_dir = os.getenv("ORACLE_CLIENT_LIB_DIR") or None
    oracledb.init_oracle_client(lib_dir=lib_dir)
    print(f"[thick mode] Oracle Instant Client habilitado desde: {lib_dir or 'LD_LIBRARY_PATH'}", file=sys.stderr)
except Exception as e:
    if "already been initialized" not in str(e):
        print(f"[thin mode] No se pudo inicializar Oracle Instant Client: {e}", file=sys.stderr)
        print("[aviso] Si la BD es Oracle < 12.1, instala Oracle Instant Client.", file=sys.stderr)


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
    return parser.parse_args()


def connect() -> oracledb.Connection:
    load_dotenv(REPO_ROOT / ".env")
    host = os.getenv("RAFAM_SOURCE_HOST")
    port = int(os.getenv("RAFAM_SOURCE_PORT", "1521"))
    service = os.getenv("RAFAM_SOURCE_SERVICE")
    user = os.getenv("RAFAM_SOURCE_USER")
    password = os.getenv("RAFAM_SOURCE_PASSWORD")
    if not all([host, service, user, password]):
        sys.exit("ERROR: faltan RAFAM_SOURCE_* en .env")
    
    dsn = oracledb.makedsn(host, port, service_name=service)
    print(f"[conn] {user}@{host}:{port}/{service}")
    return oracledb.connect(user=user, password=password, dsn=dsn)


# ─── Queries al diccionario de Oracle ────────────────────────────────────────

def fetch_tables(cur, owner: str) -> list[dict]:
    cur.execute(
        """
        SELECT TABLE_NAME, NUM_ROWS, LAST_ANALYZED, TABLESPACE_NAME
        FROM ALL_TABLES
        WHERE OWNER = :o
        ORDER BY TABLE_NAME
        """,
        o=owner,
    )
    return [
        {
            "name": r[0],
            "num_rows": int(r[1]) if r[1] is not None else None,
            "last_analyzed": r[2].isoformat() if r[2] else None,
            "tablespace": r[3],
        }
        for r in cur.fetchall()
    ]


def fetch_views(cur, owner: str) -> list[dict]:
    cur.execute(
        """
        SELECT VIEW_NAME, TEXT_LENGTH, TEXT
        FROM ALL_VIEWS
        WHERE OWNER = :o
        ORDER BY VIEW_NAME
        """,
        o=owner,
    )
    out = []
    for r in cur.fetchall():
        text = r[2]
        # TEXT viene como LONG; oracledb lo entrega como str
        out.append({"name": r[0], "text_length": int(r[1] or 0), "text": text or ""})
    return out


def fetch_columns(cur, owner: str) -> dict[str, list[dict]]:
    cur.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, DATA_LENGTH,
               DATA_PRECISION, DATA_SCALE, NULLABLE, COLUMN_ID, DATA_DEFAULT
        FROM ALL_TAB_COLUMNS
        WHERE OWNER = :o
        ORDER BY TABLE_NAME, COLUMN_ID
        """,
        o=owner,
    )
    cols: dict[str, list[dict]] = defaultdict(list)
    for r in cur.fetchall():
        # Tipo formateado estilo "VARCHAR2(13)" / "NUMBER(15,2)"
        dtype = r[2]
        if dtype in ("NUMBER",) and (r[4] is not None or r[5] is not None):
            if r[5]:
                dtype = f"NUMBER({r[4]},{r[5]})"
            else:
                dtype = f"NUMBER({r[4]})"
        elif dtype in ("VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR") and r[3]:
            dtype = f"{dtype}({r[3]})"
        default = r[8]
        if default is not None:
            try:
                default = default.read() if hasattr(default, "read") else str(default)
                default = default.strip()
            except Exception:
                default = None
        cols[r[0]].append(
            {
                "name": r[1],
                "type": dtype,
                "nullable": r[6] == "Y",
                "position": int(r[7]) if r[7] is not None else None,
                "default": default,
            }
        )
    return cols


def fetch_constraints(cur, owner: str) -> tuple[dict, dict]:
    """Devuelve (pks_por_tabla, fks_por_tabla)."""
    # PKs
    cur.execute(
        """
        SELECT c.TABLE_NAME, cc.COLUMN_NAME, cc.POSITION
        FROM ALL_CONSTRAINTS c
        JOIN ALL_CONS_COLUMNS cc
            ON cc.OWNER = c.OWNER AND cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME
        WHERE c.OWNER = :o AND c.CONSTRAINT_TYPE = 'P'
        ORDER BY c.TABLE_NAME, cc.POSITION
        """,
        o=owner,
    )
    pks: dict[str, list[str]] = defaultdict(list)
    for tn, col, _pos in cur.fetchall():
        pks[tn].append(col)

    # FKs
    cur.execute(
        """
        SELECT c.TABLE_NAME,
               c.CONSTRAINT_NAME,
               cc.COLUMN_NAME,
               cc.POSITION,
               r.OWNER AS REF_OWNER,
               r.TABLE_NAME AS REF_TABLE,
               rcc.COLUMN_NAME AS REF_COLUMN
        FROM ALL_CONSTRAINTS c
        JOIN ALL_CONS_COLUMNS cc
            ON cc.OWNER = c.OWNER AND cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME
        JOIN ALL_CONSTRAINTS r
            ON r.OWNER = c.R_OWNER AND r.CONSTRAINT_NAME = c.R_CONSTRAINT_NAME
        JOIN ALL_CONS_COLUMNS rcc
            ON rcc.OWNER = r.OWNER
           AND rcc.CONSTRAINT_NAME = r.CONSTRAINT_NAME
           AND rcc.POSITION = cc.POSITION
        WHERE c.OWNER = :o AND c.CONSTRAINT_TYPE = 'R'
        ORDER BY c.TABLE_NAME, c.CONSTRAINT_NAME, cc.POSITION
        """,
        o=owner,
    )
    fks_raw: dict[str, dict[str, dict]] = defaultdict(dict)
    for tn, cname, col, _pos, ref_owner, ref_table, ref_col in cur.fetchall():
        entry = fks_raw[tn].setdefault(
            cname,
            {"constraint": cname, "ref_owner": ref_owner, "ref_table": ref_table, "columns": [], "ref_columns": []},
        )
        entry["columns"].append(col)
        entry["ref_columns"].append(ref_col)
    fks = {tn: list(d.values()) for tn, d in fks_raw.items()}
    return pks, fks


def fetch_indexes(cur, owner: str) -> dict[str, list[dict]]:
    cur.execute(
        """
        SELECT i.TABLE_NAME, i.INDEX_NAME, i.UNIQUENESS, ic.COLUMN_NAME, ic.COLUMN_POSITION
        FROM ALL_INDEXES i
        JOIN ALL_IND_COLUMNS ic
            ON ic.INDEX_OWNER = i.OWNER AND ic.INDEX_NAME = i.INDEX_NAME
        WHERE i.OWNER = :o
        ORDER BY i.TABLE_NAME, i.INDEX_NAME, ic.COLUMN_POSITION
        """,
        o=owner,
    )
    raw: dict[str, dict[str, dict]] = defaultdict(dict)
    for tn, idx_name, uniq, col, _pos in cur.fetchall():
        entry = raw[tn].setdefault(idx_name, {"name": idx_name, "unique": uniq == "UNIQUE", "columns": []})
        entry["columns"].append(col)
    return {tn: list(d.values()) for tn, d in raw.items()}


# ─── Renderers ───────────────────────────────────────────────────────────────

def write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[json] {path} ({path.stat().st_size:,} bytes)")


def write_markdown(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = data["schema"]
    tables = data["tables"]
    views = data.get("views", [])
    columns = data["columns"]
    pks = data["primary_keys"]
    fks = data["foreign_keys"]
    indexes = data.get("indexes", {})

    lines: list[str] = []
    lines.append(f"# Esquema completo Oracle — `{schema}`")
    lines.append("")
    lines.append(f"> Generado por `scripts/dump_full_schema.py` el {data['generated_at']}")
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
            meta.append(f"**Rows (estimado):** {t['num_rows']:,}")
        if t.get("tablespace"):
            meta.append(f"**Tablespace:** `{t['tablespace']}`")
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
    schema: str = args.schema.upper()

    conn = connect()
    cur = conn.cursor()

    print(f"[fetch] tables…")
    tables = fetch_tables(cur, schema)
    print(f"        {len(tables)} tablas")

    print(f"[fetch] columns…")
    columns = fetch_columns(cur, schema)
    print(f"        {sum(len(v) for v in columns.values())} columnas en {len(columns)} tablas")

    print(f"[fetch] constraints (PK/FK)…")
    pks, fks = fetch_constraints(cur, schema)
    print(f"        {len(pks)} PKs, {sum(len(v) for v in fks.values())} FKs")

    indexes: dict = {}
    if not args.no_indexes:
        print(f"[fetch] indexes…")
        indexes = fetch_indexes(cur, schema)
        print(f"        {sum(len(v) for v in indexes.values())} indices en {len(indexes)} tablas")

    views: list[dict] = []
    if not args.no_views:
        print(f"[fetch] views (puede tardar)…")
        views = fetch_views(cur, schema)
        print(f"        {len(views)} vistas")

    cur.close()
    conn.close()

    data = {
        "schema": schema,
        "generated_at": datetime.utcnow().isoformat() + "Z",
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
