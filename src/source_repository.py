from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, MetaData, Table, and_, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Connection
from sqlalchemy.sql import Select

from .config import ENTITY_CONFIGS, SCHEMA
from .models import Checkpoint, EntityConfig


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
            col_defs = insp.get_columns(table_name, schema=self._schema)
            table = Table(table_name, self._metadata, schema=self._schema)
            for col_def in col_defs:
                table.append_column(Column(col_def["name"].upper(), col_def["type"]))
            self._tables[key] = table
            self._tables[table_name] = table
        return table

    def build_statement(self, entity: str, checkpoint: Checkpoint) -> Select:
        cfg = ENTITY_CONFIGS[entity]
        if entity == "orden_compra":
            return self._build_orden_compra_statement(cfg, checkpoint)
        if entity == "ped_items":
            return self._build_ped_items_statement(cfg, checkpoint)
        if entity == "oc_items":
            return self._build_oc_items_statement(cfg, checkpoint)
        if entity == "solic_gastos":
            return self._build_solic_gastos_statement(cfg, checkpoint)
        if entity == "orden_pago":
            return self._build_orden_pago_statement(cfg, checkpoint)
        return self._build_simple_table_statement(cfg, checkpoint)

    def execute(self, stmt: Select):
        return self._conn.execution_options(stream_results=True).execute(stmt)

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

        # Pivot: ORDEN_COMPRA → OC_ITEMS (items) → SOLIC_GASTOS (jurisdicción).
        # El cursor incremental aplica sobre ORDEN_COMPRA (FECH_OC / ESTADO_OC),
        # así solo se traen OCs recién modificadas CON sus items.
        stmt = (
            select(
                oc_items,
                oc.c.COD_PROV,
                oc.c.FECH_OC.label("OC_FECH_OC"),
                oc.c.OBSERVACIONES.label("OC_OBSERVACIONES"),
                oc.c.ESTADO_OC.label("OC_ESTADO_OC"),
                oc.c.FECH_CONFIRM.label("OC_FECH_CONFIRM"),
                oc.c.IMPORTE_TOT.label("OC_IMPORTE_TOT"),
                solic_gastos.c.JURISDICCION.label("SG_JURISDICCION"),
            )
            .select_from(
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
        )
        return self._apply_incremental_filters(stmt, oc, cfg, checkpoint)

    def _build_ped_items_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        ped_items = self._reflect_table("PED_ITEMS")
        pedidos = self._reflect_table("PEDIDOS")

        stmt = (
            select(
                ped_items,
                pedidos.c.FECH_EMI.label("PED_FECH_EMI"),
                pedidos.c.OBSERVACIONES.label("PED_OBSERVACIONES"),
                pedidos.c.CODIGO_DEP.label("PED_CODIGO_DEP"),
                pedidos.c.COSTO_TOT.label("PED_COSTO_TOT"),
            )
            .select_from(
                ped_items.outerjoin(
                    pedidos,
                    and_(
                        ped_items.c.EJERCICIO == pedidos.c.EJERCICIO,
                        ped_items.c.NUM_PED == pedidos.c.NUM_PED,
                    ),
                )
            )
        )
        return self._apply_incremental_filters(stmt, ped_items, cfg, checkpoint)

    def _build_oc_items_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        oc_items = self._reflect_table("OC_ITEMS")
        orden_compra = self._reflect_table("ORDEN_COMPRA")
        solic_gastos = self._reflect_table("SOLIC_GASTOS")

        stmt = (
            select(
                oc_items,
                orden_compra.c.COD_PROV,
                orden_compra.c.FECH_OC.label("OC_FECH_OC"),
                orden_compra.c.OBSERVACIONES.label("OC_OBSERVACIONES"),
                orden_compra.c.ESTADO_OC.label("OC_ESTADO_OC"),
                orden_compra.c.FECH_CONFIRM.label("OC_FECH_CONFIRM"),
                orden_compra.c.IMPORTE_TOT.label("OC_IMPORTE_TOT"),
                solic_gastos.c.JURISDICCION.label("SG_JURISDICCION"),
            )
            .select_from(
                oc_items.outerjoin(
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
        )
        return self._apply_incremental_filters(stmt, oc_items, cfg, checkpoint)

    def _build_solic_gastos_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        solic_gastos = self._reflect_table("SOLIC_GASTOS")
        oc_items = self._reflect_table("OC_ITEMS")
        orden_compra = self._reflect_table("ORDEN_COMPRA")

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

        stmt = (
            select(
                solic_gastos,
                oc_prov.c.OC_COD_PROV,
            )
            .select_from(
                solic_gastos.outerjoin(
                    oc_prov,
                    and_(
                        solic_gastos.c.EJERCICIO == oc_prov.c.EJERCICIO,
                        solic_gastos.c.DELEG_SOLIC == oc_prov.c.DELEG_SOLIC,
                        solic_gastos.c.NRO_SOLIC == oc_prov.c.NRO_SOLIC,
                    ),
                )
            )
        )
        return self._apply_incremental_filters(stmt, solic_gastos, cfg, checkpoint)

    def _build_orden_pago_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        orden_pago = self._reflect_table("ORDEN_PAGO")
        solic_gastos = self._reflect_table("SOLIC_GASTOS")

        stmt = (
            select(
                orden_pago,
                solic_gastos.c.DELEG_SOLIC.label("SG_DELEG_SOLIC"),
                solic_gastos.c.NRO_SOLIC.label("SG_NRO_SOLIC"),
            )
            .select_from(
                orden_pago.outerjoin(
                    solic_gastos,
                    and_(
                        orden_pago.c.EJERCICIO == solic_gastos.c.EJERCICIO,
                        orden_pago.c.NRO_CANCE == solic_gastos.c.NRO_SOLIC,
                    ),
                )
            )
        )
        return self._apply_incremental_filters(stmt, orden_pago, cfg, checkpoint)

    def _apply_incremental_filters(self, stmt: Select, table, cfg: EntityConfig, cp: Checkpoint) -> Select:
        if cfg.full_load or cp.is_fresh:
            return stmt

        filters = []

        id_col = self._safe_column(table, cfg.id_field)
        if id_col is not None and cp.last_id is not None:
            filters.append(id_col > cp.last_id)

        ts_col = self._safe_column(table, cfg.ts_field)
        if ts_col is not None and cp.last_ts is not None:
            filters.append(ts_col > cp.last_ts)

        if (
            cfg.pending_reprocess_days
            and cfg.pending_state_field
            and cfg.pending_state_value is not None
            and ts_col is not None
        ):
            state_col = self._safe_column(table, cfg.pending_state_field)
            if state_col is not None:
                window_start = datetime.now(timezone.utc) - timedelta(days=cfg.pending_reprocess_days)
                filters.append(
                    and_(state_col == cfg.pending_state_value, ts_col > window_start)
                )

        if filters:
            stmt = stmt.where(or_(*filters))

        return stmt

    @staticmethod
    def _safe_column(table, column_name: str | None):
        if not column_name:
            return None
        return table.c.get(column_name)
