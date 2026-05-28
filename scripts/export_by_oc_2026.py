#!/usr/bin/env python3
"""export_by_oc_2026.py — Exporta datos RAFAM relacionados con OC de 2026.

Estrategia:
  1. Exporta TODAS las OC de EJERCICIO=2026.
  2. Descubre OC de 2025 referenciadas por OP de 2026 (vía CTA_HOJA_DE_RUTA).
  3. Exporta también esas OC de 2025.
  4. Para cada tabla dependiente, filtra sólo los registros vinculados
     a las OC exportadas o a OP de 2026.
  5. Catálogos se exportan completos (son chicos).

Configuración via .env:
    RAFAM_SOURCE_HOST, RAFAM_SOURCE_PORT, RAFAM_SOURCE_SERVICE,
    RAFAM_SOURCE_USER, RAFAM_SOURCE_PASSWORD
    ORACLE_CLIENT_DIR  (opcional, solo si se usa Oracle Instant Client)

Uso:
    python scripts/export_by_oc_2026.py
    python scripts/export_by_oc_2026.py --ejercicio 2026
    python scripts/export_by_oc_2026.py --output-dir output/mi_carpeta
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

RAFAM_SOURCE_HOST = os.getenv("RAFAM_SOURCE_HOST", "10.10.91.241")
RAFAM_SOURCE_PORT = int(os.getenv("RAFAM_SOURCE_PORT", 1521))
RAFAM_SOURCE_SERVICE = os.getenv("RAFAM_SOURCE_SERVICE", "BDRAFAM")
RAFAM_SOURCE_USER = os.getenv("RAFAM_SOURCE_USER")
RAFAM_SOURCE_PASSWORD = os.getenv("RAFAM_SOURCE_PASSWORD")
SCHEMA = "OWNER_RAFAM"

DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "rafam_oc_2026"


# ─── Conexión ─────────────────────────────────────────────────────────────────

def get_connection() -> oracledb.Connection:
    try:
        oracle_client_dir = os.getenv("ORACLE_CLIENT_LIB_DIR") or os.getenv("ORACLE_CLIENT_DIR")
        oracledb.init_oracle_client(lib_dir=oracle_client_dir or None)
        print(f"[thick mode] Oracle Instant Client: {oracle_client_dir or 'LD_LIBRARY_PATH'}")
    except Exception as e:
        if "already been initialized" not in str(e):
            print(f"[thin mode] No Oracle Instant Client: {e}")
    dsn = oracledb.makedsn(RAFAM_SOURCE_HOST, RAFAM_SOURCE_PORT, service_name=RAFAM_SOURCE_SERVICE)
    conn = oracledb.connect(user=RAFAM_SOURCE_USER, password=RAFAM_SOURCE_PASSWORD, dsn=dsn)
    print(f"✅ Conectado a [{RAFAM_SOURCE_SERVICE}] en {RAFAM_SOURCE_HOST}:{RAFAM_SOURCE_PORT}")
    return conn


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_table_columns(cursor: oracledb.Cursor, table: str) -> list[str]:
    """Devuelve lista de nombres de columnas en orden."""
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM   ALL_TAB_COLUMNS
        WHERE  OWNER = :1 AND TABLE_NAME = :2
        ORDER BY COLUMN_ID
        """,
        [SCHEMA, table],
    )
    return [row[0] for row in cursor.fetchall()]


def table_exists(cursor: oracledb.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = :1 AND TABLE_NAME = :2",
        [SCHEMA, table],
    )
    return cursor.fetchone()[0] > 0


def view_exists(cursor: oracledb.Cursor, view: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM ALL_VIEWS WHERE OWNER = :1 AND VIEW_NAME = :2",
        [SCHEMA, view],
    )
    return cursor.fetchone()[0] > 0


def write_csv(
    cursor: oracledb.Cursor,
    sql: str,
    params: list,
    col_names: list[str],
    csv_path: Path,
) -> int:
    """Ejecuta la query y escribe resultados a CSV. Devuelve nro de filas."""
    cursor.execute(sql, params)
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
    return row_count


def export_full_table(
    cursor: oracledb.Cursor, table: str, output_dir: Path, timestamp: str,
) -> dict:
    """Exporta una tabla completa (catálogos)."""
    cols = get_table_columns(cursor, table)
    col_list = ", ".join(cols)
    sql = f"SELECT {col_list} FROM {SCHEMA}.{table}"
    csv_path = output_dir / f"{table.lower()}_{timestamp}.csv"
    rows = write_csv(cursor, sql, [], cols, csv_path)
    return {"table": table, "rows": rows, "mode": "completo", "file": csv_path.name}


