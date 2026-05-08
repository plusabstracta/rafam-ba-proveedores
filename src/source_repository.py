from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, MetaData, Table, and_, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
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
            table = Table(table_name, self._metadata, schema=self._schema)
            for col_def in col_defs:
                table.append_column(Column(col_def["name"].upper(), col_def["type"]))
            self._tables[key] = table
            self._tables[table_name] = table
        return table

    def _reflect_optional_table(self, table_name: str):
        try:
            return self._reflect_table(table_name)
        except SQLAlchemyError:
            return None

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

    def fetch_retenciones_for_ops(
        self,
        op_keys: list[tuple[int, int]] | set[tuple[int, int]],
    ) -> dict[tuple[int, int], list[dict]]:
        """Trae retenciones para un set de OPs identificadas por (EJERCICIO, NRO_CANCE).

        Devuelve dict {(ejercicio, nro_cance): [{cod_ret, importe, descripcion}, ...]}.
        Se hace en query separada para evitar producto cartesiano OP×RET×CTA_HOJA_DE_RUTA
        en _build_orden_pago_statement.
        """
        if not op_keys:
            return {}

        retenciones = self._reflect_optional_table("RETENCIONES")
        if retenciones is None:
            return {}
        deducciones = self._reflect_optional_table("DEDUCCIONES")

        ret_ej = self._safe_column(retenciones, "EJERCICIO")
        ret_nc = self._safe_column(retenciones, "NRO_CANCE")
        ret_cod = self._safe_column(retenciones, "COD_RET")
        ret_imp = self._safe_column(retenciones, "IMPORTE")
        if ret_ej is None or ret_nc is None or ret_cod is None or ret_imp is None:
            return {}

        select_cols = [
            ret_ej.label("EJERCICIO"),
            ret_nc.label("NRO_CANCE"),
            ret_cod.label("COD_RET"),
            ret_imp.label("IMPORTE"),
        ]
        from_clause = retenciones

        if deducciones is not None:
            ded_codigo = self._safe_column(deducciones, "CODIGO")
            ded_desc = self._safe_column(deducciones, "DESCRIPCION")
            if ded_codigo is not None:
                join_conditions = [ret_cod == ded_codigo]
                ded_ejercicio = self._safe_column(deducciones, "EJERCICIO")
                if ded_ejercicio is not None:
                    join_conditions.append(ret_ej == ded_ejercicio)
                from_clause = from_clause.outerjoin(deducciones, and_(*join_conditions))
                if ded_desc is not None:
                    select_cols.append(ded_desc.label("DESCRIPCION"))

        # Filtrar por (EJERCICIO, NRO_CANCE) IN (...) — usamos OR de tuplas para
        # compatibilidad SQLite/Oracle.
        # Agrupamos por ejercicio para minimizar predicados.
        keys_by_ej: dict[int, set[int]] = {}
        for ej, nc in op_keys:
            if ej is None or nc is None:
                continue
            keys_by_ej.setdefault(int(ej), set()).add(int(nc))

        if not keys_by_ej:
            return {}

        ej_filters = []
        for ej, ncs in keys_by_ej.items():
            ej_filters.append(and_(ret_ej == ej, ret_nc.in_(list(ncs))))

        stmt = select(*select_cols).select_from(from_clause).where(or_(*ej_filters))

        out: dict[tuple[int, int], list[dict]] = {}
        for row in self._conn.execute(stmt):
            mapping = row._mapping
            try:
                ej = int(mapping["EJERCICIO"])
                nc = int(mapping["NRO_CANCE"])
            except (TypeError, ValueError, KeyError):
                continue
            entry = {
                "cod_ret": mapping.get("COD_RET"),
                "importe": mapping.get("IMPORTE"),
                "descripcion": mapping.get("DESCRIPCION") if "DESCRIPCION" in mapping.keys() else None,
            }
            out.setdefault((ej, nc), []).append(entry)
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
        cta_hdr = self._reflect_optional_table("CTA_HOJA_DE_RUTA")

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

        # LEFT JOIN CTA_HOJA_DE_RUTA para obtener CC_NRO (nro comprobante del gasto vinculado)
        if cta_hdr is not None:
            hdr_oc_ej = self._safe_column(cta_hdr, "OC_EJERCICIO")
            hdr_oc_uni = self._safe_column(cta_hdr, "OC_UNI_COMPRA")
            hdr_oc_nro = self._safe_column(cta_hdr, "OC_NRO")
            hdr_cc_nro = self._safe_column(cta_hdr, "CC_NRO")
            hdr_cc_tipo = self._safe_column(cta_hdr, "CC_TIPO_COMPROB")
            if hdr_oc_ej is not None and hdr_oc_uni is not None and hdr_oc_nro is not None:
                from_clause = from_clause.outerjoin(
                    cta_hdr,
                    and_(
                        oc.c.EJERCICIO == hdr_oc_ej,
                        oc.c.UNI_COMPRA == hdr_oc_uni,
                        oc.c.NRO_OC == hdr_oc_nro,
                    ),
                )
                if hdr_cc_nro is not None:
                    select_cols.append(hdr_cc_nro.label("HDR_CC_NRO"))
                if hdr_cc_tipo is not None:
                    select_cols.append(hdr_cc_tipo.label("HDR_CC_TIPO_COMPROB"))

        stmt = select(*select_cols).select_from(from_clause)
        extra_filters = []
        if not (cfg.full_load or checkpoint.is_fresh):
            fech_anul_col = self._safe_column(oc, "FECH_ANUL")
            estado_col = self._safe_column(oc, "ESTADO_OC")
            if fech_anul_col is not None and estado_col is not None:
                window_start = datetime.now(timezone.utc) - timedelta(days=cfg.pending_reprocess_days or 30)
                extra_filters.append(and_(estado_col == "A", fech_anul_col > window_start))

        stmt = self._apply_incremental_filters(stmt, oc, cfg, checkpoint, extra_filters=extra_filters)
        return stmt.order_by(oc.c.EJERCICIO, oc.c.UNI_COMPRA, oc.c.NRO_OC, oc_items.c.ITEM_OC)

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
        stmt = self._apply_incremental_filters(stmt, ped_items, cfg, checkpoint)
        return stmt.order_by(ped_items.c.EJERCICIO, ped_items.c.NUM_PED, ped_items.c.ORDEN)

    def _build_oc_items_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        oc_items = self._reflect_table("OC_ITEMS")
        orden_compra = self._reflect_table("ORDEN_COMPRA")
        solic_gastos = self._reflect_table("SOLIC_GASTOS")
        cta_hdr = self._reflect_optional_table("CTA_HOJA_DE_RUTA")

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

        # LEFT JOIN CTA_HOJA_DE_RUTA para obtener CC_NRO (nro comprobante del gasto vinculado)
        if cta_hdr is not None:
            hdr_oc_ej = self._safe_column(cta_hdr, "OC_EJERCICIO")
            hdr_oc_uni = self._safe_column(cta_hdr, "OC_UNI_COMPRA")
            hdr_oc_nro = self._safe_column(cta_hdr, "OC_NRO")
            hdr_cc_nro = self._safe_column(cta_hdr, "CC_NRO")
            hdr_cc_tipo = self._safe_column(cta_hdr, "CC_TIPO_COMPROB")
            if hdr_oc_ej is not None and hdr_oc_uni is not None and hdr_oc_nro is not None:
                from_clause = from_clause.outerjoin(
                    cta_hdr,
                    and_(
                        orden_compra.c.EJERCICIO == hdr_oc_ej,
                        orden_compra.c.UNI_COMPRA == hdr_oc_uni,
                        orden_compra.c.NRO_OC == hdr_oc_nro,
                    ),
                )
                if hdr_cc_nro is not None:
                    select_cols.append(hdr_cc_nro.label("HDR_CC_NRO"))
                if hdr_cc_tipo is not None:
                    select_cols.append(hdr_cc_tipo.label("HDR_CC_TIPO_COMPROB"))

        stmt = select(*select_cols).select_from(from_clause)
        stmt = self._apply_incremental_filters(stmt, oc_items, cfg, checkpoint)
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

        return (
            select(
                required_cols["reg_ejercicio"].label("EJERCICIO"),
                required_cols["reg_deleg_solic"].label("DELEG_SOLIC"),
                required_cols["reg_nro_solic"].label("NRO_SOLIC"),
                func.min(required_cols["cta_nro_comprob"]).label("CTA_NRO_COMPROB"),
                func.min(required_cols["cta_tipo"]).label("CTA_TIPO_COMPROB"),
                func.min(required_cols["cta_fech_comprob"]).label("CTA_FECH_COMPROB"),
                func.min(required_cols["cta_fech_vencim"]).label("CTA_FECH_VENCIM"),
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

    def _build_orden_pago_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        orden_pago = self._reflect_table("ORDEN_PAGO")
        solic_gastos = self._reflect_table("SOLIC_GASTOS")
        # NOTE: RETENCIONES y DEDUCCIONES NO se joinean acá — se traen aparte
        # via fetch_retenciones_for_ops() para evitar producto cartesiano con
        # CTA_HOJA_DE_RUTA (que tambien explota filas por OP).
        # CTA_HOJA_DE_RUTA: denormalized view linking OC→SG (and optionally PE).
        # In Oracle it's a pre-built VIEW; in SQLite dev it's a derived VIEW
        # created by load_csv_to_sqlite.py.  Required in both environments.
        cta_hdr = self._reflect_optional_table("CTA_HOJA_DE_RUTA")
        # CTA_COMPROB aporta los datos fiscales reales del comprobante
        # (IMPORTE_COMPR, FECH_COMPROB, FECH_VENCIM) para auto-crear el Gasto
        # en Paxapos cuando la SG aún no fue migrada.
        cta_comprob = self._reflect_optional_table("CTA_COMPROB")

        select_cols = [
            orden_pago,
            solic_gastos.c.DELEG_SOLIC.label("SG_DELEG_SOLIC"),
            solic_gastos.c.NRO_SOLIC.label("SG_NRO_SOLIC"),
        ]

        from_clause = orden_pago.outerjoin(
            solic_gastos,
            and_(
                orden_pago.c.EJERCICIO == solic_gastos.c.EJERCICIO,
                orden_pago.c.NRO_CANCE == solic_gastos.c.NRO_SOLIC,
            ),
        )

        # LEFT JOIN CTA_HOJA_DE_RUTA to resolve which OC/SG chain each OP belongs to.
        # The nexus is NRO_CANCE (= SG.NRO_SOLIC) which identifies the solicitud
        # being paid.  In Oracle the view is pre-built; in SQLite it's derived.
        if cta_hdr is not None:
            hdr_op_nro_col = self._safe_column(cta_hdr, "OP_NRO")
            hdr_op_ej_col = self._safe_column(cta_hdr, "OP_EJERCICIO")
        else:
            hdr_op_nro_col = None
            hdr_op_ej_col = None
        if hdr_op_nro_col is not None and hdr_op_ej_col is not None:
            from_clause = from_clause.outerjoin(
                cta_hdr,
                and_(
                    orden_pago.c.NRO_OP == hdr_op_nro_col,
                    orden_pago.c.EJERCICIO == hdr_op_ej_col,
                ),
            )
        # Select SG columns from the view
        for col_name, label in [
            ("SG_NRO", "HDR_SG_NRO"),
            ("SG_DELEG_SOLIC", "HDR_SG_DELEG"),
            ("SG_EJERCICIO", "HDR_SG_EJERCICIO"),
            ("OC_EJERCICIO", "HDR_OC_EJERCICIO"),
            ("OC_UNI_COMPRA", "HDR_OC_UNI_COMPRA"),
            ("OC_NRO", "HDR_OC_NRO"),
            ("OC_COD_PROV", "HDR_OC_COD_PROV"),
            ("CC_NRO", "HDR_CC_NRO"),
            ("CC_COD_PROV", "HDR_CC_COD_PROV"),
            ("CC_TIPO_COMPROB", "HDR_CC_TIPO_COMPROB"),
        ]:
            col = self._safe_column(cta_hdr, col_name) if cta_hdr is not None else None
            if col is not None:
                select_cols.append(col.label(label))

        # LEFT JOIN CTA_COMPROB para obtener datos fiscales reales del
        # comprobante (importe, fecha, vencimiento, tipo). Necesario para
        # auto-crear el Gasto en Paxapos si la SG no se migró todavía.
        # PK CTA_COMPROB: (EJERCICIO, TIPO, NRO_COMPROB, COD_PROV).
        # CTA_HOJA_DE_RUTA aporta CC_TIPO_COMPROB / CC_NRO / CC_COD_PROV
        # para hacer match exacto contra esa PK.
        if cta_hdr is not None and cta_comprob is not None:
            hdr_cc_tipo_col = self._safe_column(cta_hdr, "CC_TIPO_COMPROB")
            hdr_cc_nro_col = self._safe_column(cta_hdr, "CC_NRO")
            hdr_cc_cod_prov_col = self._safe_column(cta_hdr, "CC_COD_PROV")
            cta_ej_col = self._safe_column(cta_comprob, "EJERCICIO")
            cta_tipo_col = self._safe_column(cta_comprob, "TIPO")
            cta_nro_col = self._safe_column(cta_comprob, "NRO_COMPROB")
            cta_prov_col = self._safe_column(cta_comprob, "COD_PROV")
            if (
                hdr_cc_tipo_col is not None
                and hdr_cc_nro_col is not None
                and hdr_cc_cod_prov_col is not None
                and cta_ej_col is not None
                and cta_tipo_col is not None
                and cta_nro_col is not None
                and cta_prov_col is not None
            ):
                from_clause = from_clause.outerjoin(
                    cta_comprob,
                    and_(
                        orden_pago.c.EJERCICIO == cta_ej_col,
                        hdr_cc_tipo_col == cta_tipo_col,
                        hdr_cc_nro_col == cta_nro_col,
                        hdr_cc_cod_prov_col == cta_prov_col,
                    ),
                )
                for cta_col_name, label in [
                    ("IMPORTE_COMPR", "CTA_IMPORTE_COMPR"),
                    ("IMPORTE_SIN_IVA", "CTA_IMPORTE_SIN_IVA"),
                    ("FECH_COMPROB", "CTA_FECH_COMPROB"),
                    ("FECH_VENCIM", "CTA_FECH_VENCIM"),
                ]:
                    cta_col = self._safe_column(cta_comprob, cta_col_name)
                    if cta_col is not None:
                        select_cols.append(cta_col.label(label))

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
    ) -> Select:
        # Apply ejercicio_min only for entities whose config explicitly enables it.
        # It is independent from full_load/fresh checkpoint behavior.
        if cfg.ejercicio_min is not None:
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
