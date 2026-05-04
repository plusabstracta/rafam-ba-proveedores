"""
explore_schema.py — Explora el esquema Oracle OWNER_RAFAM y genera docs/rafam_schema.md
Uso: python scripts/explore_schema.py
"""

import os
import sys
import oracledb
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path

# ─── Rutas ───────────────────────────────────────────────────────────────────
REPO_ROOT  = Path(__file__).resolve().parent.parent
DOCS_DIR   = REPO_ROOT / "docs"
OUTPUT_MD  = DOCS_DIR / "rafam_schema.md"

# ─── Entorno ─────────────────────────────────────────────────────────────────
load_dotenv(REPO_ROOT / ".env")

DB_HOST     = os.getenv("RAFAM_SOURCE_HOST", "10.10.91.241")
DB_PORT     = int(os.getenv("RAFAM_SOURCE_PORT", "1521"))
DB_SERVICE  = os.getenv("RAFAM_SOURCE_SERVICE", "BDRAFAM")
DB_USER     = os.getenv("RAFAM_SOURCE_USER")
DB_PASSWORD = os.getenv("RAFAM_SOURCE_PASSWORD")
SCHEMA      = "OWNER_RAFAM"

# Tablas de interés (vacío = todas las del schema)
TARGET_TABLES: list[str] = [
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
    # Relacionadas con múltiples
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


# ─── Conexión ────────────────────────────────────────────────────────────────
def get_connection() -> oracledb.Connection:
    oracle_client_dir = os.getenv("ORACLE_CLIENT_DIR")
    if oracle_client_dir:
        oracledb.init_oracle_client(lib_dir=oracle_client_dir)
    dsn  = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE)
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=dsn)
    print(f"✅ Conectado a [{DB_SERVICE}] en {DB_HOST}:{DB_PORT}")
    return conn


# ─── Queries al diccionario de datos ─────────────────────────────────────────
def list_tables(cursor: oracledb.Cursor, schema: str, filter_tables: list[str]) -> list[str]:
    """Devuelve las tablas del schema, opcionalmente filtradas."""
    if filter_tables:
        placeholders = ", ".join(f":{i+1}" for i in range(len(filter_tables)))
        sql = f"""
            SELECT TABLE_NAME
            FROM   ALL_TABLES
            WHERE  OWNER = :owner
              AND  TABLE_NAME IN ({placeholders})
            ORDER BY TABLE_NAME
        """
        cursor.execute(sql, [schema] + filter_tables)
    else:
        cursor.execute(
            "SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER = :1 ORDER BY TABLE_NAME",
            [schema],
        )
    return [row[0] for row in cursor.fetchall()]


def get_columns(cursor: oracledb.Cursor, schema: str, table: str) -> list[dict]:
    """Devuelve columnas con nombre, tipo, longitud, nullable y comentarios."""
    cursor.execute(
        """
        SELECT
            col.COLUMN_NAME,
            col.DATA_TYPE,
            col.DATA_LENGTH,
            col.DATA_PRECISION,
            col.DATA_SCALE,
            col.NULLABLE,
            col.DATA_DEFAULT,
            com.COMMENTS
        FROM   ALL_TAB_COLUMNS col
        LEFT JOIN ALL_COL_COMMENTS com
               ON  com.OWNER       = col.OWNER
               AND com.TABLE_NAME  = col.TABLE_NAME
               AND com.COLUMN_NAME = col.COLUMN_NAME
        WHERE  col.OWNER      = :1
          AND  col.TABLE_NAME = :2
        ORDER BY col.COLUMN_ID
        """,
        [schema, table],
    )
    cols = []
    for row in cursor.fetchall():
        cols.append({
            "name":      row[0],
            "type":      row[1],
            "length":    row[2],
            "precision": row[3],
            "scale":     row[4],
            "nullable":  row[5],
            "default":   row[6],
            "comment":   row[7],
        })
    return cols


def get_constraints(cursor: oracledb.Cursor, schema: str, table: str) -> dict:
    """Devuelve PKs y FKs de la tabla."""
    cursor.execute(
        """
        SELECT
            c.CONSTRAINT_NAME,
            c.CONSTRAINT_TYPE,
            cc.COLUMN_NAME,
            cc.POSITION,
            c.R_OWNER,
            c.R_CONSTRAINT_NAME
        FROM   ALL_CONSTRAINTS  c
        JOIN   ALL_CONS_COLUMNS cc
               ON  cc.OWNER           = c.OWNER
               AND cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME
        WHERE  c.OWNER      = :1
          AND  c.TABLE_NAME = :2
          AND  c.CONSTRAINT_TYPE IN ('P', 'R')
        ORDER BY c.CONSTRAINT_TYPE, cc.POSITION
        """,
        [schema, table],
    )
    pks: list[str] = []
    fks: list[dict] = []
    for row in cursor.fetchall():
        ctype = row[1]
        col   = row[2]
        if ctype == "P" and col not in pks:
            pks.append(col)
        elif ctype == "R":
            fks.append({
                "col":            col,
                "r_owner":        row[4],
                "r_constraint":   row[5],
            })
    return {"pks": pks, "fks": fks}


