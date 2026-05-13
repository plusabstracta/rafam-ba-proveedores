"""
explore_schema.py — Dump legacy del esquema Oracle OWNER_RAFAM.

La documentacion canonica vive en docs/rafam_paxapos_source_of_truth.md.
Para evidencia completa usar scripts/generate_rafam_context.py.
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
OUTPUT_DIR = REPO_ROOT / "output" / "rafam_context"
OUTPUT_MD  = OUTPUT_DIR / "legacy_rafam_schema.md"

# ─── Entorno ─────────────────────────────────────────────────────────────────
load_dotenv(REPO_ROOT / ".env")

DB_HOST     = os.getenv("RAFAM_SOURCE_HOST", "10.10.91.241")
DB_PORT     = int(os.getenv("RAFAM_SOURCE_PORT", "1521"))
DB_SERVICE  = os.getenv("RAFAM_SOURCE_SERVICE", "BDRAFAM")
DB_USER     = os.getenv("RAFAM_SOURCE_USER")
DB_PASSWORD = os.getenv("RAFAM_SOURCE_PASSWORD")
SCHEMA      = "OWNER_RAFAM"

# Tablas RAFAM realmente necesarias para alimentar el cron RAFAM -> Paxapos.
# Justificación: Paxapos solo recibe centros_costo, proveedores, ordenes_compra,
# ordenes_pago (con retenciones inline) y gastos auto-creados. Todo lo demás
# (asientos, afectaciones, motivos de baja, cotizaciones, regulaciones,
# devengamientos, etc.) es estado interno RAFAM que se resuelve filtrando OC/OP
# confirmadas y NO se envía al endpoint /rafam/migracion/importar.
TARGET_TABLES: list[str] = [
    # ── Pasada 1: proveedores ──────────────────────────────────────────────
    "PROVEEDORES",
    # ── Pasada 2: órdenes de compra ────────────────────────────────────────
    "ORDEN_COMPRA",
    "OC_ITEMS",
    # ── Pasada 3: órdenes de pago + retenciones + vínculo a gastos ─────────
    "ORDEN_PAGO",
    "ORDEN_PAGO_IMPUT",   # bridge crítico OP ↔ CTA_COMPROB (reemplaza CTA_HOJA_DE_RUTA)
    "CTA_COMPROB",        # fuente de gasto_nro_comprobante (TIPO + NRO_COMPROB)
    "REG_COMP",           # eslabón OP -> SG -> RC -> CC
    "SOLIC_GASTOS",       # eslabón intermedio del JOIN OP -> CC
    "RETENCIONES",
    "DEDUCCIONES",        # resuelve tipo_impuesto_id (COD_RET -> nombre)
    # ── Resolución de items / mercadería (link OC_ITEMS ↔ PED_ITEMS) ───────
    "PEDIDOS",
    "PED_ITEMS",
    "ADJUDICACIONES",
    "ADJUDICACIONES_ITEMS",
    "SOLIC_GASTOS_ITEMS",
    # ── Catálogos (lookups locales para mapear, NO se envían a Paxapos) ────
    "JURISDICCIONES",     # mapea a centro_costo_id (_JURISDICCION_CENTRO_COSTO_MAP)
    "TIPOS_COMPROB",      # interpreta TIPO en CTA_COMPROB y arma PDV-NRO
    "TIPO_DOC_RES",       # tipo de documento del proveedor (CUIT/DNI)
]


# ─── Conexión ────────────────────────────────────────────────────────────────
def get_connection() -> oracledb.Connection:
    # Thick mode requerido para Oracle < 12.2
    try:
        oracle_client_dir = os.getenv("ORACLE_CLIENT_LIB_DIR") or os.getenv("ORACLE_CLIENT_DIR")
        oracledb.init_oracle_client(lib_dir=oracle_client_dir or None)
        print(f"[thick mode] Oracle Instant Client habilitado desde: {oracle_client_dir or 'LD_LIBRARY_PATH'}")
    except Exception as e:
        if "already been initialized" not in str(e):
            print(f"[thin mode] No se pudo inicializar Oracle Instant Client: {e}")
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
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        md = build_markdown(SCHEMA, tables_data)
        OUTPUT_MD.write_text(md, encoding="utf-8")
        print(f"\n💾 Esquema exportado → {OUTPUT_MD}")

    finally:
        cursor.close()
        conn.close()
        print("🔒 Conexión cerrada.\n")


if __name__ == "__main__":
    main()
