#!/usr/bin/env python3
"""export_2026.py — Exporta todos los datos del año 2026 de las tablas clave de RAFAM.

Tablas exportadas:
    PROVEEDORES, ORDEN_COMPRA, OC_ITEMS, SOLIC_GASTOS, PEDIDOS, PED_ITEMS,
    ORDEN_PAGO, ORDEN_PAGO_IMPUT, CTA_COMPROB, REG_COMP, DEDUCCIONES, RETENCIONES

Los CSV se escriben en output/rafam_2026/ con timestamp en el nombre.

Configuración via .env:
    RAFAM_SOURCE_HOST, RAFAM_SOURCE_PORT, RAFAM_SOURCE_SERVICE,
    RAFAM_SOURCE_USER, RAFAM_SOURCE_PASSWORD
    ORACLE_CLIENT_DIR  (opcional, solo si se usa Oracle Instant Client)

Uso:
    python scripts/export_2026.py
    python scripts/export_2026.py --tables ORDEN_COMPRA,OC_ITEMS
    python scripts/export_2026.py --output-dir output/mi_carpeta
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import oracledb
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

RAFAM_SOURCE_HOST     = os.getenv("RAFAM_SOURCE_HOST", "10.10.91.241")
RAFAM_SOURCE_PORT     = int(os.getenv("RAFAM_SOURCE_PORT", 1521))
RAFAM_SOURCE_SERVICE  = os.getenv("RAFAM_SOURCE_SERVICE", "BDRAFAM")
RAFAM_SOURCE_USER     = os.getenv("RAFAM_SOURCE_USER")
RAFAM_SOURCE_PASSWORD = os.getenv("RAFAM_SOURCE_PASSWORD")
SCHEMA                = "OWNER_RAFAM"

YEAR  = 2026
SINCE = datetime(YEAR, 1, 1)
UNTIL = datetime(YEAR + 1, 1, 1)

DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / f"rafam_{YEAR}"

# ─── Columnas de fecha preferidas por tabla ───────────────────────────────────
DATE_COL_PRIORITY: dict[str, list[str]] = {
    "PROVEEDORES":  ["FECHA_ULT_COMP", "FECHA_ALTA"],
    "ORDEN_COMPRA": ["FECH_OC", "FECH_CONFIRM"],
    "SOLIC_GASTOS": ["FECH_SOLIC", "FECH_CONFIRM"],
    "PEDIDOS":      ["FECH_EMI"],
    "ORDEN_PAGO":   ["FECH_OP", "FECH_CONFIRM"],
    "CTA_COMPROB":  ["FECH_MOVIM", "FECH_COMPROB"],
    "REG_COMP":     ["FECH_REG_COMP", "FECH_CONFIRM"],
    "DEDUCCIONES":    ["FECH_DEDUC"],
    "RETENCIONES":    ["FECH_RETEN"],
    "ADJUDICACIONES": ["FECH_ADJUD"],
}

# Tablas que se exportan completas (no tienen columna DATE útil propia)
FULL_LOAD_TABLES: set[str] = {
    "OC_ITEMS",
    "PED_ITEMS",
    "SOLIC_GASTOS_ITEMS",
    "ADJUDICACIONES_ITEMS",
    "TIPOS_COMPROB",
    "ORDEN_PAGO_DEDUC",
}

# Tablas filtradas por EJERCICIO (no tienen DATE pero sí columna EJERCICIO)
EJERCICIO_FILTER_TABLES: dict[str, int] = {
    "ORDEN_PAGO_IMPUT": YEAR,
    # Forma de pago real de la OP: ORDEN_PAGO -> EGRESOS (NRO_CANCE=NRO_OP) ->
    # COMPROBANTES (ORIGEN_TIPO). Se filtran por EJERCICIO para acompañar a las OP.
    "EGRESOS": YEAR,
    "COMPROBANTES": YEAR,
}

# Tablas objetivo — en orden de exportación
ALL_TABLES: list[str] = [
    "PROVEEDORES",
    "ORDEN_COMPRA",
    "OC_ITEMS",
    "SOLIC_GASTOS",
    "PEDIDOS",
    "PED_ITEMS",
    "ORDEN_PAGO",
    "ORDEN_PAGO_IMPUT",
    "EGRESOS",
    "COMPROBANTES",
    "CTA_COMPROB",
    "REG_COMP",
    "DEDUCCIONES",
    "RETENCIONES",
    "ADJUDICACIONES",
    "ORDEN_PAGO_DEDUC",
    "SOLIC_GASTOS_ITEMS",
    "ADJUDICACIONES_ITEMS",
    "TIPOS_COMPROB",
]

# ─── Conexión ─────────────────────────────────────────────────────────────────

def get_connection() -> oracledb.Connection:
    # Thick mode is required for older Oracle server versions (DPY-3010 in thin mode).
    # Set ORACLE_CLIENT_DIR (or ORACLE_CLIENT_LIB_DIR) in .env to point to Oracle
    # Instant Client. If omitted, the client must be on the system PATH.
    oracle_client_dir = os.getenv("ORACLE_CLIENT_LIB_DIR") or os.getenv("ORACLE_CLIENT_DIR")
    try:
        oracledb.init_oracle_client(lib_dir=oracle_client_dir or None)
        print(f"[thick mode] Oracle Instant Client habilitado desde: {oracle_client_dir or 'LD_LIBRARY_PATH'}")
    except Exception as exc:
        if "already been initialized" not in str(exc):
            print(f"[thin mode] No se pudo inicializar Oracle Instant Client: {exc}")
    dsn  = oracledb.makedsn(RAFAM_SOURCE_HOST, RAFAM_SOURCE_PORT, service_name=RAFAM_SOURCE_SERVICE)
    conn = oracledb.connect(user=RAFAM_SOURCE_USER, password=RAFAM_SOURCE_PASSWORD, dsn=dsn)
    print(f"✅ Conectado a [{RAFAM_SOURCE_SERVICE}] en {RAFAM_SOURCE_HOST}:{RAFAM_SOURCE_PORT}")
    return conn


# ─── Inspección de columnas ───────────────────────────────────────────────────

def get_table_columns(cursor: oracledb.Cursor, table: str) -> list[dict]:
    """Devuelve columnas con nombre y tipo de datos."""
    cursor.execute(
        """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM   ALL_TAB_COLUMNS
        WHERE  OWNER       = :1
          AND  TABLE_NAME  = :2
        ORDER BY COLUMN_ID
        """,
        [SCHEMA, table],
    )
    return [{"name": row[0], "type": row[1]} for row in cursor.fetchall()]


def pick_date_column(table: str, columns: list[dict]) -> str | None:
    """Elige la columna de fecha más apropiada para filtrar por año."""
    col_names = {c["name"] for c in columns}
    date_cols = {c["name"] for c in columns if c["type"] == "DATE"}

    # 1. Prioridad explícita configurada
    for candidate in DATE_COL_PRIORITY.get(table, []):
        if candidate in col_names:
            return candidate

    # 2. Auto-detección: preferir columnas con patrones comunes
    preferred_patterns = ["FECH_", "FECHA_", "_DATE", "_FECHA"]
    for col in (c["name"] for c in columns if c["name"] in date_cols):
        for pat in preferred_patterns:
            if pat in col:
                return col

    # 3. Cualquier DATE disponible
    if date_cols:
        return next(iter(sorted(date_cols)))

    return None


# ─── Verificar si tabla existe ────────────────────────────────────────────────

def table_exists(cursor: oracledb.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = :1 AND TABLE_NAME = :2",
        [SCHEMA, table],
    )
    return cursor.fetchone()[0] > 0


def list_all_tables(cursor: oracledb.Cursor) -> list[str]:
    """Lista TODAS las tablas del schema OWNER_RAFAM (para --all-tables)."""
    cursor.execute(
        "SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER = :1 ORDER BY TABLE_NAME",
        [SCHEMA],
    )
    return [row[0] for row in cursor.fetchall()]


# ─── Exportar tabla ───────────────────────────────────────────────────────────

def export_table(
    cursor:     oracledb.Cursor,
    table:      str,
    columns:    list[dict],
    date_col:   str | None,
    output_dir: Path,
    timestamp:  str,
    full_load:  bool,
    ejercicio:  int | None = None,
) -> dict:
    col_names = [c["name"] for c in columns]
    col_list  = ", ".join(col_names)
    qualified = f"{SCHEMA}.{table}"

    if ejercicio is not None:
        sql    = f"SELECT {col_list} FROM {qualified} WHERE EJERCICIO = :1"
        params = [ejercicio]
        mode   = f"ejercicio={ejercicio}"
    elif full_load or date_col is None:
        sql    = f"SELECT {col_list} FROM {qualified}"
        params = []
        mode   = "completo"
    else:
        sql    = f"SELECT {col_list} FROM {qualified} WHERE {date_col} >= :1 AND {date_col} < :2"
        params = [SINCE, UNTIL]
        mode   = f"{date_col} → {YEAR}"

    cursor.execute(sql, params)

    csv_path  = output_dir / f"{table.lower()}_{timestamp}.csv"
    row_count = 0
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(col_names)
        while True:
            batch = cursor.fetchmany(5000)
            if not batch:
                break
            for row in batch:
                writer.writerow([
                    v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v
                    for v in row
                ])
            row_count += len(batch)

    return {"table": table, "rows": row_count, "mode": mode, "file": csv_path.name}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Exporta todos los datos del año {YEAR} de las tablas clave de RAFAM"
    )
    parser.add_argument(
        "--tables", metavar="T1,T2",
        help=f"Tablas separadas por coma. Default: {', '.join(ALL_TABLES)}",
    )
    parser.add_argument(
        "--all-tables", action="store_true",
        help="Descubre y exporta TODAS las tablas del schema OWNER_RAFAM (auto-detecta filtro por DATE/EJERCICIO).",
    )
    parser.add_argument(
        "--output-dir", metavar="DIR", default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directorio de salida (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    tables = (
        [t.strip().upper() for t in args.tables.split(",")]
        if args.tables
        else ALL_TABLES
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not RAFAM_SOURCE_USER or not RAFAM_SOURCE_PASSWORD:
        print("❌ Faltan RAFAM_SOURCE_USER / RAFAM_SOURCE_PASSWORD en .env", file=sys.stderr)
        sys.exit(1)

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.arraysize = 5000

    if args.all_tables:
        tables = list_all_tables(cursor)
        print(f"🔎 --all-tables: {len(tables)} tablas encontradas en {SCHEMA}")

    results: list[dict] = []
    skipped: list[str]  = []

    print(f"\nExportando datos del año {YEAR}  →  {output_dir}\n")

    for table in tables:
        if not table_exists(cursor, table):
            print(f"  ⚠️  {table}: no encontrada en {SCHEMA}, omitiendo")
            skipped.append(table)
            continue

        columns   = get_table_columns(cursor, table)
        full_load = table in FULL_LOAD_TABLES
        ejercicio = EJERCICIO_FILTER_TABLES.get(table)
        date_col  = None if (full_load or ejercicio is not None) else pick_date_column(table, columns)

        if not full_load and ejercicio is None and date_col is None:
            # Sin columna DATE: si tiene EJERCICIO filtramos por año; si no, full load.
            if any(c["name"] == "EJERCICIO" for c in columns):
                ejercicio = YEAR
                print(f"  ℹ️  {table}: sin columna DATE → filtrando por EJERCICIO={YEAR}")
            else:
                print(f"  ⚠️  {table}: sin columna DATE ni EJERCICIO → export completo")
                full_load = True

        try:
            result = export_table(
                cursor, table, columns, date_col,
                output_dir, timestamp, full_load,
                ejercicio=ejercicio,
            )
            results.append(result)
            if ejercicio is not None:
                icon = "📅"
            elif full_load:
                icon = "📦"
            else:
                icon = "🗓️ "
            print(f"  {icon} {table:<40} {result['rows']:>8} filas  [{result['mode']}]")
        except oracledb.DatabaseError as exc:
            print(f"  ❌ {table}: error al exportar — {exc}", file=sys.stderr)
            skipped.append(table)

    cursor.close()
    conn.close()

    # ─── Resumen ──────────────────────────────────────────────────────────────
    total_rows = sum(r["rows"] for r in results)
    print()
    print("─" * 60)
    print(f"✅ Exportadas: {len(results)} tablas  |  {total_rows:,} filas totales")
    print(f"📁 Directorio: {output_dir}")
    if skipped:
        print(f"⚠️  Omitidas:   {', '.join(skipped)}")


if __name__ == "__main__":
    main()