# ─── Descubrimiento de OC referenciadas por OP 2026 ──────────────────────────

def discover_oc_from_op(
    cursor: oracledb.Cursor, ejercicio_op: int, ejercicio_oc_principal: int,
) -> list[tuple[int, int, int]]:
    """Devuelve (EJERCICIO, UNI_COMPRA, NRO_OC) de OCs de ejercicios anteriores
    referenciadas por OP del ejercicio indicado, usando CTA_HOJA_DE_RUTA."""
    sql = f"""
        SELECT DISTINCT OC_EJERCICIO, OC_UNI_COMPRA, OC_NRO
        FROM   {SCHEMA}.CTA_HOJA_DE_RUTA
        WHERE  OP_EJERCICIO = :1
          AND  OC_EJERCICIO IS NOT NULL
          AND  OC_NRO IS NOT NULL
          AND  OC_EJERCICIO != :2
    """
    cursor.execute(sql, [ejercicio_op, ejercicio_oc_principal])
    return [(int(r[0]), int(r[1]), int(r[2])) for r in cursor.fetchall()]


def discover_proveedores(
    cursor: oracledb.Cursor,
    ejercicio_oc: int,
    extra_oc_keys: list[tuple[int, int, int]],
    ejercicio_op: int,
) -> list[int]:
    """Devuelve lista de COD_PROV referenciados por OC y OP exportadas."""
    provs: set[int] = set()

    # Proveedores de OC principales (ejercicio_oc)
    cursor.execute(
        f"SELECT DISTINCT COD_PROV FROM {SCHEMA}.ORDEN_COMPRA WHERE EJERCICIO = :1",
        [ejercicio_oc],
    )
    provs.update(int(r[0]) for r in cursor.fetchall())

    # Proveedores de OC extra (2025, etc.)
    for ej, uni, nro in extra_oc_keys:
        cursor.execute(
            f"""SELECT DISTINCT COD_PROV FROM {SCHEMA}.ORDEN_COMPRA
                WHERE EJERCICIO = :1 AND UNI_COMPRA = :2 AND NRO_OC = :3""",
            [ej, uni, nro],
        )
        provs.update(int(r[0]) for r in cursor.fetchall())

    # Proveedores de OP
    cursor.execute(
        f"SELECT DISTINCT COD_PROV FROM {SCHEMA}.ORDEN_PAGO WHERE EJERCICIO = :1",
        [ejercicio_op],
    )
    provs.update(int(r[0]) for r in cursor.fetchall())

    return sorted(provs)


# ─── Exportaciones específicas ────────────────────────────────────────────────

def export_orden_compra(
    cursor: oracledb.Cursor,
    ejercicio: int,
    extra_oc_keys: list[tuple[int, int, int]],
    output_dir: Path,
    timestamp: str,
) -> dict:
    """Exporta OC del ejercicio + OC extra descubiertas."""
    cols = get_table_columns(cursor, "ORDEN_COMPRA")
    col_list = ", ".join(cols)

    if extra_oc_keys:
        # Construir condición para OC extra
        oc_conditions = " OR ".join(
            f"(EJERCICIO = {ej} AND UNI_COMPRA = {uni} AND NRO_OC = {nro})"
            for ej, uni, nro in extra_oc_keys
        )
        sql = f"""
            SELECT {col_list} FROM {SCHEMA}.ORDEN_COMPRA
            WHERE EJERCICIO = :1 OR ({oc_conditions})
        """
    else:
        sql = f"SELECT {col_list} FROM {SCHEMA}.ORDEN_COMPRA WHERE EJERCICIO = :1"

    csv_path = output_dir / f"orden_compra_{timestamp}.csv"
    rows = write_csv(cursor, sql, [ejercicio], cols, csv_path)
    mode = f"ejercicio={ejercicio}"
    if extra_oc_keys:
        mode += f" + {len(extra_oc_keys)} OC extra de otros ejercicios"
    return {"table": "ORDEN_COMPRA", "rows": rows, "mode": mode, "file": csv_path.name}


