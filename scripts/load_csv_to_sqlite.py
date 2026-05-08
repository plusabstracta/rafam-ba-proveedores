#!/usr/bin/env python3
"""Load CSV snapshots from output/ into a SQLite DB for local development.

Usage:
    python scripts/load_csv_to_sqlite.py
    python scripts/load_csv_to_sqlite.py --output-db state/dev_rafam.db --csv-dir output
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from sqlalchemy import Column, MetaData, Table, Text, create_engine, text

_SNAPSHOT_RE = re.compile(r"^(?P<entity>.+)_\d{8}_\d{6}$")

# Real Oracle schema columns per table. Canonical docs live in
# docs/rafam_paxapos_source_of_truth.md.
# CSVs exported from JOIN queries have extra columns that must be stripped
# so that source_repository.py JOINs work correctly on SQLite.
_SCHEMA_COLUMNS: dict[str, list[str]] = {
    "JURISDICCIONES": [
        "JURISDICCION", "DENOMINACION", "SELECCIONABLE", "VIGENTE_DESDE", "VIGENTE_HASTA",
    ],
    "OC_ITEMS": [
        "EJERCICIO", "UNI_COMPRA", "NRO_OC", "ITEM_OC", "DELEG_SOLIC", "NRO_SOLIC",
        "ITEM_REAL", "DESCRIPCION", "CANTIDAD", "IMP_UNITARIO", "CANT_RECIB", "IMPORTE_EJER",
    ],
    "ORDEN_COMPRA": [
        "EJERCICIO", "UNI_COMPRA", "NRO_OC", "NRO_ADJUD", "FECH_OC", "LUG_EMI",
        "COD_PROV", "COD_LUG_ENT", "FECH_ENTREGA", "ESTADO_OC", "TIPO_DOC_APROB",
        "NRO_DOC_APROB", "ANIO_DOC_APROB", "CONFIRMADO", "FECH_CONFIRM", "CANT_IMPRES",
        "FECH_ANUL", "MOTIVO_ANUL", "OBSERVACIONES", "IMPORTE_TOT", "COND_PAGO",
        "DESC_COND_PAGO", "OC_DIFERIDO",
    ],
    "ORDEN_PAGO": [
        "EJERCICIO", "NRO_OP", "FECH_OP", "LUG_EMI", "CODIGO_FF", "JURISDICCION",
        "CODIGO_UE", "COD_PROV", "TIPO_OP", "ESTADO_OP", "TIPO_DOC", "NRO_DOC",
        "ANIO_DOC", "NRO_CANCE", "CONFIRMADO", "FECH_CONFIRM", "IMPORTE_TOTAL",
        "IMPORTE_LIQUIDO", "CANT_IMPRES", "FECH_ANUL", "MOTIVO_ANUL", "CONCEPTO",
        "OBSERVACIONES", "COD_EMP", "IMPORTE_BONIFICACION", "IMPORTE_DEDUCCIONES",
        "ASIENTO", "ASIENTO_ANUL", "MONTO_SIN_IVA", "DEUDA", "BLOQUEADA", "RECURSO",
        "PERCIBIDO", "NO_PAGADO", "PAGADO", "RECO_DEU_ORDEN", "RECO_DEU_EJERCICIO",
        "RECO_DEU_COMPRA", "RECO_DEU_COMPRA_EJER", "F931", "SICORE",
    ],
    "PEDIDOS": [
        "EJERCICIO", "NUM_PED", "LUG_EMI", "FECH_EMI", "NUM_PED_ORI", "FECH_EMI_ORI",
        "CODIGO_DEP", "CODIGO_UE", "JURISDICCION", "COSTO_TOT", "OBSERVACIONES",
        "PED_ESTADO", "CANT_IMP", "FECH_MODI_ULT", "CODIGO_FF", "COD_LUG_ENT",
        "PLAZO_ENT", "PER_CONSUMO", "FECH_ING_COMP", "RESP_RETIRA_PED",
    ],
    "PED_ITEMS": [
        "EJERCICIO", "NUM_PED", "ORDEN", "INCISO", "PAR_PRIN", "PAR_PARC", "CLASE",
        "TIPO", "JURISDICCION", "PROGRAMA", "ACTIV_PROY", "ACTIV_OBRA", "CANTIDAD",
        "UNI_MED", "DESCRIP_BIE", "COSTO_UNI",
    ],
    "PROVEEDORES": [
        "COD_PROV", "RAZON_SOCIAL", "TIPO_PROV", "CUIT", "FANTASIA", "TIPO_SOC",
        "COD_IVA", "ING_BRUTOS", "FECHA_ALTA", "FECHA_ULT_COMP", "CALIF_PROV",
        "COD_ESTADO", "CALLE_POSTAL", "NRO_POSTAL", "NRO_POSTAL_MED", "PISO_POSTAL",
        "DEPT_POSTAL", "LOCA_POSTAL", "COD_POSTAL", "PROV_POSTAL", "PAIS_POSTAL",
        "CALLE_LEGAL", "NRO_LEGAL", "NRO_LEGAL_MED", "PISO_LEGAL", "DEPT_LEGAL",
        "LOCA_LEGAL", "COD_LEGAL", "PROV_LEGAL", "PAIS_LEGAL", "NRO_PAIS_TE1",
        "NRO_INTE_TE1", "NRO_TELE_TE1", "NRO_PAIS_TE2", "NRO_INTE_TE2",
        "NRO_TELE_TE2", "NRO_PAIS_TE3", "NRO_INTE_TE3", "NRO_TELE_TE3",
        "TE_CELULAR", "FAX", "EMAIL", "OBSERVACION", "PROV_CAJA_CHICA",
        "NRO_HAB_MUN", "DISC_RET_SUSS", "DISC_GCIAS_UTE", "DISC_IIBB_UTE",
    ],
    "SOLIC_GASTOS": [
        "EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC", "NRO_PED", "LUG_EMI", "JURISDICCION",
        "CODIGO_UE", "CODIGO_DEP", "FECH_SOLIC", "TIPO_REGIS", "NRO_ORIG", "CODIGO_FF",
        "IMPORTE_TOT", "FECH_ENTREGA", "FECH_NECESIDAD", "FECH_EST_OC", "TIPO_DOC",
        "NRO_DOC", "ANIO_DOC", "COD_LUG_ENT", "ESTADO_SOLIC", "CONFIRMADO",
        "FECH_CONFIRM", "FECH_ANUL", "MOTIVO_ANUL", "OBSERVACIONES", "CANT_IMP",
        "SG_DIFERIDO",
    ],
    # Auxiliary tables used as JOIN sources (not synced as entities)
    "CTA_HOJA_DE_RUTA": [
        "USUARIO", "PE_EJERCICIO", "PE_NRO", "PE_FECH", "PE_CODIGO_DEP",
        "PE_CODIGO_UE", "PE_JURISDICCION", "PE_ESTADO", "PE_COSTO_TOTAL",
        "SG_EJERCICIO", "SG_DELEG_SOLIC", "SG_NRO", "SG_NRO_PED", "SG_JURISDICCION",
        "SG_CODIGO_UE", "SG_CODIGO_DEP", "SG_FECH", "SG_TIPO_REGIS", "SG_CODIGO_FF",
        "SG_IMPORTE", "SG_ESTADO", "SG_CONFIRMADO", "OC_EJERCICIO", "OC_UNI_COMPRA",
        "OC_NRO", "OC_NRO_ADJUD", "OC_FECH", "OC_COD_PROV", "OC_ESTADO",
        "OC_CONFIRMADO", "OC_IMPORTE", "RC_EJERCICIO", "RC_NRO", "RC_FECH",
        "RC_JURISDICCION", "RC_COD_PROV", "RC_TIPO_REGIS", "RC_NRO_ORIG",
        "RC_CODIGO_FF", "RC_UNI_COMPRA", "RC_NRO_OC", "RC_DELEG_SOLIC", "RC_NRO_SOLIC",
        "RC_IMPORTE", "RC_ESTADO", "RC_CONFIRMADO", "RC_DEPENDENCIA", "RD_EJERCICIO",
        "RD_NRO", "RD_FECH", "RD_NRO_REG_COMP", "RD_JURISDICCION", "RD_COD_PROV",
        "RD_CODIGO_FF", "RD_IMPORTE", "RD_ESTADO", "RD_CONFIRMADO", "CC_TIPO_COMPROB",
        "CC_NRO", "CC_COD_PROV", "CC_NRO_REG_COMP", "CC_FECH_MOVIM", "CC_FECH_COMPROB",
        "CC_IMPORTE", "CC_IMPORTE_PAG", "OP_EJERCICIO", "OP_NRO", "OP_FECH",
        "OP_CODIGO_FF", "OP_JURISDICCION", "OP_CODIGO_UE", "OP_COD_PROV", "OP_TIPO",
        "OP_ESTADO", "OP_NRO_CANCE", "OP_CONFIRMADO", "OP_IMPORTE", "OP_IMPORTE_LIQUIDO",
    ],
    "REG_COMP": [
        "EJERCICIO", "NRO_REG_COMP", "FECH_REG_COMP", "LUG_EMI", "JURISDICCION",
        "CODIGO_UE", "COD_PROV", "TIPO_REGIS", "NRO_ORIG", "CODIGO_FF",
        "UNI_COMPRA", "NRO_OC", "DELEG_SOLIC", "NRO_SOLIC", "TIPO_DOC", "NRO_DOC",
        "ANIO_DOC", "IMPORTE_TOT", "ESTADO_REG_COMP", "CONFIRMADO", "FECH_CONFIRM",
        "FECH_ANUL", "MOTIVO_ANUL", "CANT_IMPRES", "CONCEPTO", "FECH_RELOJ",
        "DEUDA", "DEPENDENCIA", "INSISTIDO", "RC_DIFERIDO", "EJERCICIO_ANT",
        "NRO_REG_COMP_ANT", "RC_EJERCICIO_ANT",
    ],
    "CTA_COMPROB": [
        "EJERCICIO", "TIPO", "NRO_COMPROB", "COD_PROV", "NRO_REG_COMP",
        "FECH_MOVIM", "FECH_COMPROB", "FECH_VENCIM", "FECH_CONFORMAC",
        "PORC_BONIF", "FECH_BONIF", "IMPORTE_COMPR", "IMPORTE_PAGADO",
        "RINDE_IVA", "PORC_IVA", "PORC_CRED_FISCAL", "LIST_LIBRO_IVA",
        "FECH_LIST_IVA", "COD_PROV_REAL", "RAZON_SOCIAL", "CUIT", "DETALLE",
        "IMPORTE_SIN_IVA",
    ],
}


def _latest_csv_by_entity(csv_dir: Path) -> dict[str, Path]:
    latest: dict[str, Path] = {}
    for path in csv_dir.rglob("*.csv"):
        match = _SNAPSHOT_RE.match(path.stem)
        if match is None:
            continue
        entity = match.group("entity")
        current = latest.get(entity)
        if current is None or path.name > current.name:
            latest[entity] = path
    return latest


_CTA_HOJA_DE_RUTA_VIEW_SQL = """\
CREATE VIEW IF NOT EXISTS CTA_HOJA_DE_RUTA AS
SELECT DISTINCT
        sg.EJERCICIO    AS SG_EJERCICIO,
        sg.DELEG_SOLIC  AS SG_DELEG_SOLIC,
        sg.NRO_SOLIC    AS SG_NRO,
        sg.JURISDICCION AS SG_JURISDICCION,
        oc.EJERCICIO    AS OC_EJERCICIO,
        oc.UNI_COMPRA   AS OC_UNI_COMPRA,
        oc.NRO_OC       AS OC_NRO,
        oc.COD_PROV     AS OC_COD_PROV,
        op.EJERCICIO    AS OP_EJERCICIO,
        op.NRO_OP       AS OP_NRO,
        op.NRO_CANCE    AS OP_NRO_CANCE,
        op.ESTADO_OP    AS OP_ESTADO,
        rc.NRO_REG_COMP AS RC_NRO,
        cc.TIPO         AS CC_TIPO_COMPROB,
        cc.NRO_COMPROB  AS CC_NRO,
        cc.COD_PROV     AS CC_COD_PROV,
        cc.NRO_REG_COMP AS CC_NRO_REG_COMP,
        cc.IMPORTE_COMPR AS CC_IMPORTE,
        cc.IMPORTE_PAGADO AS CC_IMPORTE_PAG,
        pe.EJERCICIO    AS PE_EJERCICIO,
        pe.NUM_PED      AS PE_NRO,
        pe.JURISDICCION AS PE_JURISDICCION
