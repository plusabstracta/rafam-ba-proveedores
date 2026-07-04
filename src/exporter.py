"""
exporter.py — Orquestador de salida para los datos extraídos de Oracle.

Interfaz común:
    exporter.write_batch(entity, columns, rows)
    exporter.close()

Implementación:
    MigratorExporter — envía los lotes al importador RAFAM -> Paxapos
    (POST /rafam/migracion/importar.json). Soporta dry-run para preview.

Refactored: la lógica de mapping por entidad vive en src/mappers/*.
Este módulo es el orchestrator: wires mappers + HTTP transport + link persistence.
"""

import json
import logging
import os
import random  # noqa: F401 â re-export for test patches
import re
import ssl  # noqa: F401 â re-export for test patches
import time  # noqa: F401 â re-export for test patches
from abc import ABC, abstractmethod
from urllib import parse  # noqa: F401 â re-export for test patches
from urllib import error, request  # noqa: F401 â re-export for test patches

from .entity_link_store import EntityLinkStore
from .entity_writer import (
    EntityWriter,
    _persist_proveedores,
    _persist_oc_items,
    _persist_solic_gastos,
    _persist_retenciones,
)
from .http_client import (
    PaxaposHttpClient,
    build_url as _build_migrator_url_impl,
    http_request_with_retries,
    RETRYABLE_HTTP_STATUS,
    _dump_payload_path as _dump_payload_path_impl,
    _resolve_endpoint,
    _env_paxapos_url,
    _env_paxapos_tenant,
)
from .mappers.lookups import LookupResolver
from .mappers import proveedores as prov_mapper
from .mappers.oc_items import OcItemsMapper, persist_links as oc_persist_links
from .mappers.solic_gastos import (
    SolicGastosMapper,
    persist_links as sg_persist_links,
    log_stats as sg_log_stats,
    gasto_external_id as _gasto_external_id_fn,
    gasto_legacy_ref as _gasto_legacy_ref_fn,
    _gasto_ref_from_external_id as _gasto_ref_fn,
    _gasto_external_id_from_ref as _gasto_eid_from_ref_fn,
    _gasto_source_keys_from_ref as _gasto_skeys_fn,
)
from .mappers.orden_pago import (
    OrdenPagoMapper,
    persist_links_orden_pago,
    _pedido_id_from_op_row as _pedido_id_fn,
)
from .mappers.retenciones import RetencionesMapper, persist_links_retenciones
from .retry_store import REASON_BACKEND_REJECTED
from .utils import (
    build_single_index,
    env_bool,
    format_date_only,
    lookup_list,
    normalize_cuit,
    normalize_text,
    parse_money,
    redact_payload_for_dump,
    split_ref_set,
    to_int,
)

logger = logging.getLogger(__name__)


# ââ Backward-compatible re-exports for tests ââââââââââââââââââââââââââââ
# Tests import _SENSITIVE_FIELDS, _redact_payload_for_dump,
# _http_request_with_retries, _dump_payload_path, and _RETRYABLE_HTTP_STATUS
# from src.exporter. These are now re-exports from the new modules.
_SENSITIVE_FIELDS = re.compile(
    r'"(cuit|password|token|api_key|authorization|jwt|x[-_]api[-_]key)"\s*:\s*"[^"]*"',
    re.IGNORECASE,
)
_redact_payload_for_dump = redact_payload_for_dump
_http_request_with_retries = http_request_with_retries
_dump_payload_path = _dump_payload_path_impl
_RETRYABLE_HTTP_STATUS = RETRYABLE_HTTP_STATUS


# Nota: _http_request_with_retries y _dump_payload_path ya estÃ¡n re-exportados
# arriba desde http_client. No se definen aquÃ­ para evitar duplicaciÃ³n.


class AlreadyExistsError(Exception):
    """Raised when remote API reports record already exists (idempotent case)."""

    def __init__(self, message: str, parsed: dict | None = None):
        super().__init__(message)
        self.parsed = parsed or {}


class BaseExporter(ABC):
    @abstractmethod
    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        """Procesa un lote de filas para la entidad dada."""

    def attach_source(self, source_repo) -> None:
        """Inyecta SourceRepository para fetch secundarios. Default: no-op."""
        return None

    def close(self) -> None:
        """Llamado una vez al finalizar todas las entidades. Override si necesario."""