def export_oc_items(
    cursor: oracledb.Cursor,
    ejercicio: int,
    extra_oc_keys: list[tuple[int, int, int]],
    output_dir: Path,
    timestamp: str,
) -> dict:
    """Exporta OC_ITEMS para las mismas OC."""
    cols = get_table_columns(cursor, "OC_ITEMS")
    col_list = ", ".join(cols)

    if extra_oc_keys:
        oc_conditions = " OR ".join(
            f"(EJERCICIO = {ej} AND UNI_COMPRA = {uni} AND NRO_OC = {nro})"
            for ej, uni, nro in extra_oc_keys
        )
        sql = f"""
            SELECT {col_list} FROM {SCHEMA}.OC_ITEMS
            WHERE EJERCICIO = :1 OR ({oc_conditions})
        """
    else:
        sql = f"SELECT {col_list} FROM {SCHEMA}.OC_ITEMS WHERE EJERCICIO = :1"

    csv_path = output_dir / f"oc_items_{timestamp}.csv"
    rows = write_csv(cursor, sql, [ejercicio], cols, csv_path)
    mode = f"ejercicio={ejercicio}"
    if extra_oc_keys:
        mode += f" + items de {len(extra_oc_keys)} OC extra"
    return {"table": "OC_ITEMS", "rows": rows, "mode": mode, "file": csv_path.name}


def export_by_ejercicio(
    cursor: oracledb.Cursor,
    table: str,
    ejercicio: int,
    output_dir: Path,
    timestamp: str,
) -> dict:
    """Exporta tabla filtrando por EJERCICIO."""
    cols = get_table_columns(cursor, table)
    col_list = ", ".join(cols)
    sql = f"SELECT {col_list} FROM {SCHEMA}.{table} WHERE EJERCICIO = :1"
    csv_path = output_dir / f"{table.lower()}_{timestamp}.csv"
    rows = write_csv(cursor, sql, [ejercicio], cols, csv_path)
    return {"table": table, "rows": rows, "mode": f"ejercicio={ejercicio}", "file": csv_path.name}


def export_proveedores(
    cursor: oracledb.Cursor,
    cod_provs: list[int],
    output_dir: Path,
    timestamp: str,
) -> dict:
    """Exporta solo los proveedores referenciados."""
    cols = get_table_columns(cursor, "PROVEEDORES")
    col_list = ", ".join(cols)

    # Oracle IN tiene límite de 1000 elementos; chunking si necesario
    csv_path = output_dir / f"proveedores_{timestamp}.csv"
    total_rows = 0

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)

        for i in range(0, len(cod_provs), 900):
            chunk = cod_provs[i : i + 900]
            placeholders = ", ".join(f":{j+1}" for j in range(len(chunk)))
            sql = f"SELECT {col_list} FROM {SCHEMA}.PROVEEDORES WHERE COD_PROV IN ({placeholders})"
            cursor.execute(sql, chunk)
            while True:
                batch = cursor.fetchmany(5000)
                if not batch:
                    break
                for row in batch:
                    writer.writerow([
                        v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v
                        for v in row
                    ])
                total_rows += len(batch)

    return {
        "table": "PROVEEDORES",
        "rows": total_rows,
        "mode": f"{len(cod_provs)} proveedores vinculados a OC/OP",
        "file": csv_path.name,
    }


def export_cta_comprob(
    cursor: oracledb.Cursor,
    ejercicio: int,
    output_dir: Path,
    timestamp: str,
) -> dict:
    """Exporta CTA_COMPROB vinculados a OP del ejercicio via ORDEN_PAGO_IMPUT."""
    cols = get_table_columns(cursor, "CTA_COMPROB")
    col_list = ", ".join(f"cc.{c}" for c in cols)

    sql = f"""
        SELECT DISTINCT {col_list}
        FROM   {SCHEMA}.CTA_COMPROB cc
        JOIN   {SCHEMA}.ORDEN_PAGO_IMPUT opi
          ON   opi.EJERCICIO      = cc.EJERCICIO
          AND  opi.NRO_REG_COMP   = cc.NRO_REG_COMP
          AND  opi.TIPO_COMPROB   = cc.TIPO
          AND  opi.NRO_COMPROB    = cc.NRO_COMPROB
          AND  opi.COD_PROV       = cc.COD_PROV
        WHERE  opi.EJERCICIO = :1
    """
    csv_path = output_dir / f"cta_comprob_{timestamp}.csv"
    rows = write_csv(cursor, sql, [ejercicio], cols, csv_path)
    return {
        "table": "CTA_COMPROB",
        "rows": rows,
        "mode": f"vinculados a OP ejercicio={ejercicio}",
        "file": csv_path.name,
    }


