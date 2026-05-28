#!/usr/bin/env python3
"""export_2026.py — Exporta todos los datos del año 2026 de las tablas clave de RAFAM.

Tablas exportadas:
    PROVEEDORES, ORDEN_COMPRA, OC_ITEMS, SOLIC_GASTOS, PEDIDOS, PED_ITEMS,
    ORDEN_PAGO, ORDEN_PAGO_IMPUT, CTA_COMPROB, REG_COMP, DEDUCCIONES, RETENCIONES

Las tablas de detalle (OC_ITEMS, PED_ITEMS) se filtran mediante subquery a su
tabla cabecera para garantizar consistencia referencial.

Los CSV se escriben en output/rafam_2026/ con timestamp en el nombre.

Configuración via .env:
    RAFAM_SOURCE_HOST, RAFAM_SOURCE_PORT, RAFAM_SOURCE_SERVICE,
    RAFAM_SOURCE_USER, RAFAM_SOURCE_PASSWORD
    ORACLE_CLIENT_DIR  (opcional, solo si se usa Oracle Instant Client)

Uso:
    python scripts/export_2026.py
    python scripts/export_2026.py --output-dir output/mi_carpeta
    python scripts/export_2026.py --tables ORDEN_COMPRA,OC_ITEMS
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

# ─── Definición de tablas objetivo ───────────────────────────────────────────
#
# Cada entrada puede tener:
#   "date_col"   → columna DATE para filtrar por año (WHERE col >= SINCE AND col < UNTIL)
#   "subquery"   → fragmento SQL WHERE para tablas de detalle sin fecha propia;
#                  los bind variables se pasan como :since y :until
#
# Si se omite "date_col", el script intenta auto-detectar la primera columna DATE.
# Si la tabla no existe en el schema se omite con un aviso.

TARGET_TABLES: list[dict] = [
    {
        "table":    "PROVEEDORES",
        "date_col": "FECHA_ULT_COMP",
    },
    {
        "table":    "ORDEN_COMPRA",
        "date_col": "FECH_OC",
    },
    {
        # OC_ITEMS no tiene fecha propia; se filtra por las OC del año 2026
        "table":    "OC_ITEMS",
        "subquery": (
            "WHERE (EJERCICIO, UNI_COMPRA, NRO_OC) IN ("
            f"  SELECT EJERCICIO, UNI_COMPRA, NRO_OC"
            f"  FROM {SCHEMA}.ORDEN_COMPRA"
            f"  WHERE FECH_OC >= :since AND FECH_OC < :until"
            ")"
        ),
    },
    {
        "table":    "SOLIC_GASTOS",
        "date_col": "FECH_SOLIC",
    },
    {
        "table":    "PEDIDOS",
        "date_col": "FECH_EMI",
    },
    {
        # PED_ITEMS no tiene fecha propia; se filtra por los pedidos del año 2026
        "table":    "PED_ITEMS",
        "subquery": (
            "WHERE (EJERCICIO, NRO_PED) IN ("
            f"  SELECT EJERCICIO, NRO_PED"
            f"  FROM {SCHEMA}.PEDIDOS"
            f"  WHERE FECH_EMI >= :since AND FECH_EMI < :until"
            ")"
        ),
    },
    {
        "table":    "ORDEN_PAGO",
        "date_col": "FECH_OP",
    },
    {
        # ORDEN_PAGO_IMPUT: si no existe en el schema se omitirá automáticamente
        "table":    "ORDEN_PAGO_IMPUT",
        "date_col": None,   # auto-detección
    },
    {
        "table":    "CTA_COMPROB",
        "date_col": "FECH_MOVIM",
    },
    {
        "table":    "REG_COMP",
        "date_col": "FECH_REG",
    },
    {
        "table":    "DEDUCCIONES",
        "date_col": "FECH_DEDUC",
    },
    {
        "table":    "RETENCIONES",
        "date_col": "FECH_RETEN",
    },
]

# Nombres de tablas para el filtro --tables
ALL_TABLE_NAMES: list[str] = [t["table"] for t in TARGET_TABLES]

# ─── Conexión ─────────────────────────────────────────────────────────────────

def get_connection() -> oracledb.Connection:
    oracle_client_dir = os.getenv("ORACLE_CLIENT_DIR")
    if oracle_client_dir:
        oracledb.init_oracle_client(lib_dir=oracle_client_dir)
    dsn  = oracledb.makedsn(RAFAM_SOURCE_HOST, RAFAM_SOURCE_PORT, service_name=RAFAM_SOURCE_SERVICE)
    conn = oracledb.connect(user=RAFAM_SOURCE_USER, password=RAFAM_SOURCE_PASSWORD, dsn=dsn)
    print(f"✅ Conectado a [{RAFAM_SOURCE_SERVICE}] en {RAFAM_SOURCE_HOST}:{RAFAM_SOURCE_PORT}")
    return conn


# ─── Helpers de schema ────────────────────────────────────────────────────────

def table_exists(cursor: oracledb.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = :1 AND TABLE_NAME = :2",
        [SCHEMA, table],
    )
    return cursor.fetchone()[0] > 0


def get_table_columns(cursor: oracledb.Cursor, table: str) -> list[dict]:
    cursor.execute(
        """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM   ALL_TAB_COLUMNS
        WHERE  OWNER      = :1
          AND  TABLE_NAME = :2
        ORDER BY COLUMN_ID
        """,
        [SCHEMA, table],
    )
    return [{"name": row[0], "type": row[1]} for row in cursor.fetchall()]


def auto_detect_date_col(columns: list[dict]) -> str | None:
    """Devuelve la columna DATE más apropiada aplicando heurísticas de nombre."""
    date_cols = [c["name"] for c in columns if c["type"] == "DATE"]
    preferred_patterns = ["FECH_", "FECHA_", "_DATE", "_FECHA"]
    for col in date_cols:
        for pat in preferred_patterns:
            if pat in col:
                return col
    return date_cols[0] if date_cols else None


def column_exists(columns: list[dict], name: str) -> bool:
    return any(c["name"] == name for c in columns)


# ─── Exportación ─────────────────────────────────────────────────────────────

def export_table(
    cursor:     oracledb.Cursor,
    table:      str,
    columns:    list[dict],
    where_sql:  str,
    bind_params: dict,
    output_dir: Path,
    timestamp:  str,
    mode_label: str,
) -> dict:
    col_names = [c["name"] for c in columns]
    col_list  = ", ".join(col_names)
    qualified = f"{SCHEMA}.{table}"

    sql = f"SELECT {col_list} FROM {qualified} {where_sql}"
    cursor.execute(sql, bind_params)

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

    return {"table": table, "rows": row_count, "mode": mode_label, "file": csv_path.name}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Exporta todos los datos del año {YEAR} de las tablas clave de RAFAM"
    )
    parser.add_argument(
        "--tables", metavar="T1,T2",
        help=f"Tablas a exportar separadas por coma. Default: {', '.join(ALL_TABLE_NAMES)}",
    )
    parser.add_argument(
        "--output-dir", metavar="DIR", default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directorio de salida (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    requested_names: set[str] = (
        {t.strip().upper() for t in args.tables.split(",")}
        if args.tables
        else set(ALL_TABLE_NAMES)
    )

    # Mantener el orden definido en TARGET_TABLES
    tables_to_run = [t for t in TARGET_TABLES if t["table"] in requested_names]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not RAFAM_SOURCE_USER or not RAFAM_SOURCE_PASSWORD:
        print("❌ Faltan RAFAM_SOURCE_USER / RAFAM_SOURCE_PASSWORD en .env", file=sys.stderr)
        sys.exit(1)

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.arraysize = 5000

    results: list[dict] = []
    skipped: list[str]  = []

    print(f"\nExportando datos del año {YEAR}  →  {output_dir}\n")

    for table_def in tables_to_run:
        table = table_def["table"]

        if not table_exists(cursor, table):
            print(f"  ⚠️  {table}: no encontrada en {SCHEMA}, omitiendo")
            skipped.append(table)
            continue

        columns = get_table_columns(cursor, table)

        # Construir WHERE + parámetros
        if "subquery" in table_def:
            where_sql    = table_def["subquery"]
            bind_params  = {"since": SINCE, "until": UNTIL}
            mode_label   = f"subquery → {YEAR}"
        else:
            date_col = table_def.get("date_col")

            if date_col and not column_exists(columns, date_col):
                print(f"  ⚠️  {table}: columna '{date_col}' no encontrada, intentando auto-detección")
                date_col = None

            if date_col is None:
                date_col = auto_detect_date_col(columns)

            if date_col is None:
                print(f"  ⚠️  {table}: sin columna DATE detectada, omitiendo")
                skipped.append(table)
                continue

            where_sql   = f"WHERE {date_col} >= :since AND {date_col} < :until"
            bind_params = {"since": SINCE, "until": UNTIL}
            mode_label  = f"{date_col} → {YEAR}"

        try:
            result = export_table(
                cursor, table, columns,
                where_sql, bind_params,
                output_dir, timestamp, mode_label,
            )
            results.append(result)
            print(f"  ✅ {table:<40} {result['rows']:>8} filas  [{result['mode']}]")
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
