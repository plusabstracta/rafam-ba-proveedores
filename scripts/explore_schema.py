"""
explore_schema.py — Genera documentación completa del esquema Oracle OWNER_RAFAM.

Produce un Markdown con:
  - Estructura de cada tabla (columnas, tipos, PKs, FKs)
  - Mapa de JOINs usados por el pipeline (INNER/LEFT/OUTER)
  - Diagrama Mermaid de relaciones entre tablas
  - Filtros y condiciones aplicados por entidad

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
OUTPUT_MD  = OUTPUT_DIR / "rafam_schema_and_joins.md"

# ─── Entorno ─────────────────────────────────────────────────────────────────
load_dotenv(REPO_ROOT / ".env")

DB_HOST     = os.getenv("RAFAM_SOURCE_HOST", "10.10.91.241")
DB_PORT     = int(os.getenv("RAFAM_SOURCE_PORT", "1521"))
DB_SERVICE  = os.getenv("RAFAM_SOURCE_SERVICE", "BDRAFAM")
DB_USER     = os.getenv("RAFAM_SOURCE_USER")
DB_PASSWORD = os.getenv("RAFAM_SOURCE_PASSWORD")
SCHEMA      = "OWNER_RAFAM"

# Tablas RAFAM necesarias para el pipeline RAFAM → Paxapos.
TARGET_TABLES: list[str] = [
    # ── Pasada 1: proveedores ──────────────────────────────────────────────
    "PROVEEDORES",
    # ── Pasada 2: órdenes de compra ────────────────────────────────────────
    "ORDEN_COMPRA",
    "OC_ITEMS",
    # ── Pasada 3: órdenes de pago + retenciones + vínculo a gastos ─────────
    "ORDEN_PAGO",
    "ORDEN_PAGO_IMPUT",
    "ORDEN_PAGO_DEDUC",
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


# ─── JOINs del pipeline (extraídos de src/source_repository.py) ──────────────
# Cada entrada: (entidad, tipo_join, tabla_izq, tabla_der, condiciones, nota)
PIPELINE_JOINS: list[dict] = [
    # ── Entidad: orden_compra ──────────────────────────────────────────────
    {
        "entity": "orden_compra",
        "join_type": "INNER JOIN",
        "left_table": "ORDEN_COMPRA",
        "right_table": "OC_ITEMS",
        "on": [
            "ORDEN_COMPRA.EJERCICIO = OC_ITEMS.EJERCICIO",
            "ORDEN_COMPRA.UNI_COMPRA = OC_ITEMS.UNI_COMPRA",
            "ORDEN_COMPRA.NRO_OC = OC_ITEMS.NRO_OC",
        ],
        "note": "Trae los ítems de cada OC. El cursor incremental aplica sobre ORDEN_COMPRA.",
    },
    {
        "entity": "orden_compra",
        "join_type": "LEFT JOIN",
        "left_table": "OC_ITEMS",
        "right_table": "SOLIC_GASTOS",
        "on": [
            "OC_ITEMS.EJERCICIO = SOLIC_GASTOS.EJERCICIO",
            "OC_ITEMS.DELEG_SOLIC = SOLIC_GASTOS.DELEG_SOLIC",
            "OC_ITEMS.NRO_SOLIC = SOLIC_GASTOS.NRO_SOLIC",
        ],
        "note": "Obtiene JURISDICCION de la solicitud de gasto vinculada al ítem.",
    },
    {
        "entity": "orden_compra",
        "join_type": "LEFT JOIN (subquery oc_to_cc)",
        "left_table": "ORDEN_COMPRA",
        "right_table": "REG_COMP → CTA_COMPROB",
        "on": [
            "ORDEN_COMPRA.EJERCICIO = oc_to_cc.OC_EJERCICIO",
            "ORDEN_COMPRA.UNI_COMPRA = oc_to_cc.OC_UNI_COMPRA",
            "ORDEN_COMPRA.NRO_OC = oc_to_cc.OC_NRO",
        ],
        "note": (
            "Subquery agrupada: REG_COMP JOIN CTA_COMPROB ON (EJERCICIO, NRO_REG_COMP). "
            "Filtra REG_COMP donde UNI_COMPRA y NRO_OC no son NULL. "
            "Devuelve MIN(NRO_COMPROB), MIN(TIPO), MIN(COD_PROV) por OC."
        ),
    },
    # ── Entidad: ped_items ─────────────────────────────────────────────────
    {
        "entity": "ped_items",
        "join_type": "LEFT JOIN",
        "left_table": "PED_ITEMS",
        "right_table": "PEDIDOS",
        "on": [
            "PED_ITEMS.EJERCICIO = PEDIDOS.EJERCICIO",
            "PED_ITEMS.NUM_PED = PEDIDOS.NUM_PED",
        ],
        "note": "Trae cabecera del pedido: FECH_EMI, OBSERVACIONES, CODIGO_DEP, COSTO_TOT.",
    },
    # ── Entidad: oc_items ──────────────────────────────────────────────────
    {
        "entity": "oc_items",
        "join_type": "INNER JOIN",
        "left_table": "OC_ITEMS",
        "right_table": "ORDEN_COMPRA",
        "on": [
            "OC_ITEMS.EJERCICIO = ORDEN_COMPRA.EJERCICIO",
            "OC_ITEMS.UNI_COMPRA = ORDEN_COMPRA.UNI_COMPRA",
            "OC_ITEMS.NRO_OC = ORDEN_COMPRA.NRO_OC",
        ],
        "note": "Trae cabecera OC: COD_PROV, FECH_OC, OBSERVACIONES, ESTADO_OC, etc.",
    },
    {
        "entity": "oc_items",
        "join_type": "LEFT JOIN",
        "left_table": "OC_ITEMS",
        "right_table": "SOLIC_GASTOS",
        "on": [
            "OC_ITEMS.EJERCICIO = SOLIC_GASTOS.EJERCICIO",
            "OC_ITEMS.DELEG_SOLIC = SOLIC_GASTOS.DELEG_SOLIC",
            "OC_ITEMS.NRO_SOLIC = SOLIC_GASTOS.NRO_SOLIC",
        ],
        "note": "Obtiene JURISDICCION.",
    },
    {
        "entity": "oc_items",
        "join_type": "LEFT JOIN (subquery oc_to_cc)",
        "left_table": "ORDEN_COMPRA",
        "right_table": "REG_COMP → CTA_COMPROB",
        "on": [
            "ORDEN_COMPRA.EJERCICIO = oc_to_cc.OC_EJERCICIO",
            "ORDEN_COMPRA.UNI_COMPRA = oc_to_cc.OC_UNI_COMPRA",
            "ORDEN_COMPRA.NRO_OC = oc_to_cc.OC_NRO",
        ],
        "note": "Mismo subquery oc_to_cc que en orden_compra.",
    },
    # ── Entidad: solic_gastos ──────────────────────────────────────────────
    {
        "entity": "solic_gastos",
        "join_type": "LEFT JOIN (subquery oc_prov)",
        "left_table": "SOLIC_GASTOS",
        "right_table": "OC_ITEMS → ORDEN_COMPRA",
        "on": [
            "SOLIC_GASTOS.EJERCICIO = oc_prov.EJERCICIO",
            "SOLIC_GASTOS.DELEG_SOLIC = oc_prov.DELEG_SOLIC",
            "SOLIC_GASTOS.NRO_SOLIC = oc_prov.NRO_SOLIC",
        ],
        "note": (
            "Subquery: OC_ITEMS JOIN ORDEN_COMPRA ON (EJERCICIO, UNI_COMPRA, NRO_OC). "
            "GROUP BY (EJERCICIO, DELEG_SOLIC, NRO_SOLIC) → MIN(COD_PROV). "
            "Resuelve el proveedor de la OC asociada al gasto."
        ),
    },
    {
        "entity": "solic_gastos",
        "join_type": "LEFT JOIN (subquery sg_comprobantes)",
        "left_table": "SOLIC_GASTOS",
        "right_table": "REG_COMP → CTA_COMPROB",
        "on": [
            "SOLIC_GASTOS.EJERCICIO = sg_comprobantes.EJERCICIO",
            "SOLIC_GASTOS.DELEG_SOLIC = sg_comprobantes.DELEG_SOLIC",
            "SOLIC_GASTOS.NRO_SOLIC = sg_comprobantes.NRO_SOLIC",
        ],
        "note": (
            "Subquery: REG_COMP JOIN CTA_COMPROB ON (EJERCICIO, NRO_REG_COMP). "
            "Filtra REG_COMP.DELEG_SOLIC IS NOT NULL AND NRO_SOLIC IS NOT NULL. "
            "GROUP BY (EJERCICIO, DELEG_SOLIC, NRO_SOLIC) → agrega datos de comprobante. "
            "Devuelve: NRO_COMPROB, TIPO, FECH_COMPROB, FECH_VENCIM, IMPORTE_COMPR, "
            "IMPORTE_NETO, IMPORTE_SIN_IVA, COUNT(comprobantes)."
        ),
    },
    # ── Entidad: orden_pago ────────────────────────────────────────────────
    {
        "entity": "orden_pago",
        "join_type": "LEFT JOIN (subquery op_imput)",
        "left_table": "ORDEN_PAGO",
        "right_table": "ORDEN_PAGO_IMPUT → CTA_COMPROB + REG_COMP",
        "on": [
            "ORDEN_PAGO.EJERCICIO = op_imput.OPI_EJERCICIO",
            "ORDEN_PAGO.NRO_OP = op_imput.OPI_NRO_OP",
        ],
        "note": (
            "Bridge PRIMARIO OP ↔ comprobantes. Subquery sin GROUP BY (una fila por CC). "
            "ORDEN_PAGO_IMPUT LEFT JOIN CTA_COMPROB ON (EJERCICIO, TIPO=TIPO_COMPROB, "
            "NRO_COMPROB, COD_PROV). "
            "LEFT JOIN REG_COMP ON (EJERCICIO, NRO_REG_COMP, COD_PROV) para resolver OC. "
            "Devuelve: NRO_REG_COMP, TIPO_COMPROB, NRO_COMPROB, COD_PROV, "
            "DELEG_SOLIC, NRO_SOLIC, OC_EJERCICIO/NRO/UNI_COMPRA/COD_PROV, "
            "importes y fechas de CTA_COMPROB."
        ),
    },
    # ── Retenciones (queries separadas, NO joineadas a OP) ─────────────────
    {
        "entity": "orden_pago (fetch separado)",
        "join_type": "LEFT JOIN",
        "left_table": "ORDEN_PAGO_DEDUC",
        "right_table": "DEDUCCIONES",
        "on": [
            "ORDEN_PAGO_DEDUC.CODIGO_DEDUC = DEDUCCIONES.CODIGO",
            "ORDEN_PAGO_DEDUC.EJERCICIO = DEDUCCIONES.EJERCICIO (si existe)",
        ],
        "note": (
            "fetch_deducciones_for_ops(): query separada por batch de OPs. "
            "Filtro: WHERE (EJERCICIO, NRO_OP) IN (...). "
            "Devuelve: CODIGO_DEDUC, IMPORTE_RETEN, ALICUOTA, COMPROB_DEDUC, CUENTA, DESCRIPCION."
        ),
    },
    {
        "entity": "orden_pago (fallback retenciones)",
        "join_type": "LEFT JOIN",
        "left_table": "RETENCIONES",
        "right_table": "DEDUCCIONES",
        "on": [
            "RETENCIONES.COD_RET = DEDUCCIONES.CODIGO",
            "RETENCIONES.EJERCICIO = DEDUCCIONES.EJERCICIO (si existe)",
        ],
        "note": (
            "fetch_retenciones_for_ops(): fallback si ORDEN_PAGO_DEDUC no está disponible. "
            "Filtro: WHERE (EJERCICIO, NRO_CANCE) IN (...). "
            "Devuelve: COD_RET, IMPORTE, DESCRIPCION."
        ),
    },
    # ── Dependency filter: OCs requeridas por OPs confirmadas ──────────────
    {
        "entity": "orden_compra / oc_items (dependency filter)",
        "join_type": "INNER JOIN chain",
        "left_table": "ORDEN_PAGO",
        "right_table": "ORDEN_PAGO_IMPUT → REG_COMP",
        "on": [
            "ORDEN_PAGO.EJERCICIO = ORDEN_PAGO_IMPUT.EJERCICIO",
            "ORDEN_PAGO.NRO_OP = ORDEN_PAGO_IMPUT.NRO_OP",
            "ORDEN_PAGO_IMPUT.EJERCICIO = REG_COMP.EJERCICIO",
            "ORDEN_PAGO_IMPUT.NRO_REG_COMP = REG_COMP.NRO_REG_COMP",
            "ORDEN_PAGO_IMPUT.COD_PROV = REG_COMP.COD_PROV",
        ],
        "note": (
            "Subquery op_required_ocs: identifica OCs vinculadas a OPs confirmadas "
            "(ESTADO_OP IN ('C','N'), CONFIRMADO='S', FECH_CONFIRM IS NOT NULL). "
            "Se usa como LEFT JOIN al statement de OC/OC_ITEMS para incluir OCs "
            "de ejercicios anteriores al EJERCICIO_MIN si tienen OP confirmada reciente."
        ),
    },
]


# ─── Filtros por entidad ─────────────────────────────────────────────────────
ENTITY_FILTERS: list[dict] = [
    {
        "entity": "proveedores",
        "table": "PROVEEDORES",
        "incremental_cursor": "FECHA_ULT_COMP >= checkpoint.last_ts",
        "state_filter": None,
        "business_filter": None,
    },
    {
        "entity": "pedidos",
        "table": "PEDIDOS",
        "incremental_cursor": "FECH_EMI >= checkpoint.last_ts",
        "state_filter": None,
        "business_filter": None,
    },
    {
        "entity": "ped_items",
        "table": "PED_ITEMS",
        "incremental_cursor": "full_load (sin cursor incremental)",
        "state_filter": None,
        "business_filter": None,
    },
    {
        "entity": "orden_compra",
        "table": "ORDEN_COMPRA",
        "incremental_cursor": "FECH_OC >= checkpoint.last_ts",
        "state_filter": "ESTADO_OC = 'N' AND FECH_OC >= (now - 30 días) → re-procesa pendientes",
        "business_filter": "EJERCICIO >= RAFAM_EJERCICIO_MIN OR OC requerida por OP confirmada",
    },
    {
        "entity": "oc_items",
        "table": "OC_ITEMS",
        "incremental_cursor": "full_load (sin cursor incremental)",
        "state_filter": None,
        "business_filter": "EJERCICIO >= RAFAM_EJERCICIO_MIN OR OC requerida por OP confirmada",
    },
    {
        "entity": "solic_gastos",
        "table": "SOLIC_GASTOS",
        "incremental_cursor": "FECH_SOLIC >= checkpoint.last_ts",
        "state_filter": "ESTADO_SOLIC = 'C' AND FECH_SOLIC >= (now - 30 días) → re-procesa confirmados",
        "business_filter": None,
    },
    {
        "entity": "orden_pago",
        "table": "ORDEN_PAGO",
        "incremental_cursor": "FECH_CONFIRM >= checkpoint.last_ts",
        "state_filter": "ESTADO_OP = 'C' AND FECH_CONFIRM >= (now - 30 días) → re-procesa confirmados",
        "business_filter": "ESTADO_OP = 'C' AND CONFIRMADO = 'S' AND FECH_CONFIRM IS NOT NULL",
    },
]


# ─── Conexión ────────────────────────────────────────────────────────────────
def get_connection() -> oracledb.Connection:
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
        f"# Esquema RAFAM — `{schema}` — Estructura y JOINs del Pipeline",
        "",
        f"> Generado automáticamente por `scripts/explore_schema.py` el {ts}",
        f"> **No editar manualmente** — regenerar ejecutando el script.",
        "",
        "---",
        "",
    ]

    # ─── Sección 1: Diagrama Mermaid ─────────────────────────────────────
    lines += _build_mermaid_section()

    # ─── Sección 2: Resumen de JOINs por entidad ─────────────────────────
    lines += _build_joins_section()

    # ─── Sección 3: Filtros por entidad ───────────────────────────────────
    lines += _build_filters_section()

    # ─── Sección 4: Estructura de tablas ──────────────────────────────────
    lines += _build_tables_section(schema, tables_data)

    return "\n".join(lines)


def _build_mermaid_section() -> list[str]:
    lines = [
        "## Diagrama de relaciones (JOINs del pipeline)",
        "",
        "```mermaid",
        "erDiagram",
        "",
        "    PROVEEDORES {",
        "        NUMBER COD_PROV PK",
        "        DATE FECHA_ULT_COMP",
        "    }",
        "",
        "    ORDEN_COMPRA {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER UNI_COMPRA PK",
        "        NUMBER NRO_OC PK",
        "        NUMBER COD_PROV FK",
        "        DATE FECH_OC",
        "        VARCHAR2 ESTADO_OC",
        "    }",
        "",
        "    OC_ITEMS {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER UNI_COMPRA PK",
        "        NUMBER NRO_OC PK",
        "        NUMBER ITEM_OC PK",
        "        NUMBER DELEG_SOLIC FK",
        "        NUMBER NRO_SOLIC FK",
        "    }",
        "",
        "    SOLIC_GASTOS {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER DELEG_SOLIC PK",
        "        NUMBER NRO_SOLIC PK",
        "        NUMBER JURISDICCION",
        "        DATE FECH_SOLIC",
        "        VARCHAR2 ESTADO_SOLIC",
        "    }",
        "",
        "    PEDIDOS {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER NUM_PED PK",
        "        DATE FECH_EMI",
        "    }",
        "",
        "    PED_ITEMS {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER NUM_PED PK",
        "        NUMBER ORDEN PK",
        "    }",
        "",
        "    ORDEN_PAGO {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER NRO_OP PK",
        "        VARCHAR2 ESTADO_OP",
        "        VARCHAR2 CONFIRMADO",
        "        DATE FECH_CONFIRM",
        "        NUMBER NRO_CANCE",
        "    }",
        "",
        "    ORDEN_PAGO_IMPUT {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER NRO_OP PK",
        "        NUMBER NRO_REG_COMP PK",
        "        VARCHAR2 TIPO_COMPROB PK",
        "        NUMBER NRO_COMPROB PK",
        "        NUMBER COD_PROV PK",
        "    }",
        "",
        "    ORDEN_PAGO_DEDUC {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER NRO_OP PK",
        "        NUMBER CODIGO_DEDUC PK",
        "        NUMBER IMPORTE_RETEN",
        "        NUMBER ALICUOTA",
        "    }",
        "",
        "    CTA_COMPROB {",
        "        NUMBER EJERCICIO PK",
        "        VARCHAR2 TIPO PK",
        "        NUMBER NRO_COMPROB PK",
        "        NUMBER COD_PROV PK",
        "        NUMBER NRO_REG_COMP",
        "        NUMBER IMPORTE_COMPR",
        "        DATE FECH_COMPROB",
        "    }",
        "",
        "    REG_COMP {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER NRO_REG_COMP PK",
        "        NUMBER COD_PROV PK",
        "        NUMBER DELEG_SOLIC",
        "        NUMBER NRO_SOLIC",
        "        NUMBER UNI_COMPRA",
        "        NUMBER NRO_OC",
        "    }",
        "",
        "    RETENCIONES {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER NRO_CANCE PK",
        "        NUMBER COD_RET PK",
        "        NUMBER IMPORTE",
        "    }",
        "",
        "    DEDUCCIONES {",
        "        NUMBER EJERCICIO PK",
        "        NUMBER CODIGO PK",
        "        VARCHAR2 DESCRIPCION",
        "    }",
        "",
        "    JURISDICCIONES {",
        "        NUMBER CODIGO PK",
        "        VARCHAR2 DESCRIPCION",
        "    }",
        "",
        "    TIPOS_COMPROB {",
        "        VARCHAR2 TIPO PK",
        "        VARCHAR2 DESCRIPCION",
        "    }",
        "",
        "    %% Relaciones usadas por el pipeline",
        '    ORDEN_COMPRA ||--o{ OC_ITEMS : "EJERCICIO+UNI_COMPRA+NRO_OC"',
        '    OC_ITEMS }o--o| SOLIC_GASTOS : "EJERCICIO+DELEG_SOLIC+NRO_SOLIC"',
        '    ORDEN_COMPRA }o--|| PROVEEDORES : "COD_PROV"',
        '    PEDIDOS ||--o{ PED_ITEMS : "EJERCICIO+NUM_PED"',
        '    ORDEN_PAGO ||--o{ ORDEN_PAGO_IMPUT : "EJERCICIO+NRO_OP"',
        '    ORDEN_PAGO_IMPUT }o--o| CTA_COMPROB : "EJERCICIO+TIPO+NRO_COMPROB+COD_PROV"',
        '    ORDEN_PAGO_IMPUT }o--o| REG_COMP : "EJERCICIO+NRO_REG_COMP+COD_PROV"',
        '    REG_COMP }o--o| SOLIC_GASTOS : "EJERCICIO+DELEG_SOLIC+NRO_SOLIC"',
        '    REG_COMP }o--o| ORDEN_COMPRA : "EJERCICIO+UNI_COMPRA+NRO_OC"',
        '    REG_COMP }o--o| CTA_COMPROB : "EJERCICIO+NRO_REG_COMP"',
        '    ORDEN_PAGO_DEDUC }o--o| DEDUCCIONES : "CODIGO_DEDUC=CODIGO (+EJERCICIO)"',
        '    RETENCIONES }o--o| DEDUCCIONES : "COD_RET=CODIGO (+EJERCICIO)"',
        '    SOLIC_GASTOS }o--o| JURISDICCIONES : "JURISDICCION=CODIGO"',
        '    CTA_COMPROB }o--o| TIPOS_COMPROB : "TIPO"',
        "",
        "```",
        "",
    ]
    return lines


def _build_joins_section() -> list[str]:
    lines = [
        "---",
        "",
        "## JOINs del pipeline por entidad",
        "",
        "Detalle de cada JOIN que ejecuta `src/source_repository.py` al construir los statements.",
        "",
    ]

    # Agrupar por entidad
    entities_seen: list[str] = []
    joins_by_entity: dict[str, list[dict]] = {}
    for j in PIPELINE_JOINS:
        ent = j["entity"]
        if ent not in joins_by_entity:
            entities_seen.append(ent)
            joins_by_entity[ent] = []
        joins_by_entity[ent].append(j)

    for ent in entities_seen:
        lines += [f"### Entidad: `{ent}`", ""]
        for i, j in enumerate(joins_by_entity[ent], 1):
            lines += [
                f"**{i}. {j['join_type']}** — `{j['left_table']}` ↔ `{j['right_table']}`",
                "",
                "```sql",
                f"-- Condiciones ON:",
            ]
            for cond in j["on"]:
                lines.append(f"   {cond}")
            lines += [
                "```",
                "",
                f"> {j['note']}",
                "",
            ]

    return lines


def _build_filters_section() -> list[str]:
    lines = [
        "---",
        "",
        "## Filtros y cursores incrementales por entidad",
        "",
        "| Entidad | Tabla principal | Cursor incremental | Filtro de estado (reprocess) | Filtro de negocio |",
        "|---------|---------------|-------------------|------------------------------|-------------------|",
    ]
    for f in ENTITY_FILTERS:
        cursor = f["incremental_cursor"] or "—"
        state = f["state_filter"] or "—"
        biz = f["business_filter"] or "—"
        lines.append(f"| `{f['entity']}` | `{f['table']}` | {cursor} | {state} | {biz} |")

    lines += [
        "",
        "**Notas:**",
        "- El cursor usa `>=` (no `>`) para no perder filas en el borde del batch. El endpoint Paxapos es idempotente.",
        "- `pending_reprocess_days=30`: re-envía registros en estado transitorio de los últimos 30 días.",
        "- `EJERCICIO_MIN`: variable de entorno `RAFAM_EJERCICIO_MIN`. Aplica a orden_compra, oc_items, orden_pago.",
        "",
    ]
    return lines


def _build_tables_section(schema: str, tables_data: list[dict]) -> list[str]:
    lines = [
        "---",
        "",
        "## Estructura de tablas",
        "",
        "### Índice",
        "",
    ]
    for td in tables_data:
        anchor = td["name"].lower().replace("_", "_")
        lines.append(f"- [{td['name']}](#{anchor})")
    lines.append("")

    for td in tables_data:
        name = td["name"]
        cols = td["columns"]
        cons = td["constraints"]

        lines += ["---", "", f"### {name}", ""]

        if cons["pks"]:
            lines.append(f"**PK:** `{'`, `'.join(cons['pks'])}`  ")
        else:
            lines.append(f"**PK:** *(no encontrada)*  ")

        if cons["fks"]:
            fk_strs = [f"`{fk['col']}` → `{fk['ref_table']}`" for fk in cons["fks"]]
            lines.append(f"**FK:** {', '.join(fk_strs)}  ")
        lines.append("")

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

    return lines


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
