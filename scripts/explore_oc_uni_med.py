"""Conecta a Oracle RAFAM y extrae info de OC + unidades de medida.

Basado en el schema real (docs/rafam_schema_and_joins.md):
- OC_ITEMS NO tiene UNI_MED (sus columnas son: EJERCICIO, UNI_COMPRA,
  NRO_OC, ITEM_OC, DELEG_SOLIC, NRO_SOLIC, ITEM_REAL, DESCRIPCION,
  CANTIDAD, IMP_UNITARIO, CANT_RECIB, IMPORTE_EJER).
- UNI_MED está en PED_ITEMS (FK a CAT_UNI_MED).
- La cadena OC → UM pasa por:
  OC_ITEMS (DELEG_SOLIC, NRO_SOLIC) → SOLIC_GASTOS (NRO_PED) →
  PEDIDOS/PED_ITEMS (UNI_MED → CAT_UNI_MED).

Genera: docs/oc_uni_med_report.md

Uso:
    python scripts/explore_oc_uni_med.py
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

import oracledb

DB_HOST = os.getenv("RAFAM_SOURCE_HOST", os.getenv("DB_HOST", "10.10.91.241"))
DB_PORT = int(os.getenv("RAFAM_SOURCE_PORT", os.getenv("DB_PORT", "1521")))
DB_SERVICE = os.getenv("RAFAM_SOURCE_SERVICE", os.getenv("DB_SERVICE", "BDRAFAM"))
DB_USER = os.getenv("RAFAM_SOURCE_USER")
DB_PASSWORD = os.getenv("RAFAM_SOURCE_PASSWORD")
SCHEMA = "OWNER_RAFAM"


def _init_oracle():
    """Inicializa Oracle en thick mode si es posible (requerido para Oracle < 12.2)."""
    try:
        oracle_client_dir = os.getenv("ORACLE_CLIENT_LIB_DIR") or os.getenv("ORACLE_CLIENT_DIR")
        oracledb.init_oracle_client(lib_dir=oracle_client_dir or None)
        print(f"[thick mode] Oracle Instant Client habilitado desde: {oracle_client_dir or 'LD_LIBRARY_PATH'}")
    except Exception as e:
        if "already been initialized" not in str(e):
            print(f"[thin mode] No se pudo inicializar Oracle Instant Client: {e}")
            print("[aviso] Si la BD es Oracle < 12.1, instala Oracle Instant Client.")


def _connect():
    """Crea y devuelve una conexión oracledb."""
    if not DB_USER or not DB_PASSWORD:
        print("ERROR: Configurar RAFAM_SOURCE_USER y RAFAM_SOURCE_PASSWORD en .env")
        sys.exit(1)

    _init_oracle()
    dsn = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE)
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=dsn)
    print(f"Conectado a [{DB_SERVICE}] en {DB_HOST}:{DB_PORT}")
    return conn


def _safe_fetch(cursor, sql, label=""):
    """Ejecuta una query y devuelve las filas. Loguea errores sin abortar."""
    try:
        cursor.execute(sql)
        return cursor.fetchall()
    except oracledb.DatabaseError as exc:
        print(f"  [WARN] Error ejecutando {label or 'query'}: {exc}")
        return []


def _describe_table(cursor, schema, table_name):
    """Devuelve las columnas de una tabla desde ALL_TAB_COLUMNS."""
    rows = _safe_fetch(
        cursor,
        f"""
        SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE
        FROM ALL_TAB_COLUMNS
        WHERE OWNER = '{schema}' AND TABLE_NAME = '{table_name}'
        ORDER BY COLUMN_ID
        """,
        f"DESCRIBE {table_name}",
    )
    return rows


def main():
    conn = _connect()
    cursor = conn.cursor()

    lines = []
    lines.append("# Exploración OC + UNI_MED — Oracle RAFAM\n")
    lines.append(f"> Generado automáticamente desde `{DB_HOST}:{DB_PORT}/{DB_SERVICE}`\n")
    lines.append("---\n")

    # ── 0. Verificar qué tablas existen ──────────────────────────────────
    print("0/6  Verificando tablas disponibles ...")
    tables_to_check = [
        "OC_ITEMS", "ORDEN_COMPRA", "PED_ITEMS", "PEDIDOS",
        "SOLIC_GASTOS", "CAT_UNI_MED", "PROVEEDORES",
    ]
    available = _safe_fetch(
        cursor,
        f"""
        SELECT TABLE_NAME
        FROM ALL_TABLES
        WHERE OWNER = '{SCHEMA}'
          AND TABLE_NAME IN ({', '.join(f"'{t}'" for t in tables_to_check)})
        ORDER BY TABLE_NAME
        """,
        "ALL_TABLES check",
    )
    available_set = {row[0] for row in available}
    print(f"  Tablas disponibles: {sorted(available_set)}")

    lines.append("## 0. Tablas verificadas\n")
    for t in tables_to_check:
        status = "✅" if t in available_set else "❌ NO DISPONIBLE"
        lines.append(f"- `{t}`: {status}")
    lines.append("")

    # ── 1. Estructura de OC_ITEMS (columnas reales) ──────────────────────
    print("1/6  Describiendo OC_ITEMS ...")
    oc_items_cols = _describe_table(cursor, SCHEMA, "OC_ITEMS")

    lines.append("## 1. Estructura de OC_ITEMS (columnas reales)\n")
    if oc_items_cols:
        lines.append("| COLUMNA | TIPO | LARGO | NULLABLE |")
        lines.append("|---------|------|-------|----------|")
        for row in oc_items_cols:
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
        col_names = [r[0] for r in oc_items_cols]
        has_uni_med = "UNI_MED" in col_names
        lines.append(f"\n> **¿Tiene UNI_MED?** {'✅ SÍ' if has_uni_med else '❌ NO — UNI_MED está en PED_ITEMS'}")
    else:
        lines.append("_No se pudo describir OC_ITEMS._\n")
    lines.append("")

    # ── 2. Estructura de PED_ITEMS (tiene UNI_MED) ──────────────────────
    print("2/6  Describiendo PED_ITEMS ...")
    ped_items_cols = _describe_table(cursor, SCHEMA, "PED_ITEMS")

    lines.append("## 2. Estructura de PED_ITEMS (contiene UNI_MED)\n")
    if ped_items_cols:
        lines.append("| COLUMNA | TIPO | LARGO | NULLABLE |")
        lines.append("|---------|------|-------|----------|")
        for row in ped_items_cols:
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
    else:
        lines.append("_No se pudo describir PED_ITEMS._\n")
    lines.append("")

    # ── 3. Catálogo CAT_UNI_MED ──────────────────────────────────────────
    print("3/6  Extrayendo CAT_UNI_MED ...")
    if "CAT_UNI_MED" in available_set:
        cat_rows = _safe_fetch(
            cursor,
            f"SELECT CODIGO, DESCRIPCION FROM {SCHEMA}.CAT_UNI_MED ORDER BY CODIGO",
            "CAT_UNI_MED",
        )
        lines.append("## 3. Catálogo CAT_UNI_MED\n")
        if cat_rows:
            lines.append(f"Total: **{len(cat_rows)}** registros\n")
            lines.append("| CODIGO | DESCRIPCION |")
            lines.append("|--------|-------------|")
            for row in cat_rows:
                lines.append(f"| {row[0]} | {row[1]} |")
        else:
            lines.append("_Tabla existe pero no se pudieron obtener registros._\n")
    else:
        # CAT_UNI_MED no disponible — intentar extraer valores únicos de PED_ITEMS
        lines.append("## 3. CAT_UNI_MED\n")
        lines.append("> ⚠️ `CAT_UNI_MED` no está disponible (falta permiso SELECT o no existe en este schema).\n")
        lines.append("> Extrayendo valores distintos de `PED_ITEMS.UNI_MED` como alternativa.\n")

        ped_uni_rows = _safe_fetch(
            cursor,
            f"""
            SELECT DISTINCT UNI_MED
            FROM {SCHEMA}.PED_ITEMS
            ORDER BY UNI_MED
            """,
            "PED_ITEMS UNI_MED distintos",
        )
        if ped_uni_rows:
            lines.append(f"Valores distintos de `UNI_MED` en PED_ITEMS: **{len(ped_uni_rows)}**\n")
            lines.append("| UNI_MED (código) |")
            lines.append("|------------------|")
            for row in ped_uni_rows:
                lines.append(f"| {row[0]} |")
        else:
            lines.append("_No se pudieron obtener valores de PED_ITEMS.UNI_MED._\n")
        cat_rows = []
    lines.append("")

    # ── 4. UNI_MED usados en PED_ITEMS con conteo ───────────────────────
    print("4/6  Extrayendo UNI_MED distintos de PED_ITEMS con conteo ...")

    if "CAT_UNI_MED" in available_set:
        uni_med_sql = f"""
            SELECT
                pi.UNI_MED,
                cum.DESCRIPCION  AS UM_DESCRIPCION,
                COUNT(*)         AS CANT_ITEMS
            FROM {SCHEMA}.PED_ITEMS pi
            LEFT JOIN {SCHEMA}.CAT_UNI_MED cum
                ON pi.UNI_MED = cum.CODIGO
            GROUP BY pi.UNI_MED, cum.DESCRIPCION
            ORDER BY COUNT(*) DESC
        """
    else:
        uni_med_sql = f"""
            SELECT
                pi.UNI_MED,
                NULL            AS UM_DESCRIPCION,
                COUNT(*)        AS CANT_ITEMS
            FROM {SCHEMA}.PED_ITEMS pi
            GROUP BY pi.UNI_MED
            ORDER BY COUNT(*) DESC
        """

    uni_med_rows = _safe_fetch(cursor, uni_med_sql, "PED_ITEMS UNI_MED agrupado")

    lines.append("## 4. Valores de UNI_MED usados en PED_ITEMS\n")
    lines.append("Cada código de unidad de medida con su descripción del catálogo ")
    lines.append("y la cantidad de ítems de pedido que lo usan.\n")
    if uni_med_rows:
        lines.append(f"Total combinaciones distintas: **{len(uni_med_rows)}**\n")
        lines.append("| UNI_MED | DESCRIPCION | CANT_ITEMS |")
        lines.append("|---------|-------------|------------|")
        for row in uni_med_rows:
            uni_med = row[0] if row[0] is not None else "(NULL)"
            desc = row[1] if row[1] is not None else "(sin catálogo)"
            cant = row[2]
            lines.append(f"| {uni_med} | {desc} | {cant} |")
    else:
        lines.append("_No se pudieron obtener registros de PED_ITEMS._\n")
    lines.append("")

    # ── 5. Resumen ORDEN_COMPRA por ejercicio ────────────────────────────
    print("5/6  Extrayendo resumen de ORDEN_COMPRA por ejercicio ...")
    oc_summary = _safe_fetch(
        cursor,
        f"""
        SELECT
            EJERCICIO,
            COUNT(*)                 AS CANT_OCS,
            SUM(IMPORTE_TOT)         AS IMPORTE_TOTAL,
            MIN(FECH_OC)             AS FECHA_MIN,
            MAX(FECH_OC)             AS FECHA_MAX,
            COUNT(DISTINCT COD_PROV) AS PROVEEDORES_DISTINTOS
        FROM {SCHEMA}.ORDEN_COMPRA
        GROUP BY EJERCICIO
        ORDER BY EJERCICIO DESC
        """,
        "ORDEN_COMPRA resumen",
    )

    lines.append("## 5. Resumen de ORDEN_COMPRA por ejercicio\n")
    if oc_summary:
        lines.append("| EJERCICIO | CANT_OCS | IMPORTE_TOTAL | FECHA_MIN | FECHA_MAX | PROVEEDORES |")
        lines.append("|-----------|----------|---------------|-----------|-----------|-------------|")
        for row in oc_summary:
            ej = row[0]
            cant = row[1]
            importe = f"{row[2]:,.2f}" if row[2] is not None else "-"
            f_min = str(row[3])[:10] if row[3] else "-"
            f_max = str(row[4])[:10] if row[4] else "-"
            provs = row[5]
            lines.append(f"| {ej} | {cant} | {importe} | {f_min} | {f_max} | {provs} |")
    else:
        lines.append("_No se pudieron obtener registros de ORDEN_COMPRA._\n")
    lines.append("")

    # ── 6. Muestra de OC_ITEMS (30 del último ejercicio) ─────────────────
    print("6/6  Muestra de OC_ITEMS (30 ítems) ...")
    sample_rows = _safe_fetch(
        cursor,
        f"""
        SELECT
            oci.EJERCICIO,
            oci.UNI_COMPRA,
            oci.NRO_OC,
            oci.ITEM_OC,
            oci.DESCRIPCION,
            oci.CANTIDAD,
            oci.IMP_UNITARIO
        FROM {SCHEMA}.OC_ITEMS oci
        WHERE oci.EJERCICIO = (SELECT MAX(EJERCICIO) FROM {SCHEMA}.OC_ITEMS)
        AND ROWNUM <= 30
        ORDER BY oci.NRO_OC DESC, oci.ITEM_OC
        """,
        "OC_ITEMS sample",
    )

    lines.append("## 6. Muestra de OC_ITEMS (últimos 30 del ejercicio más reciente)\n")
    if sample_rows:
        lines.append("| EJERCICIO | UNI_COMPRA | NRO_OC | ITEM | DESCRIPCION | CANTIDAD | IMP_UNITARIO |")
        lines.append("|-----------|------------|--------|------|-------------|----------|--------------|")
        for row in sample_rows:
            desc = (str(row[4])[:50] + "…") if row[4] and len(str(row[4])) > 50 else (row[4] or "-")
            # Escapar pipes en descripción para no romper la tabla markdown
            desc = desc.replace("|", "\\|")
            cant = row[5] if row[5] is not None else "-"
            precio = f"{row[6]:,.5f}" if row[6] is not None else "-"
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {desc} | {cant} | {precio} |")
    else:
        lines.append("_No se pudieron obtener registros de muestra._\n")
    lines.append("")

    cursor.close()
    conn.close()

    # ── Escribir reporte ─────────────────────────────────────────────────
    output = REPO_ROOT / "docs" / "oc_uni_med_report.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        f.write("\n".join(lines))

    print(f"\n✅ Reporte generado: {output}")
    print(f"   Secciones:")
    print(f"     - Tablas verificadas: {len(available_set)}/{len(tables_to_check)}")
    print(f"     - UNI_MED en PED_ITEMS: {len(uni_med_rows)} valores distintos")
    print(f"     - ORDEN_COMPRA: {len(oc_summary)} ejercicios")
    if cat_rows:
        print(f"     - CAT_UNI_MED: {len(cat_rows)} registros")
    else:
        print(f"     - CAT_UNI_MED: no disponible (usé PED_ITEMS como fallback)")


if __name__ == "__main__":
    main()