FROM ORDEN_PAGO op
LEFT JOIN SOLIC_GASTOS sg
    ON sg.EJERCICIO = op.EJERCICIO
 AND sg.NRO_SOLIC = op.NRO_CANCE
LEFT JOIN OC_ITEMS oci
    ON oci.EJERCICIO = sg.EJERCICIO
 AND oci.DELEG_SOLIC = sg.DELEG_SOLIC
 AND oci.NRO_SOLIC = sg.NRO_SOLIC
LEFT JOIN ORDEN_COMPRA oc
    ON oc.EJERCICIO = oci.EJERCICIO
 AND oc.UNI_COMPRA = oci.UNI_COMPRA
 AND oc.NRO_OC = oci.NRO_OC
LEFT JOIN REG_COMP rc
    ON rc.EJERCICIO   = sg.EJERCICIO
   AND rc.DELEG_SOLIC = sg.DELEG_SOLIC
   AND rc.NRO_SOLIC   = sg.NRO_SOLIC
LEFT JOIN CTA_COMPROB cc
    ON cc.EJERCICIO    = rc.EJERCICIO
   AND cc.NRO_REG_COMP = rc.NRO_REG_COMP
LEFT JOIN PEDIDOS pe
  ON pe.EJERCICIO = sg.EJERCICIO
 AND pe.NUM_PED = sg.NRO_PED