def export_reg_comp(
    cursor: oracledb.Cursor,
    ejercicio: int,
    extra_oc_keys: list[tuple[int, int, int]],
    output_dir: Path,
    timestamp: str,
) -> dict:
    """Exporta REG_COMP vinculados a las OC exportadas."""
    cols = get_table_columns(cursor, "REG_COMP")
    col_list = ", ".join(cols)

    if extra_oc_keys:
        # REG_COMP tiene EJERCICIO, UNI_COMPRA, NRO_OC
        oc_conditions = " OR ".join(
            f"(EJERCICIO = {ej} AND UNI_COMPRA = {uni} AND NRO_OC = {nro})"
            for ej, uni, nro in extra_oc_keys
        )
        sql = f"""
            SELECT {col_list} FROM {SCHEMA}.REG_COMP
            WHERE EJERCICIO = :1 OR ({oc_conditions})
        """
    else:
        sql = f"SELECT {col_list} FROM {SCHEMA}.REG_COMP WHERE EJERCICIO = :1"

    csv_path = output_dir / f"reg_comp_{timestamp}.csv"
    rows = write_csv(cursor, sql, [ejercicio], cols, csv_path)
    mode = f"ejercicio={ejercicio}"
    if extra_oc_keys:
        mode += f" + vinculados a {len(extra_oc_keys)} OC extra"
    return {"table": "REG_COMP", "rows": rows, "mode": mode, "file": csv_path.name}


def export_retenciones(
    cursor: oracledb.Cursor,
    ejercicio: int,
    output_dir: Path,
    timestamp: str,
) -> dict:
    """Exporta RETENCIONES del ejercicio (vinculadas a OP via NRO_CANCE)."""
    cols = get_table_columns(cursor, "RETENCIONES")
    col_list = ", ".join(cols)
    sql = f"SELECT {col_list} FROM {SCHEMA}.RETENCIONES WHERE EJERCICIO = :1"
    csv_path = output_dir / f"retenciones_{timestamp}.csv"
    rows = write_csv(cursor, sql, [ejercicio], cols, csv_path)
    return {"table": "RETENCIONES", "rows": rows, "mode": f"ejercicio={ejercicio}", "file": csv_path.name}


