"""
explore_clasificaciones.py — Descubre y analiza las tablas de clasificaciones
(partidas presupuestarias) en la base RAFAM para diseñar una futura entidad de
migración "clasificaciones" hacia Paxapos.

RAFAM no tiene una tabla maestra limpia de partidas: la jerarquía vive repetida
en tablas transaccionales. La jerarquía es:

    inciso   (Nivel 1 — macro categoría, ej: 2 = Bienes de consumo)
    par_prin (Nivel 2 — partida principal, ej: 1 = Productos alimenticios)
    par_parc (Nivel 3 — partida parcial, ej: 1 = Alimentos para personas)
    par_subp (Nivel 4 — partida subparcial, opcional)
    DENOMINACION (texto de la partida, repetido en cada transacción)

Este script escanea TODAS las tablas/vistas del esquema buscando esas columnas,
reporta las candidatas, reconstruye el árbol distinct (inciso→par_prin→par_parc
+ denominación) y recomienda la mejor tabla fuente del catálogo de partidas.

Corre en modo SOLO LECTURA. Nunca escribe en RAFAM. Los conteos (COUNT/DISTINCT)
son opt-in porque en Oracle en vivo pueden ser costosos.

Salidas (en output/rafam_context/):
    - clasificaciones_candidates.json  (machine-readable, completo)
    - clasificaciones_candidates.md    (human-readable, completo, revisable en PR)
    - clasificaciones_arbol.csv        (árbol distinct de la fuente recomendada)

Uso:
    python scripts/explore_clasificaciones.py
    python scripts/explore_clasificaciones.py --distinct --row-counts
    python scripts/explore_clasificaciones.py --sample 100 --min-score 2 --no-views

Variables de entorno:
    RAFAM_SOURCE_BACKEND=oracle|sqlite
    RAFAM_SOURCE_* según el backend elegido (ver README.md)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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

# ─── Config de detección de clasificaciones ──────────────────────────────────

# Columnas de jerarquía en orden canónico (nombre RAFAM → nivel).
HIERARCHY_LEVELS: list[tuple[str, int]] = [
    ("INCISO", 1),
    ("PAR_PRIN", 2),
    ("PAR_PARC", 3),
    ("PAR_SUBP", 4),
]
HIERARCHY_NAMES = {name for name, _ in HIERARCHY_LEVELS}

# Columna de texto principal de la partida.
PRIMARY_NAME_COLUMN = "DENOMINACION"

# Patrón de columnas de texto que podrían nombrar la partida (fallback).
NAME_COLUMN_PATTERN = re.compile(r"DENOM|DESCRIP|NOMBRE|GLOSA|LEYENDA", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="OWNER_RAFAM", help="Owner del schema a analizar")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directorio de salida (default: output/rafam_context)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=2,
        help="Niveles de jerarquía mínimos para considerar una tabla candidata (default: 2)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=50,
        help="Filas distinct de muestra del árbol por candidata en el MD (default: 50)",
    )
    parser.add_argument(
        "--no-views",
        action="store_true",
        help="No incluir vistas en el escaneo",
    )
    parser.add_argument(
        "--row-counts",
        action="store_true",
        help="Contar filas exactas (SELECT COUNT(*)) por candidata — costoso en Oracle",
    )
    parser.add_argument(
        "--distinct",
        action="store_true",
        help="Contar combinaciones distintas de la jerarquía por candidata — costoso en Oracle",
    )
    parser.add_argument(
        "--max-distinct",
        type=int,
        default=5000,
        help="Tope de filas distinct a volcar al CSV del árbol recomendado (default: 5000)",
    )
    return parser.parse_args()


# ─── Helpers de esquema ──────────────────────────────────────────────────────

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


def _safe(default: Any, callback):
    try:
        return callback()
    except SQLAlchemyError as exc:
        print(f"[warn] introspección parcial: {exc}", file=sys.stderr)
        return default


# ─── Descubrimiento de columnas (rápido) ─────────────────────────────────────

def fetch_all_columns(
    engine: Engine,
    schema: str | None,
    include_views: bool,
) -> dict[str, dict[str, Any]]:
    """Devuelve {objeto: {"kind": "table"|"view", "columns": [{name,type}]}}.

    En Oracle usa ALL_TAB_COLUMNS/ALL_VIEWS en pocas queries (rápido). En SQLite
    cae al inspector de SQLAlchemy.
    """
    if engine.dialect.name == "oracle" and schema:
        return _fetch_all_columns_oracle(engine, schema, include_views)
    return _fetch_all_columns_inspector(engine, schema, include_views)


def _fetch_all_columns_oracle(
    engine: Engine,
    schema: str,
    include_views: bool,
) -> dict[str, dict[str, Any]]:
    with engine.connect() as conn:
        view_names = {
            str(r[0])
            for r in conn.execute(
                text("SELECT VIEW_NAME FROM ALL_VIEWS WHERE OWNER = :owner"),
                {"owner": schema},
            )
        }
        rows = conn.execute(
            text(
                """
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, DATA_LENGTH,
                       DATA_PRECISION, DATA_SCALE, COLUMN_ID
                FROM ALL_TAB_COLUMNS
                WHERE OWNER = :owner
                ORDER BY TABLE_NAME, COLUMN_ID
                """,
            ),
            {"owner": schema},
        ).all()

    objects: dict[str, dict[str, Any]] = {}
    for table_name, col_name, data_type, length, precision, scale, _ in rows:
        table_name = str(table_name)
        is_view = table_name in view_names
        if is_view and not include_views:
            continue
        obj = objects.setdefault(
            table_name,
            {"kind": "view" if is_view else "table", "columns": []},
        )
        obj["columns"].append(
            {"name": str(col_name), "type": _oracle_type(data_type, length, precision, scale)}
        )
    return objects


def _oracle_type(data_type: Any, length: Any, precision: Any, scale: Any) -> str:
    data_type = str(data_type)
    if data_type in {"NUMBER"} and precision is not None:
        if scale:
            return f"NUMBER({int(precision)},{int(scale)})"
        return f"NUMBER({int(precision)})"
    if data_type in {"VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR"} and length is not None:
        return f"{data_type}({int(length)})"
    return data_type


def _fetch_all_columns_inspector(
    engine: Engine,
    schema: str | None,
    include_views: bool,
) -> dict[str, dict[str, Any]]:
    inspector = sa_inspect(engine)
    objects: dict[str, dict[str, Any]] = {}

    table_names = _safe([], lambda: inspector.get_table_names(schema=schema))
    for name in table_names:
        cols = _safe([], lambda name=name: inspector.get_columns(name, schema=schema))
        objects[name] = {
            "kind": "table",
            "columns": [{"name": c["name"], "type": str(c.get("type", ""))} for c in cols],
        }

    if include_views:
        view_names = _safe([], lambda: inspector.get_view_names(schema=schema))
        for name in view_names:
            cols = _safe([], lambda name=name: inspector.get_columns(name, schema=schema))
            objects[name] = {
                "kind": "view",
                "columns": [{"name": c["name"], "type": str(c.get("type", ""))} for c in cols],
            }

    return objects


# ─── Clasificación de tablas ─────────────────────────────────────────────────

def classify_object(columns: list[dict[str, Any]]) -> dict[str, Any]:
    """Detecta columnas de clasificación en un objeto y calcula su score."""
    upper = {c["name"].upper(): c["name"] for c in columns}

    present_levels: list[dict[str, Any]] = []
    for name, level in HIERARCHY_LEVELS:
        if name in upper:
            present_levels.append({"column": upper[name], "level": level, "canonical": name})

    name_columns: list[str] = []
    if PRIMARY_NAME_COLUMN in upper:
        name_columns.append(upper[PRIMARY_NAME_COLUMN])
    for c in columns:
        cu = c["name"].upper()
        if cu == PRIMARY_NAME_COLUMN:
            continue
        if NAME_COLUMN_PATTERN.search(cu):
            name_columns.append(c["name"])

    return {
        "score": len(present_levels),
        "levels": present_levels,
        "name_columns": name_columns,
        "has_denominacion": PRIMARY_NAME_COLUMN in upper,
    }


# ─── Análisis de candidatas (PK/FK/conteos/árbol) ────────────────────────────

def fetch_pk_fk(
    engine: Engine,
    table_name: str,
    schema: str | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    inspector = sa_inspect(engine)
    pk = _safe({}, lambda: inspector.get_pk_constraint(table_name, schema=schema))
    raw_fks = _safe([], lambda: inspector.get_foreign_keys(table_name, schema=schema))
    fks = [
        {
            "columns": list(fk.get("constrained_columns") or []),
            "ref_table": fk.get("referred_table") or "",
            "ref_owner": fk.get("referred_schema") or schema or "",
            "ref_columns": list(fk.get("referred_columns") or []),
        }
        for fk in raw_fks
    ]
    return list(pk.get("constrained_columns") or []), fks


def _row_count(engine: Engine, table_name: str, schema: str | None) -> int | None:
    qn = _qualified_name(engine, table_name, schema)
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(f"SELECT COUNT(*) FROM {qn}")).scalar_one())
    except SQLAlchemyError as exc:
        print(f"[warn] no se pudo contar {qn}: {exc}", file=sys.stderr)
        return None


def _oracle_estimated_rows(engine: Engine, schema: str | None) -> dict[str, int | None]:
    if engine.dialect.name != "oracle" or not schema:
        return {}
    out: dict[str, int | None] = {}
    with engine.connect() as conn:
        for tname, num in conn.execute(
            text("SELECT TABLE_NAME, NUM_ROWS FROM ALL_TABLES WHERE OWNER = :owner"),
            {"owner": schema},
        ):
            out[str(tname)] = int(num) if num is not None else None
    return out


def _limited_distinct_query(
    engine: Engine,
    qualified: str,
    level_cols: list[str],
    name_col: str | None,
    limit: int,
) -> str:
    """Arma un SELECT DISTINCT de la jerarquía + denominación, acotado (dialect-safe)."""
    select_cols = list(level_cols)
    if name_col:
        select_cols.append(name_col)
    cols_sql = ", ".join(select_cols)
    first_level = level_cols[0]
    inner = (
        f"SELECT DISTINCT {cols_sql} FROM {qualified} "
        f"WHERE {first_level} IS NOT NULL ORDER BY {cols_sql}"
    )
    if engine.dialect.name == "oracle":
        return f"SELECT * FROM ({inner}) WHERE ROWNUM <= {int(limit)}"
    return f"{inner} LIMIT {int(limit)}"


def fetch_distinct_tree(
    engine: Engine,
    table_name: str,
    schema: str | None,
    level_cols: list[str],
    name_col: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    qn = _qualified_name(engine, table_name, schema)
    sql = _limited_distinct_query(engine, qn, level_cols, name_col, limit)
    header = list(level_cols) + ([name_col] if name_col else [])
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(sql)).all()
    except SQLAlchemyError as exc:
        print(f"[warn] no se pudo leer el árbol de {qn}: {exc}", file=sys.stderr)
        return []
    return [dict(zip(header, row)) for row in rows]


def count_distinct_combos(
    engine: Engine,
    table_name: str,
    schema: str | None,
    level_cols: list[str],
) -> int | None:
    qn = _qualified_name(engine, table_name, schema)
    cols_sql = ", ".join(level_cols)
    first_level = level_cols[0]
    sql = (
        f"SELECT COUNT(*) FROM (SELECT DISTINCT {cols_sql} FROM {qn} "
        f"WHERE {first_level} IS NOT NULL)"
    )
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(sql)).scalar_one())
    except SQLAlchemyError as exc:
        print(f"[warn] no se pudo contar combos de {qn}: {exc}", file=sys.stderr)
        return None


# ─── Recomendación de fuente canónica ────────────────────────────────────────

def rank_candidates(candidates: list[dict[str, Any]]) -> list[str]:
    """Ordena candidatas por 'catalog-likeness'. Devuelve nombres, mejor primero.

    Preferencia: tiene DENOMINACION → más niveles → menos filas (parece catálogo
    dedupable) → vista antes que tabla a igualdad → nombre alfabético.
    """

    def sort_key(c: dict[str, Any]) -> tuple:
        rows = c.get("num_rows_estimate")
        rows_key = rows if isinstance(rows, int) else float("inf")
        return (
            0 if c["analysis"]["has_denominacion"] else 1,
            -c["analysis"]["score"],
            rows_key,
            0 if c["kind"] == "view" else 1,
            c["table"],
        )

    eligible = [c for c in candidates if c["analysis"]["score"] >= 3]
    return [c["table"] for c in sorted(eligible or candidates, key=sort_key)]


# ─── Renderers ───────────────────────────────────────────────────────────────

def write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[json] {path} ({path.stat().st_size:,} bytes)")


def write_csv(tree: list[dict[str, Any]], header: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for row in tree:
            writer.writerow({k: row.get(k, "") for k in header})
    print(f"[csv]  {path} ({path.stat().st_size:,} bytes, {len(tree)} filas)")


def write_markdown(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = data["candidates"]
    ranking: list[str] = data["recommended_ranking"]

    lines: list[str] = []
    lines.append(f"# Clasificaciones RAFAM (partidas) — `{data['schema']}`")
    lines.append("")
    lines.append(f"> Generado por `scripts/explore_clasificaciones.py` el {data['generated_at']}")
    lines.append(f"> Backend: `{data['backend']}` · Solo lectura")
    lines.append("> **No editar manualmente** — regenerar ejecutando el script.")
    lines.append("")
    lines.append("## Objetivo")
    lines.append("")
    lines.append(
        "Detectar y analizar las tablas que contienen la jerarquía de partidas "
        "(`inciso`→`par_prin`→`par_parc`[→`par_subp`] + `DENOMINACION`) para diseñar "
        "una entidad de migración *clasificaciones* hacia la `Categoria` (nested-set) de Paxapos."
    )
    lines.append("")

    # Resumen
    lines.append("## Resumen del escaneo")
    lines.append("")
    lines.append(f"- Objetos escaneados: **{data['scanned_objects']}**")
    lines.append(f"- Candidatas (score ≥ {data['min_score']}): **{len(candidates)}**")
    strong = [c for c in candidates if c["analysis"]["score"] >= 3]
    lines.append(f"- Con jerarquía completa (3+ niveles): **{len(strong)}**")
    with_denom = [c for c in strong if c["analysis"]["has_denominacion"]]
    lines.append(f"- Con `DENOMINACION` co-localizada: **{len(with_denom)}**")
    lines.append("")

    # Recomendación
    lines.append("## Fuente canónica recomendada")
    lines.append("")
    if ranking:
        best = ranking[0]
        best_cand = next(c for c in candidates if c["table"] == best)
        if best_cand["analysis"]["has_denominacion"]:
            motivo = "tiene la jerarquía + `DENOMINACION` co-localizada; mejor relación catálogo/volumen"
        else:
            motivo = (
                "tiene la jerarquía completa; **NINGUNA candidata trae `DENOMINACION` local** — "
                "los nombres de partida habrá que resolverlos aparte (otra tabla/vista o mapeo manual)"
            )
        lines.append(f"➡️ **`{best}`** es la mejor fuente para el catálogo de partidas ({motivo}).")
        if len(ranking) > 1:
            lines.append("")
            lines.append("Orden de preferencia:")
            for i, name in enumerate(ranking, start=1):
                lines.append(f"{i}. `{name}`")
    else:
        lines.append("*(No se hallaron candidatas con jerarquía completa + denominación.)*")
    lines.append("")
    lines.append(
        "> ⚠️ Nota arquitectónica: RAFAM no tiene una tabla maestra relacional limpia de "
        "partidas. La entidad *clasificaciones* deberá construirse con un `SELECT DISTINCT` "
        "de la jerarquía + denominación sobre la fuente recomendada."
    )
    lines.append("")

    # Tabla resumen de candidatas
    lines.append("## Candidatas")
    lines.append("")
    lines.append("| Objeto | Tipo | Score | Niveles | DENOMINACION | Filas (est.) | Combos distintos |")
    lines.append("|--------|------|-------|---------|--------------|--------------|------------------|")
    for c in candidates:
        a = c["analysis"]
        levels = ", ".join(f"`{lv['column']}`" for lv in a["levels"])
        denom = "✓" if a["has_denominacion"] else "—"
        rows = c.get("num_rows_estimate")
        rows_str = f"{rows:,}" if isinstance(rows, int) else "?"
        combos = c.get("distinct_combos")
        combos_str = f"{combos:,}" if isinstance(combos, int) else "—"
        lines.append(
            f"| `{c['table']}` | {c['kind']} | {a['score']} | {levels} | {denom} | "
            f"{rows_str} | {combos_str} |"
        )
    lines.append("")

    # Detalle por candidata
    lines.append("## Detalle por candidata")
    lines.append("")
    for c in candidates:
        a = c["analysis"]
        lines.append(f"### {c['table']} ({c['kind']})")
        lines.append("")
        levels = ", ".join(f"`{lv['column']}` (N{lv['level']})" for lv in a["levels"])
        lines.append(f"- **Jerarquía:** {levels}")
        if a["name_columns"]:
            lines.append(f"- **Columnas de texto:** {', '.join(f'`{n}`' for n in a['name_columns'])}")
        else:
            lines.append("- **Columnas de texto:** *(ninguna — sin denominación local)*")
        if c.get("primary_key"):
            lines.append(f"- **PK:** {', '.join(f'`{k}`' for k in c['primary_key'])}")
        if c.get("foreign_keys"):
            lines.append("- **FKs:**")
            for fk in c["foreign_keys"]:
                cols = ", ".join(f"`{x}`" for x in fk["columns"])
                ref = ", ".join(f"`{x}`" for x in fk["ref_columns"])
                lines.append(f"  - ({cols}) → `{fk['ref_owner']}.{fk['ref_table']}` ({ref})")
        rows = c.get("num_rows_estimate")
        if isinstance(rows, int):
            lines.append(f"- **Filas (estimadas):** {rows:,}")
        if isinstance(c.get("distinct_combos"), int):
            lines.append(f"- **Combinaciones distintas de jerarquía:** {c['distinct_combos']:,}")

        tree = c.get("sample_tree") or []
        if tree:
            header = list(c["level_columns"]) + ([c["name_column"]] if c.get("name_column") else [])
            lines.append("")
            lines.append(f"Muestra del árbol distinct (hasta {data['sample']} filas):")
            lines.append("")
            lines.append("| " + " | ".join(header) + " |")
            lines.append("|" + "|".join(["---"] * len(header)) + "|")
            for row in tree:
                cells = []
                for h in header:
                    val = row.get(h, "")
                    cells.append(str(val).replace("|", "\\|") if val is not None else "")
                lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[md]   {path} ({path.stat().st_size:,} bytes)")


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    out_dir: Path = args.out_dir
    engine = create_source_engine()
    schema = _effective_schema(engine, args.schema)
    display_schema = schema or "default"
    backend = engine.dialect.name

    print(f"[conn] backend={backend} schema={display_schema}")
    print("[fetch] columnas de todos los objetos...")
    objects = fetch_all_columns(engine, schema, include_views=not args.no_views)
    print(f"        {len(objects)} objetos, {sum(len(o['columns']) for o in objects.values())} columnas")

    # Clasificar
    candidates: list[dict[str, Any]] = []
    for name in sorted(objects):
        obj = objects[name]
        analysis = classify_object(obj["columns"])
        if analysis["score"] < args.min_score:
            continue
        candidates.append({"table": name, "kind": obj["kind"], "analysis": analysis})

    print(f"[scan]  {len(candidates)} candidatas (score ≥ {args.min_score})")

    estimated = _oracle_estimated_rows(engine, schema)

    # Analizar cada candidata
    for c in candidates:
        name = c["table"]
        a = c["analysis"]
        level_cols = [lv["column"] for lv in a["levels"]]
        name_col = a["name_columns"][0] if a["name_columns"] else None
        c["level_columns"] = level_cols
        c["name_column"] = name_col

        pk, fks = fetch_pk_fk(engine, name, schema)
        c["primary_key"] = pk
        c["foreign_keys"] = fks

        c["num_rows_estimate"] = estimated.get(name)
        if args.row_counts:
            c["num_rows_exact"] = _row_count(engine, name, schema)

        if args.distinct and len(level_cols) >= 3:
            c["distinct_combos"] = count_distinct_combos(engine, name, schema, level_cols)

        # Muestra del árbol para el MD (solo candidatas fuertes)
        if len(level_cols) >= 3:
            c["sample_tree"] = fetch_distinct_tree(
                engine, name, schema, level_cols, name_col, args.sample
            )

    ranking = rank_candidates(candidates)

    data = {
        "schema": display_schema,
        "backend": backend,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "min_score": args.min_score,
        "sample": args.sample,
        "scanned_objects": len(objects),
        "recommended_ranking": ranking,
        "candidates": candidates,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(data, out_dir / "clasificaciones_candidates.json")
    write_markdown(data, out_dir / "clasificaciones_candidates.md")

    # CSV del árbol distinct de la fuente recomendada (completo, acotado por --max-distinct)
    if ranking:
        best_name = ranking[0]
        best = next(c for c in candidates if c["table"] == best_name)
        level_cols = best["level_columns"]
        name_col = best["name_column"]
        print(f"[tree]  volcando árbol distinct de `{best_name}` (máx {args.max_distinct:,})...")
        full_tree = fetch_distinct_tree(
            engine, best_name, schema, level_cols, name_col, args.max_distinct
        )
        header = list(level_cols) + ([name_col] if name_col else [])
        write_csv(full_tree, header, out_dir / "clasificaciones_arbol.csv")
    else:
        print("[tree]  sin fuente recomendada — no se genera CSV del árbol", file=sys.stderr)

    print("\n[done] revisar:")
    print(f"  - {out_dir / 'clasificaciones_candidates.md'}")
    print(f"  - {out_dir / 'clasificaciones_candidates.json'}")
    if ranking:
        print(f"  - {out_dir / 'clasificaciones_arbol.csv'}")


if __name__ == "__main__":
    main()
