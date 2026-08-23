from __future__ import annotations

import json
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

    def build_statement(
        self,
        entity: str,
        checkpoint: Checkpoint,
        retry_keys: set[str] | None = None,
    ) -> Select:
        """Arma la query de la entidad.

        ``retry_keys`` son las claves pendientes en la cola de reintentos
        (``RetryStore.pending_external_ids``). Se reinyectan como OR en el filtro
        incremental para que una fila salteada por dependencia faltante vuelva a
        entrar aunque el watermark ya haya avanzado. Solo aplica a las entidades
        que encolan (orden_pago / retenciones).
        """
        cfg = ENTITY_CONFIGS[entity]
        if entity == "oc_items":
            # oc_items es full_load: cada corrida escanea todo, asi que las
            # filas rechazadas re-entran naturalmente (no necesita reinyeccion).
            # Ojo: eso NO alcanza para las que quedaron 'permanent' en la cola
            # (rechazo persistente, ej. Pedido destino borrado) — a esas hay que
            # excluirlas explicitamente, y eso lo hace OcItemsMapper.build_payload
            # via RetryStore.permanent_external_ids() (paxapos#489).
            return self._build_oc_items_statement(cfg, checkpoint)
        if entity == "solic_gastos":
            return self._build_solic_gastos_statement(cfg, checkpoint, retry_keys)
        if entity == "orden_pago":
            return self._build_orden_pago_statement(cfg, checkpoint, retry_keys)
        if entity == "retenciones":
            # Retenciones escanea las mismas OP que orden_pago; el exporter
            # trae las deducciones por OP via fetch_deducciones_for_ops.
            return self._build_orden_pago_statement(cfg, checkpoint, retry_keys)
        if entity == "clasificaciones":
            return self._build_clasificaciones_statement(cfg, checkpoint)
        return self._build_simple_table_statement(cfg, checkpoint, retry_keys)

    def execute(self, stmt: Select):
        return self._conn.execution_options(stream_results=True).execute(stmt)

    def fetch_entity(
        self,
        entity: str,
        checkpoint: Checkpoint,
        retry_keys: set[str] | None = None,
    ):
        return self.execute(self.build_statement(entity, checkpoint, retry_keys))

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
                inner = inner.where(self._ejercicio_boundary_filter(table, ejercicio_min))
            stmt = select(func.count()).select_from(inner.subquery())
        else:
            stmt = select(func.count()).select_from(table)
            if ejercicio_min and has_ejercicio:
                stmt = stmt.where(self._ejercicio_boundary_filter(table, ejercicio_min))

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

    def fetch_forma_pago_for_ops(
        self,
        op_keys: list[tuple[int, int]] | set[tuple[int, int]],
    ) -> dict[tuple[int, int], str] | None:
        """Trae la forma de pago real de cada OP desde COMPROBANTES.ORIGEN_TIPO.

        Cadena RAFAM: ORDEN_PAGO (EJERCICIO, NRO_OP) -> EGRESOS (EJERCICIO,
        NRO_CANCE=NRO_OP) -> COMPROBANTES (EJERCICIO, NRO_CANCE). La forma de pago
        real vive en COMPROBANTES.ORIGEN_TIPO (CA/CM/NO/IN/EB/OB/EFP/INT/BSF...).

        ORDEN_PAGO NO tiene la forma de pago; el codigo anterior buscaba TIPO_CANCE
        en ORDEN_PAGO (columna inexistente) y caia siempre al default Transferencia.

        Clave: (EJERCICIO, NRO_OP). Devuelve {(ejercicio, nro_op): origen_tipo}.
        Una OP puede pagar con varios comprobantes y cada uno con distinta forma de
        pago; se conserva el ORIGEN_TIPO predominante por IMPORTE y, si hay mas de
        uno distinto, se emite un warning discriminando los codigos y montos.

        Retorna None si EGRESOS/COMPROBANTES no estan disponibles o falla la query
        (señal para que el caller use el default). Retorna {} si no hay filas.
        """
        if not op_keys:
            return {}

        egresos = self._reflect_optional_table("EGRESOS")
        comprobantes = self._reflect_optional_table("COMPROBANTES")
        if egresos is None or comprobantes is None:
            logger.warning(
                "fetch_forma_pago_for_ops: tablas EGRESOS/COMPROBANTES no disponibles "
                "(schema=%s). Se usara la forma de pago por defecto para todas las OP.",
                self._schema,
            )
            return None

        eg_ej = self._safe_column(egresos, "EJERCICIO")
        eg_nro_cance = self._safe_column(egresos, "NRO_CANCE")
        cp_ej = self._safe_column(comprobantes, "EJERCICIO")
        cp_nro_cance = self._safe_column(comprobantes, "NRO_CANCE")
        cp_origen_tipo = self._safe_column(comprobantes, "ORIGEN_TIPO")
        if any(c is None for c in (eg_ej, eg_nro_cance, cp_ej, cp_nro_cance, cp_origen_tipo)):
            logger.error(
                "fetch_forma_pago_for_ops: columnas requeridas ausentes "
                "(EGRESOS.EJERCICIO=%s, EGRESOS.NRO_CANCE=%s, COMPROBANTES.EJERCICIO=%s, "
                "COMPROBANTES.NRO_CANCE=%s, COMPROBANTES.ORIGEN_TIPO=%s). "
                "Se usara la forma de pago por defecto.",
                eg_ej is not None, eg_nro_cance is not None, cp_ej is not None,
                cp_nro_cance is not None, cp_origen_tipo is not None,
            )
            return None

        cp_importe = self._safe_column(comprobantes, "IMPORTE")
        eg_tipo_cance = self._safe_column(egresos, "TIPO_CANCE")
        eg_estado = self._safe_column(egresos, "ESTADO")

        select_cols = [
            eg_ej.label("EJERCICIO"),
            eg_nro_cance.label("NRO_OP"),
            cp_origen_tipo.label("ORIGEN_TIPO"),
        ]
        if cp_importe is not None:
            select_cols.append(cp_importe.label("IMPORTE"))

        join_on = and_(eg_ej == cp_ej, eg_nro_cance == cp_nro_cance)
        from_clause = egresos.join(comprobantes, join_on)

        keys_by_ej: dict[int, set[int]] = {}
        for ej, nro_op in op_keys:
            if ej is None or nro_op is None:
                continue
            keys_by_ej.setdefault(int(ej), set()).add(int(nro_op))
        if not keys_by_ej:
            return {}

        ej_filters = []
        for ej, nro_ops in keys_by_ej.items():
            ej_filters.append(and_(eg_ej == ej, eg_nro_cance.in_(list(nro_ops))))

        where_filters = [or_(*ej_filters)]
        # Solo pagos normales (P); descartar anulaciones (A), devoluciones (D), etc.
        # La validez del pago se determina por EGRESOS (TIPO_CANCE='P', ESTADO='N').
        # NO se filtra COMPROBANTES.ESTADO: es numerico (1/2/3/4), no la letra 'N'
        # como EGRESOS. El filtro previo cp_estado=='N' no matcheaba nunca y dejaba
        # TODAS las OP sin forma de pago (caian a "Otros").
        if eg_tipo_cance is not None:
            where_filters.append(eg_tipo_cance == "P")
        if eg_estado is not None:
            where_filters.append(eg_estado == "N")

        stmt = select(*select_cols).select_from(from_clause).where(and_(*where_filters))

        # Acumular importe por (OP, ORIGEN_TIPO) para elegir el predominante.
        accum: dict[tuple[int, int], dict[str, float]] = {}
        try:
            for row in self._conn.execute(stmt):
                mapping = row._mapping
                try:
                    ej = int(mapping["EJERCICIO"])
                    nro_op = int(mapping["NRO_OP"])
                except (TypeError, ValueError, KeyError):
                    continue
                origen = str(mapping.get("ORIGEN_TIPO") or "").strip().upper()
                if not origen:
                    continue
                try:
                    importe = abs(float(mapping.get("IMPORTE"))) if "IMPORTE" in mapping.keys() and mapping.get("IMPORTE") is not None else 0.0
                except (TypeError, ValueError):
                    importe = 0.0
                por_tipo = accum.setdefault((ej, nro_op), {})
                # +importe para ponderar; el 1e-9 asegura registrar el tipo aun con importe 0.
                por_tipo[origen] = por_tipo.get(origen, 0.0) + importe + 1e-9
        except (SQLAlchemyError, Exception) as exc:
            logger.error(
                "fetch_forma_pago_for_ops: error ejecutando query EGRESOS/COMPROBANTES: %s. "
                "Se usara la forma de pago por defecto.",
                exc,
            )
            return None

        out: dict[tuple[int, int], str] = {}
        for op_key, por_tipo in accum.items():
            if not por_tipo:
                continue
            # Predominante por importe; desempate lexical estable.
            chosen = sorted(por_tipo.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[0][0]
            out[op_key] = chosen
            if len(por_tipo) > 1:
                detalle = ", ".join(
                    f"{code}={monto:.2f}" for code, monto in sorted(por_tipo.items())
                )
                logger.warning(
                    "fetch_forma_pago_for_ops: OP %s-%s tiene %d formas de pago distintas "
                    "(%s). Se asigna la predominante '%s'.",
                    op_key[0], op_key[1], len(por_tipo), detalle, chosen,
                )

        if out:
            logger.debug(
                "fetch_forma_pago_for_ops: forma de pago resuelta para %d OPs desde COMPROBANTES.",
                len(out),
            )
        else:
            logger.debug(
                "fetch_forma_pago_for_ops: EGRESOS/COMPROBANTES no devolvio filas para %d keys.",
                len(op_keys),
            )
        return out

    def fetch_proveedores_by_keys(self, cod_provs: list[int]) -> tuple[list[str], list[tuple]]:
        """Fetch specific proveedores by COD_PROV for change detection."""
        if not cod_provs:
            return [], []
        table = self._reflect_table("PROVEEDORES")
        stmt = select(table).where(table.c.COD_PROV.in_(cod_provs))
        result = self._conn.execute(stmt)
        columns = list(result.keys())
        rows = [tuple(row) for row in result.fetchall()]
        return columns, rows

    def fetch_oc_items_by_keys(self, oc_keys: list[dict]) -> tuple[list[str], list[tuple]]:
        """Fetch specific oc_items joined with orden_compra by composite keys for change detection."""
        if not oc_keys:
            return [], []

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

        key_filters = []
        for k in oc_keys:
            key_filters.append(
                and_(
                    oc_items.c.EJERCICIO == k["ejercicio"],
                    oc_items.c.UNI_COMPRA == k["uni_compra"],
                    oc_items.c.NRO_OC == k["nro_oc"]
                )
            )
        stmt = stmt.where(or_(*key_filters))
        stmt = stmt.order_by(oc_items.c.EJERCICIO, oc_items.c.UNI_COMPRA, oc_items.c.NRO_OC, oc_items.c.ITEM_OC)

        result = self._conn.execute(stmt)
        columns = list(result.keys())
        rows = [tuple(row) for row in result.fetchall()]
        return columns, rows

    def _build_simple_table_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
        retry_keys: set[str] | None = None,
    ) -> Select:
        table = self._reflect_table(cfg.table_name)
        stmt = select(table)
        # Reinyeccion de la cola de reintentos (hoy solo aplica a proveedores:
        # las demas entidades "simples" son full_load o no encolan). Sin esto,
        # un proveedor rechazado por el receptor quedaba fuera del cursor
        # FECHA_ULT_COMP para siempre.
        retry_filter = None
        if cfg.name == "proveedores":
            retry_filter = self._proveedores_retry_filter(table, retry_keys)
        stmt = self._apply_incremental_filters(
            stmt,
            table,
            cfg,
            checkpoint,
            extra_filters=[retry_filter] if retry_filter is not None else None,
        )
        ts_col = self._safe_column(table, cfg.ts_field)
        if ts_col is not None:
            pk_cols = [c for c in table.primary_key.columns]
            stmt = stmt.order_by(ts_col, *pk_cols)
        return stmt

    def _proveedores_retry_filter(self, table, retry_keys):
        """Predicado que reinyecta proveedores pendientes de la cola.

        Las claves son ``str(COD_PROV)`` (mismo formato que el link store y
        ``exporter._outcome_key``).
        """
        cods: list[int] = []
        for key in retry_keys or ():
            try:
                cods.append(int(str(key).strip()))
            except (TypeError, ValueError):
                continue
        if not cods:
            return None
        cod_col = self._safe_column(table, "COD_PROV")
        if cod_col is None:
            return None
        if len(cods) > self._RETRY_REQUEUE_MAX:
            logger.warning(
                "Cola de reintentos con %d proveedores pendientes; se reinyectan %d en esta corrida.",
                len(cods), self._RETRY_REQUEUE_MAX,
            )
            cods = sorted(cods)[: self._RETRY_REQUEUE_MAX]
        cods = sorted(set(cods))
        clauses = [
            cod_col.in_(cods[start:start + self._IN_CHUNK])
            for start in range(0, len(cods), self._IN_CHUNK)
        ]
        logger.info("Reinyectando %d proveedores pendientes de la cola de reintentos", len(cods))
        return or_(*clauses) if len(clauses) > 1 else clauses[0]

    def _sg_retry_filter(self, table, retry_keys):
        """Predicado que reinyecta solicitudes de gasto pendientes de la cola.

        Las claves son ``json({"deleg_solic": D, "ejercicio": E, "nro_solic": N})``
        (el external_id del gasto; se toleran campos extra como ``nro_comprob``).
        """
        triples: set[tuple[int, int, int]] = set()
        for key in retry_keys or ():
            try:
                data = json.loads(key)
                triples.add((
                    int(data["ejercicio"]),
                    int(data["deleg_solic"]),
                    int(data["nro_solic"]),
                ))
            except (TypeError, ValueError, KeyError):
                continue
        if not triples:
            return None
        ej_col = self._safe_column(table, "EJERCICIO")
        deleg_col = self._safe_column(table, "DELEG_SOLIC")
        nro_col = self._safe_column(table, "NRO_SOLIC")
        if ej_col is None or deleg_col is None or nro_col is None:
            return None
        items = sorted(triples)
        if len(items) > self._RETRY_REQUEUE_MAX:
            logger.warning(
                "Cola de reintentos con %d gastos pendientes; se reinyectan %d en esta corrida.",
                len(items), self._RETRY_REQUEUE_MAX,
            )
            items = items[: self._RETRY_REQUEUE_MAX]
        clauses = [
            and_(ej_col == ej, deleg_col == deleg, nro_col == nro)
            for ej, deleg, nro in items
        ]
        logger.info("Reinyectando %d gastos pendientes de la cola de reintentos", len(items))
        return or_(*clauses) if len(clauses) > 1 else clauses[0]

    def _build_clasificaciones_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
    ) -> Select:
        """DISTINCT de la jerarquia del clasificador de gasto desde GASTOS.

        RAFAM no tiene tabla maestra del clasificador: la jerarquia de 4
        niveles + DENOMINACION vive repetida en GASTOS. Extraemos las
        combinaciones distintas (con inciso no nulo, defensa contra basura),
        ordenadas por los 4 niveles para que el mapper reconstruya el arbol
        (padres antes que hijos).
        """
        gastos = self._reflect_table(cfg.table_name)  # GASTOS
        cols = [
            gastos.c.INCISO.label("INCISO"),
            gastos.c.PAR_PRIN.label("PAR_PRIN"),
            gastos.c.PAR_PARC.label("PAR_PARC"),
            gastos.c.PAR_SUBP.label("PAR_SUBP"),
            gastos.c.DENOMINACION.label("DENOMINACION"),
        ]
        return (
            select(*cols)
            .distinct()
            .where(gastos.c.INCISO.isnot(None))
            .order_by(
                gastos.c.INCISO,
                gastos.c.PAR_PRIN,
                gastos.c.PAR_PARC,
                gastos.c.PAR_SUBP,
            )
        )

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
            fech_confirm_col=orden_compra.c.FECH_CONFIRM,
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
        retry_keys: set[str] | None = None,
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
        retry_filter = self._sg_retry_filter(solic_gastos, retry_keys)
        stmt = self._apply_incremental_filters(
            stmt,
            solic_gastos,
            cfg,
            checkpoint,
            extra_filters=[retry_filter] if retry_filter is not None else None,
        )
        return stmt.order_by(solic_gastos.c.FECH_SOLIC, solic_gastos.c.EJERCICIO, solic_gastos.c.DELEG_SOLIC, solic_gastos.c.NRO_SOLIC)

    def fetch_cta_comprob_for_sgs(
        self, sg_keys: list[tuple[int, int, int]]
    ) -> dict[tuple[int, int, int], list[dict]] | None:
        """Comprobantes individuales de cada SG (sin agrupar).

        La query principal de solic_gastos agrega los comprobantes con MIN()
        (una fila por SG). Para las SG con 2+ comprobantes eso pierde los
        demas; este fetch trae TODOS los comprobantes de las SG pedidas para
        que el mapper emita un candidato de enriquecimiento por comprobante.

        Devuelve {(ejercicio, deleg_solic, nro_solic): [dict CTA_*...]} o None
        si REG_COMP/CTA_COMPROB no estan disponibles.
        """
        if not sg_keys:
            return {}
        reg_comp = self._reflect_optional_table("REG_COMP")
        cta_comprob = self._reflect_optional_table("CTA_COMPROB")
        if reg_comp is None or cta_comprob is None:
            return None

        cols = {
            "rc_ej": self._safe_column(reg_comp, "EJERCICIO"),
            "rc_nro_rc": self._safe_column(reg_comp, "NRO_REG_COMP"),
            "rc_deleg": self._safe_column(reg_comp, "DELEG_SOLIC"),
            "rc_nro_sol": self._safe_column(reg_comp, "NRO_SOLIC"),
            "cc_ej": self._safe_column(cta_comprob, "EJERCICIO"),
            "cc_rc": self._safe_column(cta_comprob, "NRO_REG_COMP"),
            "cc_tipo": self._safe_column(cta_comprob, "TIPO"),
            "cc_nro": self._safe_column(cta_comprob, "NRO_COMPROB"),
            "cc_fec": self._safe_column(cta_comprob, "FECH_COMPROB"),
        }
        if any(v is None for v in cols.values()):
            return None

        cc_imp = self._safe_column(cta_comprob, "IMPORTE_COMPR")
        cc_sin_iva = self._safe_column(cta_comprob, "IMPORTE_SIN_IVA")
        cc_neto = self._coalesce_optional_columns(
            self._safe_column(cta_comprob, "IMPORTE_LIQUIDO"),
            self._safe_column(cta_comprob, "IMPORTE_NETO"),
            cc_sin_iva,
        )
        cc_venc = self._safe_column(cta_comprob, "FECH_VENCIM")

        select_cols = [
            cols["rc_ej"].label("EJERCICIO"),
            cols["rc_deleg"].label("DELEG_SOLIC"),
            cols["rc_nro_sol"].label("NRO_SOLIC"),
            cols["cc_nro"].label("CTA_NRO_COMPROB"),
            cols["cc_tipo"].label("CTA_TIPO_COMPROB"),
            cols["cc_fec"].label("CTA_FECH_COMPROB"),
            (cc_venc if cc_venc is not None else literal_column("NULL")).label("CTA_FECH_VENCIM"),
            (cc_imp if cc_imp is not None else literal_column("NULL")).label("CTA_IMPORTE_COMPR"),
            cc_neto.label("CTA_IMPORTE_NETO"),
            (cc_sin_iva if cc_sin_iva is not None else literal_column("NULL")).label("CTA_IMPORTE_SIN_IVA"),
        ]

        out: dict[tuple[int, int, int], list[dict]] = {}
        keys = sorted({(int(e), int(d), int(n)) for e, d, n in sg_keys})
        for start in range(0, len(keys), self._IN_CHUNK):
            chunk = keys[start:start + self._IN_CHUNK]
            key_clauses = [
                and_(cols["rc_ej"] == ej, cols["rc_deleg"] == deleg, cols["rc_nro_sol"] == nro)
                for ej, deleg, nro in chunk
            ]
            stmt = (
                select(*select_cols)
                .select_from(
                    reg_comp.join(
                        cta_comprob,
                        and_(
                            cols["rc_ej"] == cols["cc_ej"],
                            cols["rc_nro_rc"] == cols["cc_rc"],
                        ),
                    )
                )
                .where(or_(*key_clauses) if len(key_clauses) > 1 else key_clauses[0])
            )
            for row in self._conn.execute(stmt).mappings():
                ej = int(row["EJERCICIO"])
                deleg = int(row["DELEG_SOLIC"])
                nro = int(row["NRO_SOLIC"])
                out.setdefault((ej, deleg, nro), []).append(dict(row))
        return out

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
            # Partida presupuestaria imputada por la OP (clasificador de gasto).
            # Opcional: si la tabla no las expone, quedan NULL y el gasto va sin clasificar.
            "opi_inciso": self._safe_column(opi, "INCISO"),
            "opi_par_prin": self._safe_column(opi, "PAR_PRIN"),
            "opi_par_parc": self._safe_column(opi, "PAR_PARC"),
            "opi_par_subp": self._safe_column(opi, "PAR_SUBP"),
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

        opi_inciso_expr = (
            cols["opi_inciso"] if cols["opi_inciso"] is not None else literal_column("NULL")
        )
        opi_par_prin_expr = (
            cols["opi_par_prin"] if cols["opi_par_prin"] is not None else literal_column("NULL")
        )
        opi_par_parc_expr = (
            cols["opi_par_parc"] if cols["opi_par_parc"] is not None else literal_column("NULL")
        )
        opi_par_subp_expr = (
            cols["opi_par_subp"] if cols["opi_par_subp"] is not None else literal_column("NULL")
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
                opi_inciso_expr.label("OPI_INCISO"),
                opi_par_prin_expr.label("OPI_PAR_PRIN"),
                opi_par_parc_expr.label("OPI_PAR_PARC"),
                opi_par_subp_expr.label("OPI_PAR_SUBP"),
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
            cols["op_estado"] == "C",
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
        fech_confirm_col=None,
    ) -> Select:
        if cfg.ejercicio_min is None:
            return stmt

        if fech_confirm_col is not None:
            cutoff = (
                f"{cfg.ejercicio_min:04d}-01-01"
                if self._conn.dialect.name == "sqlite"
                else datetime(cfg.ejercicio_min, 1, 1)
            )
            base_filter = or_(
                key_cols["ejercicio"] >= cfg.ejercicio_min,
                and_(
                    key_cols["ejercicio"] == cfg.ejercicio_min - 1,
                    fech_confirm_col >= cutoff,
                ),
            )
        else:
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

    # Maximo de claves de la cola de reintentos que se reinyectan por corrida.
    # Evita generar un predicado gigante si la cola creció mucho; el resto entra
    # en las corridas siguientes.
    _RETRY_REQUEUE_MAX = 2000
    # Oracle limita las listas IN a 1000 elementos.
    _IN_CHUNK = 900

    @staticmethod
    def _parse_op_retry_keys(retry_keys) -> list[tuple[int, int]]:
        """Convierte claves de la cola ('{\"ejercicio\":E,\"nro_op\":N}') a tuplas."""
        pairs: list[tuple[int, int]] = []
        for key in retry_keys or ():
            try:
                data = json.loads(key)
                pairs.append((int(data["ejercicio"]), int(data["nro_op"])))
            except (TypeError, ValueError, KeyError):
                continue
        return pairs

    def _op_retry_filter(self, table, retry_keys):
        """Predicado OR que reinyecta las OP pendientes en la cola de reintentos.

        Sin esto, una OP salteada por dependencia faltante (OC aún no migrada,
        comprobante ausente) quedaba fuera del cursor para siempre porque el
        watermark avanza igual.
        """
        pairs = self._parse_op_retry_keys(retry_keys)
        if not pairs:
            return None

        ej_col = self._safe_column(table, "EJERCICIO")
        nro_col = self._safe_column(table, "NRO_OP")
        if ej_col is None or nro_col is None:
            return None

        if len(pairs) > self._RETRY_REQUEUE_MAX:
            logger.warning(
                "Cola de reintentos con %d OPs pendientes; se reinyectan las %d mas "
                "antiguas en esta corrida (el resto entra en las proximas).",
                len(pairs), self._RETRY_REQUEUE_MAX,
            )
            pairs = sorted(pairs)[: self._RETRY_REQUEUE_MAX]

        by_ejercicio: dict[int, set[int]] = {}
        for ejercicio, nro_op in pairs:
            by_ejercicio.setdefault(ejercicio, set()).add(nro_op)

        clauses = []
        for ejercicio, nros in sorted(by_ejercicio.items()):
            nros_list = sorted(nros)
            for start in range(0, len(nros_list), self._IN_CHUNK):
                chunk = nros_list[start:start + self._IN_CHUNK]
                clauses.append(and_(ej_col == ejercicio, nro_col.in_(chunk)))

        if not clauses:
            return None

        logger.info(
            "Reinyectando %d OPs pendientes de la cola de reintentos en la query",
            len(pairs),
        )
        return or_(*clauses) if len(clauses) > 1 else clauses[0]

    def _build_orden_pago_statement(
        self,
        cfg: EntityConfig,
        checkpoint: Checkpoint,
        retry_keys: set[str] | None = None,
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
                op_imput.c.OPI_INCISO,
                op_imput.c.OPI_PAR_PRIN,
                op_imput.c.OPI_PAR_PARC,
                op_imput.c.OPI_PAR_SUBP,
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
        retry_filter = self._op_retry_filter(orden_pago, retry_keys)
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

        base_condition = and_(*base_filters) if base_filters else None

        stmt = self._apply_incremental_filters(
            stmt,
            orden_pago,
            cfg,
            checkpoint,
            extra_filters=[retry_filter] if retry_filter is not None else None,
            base_condition=base_condition,
        )
        return stmt.order_by(orden_pago.c.FECH_CONFIRM, orden_pago.c.EJERCICIO, orden_pago.c.NRO_OP)

    def _ejercicio_boundary_filter(self, table, ejercicio_min: int, ej_col=None):
        """Corte por ejercicio con excepcion de cruce fiscal.

        Se incluye la fila si EJERCICIO >= ejercicio_min, O si pertenece al
        ejercicio inmediatamente anterior (ejercicio_min - 1) pero fue
        confirmada ya en el ejercicio nuevo (FECH_CONFIRM >= ejercicio_min-01-01).
        Esto captura OC/OP/SG/retenciones de 2025 confirmadas en 2026, que deben
        migrarse igual. FECH_CONFIRM solo se setea al confirmar, asi que la fecha
        actua como senial de confirmacion.

        Si la tabla no tiene FECH_CONFIRM, cae al corte simple EJERCICIO >= min.
        """
        if ej_col is None:
            ej_col = self._safe_column(table, "EJERCICIO")
        fech_confirm_col = self._safe_column(table, "FECH_CONFIRM")
        if fech_confirm_col is None:
            return ej_col >= ejercicio_min
        cutoff = (
            f"{ejercicio_min:04d}-01-01"
            if self._conn.dialect.name == "sqlite"
            else datetime(ejercicio_min, 1, 1)
        )
        return or_(
            ej_col >= ejercicio_min,
            and_(ej_col == ejercicio_min - 1, fech_confirm_col >= cutoff),
        )

    def _apply_incremental_filters(
        self,
        stmt: Select,
        table,
        cfg: EntityConfig,
        cp: Checkpoint,
        extra_filters: list | None = None,
        apply_ejercicio_min: bool = True,
        base_condition=None,
    ) -> Select:
        if apply_ejercicio_min and cfg.ejercicio_min is not None:
            ej_col = self._safe_column(table, "EJERCICIO")
            if ej_col is not None:
                stmt = stmt.where(
                    self._ejercicio_boundary_filter(table, cfg.ejercicio_min, ej_col)
                )

        if cfg.full_load or cp.is_fresh or (cp.last_id is None and cp.last_ts is None):
            if base_condition is not None:
                stmt = stmt.where(base_condition)
            return stmt

        normal_filters = []

        # Cursor `>=` (no `>`): si dos filas comparten timestamp en el borde de
        # un batch, `>` las pierde silenciosamente. Con `>=` puede haber un re-envio
        # de la ultima fila procesada, pero el endpoint Paxapos es idempotente
        # (Pedido.internal_id / Egreso.identificador_pago / Gasto unique key) y
        # descarta el duplicado. Trade-off correcto para no perder datos.
        id_col = self._safe_column(table, cfg.id_field)
        if id_col is not None and cp.last_id is not None:
            normal_filters.append(id_col >= cp.last_id)

        ts_col = self._safe_column(table, cfg.ts_field)
        if ts_col is not None and cp.last_ts is not None:
            normal_filters.append(ts_col >= cp.last_ts)

        if base_condition is not None:
            normal_filters.append(base_condition)

        normal_clause = and_(*normal_filters) if normal_filters else None

        reprocess_clause = None
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
                reprocess_clause = and_(state_filter, ts_col >= window_start)

        final_or = []
        if normal_clause is not None:
            final_or.append(normal_clause)
        if reprocess_clause is not None:
            final_or.append(reprocess_clause)

        if extra_filters:
            final_or.extend(extra_filters)

        if final_or:
            stmt = stmt.where(or_(*final_or))

        return stmt

    @staticmethod
    def _safe_column(table, column_name: str | None):
        if not column_name:
            return None
        return table.c.get(column_name)

    # ── Integridad: lookups puntuales por clave de negocio ────────────────

    # Configuración por entidad: tabla RAFAM, campos de estado y PK de negocio.
    _INTEGRIDAD_CONFIG: dict[str, dict] = {
        "proveedores": {
            "table": "PROVEEDORES",
            "pk": [("COD_PROV", "cod_prov")],          # (columna_rafam, campo_source_key)
            "estado_col": "COD_ESTADO",
            "anulado_valor": None,                      # para proveedores: any change, no fixed value
            "fech_anul_col": None,
        },
        "orden_compra": {
            "table": "ORDEN_COMPRA",
            "pk": [
                ("EJERCICIO", "ejercicio"),
                ("UNI_COMPRA", "uni_compra"),
                ("NRO_OC", "nro_oc"),
            ],
            "estado_col": "ESTADO_OC",
            "anulado_valor": "A",
            "fech_anul_col": "FECH_ANUL",
        },
        "gasto": {
            "table": "SOLIC_GASTOS",
            "pk": [
                ("EJERCICIO", "ejercicio"),
                ("DELEG_SOLIC", "deleg_solic"),
                ("NRO_SOLIC", "nro_solic"),
            ],
            "estado_col": "ESTADO_SOLIC",
            "anulado_valor": "A",
            "fech_anul_col": "FECH_ANUL",
        },
        "orden_pago": {
            "table": "ORDEN_PAGO",
            "pk": [
                ("EJERCICIO", "ejercicio"),
                ("NRO_OP", "nro_op"),
            ],
            "estado_col": "ESTADO_OP",
            "anulado_valor": "A",
            "fech_anul_col": "FECH_ANUL",
        },
        # retenciones comparte tabla con orden_pago; la anulación se detecta
        # verificando que la OP padre esté anulada.
        "retenciones": {
            "table": "ORDEN_PAGO",
            "pk": [
                ("EJERCICIO", "ejercicio"),
                ("NRO_OP", "nro_op"),
            ],
            "estado_col": "ESTADO_OP",
            "anulado_valor": "A",
            "fech_anul_col": "FECH_ANUL",
        },
    }

    def fetch_estado_by_key(
        self,
        entity: str,
        source_key: str,
    ) -> dict | None:
        """Consulta puntual del estado de anulación de un registro por su clave de negocio.

        Devuelve un dict con los campos de estado/anulación del registro, o None
        si el registro no existe físicamente en RAFAM (eliminación física, raro).

        El dict incluye siempre:
          - ``estado``: valor del campo de estado (ej. 'A', 'C', 'R', '0', ...)
          - ``anulado``: bool — True si estado == anulado_valor del config
          - ``fech_anul``: valor de FECH_ANUL si existe, o None
          - ``source_key``: echo del source_key recibido

        Uso típico en el script de integridad::

            info = repo.fetch_estado_by_key("orden_compra", source_key)
            if info is None:
                # registro eliminado físicamente
            elif info["anulado"]:
                # fue anulado en RAFAM → marcar deleted_at en link store
        """
        import json as _json

        cfg = self._INTEGRIDAD_CONFIG.get(entity)
        if cfg is None:
            raise ValueError(f"fetch_estado_by_key: entidad no soportada: {entity!r}")

        table = self._reflect_table(cfg["table"])

        # Parsear source_key: puede ser un entero directo (proveedores) o JSON
        pk_values: dict[str, object] = {}
        if len(cfg["pk"]) == 1:
            # Caso simple: source_key es el valor directo de la PK
            col_rafam, _ = cfg["pk"][0]
            try:
                pk_values[col_rafam] = int(source_key)
            except (ValueError, TypeError):
                pk_values[col_rafam] = source_key
        else:
            # Caso compuesto: source_key es JSON {"ejercicio": X, "nro_op": Y, ...}
            try:
                parsed = _json.loads(source_key)
            except (ValueError, TypeError):
                logger.error(
                    "fetch_estado_by_key: source_key no es JSON válido para %s: %r",
                    entity, source_key,
                )
                return None
            for col_rafam, key_name in cfg["pk"]:
                value = parsed.get(key_name)
                if value is not None:
                    try:
                        pk_values[col_rafam] = int(value)
                    except (ValueError, TypeError):
                        pk_values[col_rafam] = value

        # Construir los campos a seleccionar
        estado_col_name = cfg["estado_col"]
        fech_col_name = cfg.get("fech_anul_col")

        select_cols = []
        estado_col = self._safe_column(table, estado_col_name)
        if estado_col is not None:
            select_cols.append(estado_col.label("estado"))

        fech_col = self._safe_column(table, fech_col_name) if fech_col_name else None
        if fech_col is not None:
            select_cols.append(fech_col.label("fech_anul"))

        if not select_cols:
            # Fallback: al menos traemos algo para saber si existe
            select_cols.append(literal_column("1").label("exists_flag"))

        # Construir filtros de PK
        pk_filters = []
        for col_rafam, _ in cfg["pk"]:
            col = self._safe_column(table, col_rafam)
            if col is not None and col_rafam in pk_values:
                pk_filters.append(col == pk_values[col_rafam])

        if not pk_filters:
            logger.error(
                "fetch_estado_by_key: no se pudieron construir filtros PK para %s key=%r",
                entity, source_key,
            )
            return None

        stmt = select(*select_cols).select_from(table).where(and_(*pk_filters))

        try:
            row = self._conn.execute(stmt).fetchone()
        except SQLAlchemyError as exc:
            logger.error(
                "fetch_estado_by_key: error al consultar %s key=%r: %s",
                entity, source_key, exc,
            )
            return None

        if row is None:
            return None  # registro no existe físicamente

        mapping = row._mapping
        estado = mapping.get("estado")
        fech_anul = mapping.get("fech_anul") if fech_col is not None else None
        anulado_valor = cfg.get("anulado_valor")
        anulado = (str(estado) == anulado_valor) if (estado is not None and anulado_valor is not None) else False

        return {
            "source_key": source_key,
            "estado": estado,
            "anulado": anulado,
            "fech_anul": fech_anul,
        }

    def fetch_proveedor_row(self, cod_prov: int) -> dict | None:
        """Trae la fila completa de PROVEEDORES para recalcular el hash de contenido.

        Devuelve un dict con todos los campos del registro, o None si no existe.
        Usado exclusivamente por el script de integridad para detectar cambios de
        contenido en proveedores ya migrados a Paxapos.
        """
        try:
            table = self._reflect_table("PROVEEDORES")
        except Exception as exc:
            logger.error("fetch_proveedor_row: no se pudo reflejar PROVEEDORES: %s", exc)
            return None

        cod_col = self._safe_column(table, "COD_PROV")
        if cod_col is None:
            logger.error("fetch_proveedor_row: columna COD_PROV no encontrada en PROVEEDORES")
            return None

        stmt = select(table).where(cod_col == cod_prov)
        try:
            row = self._conn.execute(stmt).fetchone()
        except SQLAlchemyError as exc:
            logger.error("fetch_proveedor_row: error al consultar COD_PROV=%s: %s", cod_prov, exc)
            return None

        if row is None:
            return None
        return dict(row._mapping)