def export_cta_hoja_de_ruta(
    cursor: oracledb.Cursor,
    ejercicio: int,
    extra_oc_keys: list[tuple[int, int, int]],
    output_dir: Path,
    timestamp: str,
) -> dict:
    """Exporta filas de CTA_HOJA_DE_RUTA vinculadas a OC/OP del ejercicio."""
    cols = get_table_columns(cursor, "CTA_HOJA_DE_RUTA")
    col_list = ", ".join(cols)

    conditions = ["OP_EJERCICIO = :1", "OC_EJERCICIO = :1"]
    if extra_oc_keys:
        for ej, uni, nro in extra_oc_keys:
            conditions.append(
                f"(OC_EJERCICIO = {ej} AND OC_UNI_COMPRA = {uni} AND OC_NRO = {nro})"
            )

    where = " OR ".join(conditions)
    sql = f"SELECT {col_list} FROM {SCHEMA}.CTA_HOJA_DE_RUTA WHERE {where}"
    csv_path = output_dir / f"cta_hoja_de_ruta_{timestamp}.csv"
    rows = write_csv(cursor, sql, [ejercicio], cols, csv_path)
    return {
        "table": "CTA_HOJA_DE_RUTA",
        "rows": rows,
        "mode": f"vinculados a OC/OP ejercicio={ejercicio}",
        "file": csv_path.name,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporta datos RAFAM relacionados con OC de un ejercicio"
    )
    parser.add_argument(
        "--ejercicio", type=int, default=2026,
        help="Ejercicio principal de OC a exportar (default: 2026)",
    )
    parser.add_argument(
        "--output-dir", metavar="DIR", default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directorio de salida (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    ejercicio = args.ejercicio
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not RAFAM_SOURCE_USER or not RAFAM_SOURCE_PASSWORD:
        print("❌ Faltan RAFAM_SOURCE_USER / RAFAM_SOURCE_PASSWORD en .env", file=sys.stderr)
        sys.exit(1)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.arraysize = 5000

    results: list[dict] = []
    skipped: list[str] = []

    # ══════════════════════════════════════════════════════════════════════════
    # Fase 1: Descubrir OC de otros ejercicios referenciadas por OP del ejercicio
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'═' * 60}")
    print(f"  Fase 1: Descubrimiento de OC vinculadas a OP {ejercicio}")
    print(f"{'═' * 60}")

    extra_oc_keys: list[tuple[int, int, int]] = []
    if view_exists(cursor, "CTA_HOJA_DE_RUTA"):
        extra_oc_keys = discover_oc_from_op(cursor, ejercicio, ejercicio)
        if extra_oc_keys:
            # Agrupar por ejercicio para el reporte
            by_ej: dict[int, int] = {}
            for ej, _, _ in extra_oc_keys:
                by_ej[ej] = by_ej.get(ej, 0) + 1
            for ej, count in sorted(by_ej.items()):
                print(f"  📎 Encontradas {count} OC de ejercicio {ej} vinculadas a OP {ejercicio}")
        else:
            print(f"  ✓ No hay OC de otros ejercicios vinculadas a OP {ejercicio}")
    else:
        print("  ⚠️  Vista CTA_HOJA_DE_RUTA no existe, no se pueden descubrir OC extra")

    # ══════════════════════════════════════════════════════════════════════════
    # Fase 2: Exportar tablas principales
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'═' * 60}")
    print(f"  Fase 2: Exportación (ejercicio principal = {ejercicio})")
    print(f"{'═' * 60}\n")

    # ── ORDEN_COMPRA ───────────────────────────────────────────────────────
    try:
        r = export_orden_compra(cursor, ejercicio, extra_oc_keys, output_dir, timestamp)
        results.append(r)
        print(f"  🛒 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ ORDEN_COMPRA: {exc}", file=sys.stderr)
        skipped.append("ORDEN_COMPRA")

    # ── OC_ITEMS ───────────────────────────────────────────────────────────
    try:
        r = export_oc_items(cursor, ejercicio, extra_oc_keys, output_dir, timestamp)
        results.append(r)
        print(f"  🛒 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ OC_ITEMS: {exc}", file=sys.stderr)
        skipped.append("OC_ITEMS")

    # ── ORDEN_PAGO ─────────────────────────────────────────────────────────
    try:
        r = export_by_ejercicio(cursor, "ORDEN_PAGO", ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  💰 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ ORDEN_PAGO: {exc}", file=sys.stderr)
        skipped.append("ORDEN_PAGO")

    # ── ORDEN_PAGO_IMPUT ───────────────────────────────────────────────────
    try:
        r = export_by_ejercicio(cursor, "ORDEN_PAGO_IMPUT", ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  💰 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ ORDEN_PAGO_IMPUT: {exc}", file=sys.stderr)
        skipped.append("ORDEN_PAGO_IMPUT")

    # ── ORDEN_PAGO_DEDUC ──────────────────────────────────────────────────
    try:
        r = export_by_ejercicio(cursor, "ORDEN_PAGO_DEDUC", ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  💰 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ ORDEN_PAGO_DEDUC: {exc}", file=sys.stderr)
        skipped.append("ORDEN_PAGO_DEDUC")

    # ── CTA_COMPROB (vinculados a OP del ejercicio) ───────────────────────
    try:
        r = export_cta_comprob(cursor, ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  📄 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ CTA_COMPROB: {exc}", file=sys.stderr)
        skipped.append("CTA_COMPROB")

    # ── REG_COMP (vinculados a OC exportadas) ─────────────────────────────
    try:
        r = export_reg_comp(cursor, ejercicio, extra_oc_keys, output_dir, timestamp)
        results.append(r)
        print(f"  📄 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ REG_COMP: {exc}", file=sys.stderr)
        skipped.append("REG_COMP")

    # ── RETENCIONES ────────────────────────────────────────────────────────
    try:
        r = export_retenciones(cursor, ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  📄 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ RETENCIONES: {exc}", file=sys.stderr)
        skipped.append("RETENCIONES")

    # ── PROVEEDORES (sólo los vinculados) ─────────────────────────────────
    try:
        cod_provs = discover_proveedores(cursor, ejercicio, extra_oc_keys, ejercicio)
        r = export_proveedores(cursor, cod_provs, output_dir, timestamp)
        results.append(r)
        print(f"  👤 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ PROVEEDORES: {exc}", file=sys.stderr)
        skipped.append("PROVEEDORES")

    # ── SOLIC_GASTOS ───────────────────────────────────────────────────────
    try:
        r = export_by_ejercicio(cursor, "SOLIC_GASTOS", ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  📋 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ SOLIC_GASTOS: {exc}", file=sys.stderr)
        skipped.append("SOLIC_GASTOS")

    # ── SOLIC_GASTOS_ITEMS ─────────────────────────────────────────────────
    try:
        r = export_by_ejercicio(cursor, "SOLIC_GASTOS_ITEMS", ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  📋 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ SOLIC_GASTOS_ITEMS: {exc}", file=sys.stderr)
        skipped.append("SOLIC_GASTOS_ITEMS")

    # ── PEDIDOS ────────────────────────────────────────────────────────────
    try:
        r = export_by_ejercicio(cursor, "PEDIDOS", ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  📋 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ PEDIDOS: {exc}", file=sys.stderr)
        skipped.append("PEDIDOS")

    # ── PED_ITEMS ──────────────────────────────────────────────────────────
    try:
        r = export_by_ejercicio(cursor, "PED_ITEMS", ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  📋 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ PED_ITEMS: {exc}", file=sys.stderr)
        skipped.append("PED_ITEMS")

    # ── ADJUDICACIONES ─────────────────────────────────────────────────────
    try:
        r = export_by_ejercicio(cursor, "ADJUDICACIONES", ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  📋 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ ADJUDICACIONES: {exc}", file=sys.stderr)
        skipped.append("ADJUDICACIONES")

    # ── ADJUDICACIONES_ITEMS ───────────────────────────────────────────────
    try:
        r = export_by_ejercicio(cursor, "ADJUDICACIONES_ITEMS", ejercicio, output_dir, timestamp)
        results.append(r)
        print(f"  📋 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
    except oracledb.DatabaseError as exc:
        print(f"  ❌ ADJUDICACIONES_ITEMS: {exc}", file=sys.stderr)
        skipped.append("ADJUDICACIONES_ITEMS")

    # ── CTA_HOJA_DE_RUTA (vista pivot) ────────────────────────────────────
    if view_exists(cursor, "CTA_HOJA_DE_RUTA"):
        try:
            r = export_cta_hoja_de_ruta(cursor, ejercicio, extra_oc_keys, output_dir, timestamp)
            results.append(r)
            print(f"  🔗 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
        except oracledb.DatabaseError as exc:
            print(f"  ❌ CTA_HOJA_DE_RUTA: {exc}", file=sys.stderr)
            skipped.append("CTA_HOJA_DE_RUTA")

    # ══════════════════════════════════════════════════════════════════════════
    # Fase 3: Catálogos (export completo — son tablas chicas)
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'═' * 60}")
    print("  Fase 3: Catálogos (export completo)")
    print(f"{'═' * 60}\n")

    catalogos = ["JURISDICCIONES", "TIPOS_COMPROB", "TIPO_DOC_RES", "DEDUCCIONES"]
    for cat in catalogos:
        if not table_exists(cursor, cat):
            print(f"  ⚠️  {cat}: no encontrada, omitiendo")
            skipped.append(cat)
            continue
        try:
            r = export_full_table(cursor, cat, output_dir, timestamp)
            results.append(r)
            print(f"  📦 {r['table']:<30} {r['rows']:>8} filas  [{r['mode']}]")
        except oracledb.DatabaseError as exc:
            print(f"  ❌ {cat}: {exc}", file=sys.stderr)
            skipped.append(cat)

    cursor.close()
    conn.close()

    # ── Resumen ───────────────────────────────────────────────────────────────
    total_rows = sum(r["rows"] for r in results)
    print(f"\n{'─' * 60}")
    print(f"✅ Exportadas: {len(results)} tablas  |  {total_rows:,} filas totales")
    print(f"📁 Directorio: {output_dir}")
    if extra_oc_keys:
        by_ej: dict[int, int] = {}
        for ej, _, _ in extra_oc_keys:
            by_ej[ej] = by_ej.get(ej, 0) + 1
        for ej, count in sorted(by_ej.items()):
            print(f"📎 Incluidas {count} OC de ejercicio {ej} (referenciadas por OP {ejercicio})")
    if skipped:
        print(f"⚠️  Omitidas: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
