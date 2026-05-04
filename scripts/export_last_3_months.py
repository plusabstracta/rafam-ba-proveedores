#!/usr/bin/env python3
"""export_last_3_months.py — Exporta los últimos 3 meses de cada tabla a CSV.

Para tablas sin columna de fecha conocida hace un export completo (con aviso).
Los CSV se escriben en output/rafam_ultimos_3_meses/ con timestamp en el nombre.

Configuración via .env:
    DB_HOST, DB_PORT, DB_SERVICE, DB_USER, DB_PASSWORD
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

DB_HOST     = os.getenv("DB_HOST", "10.10.91.241")
DB_PORT     = int(os.getenv("DB_PORT", 1521))
DB_SERVICE  = os.getenv("DB_SERVICE", "BDRAFAM")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
SCHEMA      = "OWNER_RAFAM"

DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "rafam_ultimos_3_meses"

# ─── Columnas de fecha preferidas por tabla ───────────────────────────────────
# Si la tabla tiene varias columnas DATE, se usa la primera que aparezca aquí.
# Las tablas sin entrada se auto-detectan (se elige la primera DATE encontrada).
DATE_COL_PRIORITY: dict[str, list[str]] = {
    "PROVEEDORES":        ["FECHA_ULT_COMP", "FECHA_ALTA"],
    "PEDIDOS":            ["FECH_EMI"],
    "SOLIC_GASTOS":       ["FECH_SOLIC", "FECH_CONFIRM"],
    "ORDEN_COMPRA":       ["FECH_OC", "FECH_CONFIRM"],
    "ORDEN_PAGO":         ["FECH_OP", "FECH_CONFIRM"],
    "RECEPCION":          ["FECH_RECEP"],
    "ADJUDICACIONES":     ["FECH_ADJUD"],
    "DEVOLUCION":         ["FECH_DEVOL"],
    "EGRESOS":            ["FECH_EGR"],
    "EMBARGOS":           ["FECH_EMBARGO"],
    "REGUL_CAMBIO":       ["FECH_REGUL"],
    "REGUL_GASTOS":       ["FECH_REGUL"],
    "REGUL_GASTOS_EX":    ["FECH_REGUL"],
    "ORDEN_DEVOL":        ["FECH_DEVOL"],
    "ORDEN_REINT":        ["FECH_REINT"],
    "ORDEN_PAGOEA":       ["FECH_OP"],
    "REG_COMP":           ["FECH_REG"],
    "REG_DEVEN":          ["FECH_DEV"],
    "RG_COMP":            ["FECH_COMP"],
    "CTA_HOJA_DE_RUTA":   ["FECH_HOJA"],
    "RETENCIONES":        ["FECH_RETEN"],
    "DEDUCCIONES":        ["FECH_DEDUC"],
    "MOV_EXTRAPRES_DEV":  ["FECH_MOV"],
    "MOV_EXTRAPRES_PAG":  ["FECH_MOV"],
    "MOV_EXTRAPRES_REC":  ["FECH_MOV"],
    "MOV_PRES_DEV":       ["FECH_MOV"],
    "MOV_PRES_PAG":       ["FECH_MOV"],
    "MOV_PRES_COMP":      ["FECH_MOV"],
}

# Tablas que siempre se exportan completas (no tienen fecha útil)
FULL_LOAD_TABLES: set[str] = {
    "JURISDICCIONES",
    "PED_ITEMS",
    "OC_ITEMS",
    "SOLIC_GASTOS_ITEMS",
    "USUARIOS_JURISDICCIONES",
    "CALIFICACIONES",
    "DEPENDENCIAS",
    "ESTRUC_PROG",
    "FORMULARIO1", "FORMULARIO2", "FORMULARIO4",
    "FORMULARIOC1", "FORMULARIOC2", "FORMULARIOP4",
    "METAS_PROG",
    "CUOTAS_JURISDIC",
}

# Todas las tablas a exportar (mismo orden que explore_schema.py)
ALL_TABLES: list[str] = [
    # Core
    "PROVEEDORES",
    "JURISDICCIONES",
    "PEDIDOS",
    "PED_ITEMS",
    "SOLIC_GASTOS",
    "ORDEN_COMPRA",
    "OC_ITEMS",
    "ORDEN_PAGO",
    "RG_COMP",
    "CTA_HOJA_DE_RUTA",
    "RETENCIONES",
    "DEDUCCIONES",
    # Relacionadas con PROVEEDORES
    "ACT_IMP_PROV",
    "ADJUDICACIONES",
    "BENEFICIARIOS",
    "CESIONARIOS",
    "COTIZA_PROV",
    "COTIZA_PROV_ITEMS",
    "CTA_COMPROB",
    "CTA_CTACTE_MOVS",
    "CTA_PROVEEDORES_ALICUOTAS",
    "CTA_UTE",
    "CTR_DOCUM_PROV",
    "DATOS_PART_CONS",
    "DATOS_PART_CONT",
    "DEUFLO_PROV",
    "DEVOLUCION",
    "EGRESOS",
    "EMBARGOS",
    "HISTO_ESTADOS",
    "NOMINA_PROV",
    "ORDEN_PAGO_DEDUC_UTE",
    "ORDEN_PAGOEA_DEDUC_UTE",
    "ORDEN_REINT_PRESUP",
    "PER_AGENTES",
    "PER_AGENTES_HIST",
    "PER_CONCEPTOS_PROVEEDOR",
    "REGUL_CAMBIO_OCEA",
    "REGUL_CORREC_IMPUT",
    "REGUL_DESAF",
    "TES_DEPOSITOS_GARANTIAS",
    "VI_SUBRUB_PROV",
    # Relacionadas con JURISDICCIONES
    "CALCULO_MODIF",
    "CUOTAS_JURISDIC",
    "CTA_TMP_REG_DEVEN_IMP",
    "DEPENDENCIAS",
    "DEVENGAMIENTOS",
    "ESTRUC_PROG",
    "FORMULARIO1",
    "FORMULARIO2",
    "FORMULARIO4",
    "FORMULARIOC1",
    "FORMULARIOC2",
    "FORMULARIOP4",
    "INGRESOS",
    "ING_COD_INGRESOS_DET",
    "METAS_PROG",
    "MOV_PRES_COMP",
    "MOV_PRES_REC_DEV",
    "PER_CONCEPTOS_GASTOS_M",
    "PER_SELECCION_DET",
    "PRE_JURIS_RECURSOS",
    "REGUL_CORREC_RECUR_IMPUT",
    "REGUL_RECURSOS_EX_IMPUT",
    "REGUL_RETENCIONES",
    "SOLIC_GASTOS_ITEMS",
    "USUARIOS_JURISDICCIONES",
    # Relacionadas con ORDEN_PAGO
    "CTA_IMPUT_PERSONAL",
    "MOV_PRES_PAG",
    "REGUL_CAMBIO",
    # Relacionadas con ORDEN_COMPRA
    "OC_PLAN_ENT",
    "RECEPCION",
    # Relacionadas con PEDIDOS
    "PED_COTIZACIONES",
    # Relacionadas con DEDUCCIONES
    "ORDEN_PAGOEA_DEDUC",
    "ORDEN_PAGO_DEDUC",
    "REGUL_RETENCIONES_IMPUT",
    "RETENCIONES_REGDED",
    # Múltiples relaciones
    "MOV_EXTRAPRES_DEV",
    "MOV_EXTRAPRES_PAG",
    "MOV_EXTRAPRES_REC",
    "MOV_PRES_DEV",
    "ORDEN_DEVOL",
    "ORDEN_PAGOEA",
    "ORDEN_REINT",
    "REG_COMP",
    "REG_DEVEN",
    "REGUL_CAMBIO_PE_IMPUT",
    "REGUL_CORREC_EX_IMPUT",
    "REGUL_GASTOS",
    "REGUL_GASTOS_EX",
    "REGUL_OPE_DEVOL",
]


# ─── Conexión ─────────────────────────────────────────────────────────────────

def get_connection() -> oracledb.Connection:
    oracle_client_dir = os.getenv("ORACLE_CLIENT_DIR")
    if oracle_client_dir:
        oracledb.init_oracle_client(lib_dir=oracle_client_dir)
    dsn  = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE)
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=dsn)
    print(f"✅ Conectado a [{DB_SERVICE}] en {DB_HOST}:{DB_PORT}")
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
) -> dict:
    col_names = [c["name"] for c in columns]
    col_list  = ", ".join(col_names)
    qualified = f"{SCHEMA}.{table}"

    if full_load or date_col is None:
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

    if not DB_USER or not DB_PASSWORD:
        print("❌ Faltan DB_USER / DB_PASSWORD en .env", file=sys.stderr)
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
        date_col  = None if full_load else pick_date_column(table, columns)

        if not full_load and date_col is None:
            print(f"  ⚠️  {table}: sin columna DATE detectada → export completo")
            full_load = True

        try:
            result = export_table(
                cursor, table, columns, date_col,
                since, output_dir, timestamp, full_load,
            )
            results.append(result)
            icon = "📦" if full_load else "🗓️ "
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
