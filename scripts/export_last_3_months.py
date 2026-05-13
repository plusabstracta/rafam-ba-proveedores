#!/usr/bin/env python3
"""export_last_3_months.py — Exporta los últimos 3 meses de cada tabla a CSV.

Para tablas sin columna de fecha conocida hace un export completo (con aviso).
Los CSV se escriben en output/rafam_ultimos_3_meses/ con timestamp en el nombre.

Configuración via .env:
    RAFAM_SOURCE_HOST, RAFAM_SOURCE_PORT, RAFAM_SOURCE_SERVICE,
    RAFAM_SOURCE_USER, RAFAM_SOURCE_PASSWORD
    ORACLE_CLIENT_DIR  (opcional, solo si se usa Oracle Instant Client)

Uso:
    python scripts/export_last_3_months.py
    python scripts/export_last_3_months.py --months 6
    python scripts/export_last_3_months.py --tables PROVEEDORES,ORDEN_PAGO
    python scripts/export_last_3_months.py --output-dir output/mi_carpeta
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import oracledb
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

RAFAM_SOURCE_HOST = os.getenv("RAFAM_SOURCE_HOST", "10.10.91.241")
RAFAM_SOURCE_PORT = int(os.getenv("RAFAM_SOURCE_PORT", 1521))
RAFAM_SOURCE_SERVICE = os.getenv("RAFAM_SOURCE_SERVICE", "BDRAFAM")
RAFAM_SOURCE_USER = os.getenv("RAFAM_SOURCE_USER")
RAFAM_SOURCE_PASSWORD = os.getenv("RAFAM_SOURCE_PASSWORD")
SCHEMA      = "OWNER_RAFAM"

DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "rafam_ultimos_3_meses"

# ─── Columnas de fecha preferidas por tabla ───────────────────────────────────
# Si la tabla tiene varias columnas DATE, se usa la primera que aparezca aquí.
# Las tablas sin entrada se auto-detectan (se elige la primera DATE encontrada).
DATE_COL_PRIORITY: dict[str, list[str]] = {
    "PROVEEDORES":   ["FECHA_ULT_COMP", "FECHA_ALTA"],
    "PEDIDOS":       ["FECH_EMI"],
    "SOLIC_GASTOS":  ["FECH_SOLIC", "FECH_CONFIRM"],
    "ORDEN_COMPRA":  ["FECH_OC", "FECH_CONFIRM"],
    "ORDEN_PAGO":    ["FECH_OP", "FECH_CONFIRM"],
    "ADJUDICACIONES":["FECH_ADJUD"],
    "REG_COMP":      ["FECH_REG_COMP", "FECH_CONFIRM"],
    "RETENCIONES":   ["FECH_RETEN"],
    "DEDUCCIONES":   ["FECH_DEDUC"],
}

# Tablas que siempre se exportan completas (catálogos/items sin DATE útil)
FULL_LOAD_TABLES: set[str] = {
    # Catálogos chicos referenciados por el flujo de compras
    "JURISDICCIONES",
    "TIPOS_COMPROB",
    "TIPO_DOC_RES",
    # Detalle de cabeceras (no tienen FECHA propia, dependen de su cabecera)
    "PED_ITEMS",
    "OC_ITEMS",
    "SOLIC_GASTOS_ITEMS",
}

# Tablas filtradas por EJERCICIO (no tienen DATE pero sí columna EJERCICIO).
# Se exporta solo el ejercicio indicado para acotar volumen.
EJERCICIO_FILTER_TABLES: dict[str, int] = {
    "ORDEN_PAGO_IMPUT":     2026,  # bridge OP↔CC, 539K filas históricas
    "ADJUDICACIONES_ITEMS": 2026,  # link PE_ITEMS ↔ OC_ITEMS
}

# Todas las tablas a exportar — set mínimo realmente usado por el cron
# RAFAM -> Paxapos. Ver justificación en TARGET_TABLES de explore_schema.py.
ALL_TABLES: list[str] = [
    # ── Pasada 1: proveedores ──────────────────────────────────────────────
    "PROVEEDORES",
    # ── Pasada 2: órdenes de compra ────────────────────────────────────────
    "ORDEN_COMPRA",
    "OC_ITEMS",
    # ── Pasada 3: órdenes de pago + retenciones + vínculo a gastos ─────────
    "ORDEN_PAGO",
    "ORDEN_PAGO_IMPUT",   # bridge OP ↔ CTA_COMPROB (filtrado por EJERCICIO)
    "CTA_COMPROB",
    "REG_COMP",
    "SOLIC_GASTOS",
    "RETENCIONES",
    "DEDUCCIONES",
    # ── Resolución de items / mercadería ───────────────────────────────────
    "PEDIDOS",
    "PED_ITEMS",
    "ADJUDICACIONES",
    "ADJUDICACIONES_ITEMS",
    "SOLIC_GASTOS_ITEMS",
    # ── Catálogos (lookups) ────────────────────────────────────────────────
    "JURISDICCIONES",
    "TIPOS_COMPROB",
    "TIPO_DOC_RES",
]


# ─── Conexión ─────────────────────────────────────────────────────────────────

def get_connection() -> oracledb.Connection:
    # Thick mode requerido para Oracle < 12.2
    try:
        oracle_client_dir = os.getenv("ORACLE_CLIENT_LIB_DIR") or os.getenv("ORACLE_CLIENT_DIR")
        oracledb.init_oracle_client(lib_dir=oracle_client_dir or None)
        print(f"[thick mode] Oracle Instant Client habilitado desde: {oracle_client_dir or 'LD_LIBRARY_PATH'}")
    except Exception as e:
        if "already been initialized" not in str(e):
            print(f"[thin mode] No se pudo inicializar Oracle Instant Client: {e}")
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
    """Elige la columna de fecha más apropiada para filtrar los últimos N meses."""
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


# ─── Exportar tabla ───────────────────────────────────────────────────────────

def export_table(
    cursor: oracledb.Cursor,
    table: str,
    columns: list[dict],
    date_col: str | None,
    since: datetime,
    output_dir: Path,
    timestamp: str,
    full_load: bool,
    ejercicio: int | None = None,
) -> dict:
    col_names = [c["name"] for c in columns]
    col_list  = ", ".join(col_names)
    qualified = f"{SCHEMA}.{table}"

    if ejercicio is not None:
        sql = f"SELECT {col_list} FROM {qualified} WHERE EJERCICIO = :1"
        params = [ejercicio]
        mode = f"ejercicio={ejercicio}"
    elif full_load or date_col is None:
        sql = f"SELECT {col_list} FROM {qualified}"
        params: list = []
        mode = "completo"
    else:
        sql = (
            f"SELECT {col_list} FROM {qualified} "
            f"WHERE {date_col} >= :1"
        )
        params = [since]
        mode = f"desde {since.date()} via {date_col}"

    cursor.execute(sql, params)

    safe_name  = table.lower()
    csv_path   = output_dir / f"{safe_name}_{timestamp}.csv"

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
        description="Exporta los últimos N meses de cada tabla RAFAM a CSV"
    )
    parser.add_argument(
        "--months", type=int, default=3,
        help="Cantidad de meses hacia atrás a exportar (default: 3)",
    )
    parser.add_argument(
        "--tables", metavar="T1,T2",
        help="Lista de tablas separadas por coma. Default: todas.",
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
    since      = datetime.now() - timedelta(days=args.months * 30)
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
            print(f"  ⚠️  {table}: sin columna DATE detectada → export completo")
            full_load = True

        try:
            result = export_table(
                cursor, table, columns, date_col,
                since, output_dir, timestamp, full_load,
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
