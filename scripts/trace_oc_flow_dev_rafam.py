#!/usr/bin/env python3
"""Audita OC sin OP canonica en la SQLite local dev_rafam.db."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "state" / "dev_rafam.db"

REQUIRED_TABLES = {
    "ORDEN_COMPRA",
    "OC_ITEMS",
    "REG_COMP",
    "CTA_COMPROB",
    "ORDEN_PAGO_IMPUT",
    "ORDEN_PAGO",
}

OPTIONAL_TABLES = {
    "ADJUDICACIONES",
    "ADJUDICACIONES_ITEMS",
    "ORDEN_PAGO_DEDUC",
    "SOLIC_GASTOS_ITEMS",
    "TIPOS_COMPROB",
    "RETENCIONES",
    "DEDUCCIONES",
    "SOLIC_GASTOS",
    "PEDIDOS",
    "PED_ITEMS",
}

OUTPUT_COLUMNS = [
    "EJERCICIO",
    "UNI_COMPRA",
    "NRO_OC",
    "COD_PROV",
    "ESTADO_OC",
    "CONFIRMADO",
    "FECH_OC",
    "FECH_CONFIRM",
    "IMPORTE_TOT",
    "items_count",
    "reg_comp_count",
    "cta_comprob_count",
    "opi_count",
    "orden_pago_count",
    "op_valid_count",
    "motivo_sin_op",
    "prioridad_busqueda",
    "comprobantes",
    "ops_encontradas",
]


def _read_only_engine(db_path: Path) -> Engine:
    resolved = db_path.resolve()
    if not resolved.exists():
        raise SystemExit(f"No existe la DB local: {resolved}")

    def creator():
        return sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)

    return create_engine("sqlite+pysqlite://", creator=creator, future=True)


def _tables(conn: Connection) -> set[str]:
    rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    return {str(row[0]).upper() for row in rows}


def _ensure_required_tables(existing: set[str]) -> None:
    missing = sorted(REQUIRED_TABLES - existing)
    if missing:
        raise SystemExit(
            "Faltan tablas obligatorias en dev_rafam.db: " + ", ".join(missing)
        )


def _audit_rows(conn: Connection) -> list[dict]:
    sql = text(
        """
        WITH
        oc AS (
            SELECT
                CAST(EJERCICIO AS INTEGER) AS EJERCICIO,
                CAST(UNI_COMPRA AS INTEGER) AS UNI_COMPRA,
                CAST(NRO_OC AS INTEGER) AS NRO_OC,
                COD_PROV,
                NRO_ADJUD,
                ESTADO_OC,
                CONFIRMADO,
                FECH_OC,
                FECH_CONFIRM,
                CAST(IMPORTE_TOT AS REAL) AS IMPORTE_TOT
            FROM ORDEN_COMPRA
        ),
        items AS (
            SELECT
                CAST(EJERCICIO AS INTEGER) AS EJERCICIO,
                CAST(UNI_COMPRA AS INTEGER) AS UNI_COMPRA,
                CAST(NRO_OC AS INTEGER) AS NRO_OC,
                COUNT(*) AS item_rows,
                COUNT(DISTINCT CAST(ITEM_OC AS TEXT)) AS items_count,
                SUM(CAST(COALESCE(NULLIF(CANTIDAD, ''), '0') AS REAL)
                    * CAST(COALESCE(NULLIF(IMP_UNITARIO, ''), '0') AS REAL)) AS items_total_calc,
                SUM(CAST(COALESCE(NULLIF(IMPORTE_EJER, ''), '0') AS REAL)) AS items_importe_ejer
            FROM OC_ITEMS
            GROUP BY EJERCICIO, UNI_COMPRA, NRO_OC
        ),
        reg AS (
            SELECT
                CAST(EJERCICIO AS INTEGER) AS EJERCICIO,
                CAST(UNI_COMPRA AS INTEGER) AS UNI_COMPRA,
                CAST(NRO_OC AS INTEGER) AS NRO_OC,
                COUNT(*) AS reg_comp_count,
                GROUP_CONCAT(DISTINCT CAST(NRO_REG_COMP AS TEXT)) AS reg_comp_nros
            FROM REG_COMP
            WHERE NULLIF(TRIM(CAST(UNI_COMPRA AS TEXT)), '') IS NOT NULL
              AND NULLIF(TRIM(CAST(NRO_OC AS TEXT)), '') IS NOT NULL
            GROUP BY EJERCICIO, UNI_COMPRA, NRO_OC
        ),
        cta AS (
            SELECT
                CAST(rc.EJERCICIO AS INTEGER) AS EJERCICIO,
                CAST(rc.UNI_COMPRA AS INTEGER) AS UNI_COMPRA,
                CAST(rc.NRO_OC AS INTEGER) AS NRO_OC,
                COUNT(DISTINCT
                    CAST(cc.EJERCICIO AS TEXT) || '|' ||
                    COALESCE(CAST(cc.TIPO AS TEXT), '') || '|' ||
                    COALESCE(CAST(cc.NRO_COMPROB AS TEXT), '') || '|' ||
                    COALESCE(CAST(cc.COD_PROV AS TEXT), '')
                ) AS cta_comprob_count,
                SUM(CAST(COALESCE(NULLIF(cc.IMPORTE_COMPR, ''), '0') AS REAL)) AS facturas_total,
                GROUP_CONCAT(DISTINCT CASE
                    WHEN cc.NRO_COMPROB IS NOT NULL THEN
                        COALESCE(CAST(cc.TIPO AS TEXT), '') || '-' ||
                        COALESCE(CAST(cc.NRO_COMPROB AS TEXT), '') || '-prov=' ||
                        COALESCE(CAST(cc.COD_PROV AS TEXT), '')
                END) AS comprobantes
            FROM REG_COMP rc
            LEFT JOIN CTA_COMPROB cc
              ON CAST(cc.EJERCICIO AS INTEGER) = CAST(rc.EJERCICIO AS INTEGER)
             AND CAST(cc.NRO_REG_COMP AS INTEGER) = CAST(rc.NRO_REG_COMP AS INTEGER)
            WHERE NULLIF(TRIM(CAST(rc.UNI_COMPRA AS TEXT)), '') IS NOT NULL
              AND NULLIF(TRIM(CAST(rc.NRO_OC AS TEXT)), '') IS NOT NULL
            GROUP BY rc.EJERCICIO, rc.UNI_COMPRA, rc.NRO_OC
        ),
        op_link_rows AS (
            SELECT DISTINCT
                CAST(rc.EJERCICIO AS INTEGER) AS EJERCICIO,
                CAST(rc.UNI_COMPRA AS INTEGER) AS UNI_COMPRA,
                CAST(rc.NRO_OC AS INTEGER) AS NRO_OC,
                opi.EJERCICIO AS OPI_EJERCICIO,
                opi.NRO_OP AS OPI_NRO_OP,
                op.EJERCICIO AS OP_EJERCICIO,
                op.NRO_OP AS OP_NRO_OP,
                op.ESTADO_OP,
                op.CONFIRMADO AS OP_CONFIRMADO,
                op.FECH_CONFIRM AS OP_FECH_CONFIRM,
                op.IMPORTE_TOTAL AS OP_IMPORTE_TOTAL
            FROM REG_COMP rc
            JOIN CTA_COMPROB cc
              ON CAST(cc.EJERCICIO AS INTEGER) = CAST(rc.EJERCICIO AS INTEGER)
             AND CAST(cc.NRO_REG_COMP AS INTEGER) = CAST(rc.NRO_REG_COMP AS INTEGER)
            LEFT JOIN ORDEN_PAGO_IMPUT opi
              ON CAST(opi.EJERCICIO AS INTEGER) = CAST(cc.EJERCICIO AS INTEGER)
             AND CAST(opi.NRO_REG_COMP AS INTEGER) = CAST(cc.NRO_REG_COMP AS INTEGER)
             AND CAST(opi.TIPO_COMPROB AS TEXT) = CAST(cc.TIPO AS TEXT)
             AND CAST(opi.NRO_COMPROB AS TEXT) = CAST(cc.NRO_COMPROB AS TEXT)
             AND CAST(opi.COD_PROV AS TEXT) = CAST(cc.COD_PROV AS TEXT)
            LEFT JOIN ORDEN_PAGO op
              ON CAST(op.EJERCICIO AS INTEGER) = CAST(opi.EJERCICIO AS INTEGER)
             AND CAST(op.NRO_OP AS INTEGER) = CAST(opi.NRO_OP AS INTEGER)
            WHERE NULLIF(TRIM(CAST(rc.UNI_COMPRA AS TEXT)), '') IS NOT NULL
              AND NULLIF(TRIM(CAST(rc.NRO_OC AS TEXT)), '') IS NOT NULL
        ),
        op_agg AS (
            SELECT
                EJERCICIO,
                UNI_COMPRA,
                NRO_OC,
                COUNT(DISTINCT CASE
                    WHEN OPI_NRO_OP IS NOT NULL THEN
                        CAST(OPI_EJERCICIO AS TEXT) || '|' || CAST(OPI_NRO_OP AS TEXT)
                END) AS opi_count,
                COUNT(DISTINCT CASE
                    WHEN OP_NRO_OP IS NOT NULL THEN
                        CAST(OP_EJERCICIO AS TEXT) || '|' || CAST(OP_NRO_OP AS TEXT)
                END) AS orden_pago_count,
                COUNT(DISTINCT CASE
                    WHEN OP_NRO_OP IS NOT NULL
                     AND TRIM(COALESCE(ESTADO_OP, '')) = 'C'
                     AND TRIM(COALESCE(OP_CONFIRMADO, '')) = 'S'
                     AND NULLIF(TRIM(COALESCE(CAST(OP_FECH_CONFIRM AS TEXT), '')), '') IS NOT NULL
                    THEN CAST(OP_EJERCICIO AS TEXT) || '|' || CAST(OP_NRO_OP AS TEXT)
                END) AS op_confirmed_count,
                COUNT(DISTINCT CASE
                    WHEN OP_NRO_OP IS NOT NULL
                     AND CAST(COALESCE(NULLIF(OP_IMPORTE_TOTAL, ''), '0') AS REAL) > 0
                    THEN CAST(OP_EJERCICIO AS TEXT) || '|' || CAST(OP_NRO_OP AS TEXT)
                END) AS op_amount_valid_count,
                COUNT(DISTINCT CASE
                    WHEN OP_NRO_OP IS NOT NULL
                     AND TRIM(COALESCE(ESTADO_OP, '')) = 'C'
                     AND TRIM(COALESCE(OP_CONFIRMADO, '')) = 'S'
                     AND NULLIF(TRIM(COALESCE(CAST(OP_FECH_CONFIRM AS TEXT), '')), '') IS NOT NULL
                     AND CAST(COALESCE(NULLIF(OP_IMPORTE_TOTAL, ''), '0') AS REAL) > 0
                    THEN CAST(OP_EJERCICIO AS TEXT) || '|' || CAST(OP_NRO_OP AS TEXT)
                END) AS op_valid_count,
                GROUP_CONCAT(DISTINCT CASE
                    WHEN OPI_NRO_OP IS NOT NULL THEN
                        CAST(OPI_EJERCICIO AS TEXT) || '-' || CAST(OPI_NRO_OP AS TEXT)
                END) AS opi_ops,
                GROUP_CONCAT(DISTINCT CASE
                    WHEN OP_NRO_OP IS NOT NULL THEN
                        CAST(OP_EJERCICIO AS TEXT) || '-' || CAST(OP_NRO_OP AS TEXT)
                END) AS ops_encontradas
            FROM op_link_rows
            GROUP BY EJERCICIO, UNI_COMPRA, NRO_OC
        )
        SELECT
            oc.EJERCICIO,
            oc.UNI_COMPRA,
            oc.NRO_OC,
            oc.COD_PROV,
            oc.NRO_ADJUD,
            oc.ESTADO_OC,
            oc.CONFIRMADO,
            oc.FECH_OC,
            oc.FECH_CONFIRM,
            oc.IMPORTE_TOT,
            COALESCE(items.items_count, 0) AS items_count,
            COALESCE(items.item_rows, 0) AS item_rows,
            COALESCE(items.items_total_calc, 0) AS items_total_calc,
            COALESCE(items.items_importe_ejer, 0) AS items_importe_ejer,
            COALESCE(reg.reg_comp_count, 0) AS reg_comp_count,
            COALESCE(cta.cta_comprob_count, 0) AS cta_comprob_count,
            COALESCE(cta.facturas_total, 0) AS facturas_total,
            COALESCE(op_agg.opi_count, 0) AS opi_count,
            COALESCE(op_agg.orden_pago_count, 0) AS orden_pago_count,
            COALESCE(op_agg.op_confirmed_count, 0) AS op_confirmed_count,
            COALESCE(op_agg.op_amount_valid_count, 0) AS op_amount_valid_count,
            COALESCE(op_agg.op_valid_count, 0) AS op_valid_count,
            cta.comprobantes,
            op_agg.ops_encontradas,
            CASE
                WHEN COALESCE(op_agg.op_valid_count, 0) > 0 THEN 'con_op_canonica'
                WHEN COALESCE(reg.reg_comp_count, 0) = 0 THEN 'sin_reg_comp'
                WHEN COALESCE(cta.cta_comprob_count, 0) = 0 THEN 'sin_cta_comprob'
                WHEN COALESCE(op_agg.opi_count, 0) = 0 THEN 'sin_opi'
                WHEN COALESCE(op_agg.orden_pago_count, 0) = 0 THEN 'sin_orden_pago'
                WHEN COALESCE(op_agg.op_confirmed_count, 0) = 0 THEN 'op_no_confirmada'
                WHEN COALESCE(op_agg.op_amount_valid_count, 0) = 0 THEN 'op_importe_invalido'
                ELSE 'sin_op_valida'
            END AS motivo_sin_op,
            CASE
                WHEN COALESCE(op_agg.op_valid_count, 0) > 0 THEN 'ok'
                WHEN COALESCE(reg.reg_comp_count, 0) = 0 THEN 'baja'
                WHEN COALESCE(cta.cta_comprob_count, 0) = 0 THEN 'media'
                ELSE 'alta'
            END AS prioridad_busqueda
        FROM oc
        LEFT JOIN items
          ON items.EJERCICIO = oc.EJERCICIO
         AND items.UNI_COMPRA = oc.UNI_COMPRA
         AND items.NRO_OC = oc.NRO_OC
        LEFT JOIN reg
          ON reg.EJERCICIO = oc.EJERCICIO
         AND reg.UNI_COMPRA = oc.UNI_COMPRA
         AND reg.NRO_OC = oc.NRO_OC
        LEFT JOIN cta
          ON cta.EJERCICIO = oc.EJERCICIO
         AND cta.UNI_COMPRA = oc.UNI_COMPRA
         AND cta.NRO_OC = oc.NRO_OC
        LEFT JOIN op_agg
          ON op_agg.EJERCICIO = oc.EJERCICIO
         AND op_agg.UNI_COMPRA = oc.UNI_COMPRA
         AND op_agg.NRO_OC = oc.NRO_OC
        ORDER BY oc.EJERCICIO, oc.UNI_COMPRA, oc.NRO_OC
        """
    )
    rows = conn.execute(sql).mappings().all()
    return [dict(row) for row in rows]


def _filter_rows(
    rows: list[dict],
    include_with_op: bool,
    motives: set[str] | None,
    priority: str | None,
    limit: int | None,
) -> list[dict]:
    out = []
    for row in rows:
        if not include_with_op and row["motivo_sin_op"] == "con_op_canonica":
            continue
        if motives and row["motivo_sin_op"] not in motives:
            continue
        if priority and row["prioridad_busqueda"] != priority:
            continue
        out.append(row)
        if limit is not None and len(out) >= limit:
            break
    return out


def _counts_by(rows: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row[field])
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _print_summary(rows: list[dict], existing_tables: set[str]) -> None:
    without_op = [row for row in rows if row["motivo_sin_op"] != "con_op_canonica"]
    missing_optional = sorted(OPTIONAL_TABLES - existing_tables)

    print("Resumen auditoria OC -> OP canonica")
    print(f"OC auditadas: {len(rows)}")
    print(f"OC con OP canonica: {len(rows) - len(without_op)}")
    print(f"OC sin OP canonica: {len(without_op)}")
    print("Distribucion por motivo:")
    for motive, count in _counts_by(rows, "motivo_sin_op").items():
        print(f"  {motive}: {count}")
    print("Distribucion por prioridad:")
    for priority, count in _counts_by(without_op, "prioridad_busqueda").items():
        print(f"  {priority}: {count}")
    if missing_optional:
        print("Tablas opcionales no disponibles: " + ", ".join(missing_optional))
    print()


def _print_csv(rows: list[dict]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)


def _print_numbers(rows: list[dict]) -> None:
    for row in rows:
        print(f"{row['EJERCICIO']}-{row['UNI_COMPRA']}-{row['NRO_OC']}")


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("No hay OC para listar con los filtros indicados.")
        return

    print("OCs sin OP canonica")
    _print_csv(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lista OC sin OP canonica en state/dev_rafam.db"
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help=f"Ruta SQLite local (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--include-with-op",
        action="store_true",
        help="Incluye tambien OC con OP canonica",
    )
    parser.add_argument(
        "--motivo",
        action="append",
        help="Filtra por motivo_sin_op. Se puede repetir.",
    )
    parser.add_argument(
        "--prioridad",
        choices=["baja", "media", "alta", "ok"],
        help="Filtra por prioridad de busqueda.",
    )
    parser.add_argument("--limit", type=int, help="Limita cantidad de filas listadas.")
    parser.add_argument(
        "--numbers-only",
        action="store_true",
        help="Imprime solo EJERCICIO-UNI_COMPRA-NRO_OC, una OC por linea.",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Imprime solo CSV, sin resumen previo.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    engine = _read_only_engine(db_path)

    with engine.connect() as conn:
        existing_tables = _tables(conn)
        _ensure_required_tables(existing_tables)
        rows = _audit_rows(conn)

    motives = set(args.motivo) if args.motivo else None
    filtered = _filter_rows(
        rows=rows,
        include_with_op=args.include_with_op,
        motives=motives,
        priority=args.prioridad,
        limit=args.limit,
    )

    if args.csv:
        _print_csv(filtered)
        return
    if args.numbers_only:
        _print_numbers(filtered)
        return

    _print_summary(rows, existing_tables)
    _print_table(filtered)


if __name__ == "__main__":
    main()