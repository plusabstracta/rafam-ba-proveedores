from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, MetaData, Table, and_, case, func, literal_column, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import Select

from .config import ENTITY_CONFIGS, SCHEMA
from .models import Checkpoint, EntityConfig

logger = logging.getLogger(__name__)


class SourceRepository:
    """Builds SQLAlchemy statements for RAFAM entities using reflected metadata."""

    def __init__(self, conn: Connection, schema: str = SCHEMA):
        self._conn = conn
        self._schema = None if conn.dialect.name == "sqlite" else schema
        self._metadata = MetaData()
        self._tables: dict[str, object] = {}

    def _reflect_table(self, table_name: str):
        key = f"{self._schema}.{table_name}" if self._schema else table_name
        table = self._tables.get(key)
        if table is None:
            table = self._metadata.tables.get(key)
        if table is None:
            table = self._metadata.tables.get(table_name)
        if table is None:
            # Use get_columns() instead of autoload_with to bypass has_table(),
            # which uses FETCH FIRST syntax unsupported on Oracle 11g.
            # Column names are uppercased to match Oracle conventions, since
            # python-oracledb returns them lowercase from get_columns().
            insp = sa_inspect(self._conn)
            try:
                col_defs = insp.get_columns(table_name, schema=self._schema)
            except Exception as exc:
                if self._conn.dialect.name == "sqlite":
                    raise type(exc)(
                        f"{table_name} — tabla no encontrada en SQLite. "
                        f"Ejecuta 'make load-dev' para cargar CSVs, o cambia "
                        f"RAFAM_SOURCE_BACKEND=oracle en .env"
                    ) from exc
                raise
            if not col_defs:
                logger.warning(
                    "get_columns('%s', schema='%s') retorno 0 columnas. "
                    "Posible falta de privilegios SELECT o tabla inexistente.",
                    table_name, self._schema,
                )
            table = Table(table_name, self._metadata, schema=self._schema)
            for col_def in col_defs:
                table.append_column(Column(col_def["name"].upper(), col_def["type"]))
            self._tables[key] = table
            self._tables[table_name] = table
        return table

    def _reflect_optional_table(self, table_name: str):
        try:
            return self._reflect_table(table_name)
        except SQLAlchemyError as exc:
            logger.warning(
                "No se pudo reflejar tabla opcional '%s' (schema=%s): %s",
                table_name, self._schema, exc,
            )
            return None

    @staticmethod
    def _coalesce_optional_columns(*columns):
        present = [col for col in columns if col is not None]
        if not present:
            return literal_column("NULL")
        if len(present) == 1:
            return present[0]
        return func.coalesce(*present)

    def build_statement(self, entity: str, checkpoint: Checkpoint) -> Select:
        cfg = ENTITY_CONFIGS[entity]
        if entity == "orden_compra":
            return self._build_orden_compra_statement(cfg, checkpoint)
        if entity == "oc_items":
            return self._build_oc_items_statement(cfg, checkpoint)
        if entity == "solic_gastos":
            return self._build_solic_gastos_statement(cfg, checkpoint)
        if entity == "orden_pago":
            return self._build_orden_pago_statement(cfg, checkpoint)
        if entity == "retenciones":
            # Retenciones escanea las mismas OP que orden_pago; el exporter
            # trae las deducciones por OP via fetch_deducciones_for_ops.
            return self._build_orden_pago_statement(cfg, checkpoint)
        return self._build_simple_table_statement(cfg, checkpoint)

    def execute(self, stmt: Select):
        return self._conn.execution_options(stream_results=True).execute(stmt)

    def count_rows(
        self,
        table_name: str,
        *,
        distinct_fields: list[str] | None = None,
        ejercicio_min: int | None = None,
    ) -> int:
        """Cuenta filas (o combinaciones distintas) de una tabla RAFAM.

        Usado por la reconciliacion (F4) para comparar el universo de origen
        contra lo migrado localmente. Aplica el filtro de ejercicio cuando la
        tabla tiene la columna EJERCICIO.
        """
        table = self._reflect_table(table_name)
        has_ejercicio = "EJERCICIO" in table.c

        if distinct_fields:
            cols = [table.c[f] for f in distinct_fields if f in table.c]
            if not cols:
                return 0
            inner = select(*cols).distinct()
            if ejercicio_min and has_ejercicio:
                inner = inner.where(table.c.EJERCICIO >= ejercicio_min)
            stmt = select(func.count()).select_from(inner.subquery())
        else:
            stmt = select(func.count()).select_from(table)
            if ejercicio_min and has_ejercicio:
                stmt = stmt.where(table.c.EJERCICIO >= ejercicio_min)

        return int(self._conn.execute(stmt).scalar() or 0)

    def fetch_deducciones_for_ops(
        self,
        op_keys: list[tuple[int, int]] | set[tuple[int, int]],
    ) -> dict[tuple[int, int], list[dict]] | None:
        """Trae deducciones individuales por OP desde ORDEN_PAGO_DEDUC.

        Clave: (EJERCICIO, NRO_OP).
        Devuelve dict {(ejercicio, nro_op): [{codigo_deduc, importe_reten, alicuota,
        comprob_deduc, cuenta, descripcion}, ...]}.

        Retorna None si la tabla no esta disponible o no se pudo ejecutar la query
        (señal para que el caller active el fallback via RETENCIONES).
        Retorna {} si la tabla existe pero no hay filas para esas keys (caso normal,
        el caller NO debe activar fallback).

        NOTA: ORDEN_PAGO_DEDUC corresponde a las Ordenes de Pago normales (tabla
        ORDEN_PAGO). NO confundir con ORDEN_PAGOEA_DEDUC, que es para Ordenes
        de Pago de Egresos Adicionales (entidad ORDEN_PAGOEA, distinta y no migrada
        por este pipeline).
        """
        if not op_keys:
            return {}

        op_deduc = self._reflect_optional_table("ORDEN_PAGO_DEDUC")
        if op_deduc is None:
            logger.error(
                "fetch_deducciones_for_ops: tabla ORDEN_PAGO_DEDUC no disponible "
                "(schema=%s). Verificar que el usuario Oracle tenga SELECT sobre esta tabla. "
                "Sin ella NO se migraran retenciones.",
                self._schema,
            )
            return None
        deducciones = self._reflect_optional_table("DEDUCCIONES")

        od_ej = self._safe_column(op_deduc, "EJERCICIO")
        od_nro_op = self._safe_column(op_deduc, "NRO_OP")
        od_codigo = self._safe_column(op_deduc, "CODIGO_DEDUC")
        od_importe = self._safe_column(op_deduc, "IMPORTE_RETEN")
        if od_ej is None or od_nro_op is None or od_codigo is None or od_importe is None:
            logger.error(
                "fetch_deducciones_for_ops: ORDEN_PAGO_DEDUC reflejada sin columnas "
                "requeridas (EJERCICIO=%s, NRO_OP=%s, CODIGO_DEDUC=%s, IMPORTE_RETEN=%s). "
                "Columnas disponibles: %s. Sin ellas NO se migraran retenciones.",
                od_ej is not None, od_nro_op is not None,
                od_codigo is not None, od_importe is not None,
                [c.name for c in op_deduc.columns] if hasattr(op_deduc, "columns") else "?",
            )
            return None

        od_alicuota = self._safe_column(op_deduc, "ALICUOTA")
        od_comprob = self._safe_column(op_deduc, "COMPROB_DEDUC")
        od_cuenta = self._safe_column(op_deduc, "CUENTA")

        select_cols = [
            od_ej.label("EJERCICIO"),
            od_nro_op.label("NRO_OP"),
            od_codigo.label("CODIGO_DEDUC"),
            od_importe.label("IMPORTE_RETEN"),
        ]
        if od_alicuota is not None:
            select_cols.append(od_alicuota.label("ALICUOTA"))
        if od_comprob is not None:
            select_cols.append(od_comprob.label("COMPROB_DEDUC"))
        if od_cuenta is not None:
            select_cols.append(od_cuenta.label("CUENTA"))

        from_clause = op_deduc

        if deducciones is not None:
            ded_codigo = self._safe_column(deducciones, "CODIGO")
            ded_desc = self._safe_column(deducciones, "DESCRIPCION")
            if ded_codigo is not None:
                join_conditions = [od_codigo == ded_codigo]
                ded_ejercicio = self._safe_column(deducciones, "EJERCICIO")
                if ded_ejercicio is not None:
                    join_conditions.append(od_ej == ded_ejercicio)
                from_clause = from_clause.outerjoin(deducciones, and_(*join_conditions))
                if ded_desc is not None:
                    select_cols.append(ded_desc.label("DESCRIPCION"))

        keys_by_ej: dict[int, set[int]] = {}
        for ej, nro_op in op_keys:
            if ej is None or nro_op is None:
                continue
            keys_by_ej.setdefault(int(ej), set()).add(int(nro_op))

        if not keys_by_ej:
            return {}

        ej_filters = []
        for ej, nro_ops in keys_by_ej.items():
            ej_filters.append(and_(od_ej == ej, od_nro_op.in_(list(nro_ops))))

        stmt = select(*select_cols).select_from(from_clause).where(or_(*ej_filters))

        out: dict[tuple[int, int], list[dict]] = {}
        try:
            for row in self._conn.execute(stmt):
                mapping = row._mapping
                try:
                    ej = int(mapping["EJERCICIO"])
                    nro_op = int(mapping["NRO_OP"])
                except (TypeError, ValueError, KeyError):
                    continue
                entry = {
                    "codigo_deduc": mapping.get("CODIGO_DEDUC"),
                    "importe_reten": mapping.get("IMPORTE_RETEN"),
                    "alicuota": mapping.get("ALICUOTA") if "ALICUOTA" in mapping.keys() else None,
                    "comprob_deduc": mapping.get("COMPROB_DEDUC") if "COMPROB_DEDUC" in mapping.keys() else None,
                    "cuenta": mapping.get("CUENTA") if "CUENTA" in mapping.keys() else None,
                    "descripcion": mapping.get("DESCRIPCION") if "DESCRIPCION" in mapping.keys() else None,
                }
                out.setdefault((ej, nro_op), []).append(entry)
        except (SQLAlchemyError, Exception) as exc:
            logger.error(
                "fetch_deducciones_for_ops: error ejecutando query ORDEN_PAGO_DEDUC: %s. "
                "Sin esta tabla NO se migraran retenciones. Verificar privilegios Oracle.",
                exc,
            )
            return None

        if out:
            logger.debug(
                "fetch_deducciones_for_ops: %d OPs con deducciones encontradas en ORDEN_PAGO_DEDUC",
                len(out),
            )
        else:
            logger.debug(
                "fetch_deducciones_for_ops: ORDEN_PAGO_DEDUC no devolvio filas para %d keys "
                "(normal si esas OPs no tienen deducciones).",
                len(op_keys),
            )
        return out

    def _build_simple_table_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        table = self._reflect_table(cfg.table_name)
        stmt = select(table)
        return self._apply_incremental_filters(stmt, table, cfg, checkpoint)

    def _build_orden_compra_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        oc = self._reflect_table("ORDEN_COMPRA")
        oc_items = self._reflect_table("OC_ITEMS")
        solic_gastos = self._reflect_table("SOLIC_GASTOS")
        reg_comp = self._reflect_optional_table("REG_COMP")
        cta_comprob = self._reflect_optional_table("CTA_COMPROB")

        # ORDEN_COMPRA → OC_ITEMS (items) → SOLIC_GASTOS (jurisdicción).
        # El cursor incremental aplica sobre ORDEN_COMPRA (FECH_OC / ESTADO_OC),
        # así solo se traen OCs recién modificadas CON sus items.
        select_cols = [
            oc_items,
            oc.c.COD_PROV,
            oc.c.FECH_OC.label("OC_FECH_OC"),
            oc.c.OBSERVACIONES.label("OC_OBSERVACIONES"),
            oc.c.ESTADO_OC.label("OC_ESTADO_OC"),
            oc.c.FECH_CONFIRM.label("OC_FECH_CONFIRM"),
            oc.c.IMPORTE_TOT.label("OC_IMPORTE_TOT"),
            solic_gastos.c.JURISDICCION.label("SG_JURISDICCION"),
        ]

        from_clause = (
            oc.join(
                oc_items,
                and_(
                    oc.c.EJERCICIO == oc_items.c.EJERCICIO,
                    oc.c.UNI_COMPRA == oc_items.c.UNI_COMPRA,
                    oc.c.NRO_OC == oc_items.c.NRO_OC,
                ),
            ).outerjoin(
                solic_gastos,
                and_(
                    oc_items.c.EJERCICIO == solic_gastos.c.EJERCICIO,
                    oc_items.c.DELEG_SOLIC == solic_gastos.c.DELEG_SOLIC,
                    oc_items.c.NRO_SOLIC == solic_gastos.c.NRO_SOLIC,
                ),
            )
        )

        # LEFT JOIN subquery OC → SG → REG_COMP → CTA_COMPROB para obtener
        # nro de comprobante asociado a cada OC (sin pasar por la VIEW
        # (sin pasar por la VIEW CTA_HOJA_DE_RUTA: usamos las tablas reales)
        oc_cc = self._build_oc_to_cc_subquery(reg_comp, cta_comprob)
        if oc_cc is not None:
            from_clause = from_clause.outerjoin(
                oc_cc,
                and_(
                    oc.c.EJERCICIO == oc_cc.c.OC_EJERCICIO,
                    oc.c.UNI_COMPRA == oc_cc.c.OC_UNI_COMPRA,
                    oc.c.NRO_OC == oc_cc.c.OC_NRO,
                ),
            )
            select_cols.extend([
                oc_cc.c.OC_CC_NRO,
                oc_cc.c.OC_CC_TIPO_COMPROB,
                oc_cc.c.OC_CC_COD_PROV,
            ])

        stmt = select(*select_cols).select_from(from_clause)
        extra_filters = []
        if not (cfg.full_load or checkpoint.is_fresh):
            fech_anul_col = self._safe_column(oc, "FECH_ANUL")
            estado_col = self._safe_column(oc, "ESTADO_OC")
            if fech_anul_col is not None and estado_col is not None:
                window_start = datetime.now(timezone.utc) - timedelta(days=cfg.pending_reprocess_days or 30)
                extra_filters.append(and_(estado_col == "A", fech_anul_col > window_start))

        stmt = self._apply_oc_dependency_filter(
            stmt,
            cfg,
            {
                "ejercicio": oc.c.EJERCICIO,
                "uni_compra": oc.c.UNI_COMPRA,
                "nro_oc": oc.c.NRO_OC,
            },
        )
        stmt = self._apply_incremental_filters(
            stmt,
            oc,
            cfg,
            checkpoint,
            extra_filters=extra_filters,
            apply_ejercicio_min=False,
        )
        return stmt.order_by(oc.c.EJERCICIO, oc.c.UNI_COMPRA, oc.c.NRO_OC, oc_items.c.ITEM_OC)

    def _build_oc_items_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        oc_items = self._reflect_table("OC_ITEMS")
        orden_compra = self._reflect_table("ORDEN_COMPRA")
        solic_gastos = self._reflect_table("SOLIC_GASTOS")
        reg_comp = self._reflect_optional_table("REG_COMP")
        cta_comprob = self._reflect_optional_table("CTA_COMPROB")

        select_cols = [
            oc_items,
            orden_compra.c.COD_PROV,
            orden_compra.c.FECH_OC.label("OC_FECH_OC"),
            orden_compra.c.OBSERVACIONES.label("OC_OBSERVACIONES"),
            orden_compra.c.ESTADO_OC.label("OC_ESTADO_OC"),
            orden_compra.c.FECH_CONFIRM.label("OC_FECH_CONFIRM"),
            orden_compra.c.IMPORTE_TOT.label("OC_IMPORTE_TOT"),
            solic_gastos.c.JURISDICCION.label("SG_JURISDICCION"),
        ]

        from_clause = (
            oc_items.join(
                orden_compra,
                and_(
                    oc_items.c.EJERCICIO == orden_compra.c.EJERCICIO,
                    oc_items.c.UNI_COMPRA == orden_compra.c.UNI_COMPRA,
                    oc_items.c.NRO_OC == orden_compra.c.NRO_OC,
                ),
            ).outerjoin(
                solic_gastos,
                and_(
                    oc_items.c.EJERCICIO == solic_gastos.c.EJERCICIO,
                    oc_items.c.DELEG_SOLIC == solic_gastos.c.DELEG_SOLIC,
                    oc_items.c.NRO_SOLIC == solic_gastos.c.NRO_SOLIC,
                ),
            )
        )

        # LEFT JOIN subquery OC → SG → REG_COMP → CTA_COMPROB para obtener
        # nro de comprobante asociado a cada OC (sin pasar por la VIEW
        # (sin pasar por la VIEW CTA_HOJA_DE_RUTA: usamos las tablas reales)
        oc_cc = self._build_oc_to_cc_subquery(reg_comp, cta_comprob)
        if oc_cc is not None:
            from_clause = from_clause.outerjoin(
                oc_cc,
                and_(
                    orden_compra.c.EJERCICIO == oc_cc.c.OC_EJERCICIO,
                    orden_compra.c.UNI_COMPRA == oc_cc.c.OC_UNI_COMPRA,
                    orden_compra.c.NRO_OC == oc_cc.c.OC_NRO,
                ),
            )
            select_cols.extend([
                oc_cc.c.OC_CC_NRO,
                oc_cc.c.OC_CC_TIPO_COMPROB,
                oc_cc.c.OC_CC_COD_PROV,
            ])

        stmt = select(*select_cols).select_from(from_clause)
        stmt = self._apply_oc_dependency_filter(
            stmt,
            cfg,
            {
                "ejercicio": oc_items.c.EJERCICIO,
                "uni_compra": oc_items.c.UNI_COMPRA,
                "nro_oc": oc_items.c.NRO_OC,
            },
        )
        stmt = self._apply_incremental_filters(
            stmt,
            oc_items,
            cfg,
            checkpoint,
            apply_ejercicio_min=False,
        )
        return stmt.order_by(oc_items.c.EJERCICIO, oc_items.c.UNI_COMPRA, oc_items.c.NRO_OC, oc_items.c.ITEM_OC)

    def _build_solic_gastos_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        solic_gastos = self._reflect_table("SOLIC_GASTOS")
        oc_items = self._reflect_table("OC_ITEMS")
        orden_compra = self._reflect_table("ORDEN_COMPRA")
        reg_comp = self._reflect_optional_table("REG_COMP")
        cta_comprob = self._reflect_optional_table("CTA_COMPROB")

        # Subquery: one COD_PROV per (EJERCICIO, DELEG_SOLIC, NRO_SOLIC)
        # via OC_ITEMS → ORDEN_COMPRA.  MIN() is a deterministic tie-breaker
        # for the rare cases where a gasto links to OCs with different providers.
        oc_prov = (
            select(
                oc_items.c.EJERCICIO,
                oc_items.c.DELEG_SOLIC,
                oc_items.c.NRO_SOLIC,
                func.min(orden_compra.c.COD_PROV).label("OC_COD_PROV"),
            )
            .select_from(
                oc_items.join(
                    orden_compra,
                    and_(
                        oc_items.c.EJERCICIO == orden_compra.c.EJERCICIO,
                        oc_items.c.UNI_COMPRA == orden_compra.c.UNI_COMPRA,
                        oc_items.c.NRO_OC == orden_compra.c.NRO_OC,
                    ),
                )
            )
            .group_by(
                oc_items.c.EJERCICIO,
                oc_items.c.DELEG_SOLIC,
                oc_items.c.NRO_SOLIC,
            )
            .subquery("oc_prov")
        )

        select_cols = [solic_gastos, oc_prov.c.OC_COD_PROV]
        from_clause = solic_gastos.outerjoin(
            oc_prov,
            and_(
                solic_gastos.c.EJERCICIO == oc_prov.c.EJERCICIO,
                solic_gastos.c.DELEG_SOLIC == oc_prov.c.DELEG_SOLIC,
                solic_gastos.c.NRO_SOLIC == oc_prov.c.NRO_SOLIC,
            ),
        )

        comprobantes = self._build_solic_gastos_comprobantes_subquery(reg_comp, cta_comprob)
        if comprobantes is not None:
            select_cols.extend(
                [
                    comprobantes.c.CTA_NRO_COMPROB,
                    comprobantes.c.CTA_TIPO_COMPROB,
                    comprobantes.c.CTA_FECH_COMPROB,
                    comprobantes.c.CTA_FECH_VENCIM,
                    comprobantes.c.CTA_IMPORTE_COMPR,
                    comprobantes.c.CTA_IMPORTE_NETO,
                    comprobantes.c.CTA_IMPORTE_SIN_IVA,
                    comprobantes.c.CTA_COMPROB_COUNT,
                ]
            )
            from_clause = from_clause.outerjoin(
                comprobantes,
                and_(
                    solic_gastos.c.EJERCICIO == comprobantes.c.EJERCICIO,
                    solic_gastos.c.DELEG_SOLIC == comprobantes.c.DELEG_SOLIC,
                    solic_gastos.c.NRO_SOLIC == comprobantes.c.NRO_SOLIC,
                ),
            )

        stmt = select(*select_cols).select_from(from_clause)
        stmt = self._apply_incremental_filters(stmt, solic_gastos, cfg, checkpoint)
        return stmt.order_by(solic_gastos.c.EJERCICIO, solic_gastos.c.DELEG_SOLIC, solic_gastos.c.NRO_SOLIC)

    def _build_solic_gastos_comprobantes_subquery(self, reg_comp, cta_comprob):
        if reg_comp is None or cta_comprob is None:
            return None

        required_cols = {
            "reg_ejercicio": self._safe_column(reg_comp, "EJERCICIO"),
            "reg_nro_reg_comp": self._safe_column(reg_comp, "NRO_REG_COMP"),
            "reg_deleg_solic": self._safe_column(reg_comp, "DELEG_SOLIC"),
            "reg_nro_solic": self._safe_column(reg_comp, "NRO_SOLIC"),
            "cta_ejercicio": self._safe_column(cta_comprob, "EJERCICIO"),
            "cta_nro_reg_comp": self._safe_column(cta_comprob, "NRO_REG_COMP"),
            "cta_tipo": self._safe_column(cta_comprob, "TIPO"),
            "cta_nro_comprob": self._safe_column(cta_comprob, "NRO_COMPROB"),
            "cta_fech_comprob": self._safe_column(cta_comprob, "FECH_COMPROB"),
            "cta_fech_vencim": self._safe_column(cta_comprob, "FECH_VENCIM"),
        }
        if any(col is None for col in required_cols.values()):
            return None

        cta_importe_total = self._safe_column(cta_comprob, "IMPORTE_COMPR")
        cta_importe_sin_iva = self._safe_column(cta_comprob, "IMPORTE_SIN_IVA")
        cta_importe_neto = self._coalesce_optional_columns(
            self._safe_column(cta_comprob, "IMPORTE_LIQUIDO"),
            self._safe_column(cta_comprob, "IMPORTE_NETO"),
            cta_importe_sin_iva,
        )
        cta_importe_total_expr = (
            cta_importe_total if cta_importe_total is not None
            else literal_column("NULL")
        )
        cta_importe_sin_iva_expr = (
            cta_importe_sin_iva if cta_importe_sin_iva is not None
            else literal_column("NULL")
        )

        return (
            select(
                required_cols["reg_ejercicio"].label("EJERCICIO"),
                required_cols["reg_deleg_solic"].label("DELEG_SOLIC"),
                required_cols["reg_nro_solic"].label("NRO_SOLIC"),
                func.min(required_cols["cta_nro_comprob"]).label("CTA_NRO_COMPROB"),
                func.min(required_cols["cta_tipo"]).label("CTA_TIPO_COMPROB"),
                func.min(required_cols["cta_fech_comprob"]).label("CTA_FECH_COMPROB"),
                func.min(required_cols["cta_fech_vencim"]).label("CTA_FECH_VENCIM"),
                func.min(cta_importe_total_expr).label("CTA_IMPORTE_COMPR"),
                func.min(cta_importe_neto).label("CTA_IMPORTE_NETO"),
                func.min(cta_importe_sin_iva_expr).label("CTA_IMPORTE_SIN_IVA"),
                func.count(required_cols["cta_nro_comprob"]).label("CTA_COMPROB_COUNT"),
            )
            .select_from(
                reg_comp.join(
                    cta_comprob,
                    and_(
                        required_cols["reg_ejercicio"] == required_cols["cta_ejercicio"],
                        required_cols["reg_nro_reg_comp"] == required_cols["cta_nro_reg_comp"],
                    ),
                )
            )
            .where(
                and_(
                    required_cols["reg_deleg_solic"].is_not(None),
                    required_cols["reg_nro_solic"].is_not(None),
                )
            )
            .group_by(
                required_cols["reg_ejercicio"],
                required_cols["reg_deleg_solic"],
                required_cols["reg_nro_solic"],
            )
            .subquery("sg_comprobantes")
        )

    def _build_oc_to_cc_subquery(self, reg_comp, cta_comprob):
        """Subquery agrupada por (OC_EJERCICIO, OC_UNI_COMPRA, OC_NRO) que
        resuelve el comprobante (CTA_COMPROB) asociado a cada OC vía
        REG_COMP. Reemplaza la lectura directa de la VIEW CTA_HOJA_DE_RUTA.

        Path: ORDEN_COMPRA ← REG_COMP (por EJERCICIO+UNI_COMPRA+NRO_OC)
              REG_COMP → CTA_COMPROB (por EJERCICIO+NRO_REG_COMP).
        """
        if reg_comp is None or cta_comprob is None:
            return None
        cols = {
            "rc_ej": self._safe_column(reg_comp, "EJERCICIO"),
            "rc_uni": self._safe_column(reg_comp, "UNI_COMPRA"),
            "rc_nro_oc": self._safe_column(reg_comp, "NRO_OC"),
            "rc_nro_rc": self._safe_column(reg_comp, "NRO_REG_COMP"),
            "cc_ej": self._safe_column(cta_comprob, "EJERCICIO"),
            "cc_rc": self._safe_column(cta_comprob, "NRO_REG_COMP"),
            "cc_tipo": self._safe_column(cta_comprob, "TIPO"),
            "cc_nro": self._safe_column(cta_comprob, "NRO_COMPROB"),
            "cc_prov": self._safe_column(cta_comprob, "COD_PROV"),
        }
        if any(v is None for v in cols.values()):
            return None
        return (
            select(
                cols["rc_ej"].label("OC_EJERCICIO"),
                cols["rc_uni"].label("OC_UNI_COMPRA"),
                cols["rc_nro_oc"].label("OC_NRO"),
                func.min(cols["cc_nro"]).label("OC_CC_NRO"),
                func.min(cols["cc_tipo"]).label("OC_CC_TIPO_COMPROB"),
                func.min(cols["cc_prov"]).label("OC_CC_COD_PROV"),
            )
            .select_from(
                reg_comp.join(
                    cta_comprob,
                    and_(
                        cols["rc_ej"] == cols["cc_ej"],
                        cols["rc_nro_rc"] == cols["cc_rc"],
                    ),
                )
            )
            .where(
                and_(
                    cols["rc_uni"].is_not(None),
                    cols["rc_nro_oc"].is_not(None),
                )
            )
            .group_by(
                cols["rc_ej"],
                cols["rc_uni"],
                cols["rc_nro_oc"],
            )
            .subquery("oc_to_cc")
        )

    def _build_op_imput_subquery(self, opi, cta_comprob, reg_comp=None):
        """Subquery PRIMARIA: bridge real OP ↔ CTA_COMPROB vía ORDEN_PAGO_IMPUT.

        ORDEN_PAGO_IMPUT modela físicamente la imputación de cada OP a uno o más
        comprobantes (CC). PK: (EJERCICIO, NRO_OP, NRO_REG_COMP, TIPO_COMPROB,
        NRO_COMPROB, COD_PROV, ...).

        Devuelve una fila por cada comprobante imputado (sin GROUP BY) para que
        el exporter reciba TODAS las facturas de una OP. La agrupación y dedup
        se realiza en _write_batch_orden_pago via grouped_cc_nros/cc_raw_by_key.

        Joins a CTA_COMPROB por la PK exacta:
            (EJERCICIO, TIPO, NRO_COMPROB, COD_PROV)
        para traer datos fiscales reales.

        Si REG_COMP esta disponible, tambien resuelve la OC desde el mismo
        NRO_REG_COMP imputado por la OP. No se usa ORDEN_PAGO.NRO_CANCE como
        puente a OC porque puede referenciar otra solicitud/compromiso.
        """
        if opi is None or cta_comprob is None:
            return None
        cols = {
            "opi_ej": self._safe_column(opi, "EJERCICIO"),
            "opi_op": self._safe_column(opi, "NRO_OP"),
            "opi_rc": self._safe_column(opi, "NRO_REG_COMP"),
            "opi_tipo": self._safe_column(opi, "TIPO_COMPROB"),
            "opi_nro": self._safe_column(opi, "NRO_COMPROB"),
            "opi_prov": self._safe_column(opi, "COD_PROV"),
            "cc_ej": self._safe_column(cta_comprob, "EJERCICIO"),
            "cc_tipo": self._safe_column(cta_comprob, "TIPO"),
            "cc_nro": self._safe_column(cta_comprob, "NRO_COMPROB"),
            "cc_prov": self._safe_column(cta_comprob, "COD_PROV"),
            "cc_imp": self._safe_column(cta_comprob, "IMPORTE_COMPR"),
            "cc_sin_iva": self._safe_column(cta_comprob, "IMPORTE_SIN_IVA"),
            "cc_liquido": self._safe_column(cta_comprob, "IMPORTE_LIQUIDO"),
            "cc_neto": self._safe_column(cta_comprob, "IMPORTE_NETO"),
            "cc_fec": self._safe_column(cta_comprob, "FECH_COMPROB"),
            "cc_venc": self._safe_column(cta_comprob, "FECH_VENCIM"),
        }
        required = ("opi_ej", "opi_op", "opi_rc", "opi_tipo", "opi_nro", "opi_prov",
                    "cc_ej", "cc_tipo", "cc_nro", "cc_prov", "cc_imp", "cc_fec")
        if any(cols[k] is None for k in required):
            return None

        cc_neto_expr = self._coalesce_optional_columns(
            cols["cc_liquido"],
            cols["cc_neto"],
            cols["cc_sin_iva"],
        )
        cc_sin_iva_expr = (
            cols["cc_sin_iva"] if cols["cc_sin_iva"] is not None
            else literal_column("NULL")
        )
        cc_venc_expr = (
            cols["cc_venc"] if cols["cc_venc"] is not None
            else literal_column("NULL")
        )

        reg_cols = {}
        if reg_comp is not None:
            reg_cols = {
                "rc_ej": self._safe_column(reg_comp, "EJERCICIO"),
                "rc_nro_rc": self._safe_column(reg_comp, "NRO_REG_COMP"),
                "rc_deleg": self._safe_column(reg_comp, "DELEG_SOLIC"),
                "rc_nro_sol": self._safe_column(reg_comp, "NRO_SOLIC"),
                "rc_uni": self._safe_column(reg_comp, "UNI_COMPRA"),
                "rc_nro_oc": self._safe_column(reg_comp, "NRO_OC"),
                "rc_prov": self._safe_column(reg_comp, "COD_PROV"),
            }
        has_reg_comp = bool(reg_cols) and all(col is not None for col in reg_cols.values())

        def nonblank(col):
            if self._conn.dialect.name == "sqlite":
                return func.nullif(col, "")
            return col

        if has_reg_comp:
            sg_deleg_expr = nonblank(reg_cols["rc_deleg"])
            sg_nro_expr = nonblank(reg_cols["rc_nro_sol"])
            rc_ej = nonblank(reg_cols["rc_ej"])
            rc_uni = nonblank(reg_cols["rc_uni"])
            rc_nro_oc = nonblank(reg_cols["rc_nro_oc"])
            rc_prov = nonblank(reg_cols["rc_prov"])
            oc_present = and_(
                rc_uni.is_not(None),
                rc_nro_oc.is_not(None),
            )
            sg_oc_ej_expr = case((oc_present, rc_ej))
            sg_oc_nro_expr = case((oc_present, rc_nro_oc))
            sg_oc_uni_expr = case((oc_present, rc_uni))
            sg_oc_prov_expr = case((oc_present, rc_prov))
        else:
            sg_deleg_expr = literal_column("NULL")
            sg_nro_expr = literal_column("NULL")
            sg_oc_ej_expr = literal_column("NULL")
            sg_oc_nro_expr = literal_column("NULL")
            sg_oc_uni_expr = literal_column("NULL")
            sg_oc_prov_expr = literal_column("NULL")

        from_clause = opi.outerjoin(
            cta_comprob,
            and_(
                cols["opi_ej"] == cols["cc_ej"],
                cols["opi_tipo"] == cols["cc_tipo"],
                cols["opi_nro"] == cols["cc_nro"],
                cols["opi_prov"] == cols["cc_prov"],
            ),
        )
        if has_reg_comp:
            from_clause = from_clause.outerjoin(
                reg_comp,
                and_(
                    cols["opi_ej"] == reg_cols["rc_ej"],
                    cols["opi_rc"] == reg_cols["rc_nro_rc"],
                    cols["opi_prov"] == reg_cols["rc_prov"],
                ),
            )

        return (
            select(
                cols["opi_ej"].label("OPI_EJERCICIO"),
                cols["opi_op"].label("OPI_NRO_OP"),
                cols["opi_rc"].label("OPI_NRO_REG_COMP"),
                cols["opi_tipo"].label("OPI_TIPO_COMPROB"),
                cols["opi_nro"].label("OPI_NRO_COMPROB"),
                cols["opi_prov"].label("OPI_COD_PROV"),
                sg_deleg_expr.label("SG_DELEG_SOLIC"),
                sg_nro_expr.label("SG_NRO_SOLIC"),
                sg_oc_ej_expr.label("SG_OC_EJERCICIO"),
                sg_oc_nro_expr.label("SG_OC_NRO"),
                sg_oc_uni_expr.label("SG_OC_UNI_COMPRA"),
                sg_oc_prov_expr.label("SG_OC_COD_PROV"),
                cols["cc_imp"].label("CTA_IMPORTE_COMPR"),
                cc_neto_expr.label("CTA_IMPORTE_NETO"),
                cc_sin_iva_expr.label("CTA_IMPORTE_SIN_IVA"),
                cols["cc_fec"].label("CTA_FECH_COMPROB"),
                cc_venc_expr.label("CTA_FECH_VENCIM"),
            )
            .select_from(from_clause)
            .subquery("op_imput")
        )

    def _build_op_required_oc_subquery(self, ejercicio_min: int | None = None):
        """Return OCs required by in-scope confirmed OPs, without using NRO_CANCE."""
        orden_pago = self._reflect_optional_table("ORDEN_PAGO")
        opi = self._reflect_optional_table("ORDEN_PAGO_IMPUT")
        reg_comp = self._reflect_optional_table("REG_COMP")
        if orden_pago is None or opi is None or reg_comp is None:
            return None

        cols = {
            "op_ej": self._safe_column(orden_pago, "EJERCICIO"),
            "op_nro": self._safe_column(orden_pago, "NRO_OP"),
            "op_estado": self._safe_column(orden_pago, "ESTADO_OP"),
            "op_confirmado": self._safe_column(orden_pago, "CONFIRMADO"),
            "op_fech_confirm": self._safe_column(orden_pago, "FECH_CONFIRM"),
            "opi_ej": self._safe_column(opi, "EJERCICIO"),
            "opi_op": self._safe_column(opi, "NRO_OP"),
            "opi_rc": self._safe_column(opi, "NRO_REG_COMP"),
            "opi_nro": self._safe_column(opi, "NRO_COMPROB"),
            "opi_prov": self._safe_column(opi, "COD_PROV"),
            "rc_ej": self._safe_column(reg_comp, "EJERCICIO"),
            "rc_nro_rc": self._safe_column(reg_comp, "NRO_REG_COMP"),
            "rc_uni": self._safe_column(reg_comp, "UNI_COMPRA"),
            "rc_nro_oc": self._safe_column(reg_comp, "NRO_OC"),
            "rc_prov": self._safe_column(reg_comp, "COD_PROV"),
        }
        required = (
            "op_ej", "op_nro", "op_estado", "op_confirmado", "op_fech_confirm",
            "opi_ej", "opi_op", "opi_rc", "opi_nro", "opi_prov",
            "rc_ej", "rc_nro_rc", "rc_uni", "rc_nro_oc", "rc_prov",
        )
        if any(cols[k] is None for k in required):
            return None

        def nonblank(col):
            if self._conn.dialect.name == "sqlite":
                return func.nullif(col, "")
            return col

        rc_ej = nonblank(cols["rc_ej"])
        rc_uni = nonblank(cols["rc_uni"])
        rc_nro_oc = nonblank(cols["rc_nro_oc"])

        from_clause = (
            orden_pago.join(
                opi,
                and_(
                    cols["op_ej"] == cols["opi_ej"],
                    cols["op_nro"] == cols["opi_op"],
                ),
            ).join(
                reg_comp,
                and_(
                    cols["opi_ej"] == cols["rc_ej"],
                    cols["opi_rc"] == cols["rc_nro_rc"],
                    cols["opi_prov"] == cols["rc_prov"],
                ),
            )
        )

        filters = [
            cols["op_estado"].in_(("C", "N")),
            cols["op_confirmado"] == "S",
            cols["op_fech_confirm"].is_not(None),
            nonblank(cols["opi_nro"]).is_not(None),
            rc_uni.is_not(None),
            rc_nro_oc.is_not(None),
        ]
        if ejercicio_min is not None:
            cutoff = (
                f"{ejercicio_min:04d}-01-01"
                if self._conn.dialect.name == "sqlite"
                else datetime(ejercicio_min, 1, 1)
            )
            filters.append(
                or_(
                    cols["op_ej"] >= ejercicio_min,
                    cols["op_fech_confirm"] >= cutoff,
                )
            )

        return (
            select(
                rc_ej.label("OC_EJERCICIO"),
                rc_uni.label("OC_UNI_COMPRA"),
                rc_nro_oc.label("OC_NRO"),
            )
            .select_from(from_clause)
            .where(and_(*filters))
            .distinct()
            .subquery("op_required_ocs")
        )

    def _apply_oc_dependency_filter(
        self,
        stmt: Select,
        cfg: EntityConfig,
        key_cols: dict[str, object],
    ) -> Select:
        if cfg.ejercicio_min is None:
            return stmt

        base_filter = key_cols["ejercicio"] >= cfg.ejercicio_min
        required_ocs = self._build_op_required_oc_subquery(cfg.ejercicio_min)
        if required_ocs is None:
            return stmt.where(base_filter)

        dependency_join = and_(
            required_ocs.c.OC_EJERCICIO == key_cols["ejercicio"],
            required_ocs.c.OC_UNI_COMPRA == key_cols["uni_compra"],
            required_ocs.c.OC_NRO == key_cols["nro_oc"],
        )
        return stmt.outerjoin(required_ocs, dependency_join).where(
            or_(base_filter, required_ocs.c.OC_EJERCICIO.is_not(None))
        )

    def _build_orden_pago_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        orden_pago = self._reflect_table("ORDEN_PAGO")
        # NOTE: las deducciones/retenciones NO se joinean acá — se traen aparte
        # via fetch_deducciones_for_ops() para evitar producto cartesiano.
        cta_comprob = self._reflect_optional_table("CTA_COMPROB")
        # ORDEN_PAGO_IMPUT: bridge fisico OP ↔ CTA_COMPROB (PK incluye
        # NRO_REG_COMP+TIPO_COMPROB+NRO_COMPROB+COD_PROV). Path PRIMARIO.
        opi = self._reflect_optional_table("ORDEN_PAGO_IMPUT")
        # REG_COMP: se usa solo por el NRO_REG_COMP exacto imputado en OPI.
        # No usar ORDEN_PAGO.NRO_CANCE como puente a OC: puede apuntar a otra SG.
        reg_comp = self._reflect_optional_table("REG_COMP")

        select_cols = [orden_pago]
        from_clause = orden_pago

        # ── Path PRIMARIO: ORDEN_PAGO ⨝ ORDEN_PAGO_IMPUT ⨝ CTA_COMPROB ───
        # Bridge real OP ↔ CC. Una OP puede pagar N comprobantes; la subquery
        # devuelve una fila por comprobante (sin GROUP BY) y el exporter los
        # acumula por (EJERCICIO, NRO_OP) en _write_batch_orden_pago.
        op_imput = self._build_op_imput_subquery(opi, cta_comprob, reg_comp)
        if op_imput is not None:
            from_clause = from_clause.outerjoin(
                op_imput,
                and_(
                    orden_pago.c.EJERCICIO == op_imput.c.OPI_EJERCICIO,
                    orden_pago.c.NRO_OP == op_imput.c.OPI_NRO_OP,
                ),
            )
            select_cols.extend([
                op_imput.c.OPI_NRO_REG_COMP,
                op_imput.c.OPI_TIPO_COMPROB,
                op_imput.c.OPI_NRO_COMPROB,
                op_imput.c.OPI_COD_PROV,
                op_imput.c.SG_DELEG_SOLIC,
                op_imput.c.SG_NRO_SOLIC,
                op_imput.c.SG_OC_EJERCICIO,
                op_imput.c.SG_OC_NRO,
                op_imput.c.SG_OC_UNI_COMPRA,
                op_imput.c.SG_OC_COD_PROV,
                op_imput.c.CTA_IMPORTE_COMPR,
                op_imput.c.CTA_IMPORTE_NETO,
                op_imput.c.CTA_IMPORTE_SIN_IVA,
                op_imput.c.CTA_FECH_COMPROB,
                op_imput.c.CTA_FECH_VENCIM,
            ])

        stmt = select(*select_cols).select_from(from_clause)
        stmt = self._apply_incremental_filters(stmt, orden_pago, cfg, checkpoint)
        base_filters = []
        estado_col = self._safe_column(orden_pago, "ESTADO_OP")
        confirmado_col = self._safe_column(orden_pago, "CONFIRMADO")
        fech_confirm_col = self._safe_column(orden_pago, "FECH_CONFIRM")
        if estado_col is not None:
            base_filters.append(estado_col == "C")
        if confirmado_col is not None:
            base_filters.append(confirmado_col == "S")
        if fech_confirm_col is not None:
            base_filters.append(fech_confirm_col.is_not(None))
        if base_filters:
            stmt = stmt.where(and_(*base_filters))
        return stmt.order_by(orden_pago.c.EJERCICIO, orden_pago.c.NRO_OP)

    def _apply_incremental_filters(
        self,
        stmt: Select,
        table,
        cfg: EntityConfig,
        cp: Checkpoint,
        extra_filters: list | None = None,
        apply_ejercicio_min: bool = True,
    ) -> Select:
        # Apply ejercicio_min only for entities whose config explicitly enables it.
        # It is independent from full_load/fresh checkpoint behavior.
        if apply_ejercicio_min and cfg.ejercicio_min is not None:
            ej_col = self._safe_column(table, "EJERCICIO")
            if ej_col is not None:
                stmt = stmt.where(ej_col >= cfg.ejercicio_min)

        if cfg.full_load or cp.is_fresh or (cp.last_id is None and cp.last_ts is None):
            return stmt

        filters = []

        # Cursor `>=` (no `>`): si dos filas comparten timestamp en el borde de
        # un batch, `>` las pierde silenciosamente. Con `>=` puede haber un re-envio
        # de la ultima fila procesada, pero el endpoint Paxapos es idempotente
        # (Pedido.internal_id / Egreso.identificador_pago / Gasto unique key) y
        # descarta el duplicado. Trade-off correcto para no perder datos.
        id_col = self._safe_column(table, cfg.id_field)
        if id_col is not None and cp.last_id is not None:
            filters.append(id_col >= cp.last_id)

        ts_col = self._safe_column(table, cfg.ts_field)
        if ts_col is not None and cp.last_ts is not None:
            filters.append(ts_col >= cp.last_ts)

        if (
            cfg.pending_reprocess_days
            and cfg.pending_state_field
            and cfg.pending_state_value is not None
            and ts_col is not None
        ):
            state_col = self._safe_column(table, cfg.pending_state_field)
            if state_col is not None:
                window_start = datetime.now(timezone.utc) - timedelta(days=cfg.pending_reprocess_days)
                # Soportar pending_state_value como string o lista/tuple para
                # cubrir multiples estados a re-evaluar (ej: ('N', 'A')).
                pending_value = cfg.pending_state_value
                if isinstance(pending_value, (list, tuple, set)):
                    state_filter = state_col.in_(list(pending_value))
                else:
                    state_filter = state_col == pending_value
                filters.append(
                    and_(state_filter, ts_col >= window_start)
                )

        if extra_filters:
            filters.extend(extra_filters)

        if filters:
            stmt = stmt.where(or_(*filters))

        return stmt

    @staticmethod
    def _safe_column(table, column_name: str | None):
        if not column_name:
            return None
        return table.c.get(column_name)