"""


def _ensure_cta_hoja_de_ruta_view(conn) -> None:
    """Always create CTA_HOJA_DE_RUTA as a derived VIEW (it's a JOIN view, not a real table)."""
    from sqlalchemy import text
    existing = conn.execute(
        text("SELECT type FROM sqlite_master WHERE name = 'CTA_HOJA_DE_RUTA'")
    ).scalar()
    if existing == "table":
        count = conn.execute(text("SELECT COUNT(*) FROM CTA_HOJA_DE_RUTA")).scalar()
        if count:
            print(f"[CTA_HOJA_DE_RUTA] tabla CSV preservada ({count} filas)")
            return
        print("[CTA_HOJA_DE_RUTA] tabla CSV vacía; se reemplaza por VIEW derivada")
        conn.execute(text("DROP TABLE CTA_HOJA_DE_RUTA"))
    if existing == "view":
        conn.execute(text("DROP VIEW CTA_HOJA_DE_RUTA"))
    conn.execute(text(_CTA_HOJA_DE_RUTA_VIEW_SQL))
    count = conn.execute(text("SELECT COUNT(*) FROM CTA_HOJA_DE_RUTA")).scalar()
    print(f"[CTA_HOJA_DE_RUTA] VIEW derivada creada ({count} filas)")


def _create_table_from_csv(metadata: MetaData, entity: str, header: list[str]) -> Table:
    # SQLite typing is permissive. We start as TEXT-like columns to avoid lossy casts.
    return Table(
        entity.upper(),
        metadata,
        *[Column(col, Text) for col in header],
    )


def load_csvs(csv_dir: Path, output_db: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{output_db}", future=True)
    output_db.parent.mkdir(parents=True, exist_ok=True)

    latest = _latest_csv_by_entity(csv_dir)
    if not latest:
        raise RuntimeError(f"No se encontraron CSV en {csv_dir}")

    metadata = MetaData()

    with engine.begin() as conn:
        for entity, path in sorted(latest.items()):
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    continue

                table_name = entity.upper()
                schema_cols = _SCHEMA_COLUMNS.get(table_name)

                if schema_cols is not None:
                    # Filter: only keep columns that exist in the real Oracle schema
                    allowed = set(schema_cols)
                    extra = [c for c in reader.fieldnames if c not in allowed]
                    header = [c for c in reader.fieldnames if c in allowed]
                    if extra:
                        print(f"[{entity}] columnas JOIN descartadas: {extra}")
                else:
                    header = list(reader.fieldnames)

                existing = conn.execute(
                    text("SELECT type FROM sqlite_master WHERE name = :name"),
                    {"name": table_name},
                ).scalar()
                if existing == "view":
                    conn.execute(text(f'DROP VIEW "{table_name}"'))

                table = _create_table_from_csv(metadata, entity, header)
                table.drop(conn, checkfirst=True)
                table.create(conn, checkfirst=True)

                rows = [{k: row[k] for k in header} for row in reader]
                if rows:
                    conn.execute(table.insert(), rows)
                print(f"[{entity}] {len(rows)} filas cargadas desde {path.name} ({len(header)} cols)")

        # If CTA_HOJA_DE_RUTA was NOT loaded from CSV, create it as a derived
        # VIEW from the existing tables so that source_repository JOINs work
        # identically in dev (SQLite) and prod (Oracle).
        _ensure_cta_hoja_de_ruta_view(conn)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cargar snapshots CSV a SQLite para desarrollo")
    parser.add_argument("--csv-dir", default="output", help="Directorio con CSV exportados")
    parser.add_argument("--output-db", default="state/dev_rafam.db", help="Ruta del archivo SQLite destino")
    args = parser.parse_args()

    load_csvs(Path(args.csv_dir), Path(args.output_db))


if __name__ == "__main__":
    main()