def resolve_fk_table(cursor: oracledb.Cursor, r_owner: str, r_constraint: str) -> str:
    """Resuelve el nombre de la tabla referenciada por una FK."""
    try:
        cursor.execute(
            "SELECT TABLE_NAME FROM ALL_CONSTRAINTS WHERE OWNER = :1 AND CONSTRAINT_NAME = :2",
            [r_owner, r_constraint],
        )
        row = cursor.fetchone()
        return f"{r_owner}.{row[0]}" if row else r_constraint
    except Exception:
        return r_constraint


# ─── Formato de tipo de columna ───────────────────────────────────────────────
def format_type(col: dict) -> str:
    dtype = col["type"]
    if dtype == "NUMBER":
        if col["precision"] and col["scale"] is not None:
            return f"NUMBER({col['precision']},{col['scale']})"
        if col["precision"]:
            return f"NUMBER({col['precision']})"
        return "NUMBER"
    if dtype in ("VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR"):
        return f"{dtype}({col['length']})"
    return dtype


# ─── Generador de Markdown ────────────────────────────────────────────────────
def build_markdown(schema: str, tables_data: list[dict]) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# Esquema RAFAM — `{schema}`",
        f"",
        f"> Generado automáticamente por `scripts/explore_schema.py` el {ts}",
        f"> **No editar manualmente** — regenerar ejecutando el script.",
        f"",
        f"## Índice de tablas",
        f"",
    ]
    for td in tables_data:
        anchor = td["name"].lower()
        lines.append(f"- [{td['name']}](#{anchor})")
    lines.append("")

    for td in tables_data:
        name = td["name"]
        cols = td["columns"]
        cons = td["constraints"]

        lines += [f"---", f"", f"## {name}", f""]

        # PKs
        if cons["pks"]:
            lines.append(f"**PK:** `{'`, `'.join(cons['pks'])}`  ")
        else:
            lines.append(f"**PK:** *(no encontrada)*  ")

        # FKs
        if cons["fks"]:
            fk_strs = [f"`{fk['col']}` → `{fk['ref_table']}`" for fk in cons["fks"]]
            lines.append(f"**FK:** {', '.join(fk_strs)}  ")
        lines.append("")

        # Columnas
        lines += [
            "| Columna | Tipo | Nulo | Default | Comentario |",
            "|---------|------|------|---------|------------|",
        ]
        for col in cols:
            nullable = "✓" if col["nullable"] == "Y" else "✗"
            default  = col["default"].strip() if col["default"] else ""
            comment  = (col["comment"] or "").replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| `{col['name']}` | `{format_type(col)}` | {nullable} | {default} | {comment} |"
            )
        lines.append("")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print(f"\n🔍 Explorando esquema {SCHEMA}\n" + "─" * 50)

    conn   = get_connection()
    cursor = conn.cursor()

    try:
        tables = list_tables(cursor, SCHEMA, TARGET_TABLES)
        if not tables:
            print(f"⚠️  No se encontraron tablas en {SCHEMA}. Verificá permisos y nombre del schema.")
            sys.exit(1)

        print(f"\n📦 Tablas encontradas ({len(tables)}):")
        for t in tables:
            print(f"   • {t}")
        print()

        tables_data = []
        for table in tables:
            print(f"  📋 Leyendo {table}...", end=" ")
            cols = get_columns(cursor, SCHEMA, table)
            cons = get_constraints(cursor, SCHEMA, table)

            # Resolver nombre de tabla referenciada en FKs
            for fk in cons["fks"]:
                fk["ref_table"] = resolve_fk_table(cursor, fk["r_owner"], fk["r_constraint"])

            tables_data.append({"name": table, "columns": cols, "constraints": cons})
            print(f"{len(cols)} columnas, {len(cons['pks'])} PK, {len(cons['fks'])} FK")

        # Escribir Markdown
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        md = build_markdown(SCHEMA, tables_data)
        OUTPUT_MD.write_text(md, encoding="utf-8")
        print(f"\n💾 Esquema exportado → {OUTPUT_MD}")

    finally:
        cursor.close()
        conn.close()
        print("🔒 Conexión cerrada.\n")


if __name__ == "__main__":
    main()
