"""Conecta a Oracle RAFAM y extrae:

1. El catálogo completo de CAT_UNI_MED (unidades de medida).
2. Los valores DISTINTOS de UNI_MED usados en OC_ITEMS, con su descripción
   desde CAT_UNI_MED y la cantidad de ítems que usan cada uno.
3. Un resumen de ORDEN_COMPRA (cabecera de órdenes de compra) con totales y
   distribución por ejercicio.

Genera: docs/oc_uni_med_report.md
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


def main():
    conn = _connect()
    cursor = conn.cursor()

    lines = []
    lines.append("# Exploración OC + UNI_MED — Oracle RAFAM\n")
    lines.append(f"> Generado automáticamente desde `{DB_HOST}:{DB_PORT}/{DB_SERVICE}`\n")
    lines.append("---\n")

    # ── 1. Catálogo CAT_UNI_MED ──────────────────────────────────────────
    print("1/3  Extrayendo CAT_UNI_MED ...")
    cat_rows = _safe_fetch(
        cursor,
        f"SELECT CODIGO, DESCRIPCION FROM {SCHEMA}.CAT_UNI_MED ORDER BY CODIGO",
        "CAT_UNI_MED",
    )

    lines.append("## 1. Catálogo CAT_UNI_MED (Unidades de Medida RAFAM)\n")
    lines.append(f"Total: **{len(cat_rows)}** registros\n")
    if cat_rows:
        lines.append("| CODIGO | DESCRIPCION |")
        lines.append("|--------|-------------|")
        for row in cat_rows:
            lines.append(f"| {row[0]} | {row[1]} |")
    else:
        lines.append("_No se pudieron obtener registros de CAT_UNI_MED._\n")
    lines.append("")

    # ── 2. UNI_MED distintos usados en OC_ITEMS ─────────────────────────
    print("2/3  Extrayendo UNI_MED distintos de OC_ITEMS + CAT_UNI_MED ...")
    uni_med_rows = _safe_fetch(
        cursor,
        f"""
        SELECT
            oci.UNI_MED,
            cum.DESCRIPCION  AS UM_DESCRIPCION,
            COUNT(*)         AS CANT_ITEMS
        FROM {SCHEMA}.OC_ITEMS oci
        LEFT JOIN {SCHEMA}.CAT_UNI_MED cum
            ON oci.UNI_MED = cum.CODIGO
        GROUP BY oci.UNI_MED, cum.DESCRIPCION
        ORDER BY COUNT(*) DESC
        """,
        "OC_ITEMS UNI_MED",
    )

    lines.append("## 2. Valores de UNI_MED usados en OC_ITEMS\n")
    lines.append("Muestra cada código de unidad de medida con su descripción del catálogo ")
    lines.append("y la cantidad de ítems de OC que lo usan.\n")
    if uni_med_rows:
        lines.append(f"Total combinaciones distintas: **{len(uni_med_rows)}**\n")
        lines.append("| UNI_MED | DESCRIPCION (CAT_UNI_MED) | CANT_ITEMS |")
        lines.append("|---------|---------------------------|------------|")
        for row in uni_med_rows:
            uni_med = row[0] if row[0] is not None else "(NULL)"
            desc = row[1] if row[1] is not None else "(sin catálogo)"
            cant = row[2]
            lines.append(f"| {uni_med} | {desc} | {cant} |")
    else:
        lines.append("_No se pudieron obtener registros de OC_ITEMS._\n")
    lines.append("")

    # ── 3. Resumen ORDEN_COMPRA por ejercicio ────────────────────────────
    print("3/3  Extrayendo resumen de ORDEN_COMPRA por ejercicio ...")
    oc_summary = _safe_fetch(
        cursor,
        f"""
        SELECT
            EJERCICIO,
            COUNT(*)                     AS CANT_OCS,
            SUM(IMPORTE_TOT)             AS IMPORTE_TOTAL,
            MIN(FECH_OC)                 AS FECHA_MIN,
            MAX(FECH_OC)                 AS FECHA_MAX,
            COUNT(DISTINCT COD_PROV)     AS PROVEEDORES_DISTINTOS,
            COUNT(DISTINCT JURISDICCION) AS JURISDICCIONES_DISTINTAS
        FROM {SCHEMA}.ORDEN_COMPRA
        GROUP BY EJERCICIO
        ORDER BY EJERCICIO DESC
        """,
        "ORDEN_COMPRA resumen",
    )

    lines.append("## 3. Resumen de ORDEN_COMPRA por ejercicio\n")
    if oc_summary:
        lines.append("| EJERCICIO | CANT_OCS | IMPORTE_TOTAL | FECHA_MIN | FECHA_MAX | PROVEEDORES | JURISDICCIONES |")
        lines.append("|-----------|----------|---------------|-----------|-----------|-------------|----------------|")
        for row in oc_summary:
            ej = row[0]
            cant = row[1]
            importe = f"{row[2]:,.2f}" if row[2] is not None else "-"
            f_min = str(row[3])[:10] if row[3] else "-"
            f_max = str(row[4])[:10] if row[4] else "-"
            provs = row[5]
            juris = row[6]
            lines.append(f"| {ej} | {cant} | {importe} | {f_min} | {f_max} | {provs} | {juris} |")
    else:
        lines.append("_No se pudieron obtener registros de ORDEN_COMPRA._\n")
    lines.append("")

    # ── 4. Primeros 30 ítems de OC_ITEMS (muestra) ──────────────────────
    print("  Extra: Muestra de 30 OC_ITEMS ...")
    sample_rows = _safe_fetch(
        cursor,
        f"""
        SELECT
            oci.EJERCICIO,
            oci.UNI_COMPRA,
            oci.NRO_OC,
            oci.ITEM_OC,
            oci.DESCRIPCION,
            oci.UNI_MED,
            cum.DESCRIPCION AS UM_DESC,
            oci.CANT,
            oci.PRECIO_UNIT
        FROM {SCHEMA}.OC_ITEMS oci
        LEFT JOIN {SCHEMA}.CAT_UNI_MED cum
            ON oci.UNI_MED = cum.CODIGO
        WHERE oci.EJERCICIO = (SELECT MAX(EJERCICIO) FROM {SCHEMA}.OC_ITEMS)
        AND ROWNUM <= 30
        ORDER BY oci.EJERCICIO DESC, oci.NRO_OC DESC, oci.ITEM_OC
        """,
        "OC_ITEMS sample",
    )

    lines.append("## 4. Muestra de OC_ITEMS (últimos 30 del ejercicio más reciente)\n")
    if sample_rows:
        lines.append("| EJERCICIO | UNI_COMPRA | NRO_OC | ITEM | DESCRIPCION | UNI_MED | UM_DESC | CANT | PRECIO_UNIT |")
        lines.append("|-----------|------------|--------|------|-------------|---------|---------|------|-------------|")
        for row in sample_rows:
            desc = (str(row[4])[:40] + "…") if row[4] and len(str(row[4])) > 40 else (row[4] or "-")
            um = row[5] if row[5] is not None else "(NULL)"
            um_desc = row[6] if row[6] is not None else "-"
            cant = row[7] if row[7] is not None else "-"
            precio = f"{row[8]:,.2f}" if row[8] is not None else "-"
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {desc} | {um} | {um_desc} | {cant} | {precio} |")
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
    print(f"   Secciones: CAT_UNI_MED ({len(cat_rows)}), UNI_MED en OC_ITEMS ({len(uni_med_rows)}), "
          f"ORDEN_COMPRA ({len(oc_summary)})")


if __name__ == "__main__":
    main()