class MigratorExporter(BaseExporter):
    """EnvÃ­a lotes al importador RAFAM -> Paxapos via /rafam/migracion/importar.json.

    Orchestrator: delega mapping a src/mappers/* y gestiona HTTP + link persistence.
    """

    def __init__(self, dry_run: bool = False):
        # HTTP client encapsula auth, retries, SSL, URL construction.
        self._http = PaxaposHttpClient()
        self._import_url = self._http.import_url
        self._dry_run = dry_run
        self._link_store = EntityLinkStore()

        # Backward-compat: tests acceden a estos atributos directamente.
        self._base_url = self._http.base_url
        self._tenant = self._http.tenant
        self._api_key = self._http._api_key
        self._timeout = self._http._timeout
        self._verify_ssl = self._http._verify_ssl

        # URL del resolvedor de mercaderías para compatibilidad retroactiva con tests
        self._resolver_endpoint = _resolve_endpoint(
            "PAXAPOS_RAFAM_RESOLVER_PATH", "rafam/migracion/resolver_mercaderia.json"
        )
        self._resolver_url = _build_migrator_url_impl(
            self._base_url, self._tenant, self._resolver_endpoint
        )

        self._lookup_payload = fetch_migrator_lookups([
            "unidades_de_medida",
            "tipos_factura",
            "tipos_de_pago",
            "tipos_retencion",
        ])
        self._lookup = LookupResolver(self._lookup_payload)
        self._source_repo = None
        self._retry_store = None
        # Ultima respuesta parseada del receptor; la usa _record_batch_outcomes
        self._last_parsed = None

        # ââ Mapper instances âââââââââââââââââââââââââââââââââââââââââââââ
        self._oc_mapper = OcItemsMapper(link_store=self._link_store, lookup_resolver=self._lookup)
        self._sg_mapper = SolicGastosMapper(link_store=self._link_store, lookup_resolver=self._lookup)
        self._op_mapper = OrdenPagoMapper(link_store=self._link_store, lookup_resolver=self._lookup)
        self._ret_mapper = RetencionesMapper(link_store=self._link_store, lookup_resolver=self._lookup)

        if isinstance(self._lookup_payload, dict) and self._lookup_payload.get("_partial_errors"):
            logger.warning("Migrator lookups parciales: %s", self._lookup_payload.get("_partial_errors"))

        # Writers registry (Strategy pattern)
        self._writers = {
            "proveedores": EntityWriter(
                entity_name="proveedores",
                mapper=prov_mapper,
                persist_fn=_persist_proveedores,
                result_section="proveedores",
            ),
            "oc_items": EntityWriter(
                entity_name="oc_items",
                mapper=self._oc_mapper,
                persist_fn=_persist_oc_items,
                result_section="ordenes_compra",
            ),
            "solic_gastos": EntityWriter(
                entity_name="solic_gastos",
                mapper=self._sg_mapper,
                persist_fn=_persist_solic_gastos,
                result_section="gastos",
                log_stats_fn=lambda parsed, payload, dry_run: sg_log_stats(
                    parsed, len(payload.get("gastos", [])) if payload else 0, dry_run
                ),
            ),
        }

    def attach_source(self, source_repo) -> None:
        self._source_repo = source_repo
        self._op_mapper._source_repo = source_repo
        self._ret_mapper._source_repo = source_repo

    def attach_retry_store(self, retry_store) -> None:
        """Inyecta la cola de reintentos (F1)."""
        self._retry_store = retry_store
        self._op_mapper._retry_store = retry_store
        self._ret_mapper._retry_store = retry_store

    # Seccion de la respuesta `results`/`errors` por nombre de entidad de config.
    _RESULT_SECTION_BY_ENTITY = {
        "proveedores": "proveedores",
        "oc_items": "ordenes_compra",
        "solic_gastos": "gastos",
        "orden_pago": "ordenes_pago",
        "retenciones": "retenciones",
    }

    @staticmethod
    def _outcome_key(section: str, external_id) -> str | None:
        """Construye la clave estable de la cola desde el external_id de la respuesta."""
        if external_id is None:
            return None
        if not isinstance(external_id, dict):
            return str(external_id)
        if section == "proveedores":
            value = external_id.get("cod_prov")
            return str(value) if value is not None else None
        if section == "ordenes_compra":
            fields = ["ejercicio", "uni_compra", "nro_oc"]
        elif section in ("ordenes_pago", "retenciones"):
            fields = ["ejercicio", "nro_op"]
        else:
            return json.dumps(external_id, sort_keys=True)
        key_dict = {k: external_id[k] for k in fields if k in external_id}
        if len(key_dict) != len(fields):
            return None
        return json.dumps(key_dict, sort_keys=True)

    def _record_batch_outcomes(self, entity: str, parsed) -> None:
        """Actualiza la cola de reintentos con el resultado por fila del batch."""
        if self._retry_store is None or self._dry_run or not isinstance(parsed, dict):
            return
        section = self._RESULT_SECTION_BY_ENTITY.get(entity)
        if section is None:
            return

        results = parsed.get("results", {})
        if isinstance(results, dict):
            for result in results.get(section, []) or []:
                if not isinstance(result, dict) or not result.get("success"):
                    continue
                key = self._outcome_key(section, result.get("external_id"))
                if key is not None:
                    self._retry_store.resolve(entity, key)

        errors = parsed.get("errors")
        if isinstance(errors, list):
            for err in errors:
                if not isinstance(err, dict) or err.get("section") != section:
                    continue
                key = self._outcome_key(section, err.get("external_id"))
                if key is None:
                    continue
                message = err.get("message") or "fila rechazada por el receptor"
                self._retry_store.enqueue(entity, key, REASON_BACKEND_REJECTED, str(message)[:500])

    def _payload_options(self) -> dict:
        return {
            "upsert": True,
            "atomic": False,
            "fail_fast": False,
            "send_oc_mail": False,
            "strict_mail": False,
            "auto_create_mercaderia": True,
            "auto_create_gasto": True,
            "auto_calcular_retenciones": False,
            "notificar_proveedor_pago": False,
        }

    # ââ write_batch: orchestrator ââââââââââââââââââââââââââââââââââââââââ

    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        self._last_parsed = None

        if entity == "proveedores":
            return self._write_batch_proveedores(columns, rows)

        if entity == "ped_items":
            logger.warning("Migrator [ped_items]: entidad deshabilitada — los pedidos se migran como OCs via 'oc_items'.")
            return

        if entity == "oc_items":
            return self._write_batch_oc_items(columns, rows)

        if entity == "orden_compra":
            logger.warning(
                "Migrator [orden_compra]: entidad deshabilitada en migrator — las OCs se migran via 'oc_items' "
                "(que envia header + items embebidos). El header-only generaba OCs vacias en Paxapos."
            )
            return

        if entity == "solic_gastos":
            logger.warning(
                "Migrator [solic_gastos]: entidad deshabilitada en migrator — los gastos NO se migran desde RAFAM. "
                "En Paxapos los crean los usuarios al subir la factura del proveedor; el endpoint de OP los auto-crea "
                "si todavia no existen al momento de pagar (via gasto_nro_comprobante PDV-NRO_COMPROB)."
            )
            return

        if entity == "orden_pago":
            return self._write_batch_orden_pago(columns, rows)

        if entity == "pedidos":
            logger.warning(
                "Migrator [%s]: entidad recibida sin items. Para migrar solicitudes usa 'ped_items' (genera pedidos con items).",
                entity,
            )
            return

        raise ValueError(
            "Modo migrator soporta solo 3 entidades oficiales: proveedores, oc_items, orden_pago. "
            f"Recibido: {entity!r}"
        )

    def _write_batch_proveedores(self, columns: list[str], rows: list[tuple]) -> None:
        proveedores = []
        raw_by_source_key: dict[str, dict] = {}
        self._temp_proveedor_payload_hashes = {}
        for row in rows:
            raw = dict(zip(columns, row))
            payload_row = self._map_row("proveedores", raw)
            if payload_row is None:
                continue
            source_key = self._source_key("proveedores", raw)
            if source_key is not None:
                raw_by_source_key[source_key] = raw
                from .change_detection import compute_payload_hash
                self._temp_proveedor_payload_hashes[str(source_key)] = compute_payload_hash(payload_row.get("Proveedor", {}))
            proveedores.append(payload_row)

        if not proveedores:
            logger.info("Migrator [proveedores]: lote vacio luego del mapeo")
            return

        payload = {
            "dry_run": self._dry_run,
            "options": self._payload_options(),
            "proveedores": proveedores,
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": [],
            "ordenes_pago": [],
        }

        url = self._import_url
        logger.debug("Migrator request [proveedores] POST %s dry_run=%s items=%d", url, self._dry_run, len(proveedores))
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("proveedores", {}) if isinstance(stats, dict) else {}
        ok_count = section_stats.get("ok", 0)
        error_count = section_stats.get("error", 0)

        self._persist_links("proveedores", parsed, raw_by_source_key)
        self._raise_on_migrator_errors(parsed)
        logger.info(
            "Migrator OK [proveedores]: %d ok, %d error, dry_run=%s",
            ok_count,
            error_count,
            self._dry_run,
        )

    def _write_batch_ped_items(self, columns: list[str], rows: list[tuple]) -> None:
        grouped: dict[tuple[int, int], dict] = {}
        unresolved_items = 0

        for row in rows:
            raw = dict(zip(columns, row))

            ejercicio = self._to_int(raw.get("EJERCICIO"))
            num_ped = self._to_int(raw.get("NUM_PED"))
            if ejercicio is None or num_ped is None:
                continue

            key = (ejercicio, num_ped)
            if key not in grouped:
                pedido_header: dict = {
                    "internal_id": f"rafam-ped-{ejercicio}-{num_ped}",
                    "tipo": "solicitud",
                    "observacion": f"Migrado RAFAM PED {ejercicio}-{num_ped}",
                }
                costo_tot = raw.get("PED_COSTO_TOT")
                if costo_tot is not None:
                    try:
                        pedido_header["monto_presupuestado"] = float(costo_tot)
                    except (TypeError, ValueError):
                        pass
                grouped[key] = {
                    "external_id": {"ejercicio": ejercicio, "num_ped": num_ped},
                    "Pedido": pedido_header,
                    "items": [],
                }
                centro_costo_id = self._resolve_centro_costo_id(raw.get("JURISDICCION"))
                if centro_costo_id is not None:
                    grouped[key]["centro_costo_id"] = centro_costo_id

            item = self._map_ped_item(raw)
            if item is None:
                unresolved_items += 1
                self._track_unresolved_item(raw.get("DESCRIP_BIE"), raw.get("COD_PROV"))
                continue
            grouped[key]["items"].append(item)

        pedidos = [p for p in grouped.values() if p["items"]]
        if not pedidos:
            msg = f"Migrator [ped_items]: lote sin items resolubles (omitidos={unresolved_items})"
            if self._dry_run:
                logger.warning(msg)
                return
            raise RuntimeError(msg)

        payload = {
            "dry_run": self._dry_run,
            "options": self._payload_options(),
            "proveedores": [],
            "pedidos": pedidos,
            "ordenes_compra": [],
            "gastos": [],
            "ordenes_pago": [],
        }

        url = self._import_url
        logger.debug(
            "Migrator request [ped_items] POST %s dry_run=%s pedidos=%d items_omitidos=%d",
            url,
            self._dry_run,
            len(pedidos),
            unresolved_items,
        )
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("pedidos", {}) if isinstance(stats, dict) else {}
        ok_count = section_stats.get("ok", 0)
        error_count = section_stats.get("error", 0)

        self._persist_links("ped_items", parsed, {})
        self._raise_on_migrator_errors(parsed)
        logger.info(
            "Migrator OK [ped_items->pedidos]: %d ok, %d error, pedidos=%d, items_omitidos=%d, dry_run=%s",
            ok_count,
            error_count,
            len(pedidos),
            unresolved_items,
            self._dry_run,
        )
        self._log_unresolved_summary("ped_items")

    def _write_batch_oc_items(self, columns: list[str], rows: list[tuple]) -> None:
        # ── 1. Agrupar filas por OC (cabecera + items) ────────────────────
        grouped: dict[tuple[int, int, int], dict] = {}
        grouped_raw: dict[tuple[int, int, int], dict] = {}
        grouped_gasto_refs: dict[tuple[int, int, int], list[str]] = {}
        # seen_items_per_oc: dedup por ITEM_OC porque el LEFT JOIN a
        # SOLIC_GASTOS y oc_to_cc (REG_COMP→CTA_COMPROB) puede multiplicar filas (44% multi-
        # match en SG, 8% en CC). Sin esto, los totales en Paxapos se inflan
        # porque sum(item.precio) cuenta cada item N veces.
        seen_items_per_oc: dict[tuple[int, int, int], set[int]] = {}
        skipped_no_prov: set[tuple[int, int, int]] = set()
        unresolved_items = 0

        for row in rows:
            raw = dict(zip(columns, row))

            ejercicio = self._to_int(raw.get("EJERCICIO"))
            uni_compra = self._to_int(raw.get("UNI_COMPRA"))
            nro_oc = self._to_int(raw.get("NRO_OC"))
            if ejercicio is None or uni_compra is None or nro_oc is None:
                continue

            key = (ejercicio, uni_compra, nro_oc)
            if key in skipped_no_prov:
                continue
            if key not in grouped:
                # Resolver proveedor_id via link_store (RAFAM COD_PROV → Paxapos id)
                cod_prov = raw.get("COD_PROV")
                remote_prov_id: int | None = None
                if cod_prov is not None:
                    remote_prov = self._link_store.get_remote_id("proveedores", str(cod_prov))
                    if remote_prov:
                        remote_prov_id = int(remote_prov)

                # Omitir OC sin proveedor — no tiene sentido migrarla
                if remote_prov_id is None:
                    logger.warning(
                        "Migrator [oc_items] OC %s-%s-%s: omitida — sin proveedor (COD_PROV=%s)",
                        ejercicio, uni_compra, nro_oc, cod_prov,
                    )
                    skipped_no_prov.add(key)
                    continue

                pedido: dict = {
                    "internal_id": f"{ejercicio % 100}-{nro_oc}",
                    "tipo": "orden_compra",
                    "estado_aprobacion": 2,
                    "proveedor_id": remote_prov_id,
                }

                # Observación: solo incluir si la OC tiene observaciones reales en RAFAM
                obs = self._compose_oc_observacion(raw)
                if obs:
                    pedido["observacion"] = obs

                # Fecha de creación real de RAFAM (no la de migración)
                fech_oc = self._format_date_only(raw.get("OC_FECH_OC"))
                if fech_oc:
                    pedido["created"] = f"{fech_oc} 00:00:00"

                oc_data: dict = {
                    "external_id": {
                        "ejercicio": ejercicio,
                        "uni_compra": uni_compra,
                        "nro_oc": nro_oc,
                    },
                    "Pedido": pedido,
                    "items": [],
                }

                # centro_costo_id desde la primera JURISDICCION disponible
                sg_jurisdiccion = raw.get("SG_JURISDICCION")
                centro_costo_id = self._resolve_centro_costo_id(sg_jurisdiccion)
                if centro_costo_id is not None:
                    oc_data["centro_costo_id"] = centro_costo_id

                grouped[key] = oc_data
                # Guardar datos de cabecera OC para extras del link
                grouped_raw[key] = raw

            # Recolectar ref de gasto desde DELEG_SOLIC + NRO_SOLIC del ítem
            deleg_solic = self._to_int(raw.get("DELEG_SOLIC"))
            nro_solic = self._to_int(raw.get("NRO_SOLIC"))
            if deleg_solic is not None and nro_solic is not None:
                rafam_ref = f"SG-{ejercicio}-{deleg_solic}-{nro_solic}"
                refs = grouped_gasto_refs.setdefault(key, [])
                if rafam_ref not in refs:
                    refs.append(rafam_ref)

            # Dedup por ITEM_OC: el LEFT JOIN a SOLIC_GASTOS / oc_to_cc
            # multiplica filas. Sin esto los items se duplican y el total
            # (sum(precio_unitario x cantidad)) en Paxapos queda inflado.
            item_oc = self._to_int(raw.get("ITEM_OC"))
            seen_items = seen_items_per_oc.setdefault(key, set())
            if item_oc is not None and item_oc in seen_items:
                continue

            item = self._map_oc_item(raw)
            if item is None:
                unresolved_items += 1
                self._track_unresolved_item(raw.get("DESCRIPCION"), raw.get("COD_PROV"))
                continue
            if item_oc is not None:
                seen_items.add(item_oc)
            grouped[key]["items"].append(item)

        # ── 2. Clasificar OCs por acción según estado y link previo ───────
        ocs_to_create: list[dict] = []      # estado R, sin link o link con estado != R
        ocs_to_anular: list[dict] = []      # estado A, link previo con estado R (estaba en Paxapos), sin OP
        ocs_to_skip_register: list[tuple[int, int, int]] = []  # estado N/A sin link previo R
        ocs_to_skip_has_op: list[tuple[int, int, int]] = []    # estado A con OP asociada → no eliminar
        ocs_same_state: list[tuple[int, int, int]] = []  # estado R ya enviado, sin gastos nuevos
        created_count = 0
        anuladas_count = 0
        skipped_same_state = 0

        for key, oc_data in grouped.items():
            if not oc_data["items"]:
                continue

            raw = grouped_raw[key]
            estado_actual = str(raw.get("OC_ESTADO_OC", "")).strip().upper()
            source_key = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            link_previo = self._link_store.get_link("orden_compra", source_key)
            estado_previo = link_previo.get("estado_oc", "").strip().upper() if link_previo else None

            if estado_actual == "R":
                if link_previo is None or estado_previo != "R":
                    # Nueva para Paxapos: no existía o venía de otro estado
                    ocs_to_create.append(oc_data)
                else:
                    # Ya estaba con R y ya tiene remote_id → skip envío
                    ocs_same_state.append(key)
                    skipped_same_state += 1
            elif estado_actual == "A":
                if link_previo and estado_previo == "R" and link_previo.get("remote_id"):
                    if link_previo.get("has_op"):
                        # Tiene OP asociada → NO eliminar de Paxapos
                        logger.info(
                            "Migrator [oc_items] OC %s-%s-%s anulada en RAFAM pero tiene OP,"
                            " no se elimina de Paxapos",
                            key[0], key[1], key[2],
                        )
                        ocs_to_skip_has_op.append(key)
                    else:
                        # Estaba en Paxapos con R, sin OP → soft-delete
                        oc_data["Pedido"]["deleted"] = 1
                        ocs_to_anular.append(oc_data)
                else:
                    # Anulada sin haber sido R → solo registrar localmente
                    ocs_to_skip_register.append(key)
            else:
                # Estado N u otro → solo registrar localmente
                ocs_to_skip_register.append(key)

        # ── 3. Registrar en link TODAS las OCs (con o sin envío) ──────────
        # Las que se saltan o registran solo localmente (R, A sin N previo)
        for key in ocs_to_skip_register + ocs_same_state + ocs_to_skip_has_op:
            raw = grouped_raw[key]
            source_key = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            estado_oc = str(raw.get("OC_ESTADO_OC", "")).strip().upper() or None
            fech_confirm = self._format_date_only(raw.get("OC_FECH_CONFIRM", "")) or None
            cod_prov = str(raw.get("COD_PROV")) if raw.get("COD_PROV") is not None else None
            importe_tot = str(raw.get("OC_IMPORTE_TOT")) if raw.get("OC_IMPORTE_TOT") is not None else None
            gasto_refs_list = grouped_gasto_refs.get(key, [])
            gasto_refs = ",".join(gasto_refs_list) if gasto_refs_list else ""

            # Preservar remote_id si ya existía
            existing = self._link_store.get_link("orden_compra", source_key)
            remote_id = existing.get("remote_id", "") if existing else ""
            gasto_linked_refs = existing.get("gasto_linked_refs", "") if existing else ""

            self._link_store.save_link(
                entity="orden_compra",
                source_key=source_key,
                remote_id=remote_id,
                estado_oc=estado_oc,
                fech_confirm=fech_confirm,
                cod_prov=cod_prov,
                importe_tot=importe_tot,
                gasto_refs=gasto_refs,
                gasto_linked_refs=gasto_linked_refs,
            )

        # ── 4. Enviar OCs a crear + OCs a anular en un solo payload ───────
        ordenes_compra = ocs_to_create + ocs_to_anular
        raw_by_source_key: dict[str, dict] = {}
        for key in grouped_raw:
            sk = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            raw_by_source_key[sk] = grouped_raw[key]
            # Agregar gasto_refs para persist
            gasto_refs_list = grouped_gasto_refs.get(key, [])
            raw_by_source_key[sk]["_GASTO_REFS"] = ",".join(gasto_refs_list) if gasto_refs_list else ""
            raw_by_source_key[sk]["_GASTO_LINKED_REFS"] = ""

        if not ordenes_compra:
            logger.info(
                "Migrator [oc_items]: nada que enviar (skip_estado=%d, mismo_estado=%d, skip_has_op=%d, sin_items=%d)",
                len(ocs_to_skip_register),
                skipped_same_state,
                len(ocs_to_skip_has_op),
                unresolved_items,
            )
            return

        payload = {
            "dry_run": self._dry_run,
            "options": self._payload_options(),
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": ordenes_compra,
            "gastos": [],
            "ordenes_pago": [],
        }

        url = self._import_url
        logger.debug(
            "Migrator request [oc_items] POST %s dry_run=%s crear=%d anular=%d items_omitidos=%d",
            url,
            self._dry_run,
            len(ocs_to_create),
            len(ocs_to_anular),
            unresolved_items,
        )
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("ordenes_compra", {}) if isinstance(stats, dict) else {}
        ok_count = section_stats.get("ok", 0)
        error_count = section_stats.get("error", 0)

        self._persist_links("oc_items", parsed, raw_by_source_key)
        self._raise_on_migrator_errors(parsed)
        logger.info(
            "Migrator OK [oc_items->ordenes_compra]: %d ok, %d error, crear=%d, anular=%d, "
            "skip_estado=%d, mismo_estado=%d, skip_has_op=%d, dry_run=%s",
            ok_count,
            error_count,
            len(ocs_to_create),
            len(ocs_to_anular),
            len(ocs_to_skip_register),
            skipped_same_state,
            len(ocs_to_skip_has_op),
            self._dry_run,
        )
        self._log_unresolved_summary("oc_items")

    def _group_oc_rows(self, columns: list[str], rows: list[tuple]) -> tuple[dict, dict, dict, int]:
        """Agrupa las filas de OC en payloads completos de OC (cabecera + items)."""
        grouped: dict[tuple[int, int, int], dict] = {}
        grouped_raw: dict[tuple[int, int, int], dict] = {}
        grouped_gasto_refs: dict[tuple[int, int, int], list[str]] = {}
        seen_items_per_oc: dict[tuple[int, int, int], set[int]] = {}
        skipped_no_prov: set[tuple[int, int, int]] = set()
        unresolved_items = 0

        for row in rows:
            raw = dict(zip(columns, row))

            ejercicio = self._to_int(raw.get("EJERCICIO"))
            uni_compra = self._to_int(raw.get("UNI_COMPRA"))
            nro_oc = self._to_int(raw.get("NRO_OC"))
            if ejercicio is None or uni_compra is None or nro_oc is None:
                continue

            key = (ejercicio, uni_compra, nro_oc)
            if key in skipped_no_prov:
                continue
            if key not in grouped:
                # Resolver proveedor_id via link_store (RAFAM COD_PROV → Paxapos id)
                cod_prov = raw.get("COD_PROV")
                remote_prov_id: int | None = None
                if cod_prov is not None:
                    remote_prov = self._link_store.get_remote_id("proveedores", str(cod_prov))
                    if remote_prov:
                        remote_prov_id = int(remote_prov)

                # Omitir OC sin proveedor — no tiene sentido migrarla
                if remote_prov_id is None:
                    logger.warning(
                        "Migrator [orden_compra] OC %s-%s-%s: omitida — sin proveedor (COD_PROV=%s)",
                        ejercicio, uni_compra, nro_oc, cod_prov,
                    )
                    skipped_no_prov.add(key)
                    continue

                pedido: dict = {
                    "internal_id": f"{ejercicio % 100}-{nro_oc}",
                    "tipo": "orden_compra",
                    "estado_aprobacion": 2,
                    "proveedor_id": remote_prov_id,
                }

                # Observación: solo incluir si la OC tiene observaciones reales en RAFAM
                obs = self._compose_oc_observacion(raw)
                if obs:
                    pedido["observacion"] = obs

                # Fecha de creación real de RAFAM (no la de migración)
                fech_oc = self._format_date_only(raw.get("OC_FECH_OC"))
                if fech_oc:
                    pedido["created"] = f"{fech_oc} 00:00:00"

                oc_data: dict = {
                    "external_id": {
                        "ejercicio": ejercicio,
                        "uni_compra": uni_compra,
                        "nro_oc": nro_oc,
                    },
                    "Pedido": pedido,
                    "items": [],
                    # Campo shadow solo para hash: no se envía a Paxapos, pero
                    # permite que sync-changes detecte anulaciones (R→A) como
                    # un cambio de hash sin lógica de deletes separada.
                    "_rafam_estado_oc": str(raw.get("OC_ESTADO_OC", "")).strip().upper(),
                }

                # centro_costo_id desde la primera JURISDICCION disponible
                sg_jurisdiccion = raw.get("SG_JURISDICCION")
                centro_costo_id = self._resolve_centro_costo_id(sg_jurisdiccion)
                if centro_costo_id is not None:
                    oc_data["centro_costo_id"] = centro_costo_id

                grouped[key] = oc_data
                grouped_raw[key] = raw

            # Recolectar ref de gasto
            deleg_solic = self._to_int(raw.get("DELEG_SOLIC"))
            nro_solic = self._to_int(raw.get("NRO_SOLIC"))
            if deleg_solic is not None and nro_solic is not None:
                rafam_ref = f"SG-{ejercicio}-{deleg_solic}-{nro_solic}"
                refs = grouped_gasto_refs.setdefault(key, [])
                if rafam_ref not in refs:
                    refs.append(rafam_ref)

            # Dedup por ITEM_OC: el LEFT JOIN a SOLIC_GASTOS / oc_to_cc
            # multiplica filas. Sin esto los items se duplican y el total
            # (sum(precio_unitario x cantidad)) en Paxapos queda inflado.
            item_oc = self._to_int(raw.get("ITEM_OC"))
            seen_items = seen_items_per_oc.setdefault(key, set())
            if item_oc is not None and item_oc in seen_items:
                continue

            item = self._map_oc_item(raw)
            if item is None:
                unresolved_items += 1
                self._track_unresolved_item(raw.get("DESCRIPCION"), raw.get("COD_PROV"))
                continue
            if item_oc is not None:
                seen_items.add(item_oc)
            grouped[key]["items"].append(item)

        return grouped, grouped_raw, grouped_gasto_refs, unresolved_items

    def _write_batch_orden_compra(self, columns: list[str], rows: list[tuple]) -> None:
        """Sync incremental de ORDEN_COMPRA con items.

        La query trae filas a nivel de ítem (ORDEN_COMPRA → OC_ITEMS → SOLIC_GASTOS),
        con cursor incremental sobre FECH_OC / ESTADO_OC.
        Reutiliza la misma lógica de agrupación/mapeo que _write_batch_oc_items.

        Casos:
        - estado R sin link previo → crear en Paxapos (con items)
        - estado R ya enviada sin gastos nuevos → skip
        - estado R ya enviada con gastos nuevos → re-enviar para vincular
        - estado R→A con remote_id → anular en Paxapos
        - estado N/A sin link R previo → solo registrar localmente
        """
        grouped, grouped_raw, grouped_gasto_refs, unresolved_items = self._group_oc_rows(columns, rows)

        # Calcular hashes para todas las OCs agrupadas
        self._temp_oc_payload_hashes = {}
        from .change_detection import compute_payload_hash
        for key, oc_data in grouped.items():
            source_key = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            self._temp_oc_payload_hashes[source_key] = compute_payload_hash(oc_data)

        # ── 2. Clasificar OCs por acción según estado y link previo ───────
        ocs_to_create: list[dict] = []
        ocs_to_anular: list[dict] = []
        ocs_to_skip_register: list[tuple[int, int, int]] = []
        ocs_to_skip_has_op: list[tuple[int, int, int]] = []
        ocs_same_state: list[tuple[int, int, int]] = []

        for key, oc_data in grouped.items():
            if not oc_data["items"]:
                continue

            raw = grouped_raw[key]
            estado_actual = str(raw.get("OC_ESTADO_OC", "")).strip().upper()
            source_key = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            link_previo = self._link_store.get_link("orden_compra", source_key)
            estado_previo = link_previo.get("estado_oc", "").strip().upper() if link_previo else None

            if estado_actual == "R":
                if link_previo is None or estado_previo != "R":
                    ocs_to_create.append(oc_data)
                else:
                    ocs_same_state.append(key)
            elif estado_actual == "A":
                if link_previo and estado_previo == "R" and link_previo.get("remote_id"):
                    if link_previo.get("has_op"):
                        logger.info(
                            "Migrator [orden_compra] OC %s-%s-%s anulada en RAFAM pero tiene OP,"
                            " no se elimina de Paxapos",
                            key[0], key[1], key[2],
                        )
                        ocs_to_skip_has_op.append(key)
                    else:
                        oc_data["Pedido"]["deleted"] = 1
                        ocs_to_anular.append(oc_data)
                else:
                    ocs_to_skip_register.append(key)
            else:
                # Estado N u otro → solo registrar localmente
                ocs_to_skip_register.append(key)

        # ── 3. Registrar en link TODAS las OCs que no se envían ───────────
        for key in ocs_to_skip_register + ocs_same_state + ocs_to_skip_has_op:
            raw = grouped_raw[key]
            source_key = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            estado_oc = str(raw.get("OC_ESTADO_OC", "")).strip().upper() or None
            fech_confirm = self._format_date_only(raw.get("OC_FECH_CONFIRM", "")) or None
            cod_prov = str(raw.get("COD_PROV")) if raw.get("COD_PROV") is not None else None
            importe_tot = str(raw.get("OC_IMPORTE_TOT")) if raw.get("OC_IMPORTE_TOT") is not None else None
            gasto_refs_list = grouped_gasto_refs.get(key, [])
            gasto_refs = ",".join(gasto_refs_list) if gasto_refs_list else ""

            existing = self._link_store.get_link("orden_compra", source_key)
            remote_id = existing.get("remote_id", "") if existing else ""
            gasto_linked_refs = existing.get("gasto_linked_refs", "") if existing else ""

            payload_hash = self._temp_oc_payload_hashes.get(source_key)
            self._link_store.save_link(
                entity="orden_compra",
                source_key=source_key,
                remote_id=remote_id,
                estado_oc=estado_oc,
                fech_confirm=fech_confirm,
                cod_prov=cod_prov,
                importe_tot=importe_tot,
                gasto_refs=gasto_refs,
                gasto_linked_refs=gasto_linked_refs,
                payload_hash=payload_hash,
            )

        # ── 4. Enviar OCs a crear + OCs a anular ─────────────────────────
        ordenes_compra = ocs_to_create + ocs_to_anular
        raw_by_source_key: dict[str, dict] = {}
        for key in grouped_raw:
            sk = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            raw_by_source_key[sk] = grouped_raw[key]
            gasto_refs_list = grouped_gasto_refs.get(key, [])
            raw_by_source_key[sk]["_GASTO_REFS"] = ",".join(gasto_refs_list) if gasto_refs_list else ""
            raw_by_source_key[sk]["_GASTO_LINKED_REFS"] = ""

        if not ordenes_compra:
            logger.info(
                "Migrator [orden_compra]: nada que enviar (skip_estado=%d, mismo_estado=%d, skip_has_op=%d, sin_items=%d)",
                len(ocs_to_skip_register),
                len(ocs_same_state),
                len(ocs_to_skip_has_op),
                unresolved_items,
            )
            return

        payload = {
            "dry_run": self._dry_run,
            "options": self._payload_options(),
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": ordenes_compra,
            "gastos": [],
            "ordenes_pago": [],
        }

        url = self._import_url
        logger.debug(
            "Migrator request [orden_compra] POST %s dry_run=%s crear=%d anular=%d items_omitidos=%d",
            url,
            self._dry_run,
            len(ocs_to_create),
            len(ocs_to_anular),
            unresolved_items,
        )
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("ordenes_compra", {}) if isinstance(stats, dict) else {}
        ok_count = section_stats.get("ok", 0)
        error_count = section_stats.get("error", 0)

        self._persist_links("orden_compra", parsed, raw_by_source_key)
        self._raise_on_migrator_errors(parsed)
        logger.info(
            "Migrator OK [orden_compra]: %d ok, %d error, crear=%d, anular=%d, "
            "skip_estado=%d, mismo_estado=%d, skip_has_op=%d, dry_run=%s",
            ok_count,
            error_count,
            len(ocs_to_create),
            len(ocs_to_anular),
            len(ocs_to_skip_register),
            len(ocs_same_state),
            len(ocs_to_skip_has_op),
            self._dry_run,
        )
        self._log_unresolved_summary("orden_compra")

    def _write_batch_solic_gastos(self, columns: list[str], rows: list[tuple]) -> None:
        # Solo enviar gastos vinculados a OCs ya enviadas a Paxapos
        allowed_refs = self._link_store.get_sent_oc_gasto_refs()

        gastos = []
        raw_by_source_key: dict[str, dict] = {}
        skipped_no_oc = 0
        for row in rows:
            raw = dict(zip(columns, row))
            gasto = self._map_solic_gasto(raw)
            if gasto is None:
                continue

            # Filtrar: solo gastos cuya ref esté vinculada a una OC enviada
            ext = gasto.get("external_id", {})
            rafam_ref = self._gasto_ref_from_external_id(ext) if ext else ""
            if rafam_ref not in allowed_refs:
                skipped_no_oc += 1
                continue

            gastos.append(gasto)
            if ext:
                sk = json.dumps(ext, sort_keys=True)
                raw_by_source_key[sk] = raw

        if skipped_no_oc:
            logger.info(
                "Migrator [solic_gastos]: %d gastos omitidos (sin OC enviada vinculada)",
                skipped_no_oc,
            )

        if not gastos:
            logger.info("Migrator [solic_gastos]: lote vacío luego del mapeo")
            return

        payload = {
            "dry_run": self._dry_run,
            "options": self._payload_options(),
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": gastos,
            "ordenes_pago": [],
        }

        url = self._import_url
        logger.debug(
            "Migrator request [solic_gastos] POST %s dry_run=%s gastos=%d",
            url, self._dry_run, len(gastos),
        )
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("gastos", {}) if isinstance(stats, dict) else {}
        ok_count = section_stats.get("ok", 0)
        error_count = section_stats.get("error", 0)

        self._persist_links("solic_gastos", parsed, raw_by_source_key)
        self._raise_on_migrator_errors(parsed)
        logger.info(
            "Migrator OK [solic_gastos->gastos]: %d ok, %d error, gastos=%d, dry_run=%s",
            ok_count, error_count, len(gastos), self._dry_run,
        )

    def _map_solic_gasto(self, raw: dict) -> dict | None:
        ejercicio = self._to_int(raw.get("EJERCICIO"))
        deleg_solic = self._to_int(raw.get("DELEG_SOLIC"))
        nro_solic = self._to_int(raw.get("NRO_SOLIC"))
        if ejercicio is None or deleg_solic is None or nro_solic is None:
            return None

        fecha_raw = raw.get("FECH_SOLIC")
        fecha = self._format_date_only(fecha_raw)
        if not fecha:
            return None

        # Excluir anuladas
        if str(raw.get("ESTADO_SOLIC", "")).strip().upper() == "A":
            return None

        cta_count = self._to_int(raw.get("CTA_COMPROB_COUNT"))
        if cta_count != 1:
            logger.debug(
                "Migrator [solic_gastos] SG %s-%s-%s omitida: CTA_COMPROB_COUNT=%s",
                ejercicio, deleg_solic, nro_solic, raw.get("CTA_COMPROB_COUNT"),
            )
            return None

        importe_total = self._parse_money(raw.get("CTA_IMPORTE_COMPR"))
        if importe_total is None:
            importe_total = self._parse_money(raw.get("IMPORTE_TOT"))
        if importe_total is None:
            return None

        importe_neto = self._parse_money(raw.get("CTA_IMPORTE_NETO"))
        if importe_neto is None:
            importe_neto = self._parse_money(raw.get("CTA_IMPORTE_SIN_IVA"))
        if importe_neto is None:
            importe_neto = importe_total

        gasto_data: dict = {
            "fecha": fecha,
            "importe_total": importe_total,
            "importe_neto": importe_neto,
        }

        nro_comprob = str(raw.get("CTA_NRO_COMPROB") or "").strip()
        if not nro_comprob:
            logger.debug(
                "Migrator [solic_gastos] SG %s-%s-%s omitida: sin CTA_COMPROB.NRO_COMPROB",
                ejercicio, deleg_solic, nro_solic,
            )
            return None

        tipo_factura_id = self._resolve_tipo_factura_id(raw.get("CTA_TIPO_COMPROB") or raw.get("TIPO_DOC"))
        if tipo_factura_id is not None:
            gasto_data["tipo_factura_id"] = tipo_factura_id

        # Parsear NRO_COMPROB: si tiene guion, separar en punto_de_venta + factura_nro
        dash_pos = nro_comprob.find("-")
        if dash_pos > 0:
            gasto_data["punto_de_venta"] = nro_comprob[:dash_pos]
            gasto_data["factura_nro"] = nro_comprob[dash_pos + 1:]
        else:
            raise ValueError(
                "Modo migrator soporta solo las 5 entidades oficiales: "
                "proveedores, oc_items, solic_gastos, orden_pago, retenciones. "
                f"Recibido: {entity!r}"
            )

        self._record_batch_outcomes(entity, self._last_parsed)

    def _write_batch_proveedores(self, columns, rows):
        """Delegado a EntityWriter."""
        writer = self._writers["proveedores"]
        parsed = writer.write_batch(
            columns, rows,
            dry_run=self._dry_run,
            payload_options=self._payload_options(),
            import_url=self._import_url,
            post_fn=self._post_json,
            link_store=self._link_store,
            raise_on_errors_fn=self._raise_on_migrator_errors,
        )
        if parsed is not None:
            self._last_parsed = parsed

    def _write_batch_oc_items(self, columns, rows):
        """Delegado a EntityWriter."""
        writer = self._writers["oc_items"]
        parsed = writer.write_batch(
            columns, rows,
            dry_run=self._dry_run,
            payload_options=self._payload_options(),
            import_url=self._import_url,
            post_fn=self._post_json,
            link_store=self._link_store,
            raise_on_errors_fn=self._raise_on_migrator_errors,
        )
        if parsed is not None:
            self._last_parsed = parsed

    def _write_batch_solic_gastos(self, columns, rows):
        """Delegado a EntityWriter."""
        writer = self._writers["solic_gastos"]
        parsed = writer.write_batch(
            columns, rows,
            dry_run=self._dry_run,
            payload_options=self._payload_options(),
            import_url=self._import_url,
            post_fn=self._post_json,
            link_store=self._link_store,
            raise_on_errors_fn=self._raise_on_migrator_errors,
        )
        if parsed is not None:
            self._last_parsed = parsed

    def _write_batch_orden_pago(self, columns, rows):
        payload, raw_by_source_key = self._op_mapper.build_payload(
            columns, rows,
            dry_run=self._dry_run,
            payload_options=self._payload_options(),
        )
        if payload is None:
            return

        url = self._import_url
        logger.debug("Migrator request [orden_pago] POST %s dry_run=%s ops=%d gastos=%d",
                      url, self._dry_run,
                      len(payload.get("ordenes_pago", [])),
                      len(payload.get("gastos", [])))
        parsed = self._post_json(url, payload)

        self._op_mapper.process_response(parsed, raw_by_source_key,
                                          link_store=self._link_store, dry_run=self._dry_run)
        self._raise_on_migrator_errors(parsed)
        self._op_mapper.log_stats(parsed, self._dry_run)

    def _write_batch_retenciones(self, columns, rows):
        payload, pending_fingerprints = self._ret_mapper.build_payload(
            columns, rows,
            dry_run=self._dry_run,
            payload_options=self._payload_options(),
        )
        if payload is None:
            return

        url = self._import_url
        logger.debug("Migrator request [retenciones] POST %s dry_run=%s ops=%d",
                      url, self._dry_run, len(payload.get("retenciones", [])))
        parsed = self._post_json(url, payload)

        persist_links_retenciones(parsed, pending_fingerprints, self._link_store, self._dry_run)
        self._raise_on_migrator_errors(parsed)
        self._ret_mapper.log_stats(parsed, self._dry_run)

    # ââ HTTP transport (usa PaxaposHttpClient para config, inline para patches) â

    def _headers(self) -> dict[str, str]:
        """Backward-compat shim: tests pueden mockear _headers."""
        return self._http._build_headers(content_type="application/json")

    def _post_json(self, url: str, payload: dict) -> dict:
        """POST JSON. Construye request inline para que patches en src.exporter funcionen."""
        import ssl as _ssl
        from .http_client import _dump_request, _dump_response

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        _dump_request(url, payload)

        req = request.Request(url=url, data=data, headers=self._headers(), method="POST")
        ssl_context = None
        if not self._http._verify_ssl:
            ssl_context = _ssl._create_unverified_context()

        try:
            with _http_request_with_retries(req, timeout=self._http._timeout, ssl_context=ssl_context) as resp:
                status = resp.getcode()
                final_url = resp.geturl()
                content_type = (resp.headers.get("Content-Type") or "").lower()
                body = resp.read().decode("utf-8", errors="replace")

                logger.debug(
                    "Migrator response status=%s content_type=%s final_url=%s",
                    status, content_type, final_url,
                )

                if status < 200 or status >= 300:
                    raise RuntimeError(f"HTTP {status}: {body[:500]}")

                if "json" not in content_type:
                    raise RuntimeError(f"Respuesta no JSON (Content-Type={content_type})")

                parsed = json.loads(body) if body else {}
                self._last_parsed = parsed
                if isinstance(parsed, dict) and parsed.get("errors"):
                    logger.debug("Migrator response errors=%s", parsed.get("errors"))
                _dump_response(url, parsed)
                return parsed
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"URL error: {exc.reason}") from exc

    @staticmethod
    def _raise_on_migrator_errors(parsed: dict) -> None:
        """Procesa la respuesta del migrator y reporta errores parciales."""
        if not isinstance(parsed, dict):
            return

        strict = env_bool("RAFAM_STRICT_PARTIAL_ERRORS", False)

        has_errors = False
        errors = parsed.get("errors")
        if isinstance(errors, list) and errors:
            log_fn = logger.error if strict else logger.warning
            log_fn(
                "Migrator devolvio %d error(es) parcial(es) (filas individuales fallaron, "
                "el resto del batch SI se proceso): %s",
                len(errors),
                json.dumps(errors[:20], ensure_ascii=False),
            )
            if len(errors) > 20:
                logger.warning("... y %d error(es) mas omitidos del log", len(errors) - 20)
            has_errors = True

        stats = parsed.get("stats")
        if not isinstance(stats, dict):
            if has_errors and strict:
                raise RuntimeError("Migrator devolvio errores parciales")
            return

        failed = []
        fully_failed = []
        for section, section_stats in stats.items():
            if not isinstance(section_stats, dict):
                continue
            error_count = section_stats.get("error", 0)
            ok_count = section_stats.get("ok", 0)
            try:
                error_count = int(error_count)
            except (TypeError, ValueError):
                error_count = 0
            try:
                ok_count = int(ok_count)
            except (TypeError, ValueError):
                ok_count = 0
            if error_count > 0:
                failed.append(f"{section}={error_count}")
                if ok_count == 0:
                    fully_failed.append(f"{section}={error_count}")

        if failed:
            log_fn = logger.error if strict else logger.warning
            log_fn(
                "Migrator stats: %s fila(s) fallaron pero el batch continuo. "
                "Las filas OK ya fueron persistidas.",
                ", ".join(failed),
            )
            has_errors = True

        if fully_failed:
            details = ", ".join(fully_failed)
            err_list = []
            if isinstance(errors, list):
                for err in errors:
                    msg = err.get("message") or "Error desconocido"
                    val_errs = err.get("validationErrors")
                    if val_errs:
                        msg += f" -> **DETALLE DE VALIDACIÓN: {json.dumps(val_errs, ensure_ascii=False)}**"
                    err_list.append(f"[{err.get('section', 'unknown').upper()}] {msg}")
            
            err_msg = f"Migrator devolvió errores para todas las filas de una sección: {details}"
            if err_list:
                err_msg += "\n\n >>> RESPUESTA DE ERROR DE PAXAPOS >>>\n"
                err_msg += "\n".join(f"  * {e}" for e in err_list)
                err_msg += "\n <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
            raise RuntimeError(err_msg)

        if has_errors and strict:
            details = ", ".join(failed) if failed else "ver errors en respuesta"
            err_list = []
            if isinstance(errors, list):
                for err in errors:
                    msg = err.get("message") or "Error desconocido"
                    val_errs = err.get("validationErrors")
                    if val_errs:
                        msg += f" -> **DETALLE DE VALIDACIÓN: {json.dumps(val_errs, ensure_ascii=False)}**"
                    err_list.append(f"[{err.get('section', 'unknown').upper()}] {msg}")
            
            err_msg = f"Migrator devolvió errores parciales: {details}"
            if err_list:
                err_msg += "\n\n >>> RESPUESTA DE ERROR DE PAXAPOS >>>\n"
                err_msg += "\n".join(f"  * {e}" for e in err_list)
                err_msg += "\n <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
            raise RuntimeError(err_msg)

    def close(self) -> None:
        self._link_store.close()

        results = parsed.get("results", {})
        if not isinstance(results, dict):
            return

        if entity == "proveedores":
            self._persist_links_proveedores(results, raw_by_source_key)
        elif entity == "ped_items":
            self._persist_links_section(results, "pedidos", "pedido", ["ejercicio", "num_ped"])
        elif entity == "oc_items":
            self._persist_links_orden_compra(results, raw_by_source_key)
        elif entity == "orden_compra":
            self._persist_links_orden_compra(results, raw_by_source_key)
        elif entity == "solic_gastos":
            self._persist_links_solic_gastos(results, raw_by_source_key)
        elif entity == "orden_pago":
            self._persist_links_orden_pago(results, raw_by_source_key)

    def _persist_links_proveedores(self, results: dict, raw_by_source_key: dict[str, dict]) -> None:
        proveedores = results.get("proveedores", [])
        if not isinstance(proveedores, list):
            return

        for result in proveedores:
            if not isinstance(result, dict) or not result.get("success"):
                continue
            external_id = result.get("external_id") or {}
            if not isinstance(external_id, dict):
                continue
            source_key = external_id.get("cod_prov")
            remote_id = result.get("id")
            if source_key is None or remote_id is None:
                continue

            raw = raw_by_source_key.get(str(source_key))
            cuit = self._normalize_cuit(raw.get("CUIT")) if raw else None
            cod_estado = str(raw.get("COD_ESTADO")) if raw and raw.get("COD_ESTADO") is not None else None

            payload_hash = getattr(self, "_temp_proveedor_payload_hashes", {}).get(str(source_key))
            if not payload_hash and raw:
                from .change_detection import compute_payload_hash
                mapped = map_proveedor_migrator_row(raw)
                if mapped:
                    payload_hash = compute_payload_hash(mapped.get("Proveedor", {}))

            self._link_store.save_link(
                entity="proveedores",
                source_key=str(source_key),
                remote_id=str(remote_id),
                cuit=cuit,
                cod_estado=cod_estado,
                payload_hash=payload_hash,
            )

    def _persist_links_orden_compra(self, results: dict, raw_by_source_key: dict[str, dict]) -> None:
        """Persiste entity_links para ordenes_compra con extras (estado_oc, fech_confirm, etc.)."""
        section = results.get("ordenes_compra", [])
        if not isinstance(section, list):
            return

        pk_fields = ["ejercicio", "uni_compra", "nro_oc"]
        for result in section:
            if not isinstance(result, dict) or not result.get("success"):
                continue
            external_id = result.get("external_id") or {}
            if not isinstance(external_id, dict):
                continue
            remote_id = result.get("id")
            if remote_id is None:
                continue

            key_dict = {k: external_id[k] for k in pk_fields if k in external_id}
            if len(key_dict) != len(pk_fields):
                logger.warning("Migrator [orden_compra]: external_id incompleto: %s", external_id)
                continue
            source_key = json.dumps(key_dict, sort_keys=True)

            raw = raw_by_source_key.get(source_key, {})
            estado_oc = str(raw.get("OC_ESTADO_OC", "")).strip().upper() or None
            fech_confirm = self._format_date_only(raw.get("OC_FECH_CONFIRM", "")) or None
            cod_prov = str(raw.get("COD_PROV")) if raw.get("COD_PROV") is not None else None
            importe_tot = str(raw.get("OC_IMPORTE_TOT")) if raw.get("OC_IMPORTE_TOT") is not None else None

            gasto_refs = raw.get("_GASTO_REFS", "")
            gasto_linked_refs = raw.get("_GASTO_LINKED_REFS", "")

            # gasto_ids returned by Paxapos in the OC response
            paxapos_gasto_ids_list = result.get("gasto_ids") or []
            paxapos_gasto_ids = ",".join(str(g) for g in paxapos_gasto_ids_list) if paxapos_gasto_ids_list else ""

            payload_hash = getattr(self, "_temp_oc_payload_hashes", {}).get(source_key)

            self._link_store.save_link(
                entity="orden_compra",
                source_key=source_key,
                remote_id=str(remote_id),
                estado_oc=estado_oc,
                fech_confirm=fech_confirm,
                cod_prov=cod_prov,
                importe_tot=importe_tot,
                gasto_refs=gasto_refs,
                gasto_linked_refs=gasto_linked_refs,
                paxapos_gasto_ids=paxapos_gasto_ids,
                payload_hash=payload_hash,
            )

    def _persist_links_solic_gastos(self, results: dict, raw_by_source_key: dict[str, dict]) -> None:
        """Persiste entity_links para gastos con extras (estado_solic, importe_tot, cod_prov)."""
        section = results.get("gastos", [])
        if not isinstance(section, list):
            return

        for result in section:
            if not isinstance(result, dict) or not result.get("success"):
                continue
            external_id = result.get("external_id") or {}
            if not isinstance(external_id, dict):
                continue
            remote_id = result.get("id")
            if remote_id is None:
                continue

            source_key = json.dumps(external_id, sort_keys=True)

            raw = raw_by_source_key.get(source_key, {})
            estado_solic = str(raw.get("ESTADO_SOLIC", "")).strip().upper() or None
            importe_tot = str(raw.get("IMPORTE_TOT")) if raw.get("IMPORTE_TOT") is not None else None
            cod_prov = str(raw.get("OC_COD_PROV")) if raw.get("OC_COD_PROV") is not None else None

            self._link_store.save_link(
                entity="gasto",
                source_key=source_key,
                remote_id=str(remote_id),
                estado_solic=estado_solic,
                importe_tot=importe_tot,
                cod_prov=cod_prov,
            )

            rafam_ref = self._gasto_ref_from_external_id(external_id)
            alias_keys = self._gasto_source_keys_from_ref(rafam_ref) if rafam_ref else []
            for alias_key in alias_keys:
                if alias_key == source_key:
                    continue
                self._link_store.save_link(
                    entity="gasto",
                    source_key=alias_key,
                    remote_id=str(remote_id),
                    estado_solic=estado_solic,
                    importe_tot=importe_tot,
                    cod_prov=cod_prov,
                )

    def _persist_links_orden_pago(self, results: dict, raw_by_source_key: dict[str, dict]) -> None:
        """Persiste entity_links para ordenes_pago con extras de auditoria."""
        section = results.get("ordenes_pago", [])
        if not isinstance(section, list):
            return

        pk_fields = ["ejercicio", "nro_op"]
        for result in section:
            if not isinstance(result, dict) or not result.get("success"):
                continue
            external_id = result.get("external_id") or {}
            if not isinstance(external_id, dict):
                continue
            remote_id = result.get("id")
            if remote_id is None:
                continue

            key_dict = {k: external_id[k] for k in pk_fields if k in external_id}
            if len(key_dict) != len(pk_fields):
                logger.warning("Migrator [orden_pago]: external_id incompleto: %s", external_id)
                continue
            source_key = json.dumps(key_dict, sort_keys=True)

            raw = raw_by_source_key.get(source_key, {})
            estado_op = str(raw.get("ESTADO_OP", "")).strip().upper() or None
            confirmado = str(raw.get("CONFIRMADO", "")).strip().upper() or None
            fech_confirm = self._format_date_only(raw.get("FECH_CONFIRM", "")) or None
            importe_total = str(raw.get("IMPORTE_TOTAL")) if raw.get("IMPORTE_TOTAL") is not None else None

            self._link_store.save_link(
                entity="orden_pago",
                source_key=source_key,
                remote_id=str(remote_id),
                estado_op=estado_op,
                confirmado=confirmado,
                fech_confirm=fech_confirm,
                importe_total=importe_total,
            )

    def _persist_links_section(
        self,
        results: dict,
        section_key: str,
        entity_type: str,
        pk_fields: list[str] | None,
    ) -> None:
        """Persiste entity_links para una sección genérica de la respuesta.

        Si pk_fields es None, usa external_id serializado completo como source_key.
        Si pk_fields está definido, construye source_key solo con esos campos (orden fijo).
        """
        section = results.get(section_key, [])
        if not isinstance(section, list):
            return

        for result in section:
            if not isinstance(result, dict) or not result.get("success"):
                continue
            external_id = result.get("external_id") or {}
            if not isinstance(external_id, dict):
                continue
            remote_id = result.get("id")
            if remote_id is None:
                continue

            if pk_fields:
                key_dict = {k: external_id[k] for k in pk_fields if k in external_id}
                if len(key_dict) != len(pk_fields):
                    logger.warning(
                        "Migrator [%s]: external_id incompleto para source_key: %s",
                        entity_type,
                        external_id,
                    )
                    continue
                source_key = json.dumps(key_dict, sort_keys=True)
            else:
                source_key = json.dumps(external_id, sort_keys=True)

            self._link_store.save_link(
                entity=entity_type,
                source_key=source_key,
                remote_id=str(remote_id),
            )

    @staticmethod
    def _to_int(value):
        return to_int(value)

    @staticmethod
    def _normalize_text(value):
        return normalize_text(value)

    @staticmethod
    def _normalize_cuit(value):
        return normalize_cuit(value)

    @staticmethod
    def _format_date_only(value):
        return format_date_only(value)

    @staticmethod
    def _parse_money(value):
        return parse_money(value)

    @staticmethod
    def _lookup_list(payload, key):
        return lookup_list(payload, key)

    @staticmethod
    def _build_single_index(items, field):
        return build_single_index(items, field)

    @staticmethod
    def _split_ref_set(value):
        return split_ref_set(value)

    def _resolve_tipo_factura_id(self, tipo_doc):
        return self._lookup.resolve_tipo_factura_id(tipo_doc)

    def _resolve_tipo_pago_id(self, raw=None):
        return self._lookup.resolve_tipo_pago_id(raw)

    def _resolve_tipo_retencion_id(self, cod_ret, descripcion):
        return self._lookup.resolve_tipo_retencion_id(cod_ret, descripcion)

    def _resolve_tipo_retencion_id_by_alias(self, alias):
        return self._lookup.resolve_tipo_retencion_id_by_alias(alias)

    @staticmethod
    def _retencion_alias(value):
        return LookupResolver.retencion_alias(value)

    def _resolve_centro_costo_id(self, jurisdiccion):
        return self._lookup.resolve_centro_costo_id(jurisdiccion)

    def _resolve_unidad_medida_id(self, raw):
        return self._lookup.resolve_unidad_medida_id(raw)

    def _map_solic_gasto(self, raw):
        return self._sg_mapper._map_solic_gasto(raw)

    def _map_oc_item(self, raw):
        return self._oc_mapper._map_oc_item(raw)

    def _map_deduccion_dict(self, ded, ejercicio, nro_op):
        return self._op_mapper._map_deduccion_dict(ded, ejercicio, nro_op)

    def _map_retencion(self, raw, ejercicio, nro_op):
        """Backward-compatible shim for test_map_retencion tests.
        Maps old RET_* field names to the new dict-based deduccion format.
        """
        cod_ret = raw.get("RET_COD_RET")
        importe = raw.get("RET_IMPORTE")
        descripcion = raw.get("RET_DESCRIPCION", "")
        if cod_ret is None or importe is None:
            return None
        ded = {
            "codigo_deduc": cod_ret,
            "importe_reten": importe,
            "descripcion": descripcion,
        }
        result = self._op_mapper._map_deduccion_dict(ded, ejercicio, nro_op)
        if result is None:
            return None
        # Add legacy fields expected by old tests
        alias = self._lookup.retencion_alias(descripcion or str(cod_ret))
        if alias:
            result["tipo"] = alias
        ext = result.get("external_id", {})
        if ext and "codigo_deduc" in ext:
            ext["cod_ret"] = ext.pop("codigo_deduc")
        return result

    def _map_retencion_dict(self, ded, ejercicio, nro_op):
        """Backward-compatible shim: normalizes old field names before delegating."""
        normalized = dict(ded)
        # Old API used cod_ret/importe; new mapper uses codigo_deduc/importe_reten
        if "cod_ret" in normalized and "codigo_deduc" not in normalized:
            normalized["codigo_deduc"] = normalized.pop("cod_ret")
        if "importe" in normalized and "importe_reten" not in normalized:
            normalized["importe_reten"] = normalized.pop("importe")
        return self._op_mapper._map_deduccion_dict(normalized, ejercicio, nro_op)

    @staticmethod
    def _gasto_external_id(ejercicio, deleg_solic, nro_solic):
        return _gasto_external_id_fn(ejercicio, deleg_solic, nro_solic)

    @staticmethod
    def _gasto_legacy_ref(ejercicio, deleg_solic, nro_solic):
        return _gasto_legacy_ref_fn(ejercicio, deleg_solic, nro_solic)

    @staticmethod
    def _gasto_ref_from_external_id(external_id):
        return _gasto_ref_fn(external_id)

    @staticmethod
    def _gasto_external_id_from_ref(rafam_ref):
        return _gasto_eid_from_ref_fn(rafam_ref)

    @staticmethod
    def _gasto_source_keys_from_ref(rafam_ref):
        return _gasto_skeys_fn(rafam_ref)

    @staticmethod
    def _pedido_id_from_op_row(raw):
        return _pedido_id_fn(raw)

    def _resolve_pedido_id_from_oc_link(self, raw):
        return self._op_mapper._resolve_pedido_id_from_oc_link(raw)

    def _resolve_gasto_refs_via_oc(self, ejercicio, reco_compra, reco_ejer):
        oc_nro = to_int(reco_compra)
        if oc_nro is None:
            return []
        oc_ejer = to_int(reco_ejer) or ejercicio
        table = self._link_store._ensure_table("orden_compra")
        pattern = f'%"ejercicio": {oc_ejer}%"nro_oc": {oc_nro}%'
        rows = self._link_store._conn.execute(
            f"SELECT gasto_refs FROM [{table}] WHERE source_key LIKE ? AND gasto_refs != ''",
            (pattern,),
        ).fetchall()
        refs: list[str] = []
        for row in rows:
            for ref in row["gasto_refs"].split(","):
                ref = ref.strip()
                if ref and ref not in refs:
                    refs.append(ref)
        return refs

    def _persist_links(self, entity, parsed, raw_by_source_key):
        """Backward-compatible shim for direct _persist_links calls in tests."""
        if entity == "proveedores":
            prov_mapper.persist_links(parsed, raw_by_source_key, self._link_store)
        elif entity == "oc_items":
            oc_persist_links(parsed, raw_by_source_key, self._link_store)
        elif entity == "solic_gastos":
            sg_persist_links(parsed, raw_by_source_key, self._link_store)
        elif entity == "orden_pago":
            persist_links_orden_pago(parsed, raw_by_source_key, self._link_store, self._dry_run)

    @staticmethod
    def _source_key(entity, raw):
        """Backward-compatible shim."""
        if entity == "proveedores":
            value = raw.get("COD_PROV")
            return str(value) if value is not None else None
        return None

    @staticmethod
    def _map_row(entity, raw):
        """Backward-compatible shim."""
        if entity == "proveedores":
            from .gateway_mapper import map_proveedor_migrator_row
            return map_proveedor_migrator_row(raw)
        return None


