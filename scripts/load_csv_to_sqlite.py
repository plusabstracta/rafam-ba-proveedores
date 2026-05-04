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

from sqlalchemy import Column, MetaData, Table, Text, create_engine

_SNAPSHOT_RE = re.compile(r"^(?P<entity>.+)_\d{8}_\d{6}$")

# Real Oracle schema columns per table (from docs/rafam_schema.md).
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
        "PE_EJERCICIO", "PE_NRO", "SG_EJERCICIO", "SG_NRO", "SG_DELEG",
        "OC_EJERCICIO", "OC_NRO_OC", "OC_COD_PROV", "OP_NRO_OP", "ESTADO_OP",
        "OP_NRO_CANCE", "PE_JURISDICCION", "FECH_HOJA",
    ],
    "RG_COMP": [
        "EJERCICIO", "NRO_REG_COMP", "NRO_OC", "COD_PROV", "JURISDICCION",
        "FECH_REG_COMP",
    ],
}


def _latest_csv_by_entity(csv_dir: Path) -> dict[str, Path]:
    latest: dict[str, Path] = {}
    for path in csv_dir.glob("*.csv"):
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
    sg.NRO_SOLIC    AS SG_NRO,
    sg.DELEG_SOLIC  AS SG_DELEG,
    oc.EJERCICIO    AS OC_EJERCICIO,
    oc.NRO_OC       AS OC_NRO_OC,
    oc.COD_PROV     AS OC_COD_PROV,
    pe.EJERCICIO    AS PE_EJERCICIO,
    pe.NUM_PED      AS PE_NRO,
    pe.JURISDICCION AS PE_JURISDICCION,
    oc.FECH_CONFIRM AS FECH_HOJA
FROM OC_ITEMS oci
JOIN SOLIC_GASTOS sg
  ON sg.EJERCICIO = oci.EJERCICIO
 AND sg.DELEG_SOLIC = oci.DELEG_SOLIC
 AND sg.NRO_SOLIC = oci.NRO_SOLIC
JOIN ORDEN_COMPRA oc
  ON oc.EJERCICIO = oci.EJERCICIO
 AND oc.UNI_COMPRA = oci.UNI_COMPRA
 AND oc.NRO_OC = oci.NRO_OC
LEFT JOIN PEDIDOS pe
  ON pe.EJERCICIO = sg.EJERCICIO
 AND pe.NUM_PED = sg.NRO_PED
"""


def _ensure_cta_hoja_de_ruta_view(conn) -> None:
    """Create CTA_HOJA_DE_RUTA as a derived VIEW when no CSV was loaded for it."""
    from sqlalchemy import text
    # Check if a real table was already loaded from CSV
    existing = conn.execute(
        text("SELECT type FROM sqlite_master WHERE name = 'CTA_HOJA_DE_RUTA'")
    ).scalar()
    if existing == "table":
        print("[CTA_HOJA_DE_RUTA] tabla cargada desde CSV, no se crea VIEW")
        return
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
