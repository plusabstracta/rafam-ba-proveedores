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
            self._write_batch_proveedores(columns, rows)
        elif entity == "oc_items":
            self._write_batch_oc_items(columns, rows)
        elif entity == "solic_gastos":
            self._write_batch_solic_gastos(columns, rows)
        elif entity == "orden_pago":
            self._write_batch_orden_pago(columns, rows)
        elif entity == "retenciones":
            self._write_batch_retenciones(columns, rows)
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

    # ââ Backward-compatible shims (delegados a mappers/utils) âââââââââ
    # Los tests existentes acceden a estos mÃ©todos internos directamente.
    # Son proxies estables hasta que los tests se actualicen.

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