# âââ Factory âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def build_exporter(dry_run: bool = False) -> MigratorExporter:
    """Construye el exporter migrator (Ãºnico destino de salida)."""
    return MigratorExporter(dry_run=dry_run)


def fetch_migrator_spec() -> dict:
    return _fetch_migrator_json(endpoint_env="PAXAPOS_RAFAM_SPEC_PATH", default_endpoint="rafam/migracion/spec.json")


def fetch_migrator_lookups(only: list[str] | None = None) -> dict:
    filtered = [item.strip() for item in (only or []) if item and item.strip()]

    if not filtered:
        try:
            return _fetch_migrator_json(
                endpoint_env="PAXAPOS_RAFAM_LOOKUPS_PATH",
                default_endpoint="rafam/migracion/lookups.json",
            )
        except Exception:
            filtered = [
                "centros_costo",
                "mercaderias",
                "unidades_de_medida",
                "tipos_factura",
                "tipos_de_pago",
                "tipos_retencion",
                "proveedores",
                "gastos",
            ]

    if len(filtered) == 1:
        return _fetch_migrator_json(
            endpoint_env="PAXAPOS_RAFAM_LOOKUPS_PATH",
            default_endpoint="rafam/migracion/lookups.json",
            query_params={"only": filtered[0]},
        )

    merged: dict = {}
    partial_errors: dict[str, str] = {}
    for section in filtered:
        try:
            payload = _fetch_migrator_json(
                endpoint_env="PAXAPOS_RAFAM_LOOKUPS_PATH",
                default_endpoint="rafam/migracion/lookups.json",
                query_params={"only": section},
            )
            if isinstance(payload, dict):
                for key, value in payload.items():
                    merged[key] = value
        except Exception as exc:
            partial_errors[section] = str(exc)

    if not merged and partial_errors:
        raise RuntimeError(f"Todas las secciones fallaron: {partial_errors}")

    if partial_errors:
        merged["_partial_errors"] = partial_errors

    return merged


def _fetch_migrator_json(endpoint_env: str, default_endpoint: str, query_params: dict[str, str] | None = None) -> dict:
    """GET JSON desde Paxapos. Usa _http_request_with_retries del scope del exporter
    para que los test patches en src.exporter funcionen."""
    import ssl as _ssl

    base_url = _paxapos_url()
    tenant = _paxapos_tenant()
    api_key = os.getenv("PAXAPOS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Falta PAXAPOS_API_KEY en .env para consultar migrator")

    timeout = int(os.getenv("PAXAPOS_TIMEOUT_SECONDS", "20"))
    verify_ssl = env_bool("PAXAPOS_VERIFY_SSL", default="true")
    endpoint = _migrator_endpoint(endpoint_env, default_endpoint)

    headers = {
        "Accept": "application/json",
        "X-Api-Key": api_key,
        "X-Tenant-Id": tenant,
        "User-Agent": "rafam-sync/1.0",
    }
    url = _build_migrator_url(base_url, tenant, endpoint)
    if query_params:
        url = f"{url}?{parse.urlencode(query_params)}"
    req = request.Request(url=url, headers=headers, method="GET")
    ssl_context = None
    if not verify_ssl:
        ssl_context = _ssl._create_unverified_context()

    try:
        with _http_request_with_retries(req, timeout=timeout, ssl_context=ssl_context) as resp:
            content_type = (resp.headers.get("Content-Type") or "").lower()
            body = resp.read().decode("utf-8", errors="replace")
            if "json" not in content_type:
                raise RuntimeError(f"Respuesta no JSON (Content-Type={content_type})")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"URL error: {exc.reason}") from exc


def _env_bool(name: str, default="true") -> bool:
    """Backward-compatible alias for utils.env_bool."""
    return env_bool(name, default)


# ââ Backward-compatible URL helpers (re-exports from http_client) ââââââââ

def _paxapos_url() -> str:
    return _env_paxapos_url()


def _paxapos_tenant() -> str:
    return _env_paxapos_tenant()


def _migrator_endpoint(endpoint_env: str, default_endpoint: str) -> str:
    return _resolve_endpoint(endpoint_env, default_endpoint)


def _build_migrator_url(base_url: str, tenant: str, endpoint: str) -> str:
    return _build_migrator_url_impl(base_url, tenant, endpoint)
