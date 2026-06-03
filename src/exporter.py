"""
exporter.py — Destinos de salida intercambiables para los datos extraídos de Oracle.

Interfaz común:
    exporter.write_batch(entity, columns, rows)
    exporter.close()

Implementaciones:
    CsvExporter   — escribe archivos CSV en output/
    NoopExporter  — descarta los datos (modo dry-run / solo checkpoints)

Cuando se implemente el gateway Paxapos, se agrega GatewayExporter aquí
y se cambia una sola línea en main.py.
"""

import csv
import json
import logging
import os
import random
import re
import ssl
import time
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import IO
from urllib import parse
from urllib import error, request

from .entity_link_store import EntityLinkStore
from .gateway_mapper import map_proveedor_migrator_row, map_proveedor_row, resolve_centro_costo_id

logger = logging.getLogger(__name__)


# Errores HTTP transitorios que vale la pena reintentar.
_RETRYABLE_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def _http_request_with_retries(
    req: request.Request,
    *,
    timeout: float,
    ssl_context=None,
    max_attempts: int = 3,
    base_backoff: float = 0.5,
):
    """Ejecuta urlopen con retries acotados ante errores transitorios.

    Reintenta solo URLError (red caida, DNS, timeout) y HTTPError con status en
    `_RETRYABLE_HTTP_STATUS`. Errores 4xx normales (validacion, auth) NO se
    reintentan — falla rapido para que el caller actue.

    Usa backoff exponencial con jitter aleatorio para evitar thundering herd
    si varios cron salen al mismo tiempo. Devuelve el response object abierto;
    el caller debe usarlo dentro de `with`.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return request.urlopen(req, timeout=timeout, context=ssl_context)
        except error.HTTPError as exc:
            # Solo reintentamos status transitorios. 4xx no transitorios suben directo.
            if exc.code not in _RETRYABLE_HTTP_STATUS or attempt == max_attempts:
                raise
            last_exc = exc
        except error.URLError as exc:
            if attempt == max_attempts:
                raise
            last_exc = exc

        backoff = base_backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
        logger.warning(
            "HTTP retry %d/%d a %s tras error transitorio: %s (backoff %.2fs)",
            attempt, max_attempts - 1, req.full_url, last_exc, backoff,
        )
        time.sleep(backoff)
    # Defensa: nunca se alcanza, pero si llega significa que loop salio sin raise.
    raise RuntimeError("HTTP retries agotados sin excepcion observable") from last_exc


# Patron para redactar campos sensibles en dumps de payload.
_SENSITIVE_FIELDS = re.compile(
    r'"(cuit|password|token|api_key|authorization|jwt|x[-_]api[-_]key)"\s*:\s*"[^"]*"',
    re.IGNORECASE,
)


def _redact_payload_for_dump(text: str) -> str:
    """Enmascara CUIT y secrets en string JSON serializado para no leak en dumps."""
    return _SENSITIVE_FIELDS.sub(lambda m: f'"{m.group(1)}":"***REDACTED***"', text)


def _dump_payload_path() -> str | None:
    """Devuelve path de DUMP_PAYLOAD si esta habilitado y APP_ENV no es 'prod'.

    En produccion bloqueamos el dump para evitar leak accidental de datos
    fiscales (CUIT, importes, identificadores). Para forzar dump en prod hay
    que setear `DUMP_PAYLOAD_FORCE=1` explicitamente.
    """
    path = os.environ.get("DUMP_PAYLOAD")
    if not path:
        return None
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    if app_env == "prod" and os.environ.get("DUMP_PAYLOAD_FORCE", "").strip() != "1":
        logger.warning(
            "DUMP_PAYLOAD ignorado en APP_ENV=prod. Setear DUMP_PAYLOAD_FORCE=1 para forzar."
        )
        return None
    return path


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


# ─── CSV ─────────────────────────────────────────────────────────────────────

class CsvExporter(BaseExporter):
    """
    Escribe un archivo CSV por entidad en output/.
    Todos los lotes de la misma entidad se acumulan en el mismo archivo.
    El archivo se crea (o sobreescribe) al enviar el primer lote.
    """

    def __init__(self, output_dir: str | Path = "output"):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._writers: dict[str, csv.writer] = {}
        self._files:   dict[str, IO[str]]     = {}
        self._timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _get_writer(self, entity: str, columns: list[str]) -> csv.writer:
        if entity not in self._writers:
            path = self._output_dir / f"{entity}_{self._timestamp}.csv"
            f = open(path, "w", newline="", encoding="utf-8")
            writer = csv.writer(f)
            writer.writerow(columns)
            self._files[entity]   = f
            self._writers[entity] = writer
            logger.info("Archivo creado: %s", path)
        return self._writers[entity]

    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        writer = self._get_writer(entity, columns)
        writer.writerows(rows)
        # Flush after each batch so partial data is visible if the run is interrupted
        self._files[entity].flush()

    def close(self) -> None:
        for f in self._files.values():
            f.close()
        self._files.clear()
        self._writers.clear()


# ─── Noop (dry-run) ──────────────────────────────────────────────────────────

class NoopExporter(BaseExporter):
    """Descarta los datos. Útil para correr solo la lógica de checkpoints."""

    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        pass


# ─── Gateway (Paxapos) ───────────────────────────────────────────────────────

class GatewayExporter(BaseExporter):
    """Envía los lotes traducidos a endpoints JSON de Paxapos (CakePHP 2)."""

    def __init__(self, force_update: bool = False):
        self._base_url = _paxapos_url()
        self._tenant = _paxapos_tenant()

        self._app_env = os.getenv("APP_ENV", "dev").strip().lower()
        self._timeout = int(os.getenv("PAXAPOS_TIMEOUT_SECONDS", "20"))
        self._verify_ssl = _env_bool("PAXAPOS_VERIFY_SSL", default="true")
        self._jwt = os.getenv("PAXAPOS_JWT", "").strip()
        if not self._jwt:
            raise ValueError("Falta PAXAPOS_JWT en .env para modo gateway")

        self._entity_endpoints = {
            "proveedores": os.getenv("PAXAPOS_PROVEEDORES_ENDPOINT", "account/proveedores.json"),
        }
        self._entity_update_endpoints = {
            "proveedores": os.getenv("PAXAPOS_PROVEEDORES_UPDATE_ENDPOINT", "account/proveedores/edit/{id}.json"),
        }
        self._entity_lookup_endpoints = {
            "proveedores": os.getenv("PAXAPOS_PROVEEDORES_LOOKUP_ENDPOINT", "account/proveedores/buscar.json"),
        }
        self._entity_lookup_index_endpoints = {
            "proveedores": os.getenv("PAXAPOS_PROVEEDORES_LOOKUP_INDEX_ENDPOINT", "account/proveedores/index.json"),
        }
        self._lookup_proveedores_enabled = True
        self._force_update = force_update
        self._link_store = EntityLinkStore()

        if not self._verify_ssl:
            logger.warning("PAXAPOS_VERIFY_SSL=false: SSL certificate verification deshabilitada para gateway")

    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        endpoint = self._entity_endpoints.get(entity)
        if not endpoint:
            raise ValueError(
                f"No hay endpoint gateway configurado para entidad '{entity}'. "
                "Actualmente soportadas: proveedores"
            )

        sent = 0
        updated = 0
        skipped_existing = 0
        skipped_linked = 0
        errors_count = 0

        for row in rows:
            raw = dict(zip(columns, row))
            payload = self._map_payload(entity, raw)
            if payload is None:
                continue

            source_key = self._source_key(entity, raw)
            if source_key is not None:
                known_remote_id = self._link_store.get_remote_id(entity, source_key)
                if known_remote_id:
                    if self._force_update:
                        update_url = self._build_update_url(entity, known_remote_id)
                        if update_url is None:
                            skipped_linked += 1
                            continue
                        try:
                            logger.debug(
                                "Gateway update [%s] POST %s remote_id=%s payload_keys=%s",
                                entity,
                                update_url,
                                known_remote_id,
                                sorted(payload.keys()),
                            )
                            parsed = self._post_json(update_url, payload)
                            self._persist_link(entity, raw, parsed, fallback_remote_id=str(known_remote_id))
                            updated += 1
                            continue
                        except Exception as exc:
                            errors_count += 1
                            logger.error("Gateway update error en %s (%s): %s", entity, update_url, exc)
                            continue
                    skipped_linked += 1
                    continue

            url = f"{self._base_url}/{endpoint.lstrip('/')}"
            try:
                logger.debug("Gateway request [%s] POST %s payload_keys=%s", entity, url, sorted(payload.keys()))
                parsed = self._post_json(url, payload)
                self._persist_link(entity, raw, parsed)
                sent += 1
            except AlreadyExistsError as exc:
                skipped_existing += 1
                self._resolve_and_persist_existing(entity, raw, exc.parsed)
                logger.debug("Gateway skip existente [%s]: %s", entity, exc)
            except Exception as exc:
                errors_count += 1
                logger.error("Gateway error en %s (%s): %s", entity, url, exc)

        if errors_count:
            raise RuntimeError(f"{entity}: {errors_count} envíos fallidos al gateway")

        logger.info(
            "Gateway OK [%s]: %d creados, %d actualizados, %d ya existentes, %d ya vinculados localmente",
            entity,
            sent,
            updated,
            skipped_existing,
            skipped_linked,
        )

    def _map_payload(self, entity: str, raw: dict) -> dict | None:
        if entity == "proveedores":
            return map_proveedor_row(raw)
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Tenant-Id": self._tenant,
            "Authorization": f"Bearer {self._jwt}",
            "User-Agent": "rafam-sync/1.0",
        }

    def _post_json(self, url: str, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(url=url, data=data, headers=self._headers(), method="POST")
        ssl_context = None
        if not self._verify_ssl:
            ssl_context = ssl._create_unverified_context()

        try:
            with _http_request_with_retries(req, timeout=self._timeout, ssl_context=ssl_context) as resp:
                status = resp.getcode()
                final_url = resp.geturl()
                content_type = (resp.headers.get("Content-Type") or "").lower()
                body = resp.read().decode("utf-8", errors="replace")

                logger.debug(
                    "Gateway response status=%s content_type=%s final_url=%s",
                    status,
                    content_type,
                    final_url,
                )

                if status < 200 or status >= 300:
                    raise RuntimeError(f"HTTP {status}: {body[:500]}")

                # urllib puede seguir 302 al login y devolver HTML 200.
                if final_url.rstrip("/") != url.rstrip("/"):
                    raise RuntimeError(
                        f"Redirect inesperado a {final_url}. Posible falta de autenticacion."
                    )

                if "json" not in content_type:
                    raise RuntimeError(
                        f"Respuesta no JSON (Content-Type={content_type}). "
                        "Posible login HTML o endpoint incorrecto."
                    )

                parsed = json.loads(body) if body else {}
                logger.debug(
                    "Gateway response [%s] %s",
                    status,
                    self._summarize_gateway_payload(parsed),
                )
                if isinstance(parsed, dict) and ("error" in parsed or "validationErrors" in parsed):
                    if self._is_duplicate_cuit_error(parsed):
                        raise AlreadyExistsError("Proveedor ya existe por CUIT", parsed=parsed)
                    raise RuntimeError(f"Error de validacion CakePHP: {json.dumps(parsed, ensure_ascii=False)[:500]}")
                return parsed
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"URL error: {exc.reason}") from exc

    def _get_json(self, url: str) -> dict:
        req = request.Request(url=url, headers=self._headers(), method="GET")
        ssl_context = None
        if not self._verify_ssl:
            ssl_context = ssl._create_unverified_context()

        with _http_request_with_retries(req, timeout=self._timeout, ssl_context=ssl_context) as resp:
            status = resp.getcode()
            final_url = resp.geturl()
            content_type = (resp.headers.get("Content-Type") or "").lower()
            body = resp.read().decode("utf-8", errors="replace")

            if status < 200 or status >= 300:
                raise RuntimeError(f"Lookup HTTP {status}")

            if final_url.rstrip("/") != url.rstrip("/"):
                raise RuntimeError(f"Lookup redirect inesperado a {final_url}")

            if "json" not in content_type:
                raise RuntimeError(f"Lookup no devolvio JSON (Content-Type={content_type})")

            return json.loads(body) if body else {}

    def _persist_link(self, entity: str, raw: dict, parsed: dict, fallback_remote_id: str | None = None) -> None:
        if entity != "proveedores":
            return

        remote_id = None
        if isinstance(parsed, dict):
            proveedor = parsed.get("Proveedor")
            if isinstance(proveedor, dict):
                remote_id = proveedor.get("id")
        if remote_id is None:
            remote_id = fallback_remote_id

        source_key = raw.get("COD_PROV")
        cuit = self._normalize_cuit(raw.get("CUIT"))

        if remote_id is None or source_key is None:
            return

        self._link_store.save_link(
            entity=entity,
            source_key=str(source_key),
            remote_id=str(remote_id),
            cuit=cuit,
        )

    def _build_update_url(self, entity: str, remote_id: str) -> str | None:
        template = self._entity_update_endpoints.get(entity)
        if not template:
            return None
        path = template.format(id=remote_id)
        return f"{self._base_url}/{path.lstrip('/')}"

    def _resolve_and_persist_existing(self, entity: str, raw: dict, parsed: dict) -> None:
        if entity != "proveedores":
            return

        source_key = raw.get("COD_PROV")
        cuit = self._normalize_cuit(raw.get("CUIT"))
        if source_key is None or not cuit:
            return

        remote_id = self._lookup_proveedor_id_by_cuit(cuit)
        if not remote_id:
            if self._lookup_proveedores_enabled:
                logger.warning("No se pudo resolver ID remoto para proveedor existente CUIT=%s", cuit)
            return

        self._link_store.save_link(
            entity=entity,
            source_key=str(source_key),
            remote_id=str(remote_id),
            cuit=cuit,
        )

    def _lookup_proveedor_id_by_cuit(self, cuit: str) -> str | None:
        if not self._lookup_proveedores_enabled:
            return None

        lookup_errors: list[str] = []

        # 1) Preferimos index.json con filterArgs del modelo (cuit/search)
        # porque suele estar mejor soportado por permisos y vistas en CakePHP.
        index_endpoint = self._entity_lookup_index_endpoints.get("proveedores")
        if index_endpoint:
            for params in ({"cuit": cuit}, {"search": cuit}):
                query = parse.urlencode(params)
                url = f"{self._base_url}/{index_endpoint.lstrip('/')}?{query}"
                try:
                    parsed = self._get_json(url)
                    provider_id = self._extract_provider_id_from_index_payload(parsed, cuit)
                    if provider_id:
                        return provider_id
                except Exception as exc:
                    lookup_errors.append(f"index({params})={exc}")

        # 2) Fallback al endpoint buscar.json (q, limit)
        search_endpoint = self._entity_lookup_endpoints.get("proveedores")
        if search_endpoint:
            query = parse.urlencode({"q": cuit, "limit": 20})
            url = f"{self._base_url}/{search_endpoint.lstrip('/')}?{query}"
            try:
                parsed = self._get_json(url)
                provider_id = self._extract_provider_id_from_search_payload(parsed, cuit)
                if provider_id:
                    return provider_id
            except Exception as exc:
                lookup_errors.append(f"buscar={exc}")

        if lookup_errors:
            self._lookup_proveedores_enabled = False
            logger.warning(
                "Lookup proveedor por CUIT deshabilitado para esta corrida: %s",
                " | ".join(lookup_errors),
            )
        return None

    def _extract_provider_id_from_search_payload(self, parsed: dict, cuit: str) -> str | None:
        proveedores = parsed.get("proveedores", []) if isinstance(parsed, dict) else []
        if not isinstance(proveedores, list):
            return None

        for prov in proveedores:
            if not isinstance(prov, dict):
                continue
            if self._normalize_cuit(prov.get("cuit")) == cuit:
                pid = prov.get("id")
                return str(pid) if pid is not None else None
        return None

    def _extract_provider_id_from_index_payload(self, parsed, cuit: str) -> str | None:
        # View Proveedores/json/index.ctp devuelve lista [{"id": ..., "value": "Nombre (CUIT)"}]
        if not isinstance(parsed, list):
            return None

        for item in parsed:
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            value_cuit = self._normalize_cuit(value)
            if value_cuit == cuit:
                pid = item.get("id")
                return str(pid) if pid is not None else None
        return None

    @staticmethod
    def _normalize_cuit(value) -> str | None:
        if value is None:
            return None
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        return digits if len(digits) == 11 else None

    @staticmethod
    def _source_key(entity: str, raw: dict) -> str | None:
        if entity == "proveedores":
            value = raw.get("COD_PROV")
            return str(value) if value is not None else None
        return None

    @staticmethod
    def _summarize_gateway_payload(parsed: dict) -> str:
        if not isinstance(parsed, dict):
            return "payload no-objeto"

        if "Proveedor" in parsed and isinstance(parsed["Proveedor"], dict):
            prov = parsed["Proveedor"]
            pid = prov.get("id")
            cuit = prov.get("cuit")
            return f"Proveedor creado/obtenido id={pid} cuit={cuit}"

        if "error" in parsed or "validationErrors" in parsed:
            err = parsed.get("error")
            val = parsed.get("validationErrors")
            return f"error={err} validationErrors={val}"

        return f"keys={sorted(parsed.keys())}"

    @staticmethod
    def _is_duplicate_cuit_error(parsed: dict) -> bool:
        """Detect CakePHP validation error for duplicate CUIT to keep sync idempotent."""
        validation_errors = parsed.get("validationErrors")
        if not isinstance(validation_errors, dict):
            return False

        cuit_errors = validation_errors.get("cuit")
        if not isinstance(cuit_errors, list):
            return False

        text = " ".join(str(e).lower() for e in cuit_errors)
        return "ya existe" in text and "cuit" in text

    def close(self) -> None:
        self._link_store.close()


class MigratorExporter(BaseExporter):
    """Envía lotes al importador RAFAM -> Paxapos via /rafam/migracion/importar.json."""

    def __init__(self, dry_run: bool = False):
        self._base_url = _paxapos_url()
        self._tenant = _paxapos_tenant()

        self._api_key = os.getenv("PAXAPOS_API_KEY", "").strip()
        if not self._api_key:
            raise ValueError("Falta PAXAPOS_API_KEY en .env para modo migrator")

        self._timeout = int(os.getenv("PAXAPOS_TIMEOUT_SECONDS", "20"))
        self._verify_ssl = _env_bool("PAXAPOS_VERIFY_SSL", default="true")
        self._import_endpoint = _migrator_endpoint("PAXAPOS_RAFAM_IMPORT_PATH", "rafam/migracion/importar.json")
        self._import_url = _build_migrator_url(self._base_url, self._tenant, self._import_endpoint)
        self._dry_run = dry_run
        self._link_store = EntityLinkStore()
        self._lookup_payload = fetch_migrator_lookups([
            "unidades_de_medida",
            "tipos_factura",
            "tipos_de_pago",
            "tipos_retencion",
        ])
        self._unidades = self._lookup_list(self._lookup_payload, "unidades_de_medida")
        self._tipos_factura = self._lookup_list(self._lookup_payload, "tipos_factura")
        self._tipos_factura_by_codename = self._build_single_index(self._tipos_factura, "codename")
        self._tipos_factura_by_name = self._build_single_index(self._tipos_factura, "name")
        self._default_tipo_factura_id = self._to_int(os.getenv("PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID"))
        self._tipos_de_pago = self._lookup_list(self._lookup_payload, "tipos_de_pago")
        self._tipos_de_pago_by_name = self._build_single_index(self._tipos_de_pago, "name")
        self._default_tipo_pago_id = self._to_int(os.getenv("PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID")) or 1
        self._tipos_retencion = self._lookup_list(self._lookup_payload, "tipos_retencion")
        self._tipos_retencion_by_codigo = self._build_single_index(self._tipos_retencion, "codigo")
        self._tipos_retencion_by_codename = self._build_single_index(self._tipos_retencion, "codename")
        self._tipos_retencion_by_name = self._build_single_index(self._tipos_retencion, "name")
        self._missing_mercaderia_matches: dict[str, int] = {}
        self._source_repo = None
        self._retencion_skipped_no_catalog: int = 0
        self._retencion_skipped_no_match: dict[str, int] = {}

        if not self._verify_ssl:
            logger.warning("PAXAPOS_VERIFY_SSL=false: SSL certificate verification deshabilitada para migrator")
        if isinstance(self._lookup_payload, dict) and self._lookup_payload.get("_partial_errors"):
            logger.warning("Migrator lookups parciales: %s", self._lookup_payload.get("_partial_errors"))

    def attach_source(self, source_repo) -> None:
        self._source_repo = source_repo

    def _payload_options(self) -> dict:
        # auto_create_gasto queda siempre activo: las OP vinculan/crean gastos
        # desde el numero de comprobante RAFAM cuando Paxapos aun no lo tiene.
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

    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
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
        for row in rows:
            raw = dict(zip(columns, row))
            payload_row = self._map_row("proveedores", raw)
            if payload_row is None:
                continue
            source_key = self._source_key("proveedores", raw)
            if source_key is not None:
                raw_by_source_key[source_key] = raw
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
                # Estado N u otro → fallback: si tiene comprobante o OP
                # asociada en RAFAM, enviar a Paxapos (la OC ya tiene
                # actividad downstream real).
                has_cc = bool(str(raw.get("OC_CC_NRO") or "").strip())
                has_op = bool(link_previo and link_previo.get("has_op"))
                if has_cc or has_op:
                    logger.info(
                        "Migrator [oc_items] OC %s-%s-%s estado %s pero tiene %s,"
                        " enviando a Paxapos como fallback",
                        key[0], key[1], key[2], estado_actual,
                        "comprobante+OP" if (has_cc and has_op)
                        else ("comprobante" if has_cc else "OP"),
                    )
                    ocs_to_create.append(oc_data)
                else:
                    # Sin actividad downstream → solo registrar localmente
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
                # Estado N u otro → fallback: si tiene comprobante o OP
                # asociada en RAFAM, enviar a Paxapos.
                has_cc = bool(str(raw.get("OC_CC_NRO") or "").strip())
                has_op = bool(link_previo and link_previo.get("has_op"))
                if has_cc or has_op:
                    logger.info(
                        "Migrator [orden_compra] OC %s-%s-%s estado %s pero tiene %s,"
                        " enviando a Paxapos como fallback",
                        key[0], key[1], key[2], estado_actual,
                        "comprobante+OP" if (has_cc and has_op)
                        else ("comprobante" if has_cc else "OP"),
                    )
                    ocs_to_create.append(oc_data)
                else:
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
            gasto_data["factura_nro"] = nro_comprob



        # fecha_vencimiento: FECH_NECESIDAD con fallback a FECH_ENTREGA
        fech_venc = (
            self._format_date_only(raw.get("CTA_FECH_VENCIM"))
            or self._format_date_only(raw.get("FECH_NECESIDAD"))
            or self._format_date_only(raw.get("FECH_ENTREGA"))
        )
        if fech_venc:
            gasto_data["fecha_vencimiento"] = fech_venc

        # proveedor_id via EntityLinkStore (COD_PROV traído por LEFT JOIN a ORDEN_COMPRA via OC_ITEMS)
        cod_prov = self._to_int(raw.get("OC_COD_PROV"))
        if cod_prov is not None:
            remote_prov = self._link_store.get_remote_id("proveedores", str(cod_prov))
            if remote_prov:
                gasto_data["proveedor_id"] = int(remote_prov)
            else:
                logger.debug(
                    "Migrator [solic_gastos] SG %s-%s-%s: proveedor COD_PROV=%s sin link remoto",
                    ejercicio, deleg_solic, nro_solic, cod_prov,
                )

        obs = raw.get("OBSERVACIONES")
        if obs and str(obs).strip():
            gasto_data["observacion"] = str(obs).strip()[:255]

        return {
            "external_id": self._gasto_external_id(ejercicio, deleg_solic, nro_solic),
            "Gasto": gasto_data,
        }

    def _resolve_gasto_refs_via_oc(self, ejercicio: int, reco_compra, reco_ejer) -> list[str]:
        """Fallback: resolve gasto refs via RECO_DEU_COMPRA → OC link_store → gasto_refs.

        When the direct NRO_CANCE → SOLIC_GASTOS join fails, we can trace the
        chain: OP.RECO_DEU_COMPRA → ORDEN_COMPRA → OC link (gasto_refs stored
        as comma-separated SG-ej-deleg-nro strings).
        """
        oc_nro = self._to_int(reco_compra)
        if oc_nro is None:
            return []
        oc_ejer = self._to_int(reco_ejer) or ejercicio

        # OC link_store keys include uni_compra; scan all matching OCs for this
        # ejercicio+nro_oc since we don't know the UNI_COMPRA from ORDEN_PAGO.
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

    def _pedido_id_from_op_row(self, raw: dict) -> int | None:
        """Devuelve el pedido_id si la fila ya lo trae; no resuelve links locales."""
        for field in ("pedido_id", "PEDIDO_ID", "PAXAPOS_PEDIDO_ID"):
            pedido_id = self._to_int(raw.get(field))
            if pedido_id is not None:
                return pedido_id
        return None

    def _resolve_pedido_id_from_oc_link(self, raw: dict) -> int | None:
        """Resuelve pedido_id consultando link_store con la clave de OC RAFAM
        provista por el REG_COMP exacto imputado en ORDEN_PAGO_IMPUT.

        El backend usa pedido_id para vincular el Gasto auto-creado por la OP
        a la OC original. Sin esta resolución, el Gasto queda huérfano de OC.
        """
        ej = self._to_int(raw.get("SG_OC_EJERCICIO"))
        uni = self._to_int(raw.get("SG_OC_UNI_COMPRA"))
        nro = self._to_int(raw.get("SG_OC_NRO"))
        if ej is None or uni is None or nro is None:
            return None
        source_key = json.dumps(
            {"ejercicio": ej, "nro_oc": nro, "uni_compra": uni},
            sort_keys=True,
        )
        link = self._link_store.get_link("orden_compra", source_key)
        if not link:
            return None
        remote_id = link.get("remote_id")
        try:
            return int(remote_id) if remote_id is not None else None
        except (TypeError, ValueError):
            return None

    def _build_gasto_from_op_row(
        self, raw: dict
    ) -> tuple[dict | None, tuple[int, str, str] | None]:
        """Construye un bloque Gasto a partir de un row de OP enriquecido con CTA_COMPROB.

        Devuelve (gasto_payload, dedup_key) donde dedup_key es
        (proveedor_id, punto_de_venta, factura_nro) — la clave de upsert real
        de Paxapos. Si faltan datos esenciales (factura_nro, proveedor_id,
        importe o fecha), devuelve (None, None).
        """
        cc_nro = str(raw.get("OPI_NRO_COMPROB") or "").strip()
        if not cc_nro:
            return None, None

        # proveedor_id: priorizar el del comprobante (OPI_COD_PROV) que es el
        # emisor real de la factura; fallback al de la OC y al de la OP.
        remote_prov_id: int | None = None
        for cod_prov in (
            raw.get("OPI_COD_PROV"),
            raw.get("SG_OC_COD_PROV"),
            raw.get("COD_PROV"),
        ):
            if cod_prov is None or str(cod_prov).strip() == "":
                continue
            remote_prov = self._link_store.get_remote_id(
                "proveedores", str(cod_prov).strip()
            )
            if remote_prov:
                remote_prov_id = int(remote_prov)
                break
        if remote_prov_id is None:
            return None, None

        # importe: priorizar CTA_COMPROB.IMPORTE_COMPR (dato fiscal real).
        importe_raw = raw.get("CTA_IMPORTE_COMPR")
        if importe_raw is None:
            return None, None
        try:
            importe_total = round(float(importe_raw), 2)
        except (TypeError, ValueError):
            return None, None

        importe_neto = self._parse_money(raw.get("CTA_IMPORTE_NETO"))
        if importe_neto is None:
            importe_neto = self._parse_money(raw.get("CTA_IMPORTE_SIN_IVA"))
        if importe_neto is None:
            importe_neto = importe_total

        # fecha: CTA_COMPROB.FECH_COMPROB; obligatoria en Paxapos.
        fecha = self._format_date_only(raw.get("CTA_FECH_COMPROB"))
        if not fecha:
            return None, None

        gasto_data: dict = {
            "fecha": fecha,
            "importe_total": importe_total,
            "importe_neto": importe_neto,
            "proveedor_id": remote_prov_id,
        }
        pedido_id = self._to_int(raw.get("_PAXAPOS_PEDIDO_ID") or raw.get("pedido_id"))
        if pedido_id is not None:
            gasto_data["pedido_id"] = pedido_id

        # tipo_factura_id desde OPI_TIPO_COMPROB
        tipo_factura_id = self._resolve_tipo_factura_id(raw.get("OPI_TIPO_COMPROB"))
        if tipo_factura_id is not None:
            gasto_data["tipo_factura_id"] = tipo_factura_id

        # Parsear NRO_COMPROB: si tiene guion, separar punto_de_venta + factura_nro
        dash_pos = cc_nro.find("-")
        if dash_pos > 0:
            punto_de_venta = cc_nro[:dash_pos]
            factura_nro = cc_nro[dash_pos + 1:]
        else:
            punto_de_venta = ""
            factura_nro = cc_nro
        gasto_data["punto_de_venta"] = punto_de_venta
        gasto_data["factura_nro"] = factura_nro

        # fecha_vencimiento opcional
        fech_venc = self._format_date_only(raw.get("CTA_FECH_VENCIM"))
        if fech_venc:
            gasto_data["fecha_vencimiento"] = fech_venc

        # external_id: si el REG_COMP exacto del OPI trae SG asociada, usar el
        # formato canónico; si no, usar uno basado en el comprobante fiscal.
        sg_ej = self._to_int(raw.get("EJERCICIO"))
        sg_deleg = self._to_int(raw.get("SG_DELEG_SOLIC"))
        sg_nro = self._to_int(raw.get("SG_NRO_SOLIC"))
        if sg_ej is not None and sg_deleg is not None and sg_nro is not None:
            external_id = self._gasto_external_id(sg_ej, sg_deleg, sg_nro)
        else:
            external_id = {
                "rafam_ref": (
                    f"CC-{raw.get('EJERCICIO')}-{raw.get('OPI_TIPO_COMPROB') or ''}-"
                    f"{cc_nro}-{raw.get('OPI_COD_PROV') or ''}"
                )
            }

        # tipo_factura_id forma parte del dedup_key porque un mismo proveedor puede
        # tener Factura A y Nota de Credito A con identico PDV+factura_nro (RAFAM
        # CC_TIPO_COMPROB FAA vs NCA), y son comprobantes distintos en Paxapos.
        dedup_key = (remote_prov_id, punto_de_venta, factura_nro, tipo_factura_id)
        return {"external_id": external_id, "Gasto": gasto_data}, dedup_key

    def _write_batch_orden_pago(self, columns: list[str], rows: list[tuple]) -> None:
        # Agrupa por (EJERCICIO, NRO_OP) y acumula las refs de gastos del REG_COMP
        # exacto de ORDEN_PAGO_IMPUT cuando existe.
        # NOTA: las retenciones NO vienen en este batch — se traen por separado
        # via source_repo.fetch_retenciones_for_ops() para evitar producto cartesiano
        # con los comprobantes pagados. Ver source_repository._build_orden_pago_statement.
        grouped: dict[tuple[int, int], dict] = {}
        grouped_gasto_refs: dict[tuple[int, int], list[str]] = {}
        grouped_cc_nros: dict[tuple[int, int], list[str]] = {}
        grouped_cc_keys: dict[tuple[int, int], list[tuple[str, str, str]]] = {}
        grouped_pedido_ids: dict[tuple[int, int], list[int]] = {}
        grouped_pedido_internal_ids: dict[tuple[int, int], list[str]] = {}
        grouped_oc_source_keys: dict[tuple[int, int], list[str]] = {}
        grouped_has_opi: set[tuple[int, int]] = set()
        raw_by_source_key: dict[str, dict] = {}
        # cc_raw_by_key: dedup por comprobante fiscal real para emitir gastos[]
        # con datos de CTA_COMPROB (importe, fecha, tipo, vencimiento). La key
        # es (CC_TIPO, CC_NRO, CC_COD_PROV) — PK lógica del comprobante en RAFAM.
        cc_raw_by_key: dict[tuple[str, str, str], dict] = {}
        skipped_estado: dict[str, int] = {}
        skipped_confirmado: dict[str, int] = {}
        skipped_no_fech_confirm = 0
        skipped_importe_invalido: dict[str, int] = {}
        skipped_existing_keys: set[tuple[int, int]] = set()

        for row in rows:
            raw = dict(zip(columns, row))
            ejercicio = self._to_int(raw.get("EJERCICIO"))
            nro_op = self._to_int(raw.get("NRO_OP"))
            if ejercicio is None or nro_op is None:
                continue

            key = (ejercicio, nro_op)

            if any(
                str(raw.get(field) or "").strip()
                for field in ("OPI_NRO_REG_COMP", "OPI_TIPO_COMPROB", "OPI_NRO_COMPROB", "OPI_COD_PROV")
            ):
                grouped_has_opi.add(key)

            # Recolectar ref de gasto desde columnas del LEFT JOIN
            sg_deleg = self._to_int(raw.get("SG_DELEG_SOLIC"))
            sg_nro = self._to_int(raw.get("SG_NRO_SOLIC"))
            if sg_deleg is not None and sg_nro is not None:
                rafam_ref = f"SG-{ejercicio}-{sg_deleg}-{sg_nro}"
                refs = grouped_gasto_refs.setdefault(key, [])
                if rafam_ref not in refs:
                    refs.append(rafam_ref)

            # Recolectar nro_comprobante (CC) directamente desde ORDEN_PAGO_IMPUT
            # (path PRIMARIO). OPI_NRO_COMPROB / OPI_TIPO_COMPROB / OPI_COD_PROV
            # son ya las claves canonicas del comprobante asociado a esta OP.
            # No hay promocion de columnas: los datos vienen del bridge real
            # OP_IMPUT, no de una vista derivada.
            cc_nro = str(raw.get("OPI_NRO_COMPROB") or "").strip()
            if cc_nro:
                cc_nros = grouped_cc_nros.setdefault(key, [])
                if cc_nro not in cc_nros:
                    cc_nros.append(cc_nro)
                # Guardar raw representativo por comprobante para emitir gastos[]
                # con datos de CTA_COMPROB (importe/fecha/vencimiento/tipo).
                cc_tipo = str(raw.get("OPI_TIPO_COMPROB") or "").strip()
                cc_prov = str(raw.get("OPI_COD_PROV") or "").strip()
                cc_key = (cc_tipo, cc_nro, cc_prov)
                cc_keys = grouped_cc_keys.setdefault(key, [])
                if cc_key not in cc_keys:
                    cc_keys.append(cc_key)
                existing = cc_raw_by_key.get(cc_key)
                # Preferir el raw que ya trae datos fiscales reales (CTA_COMPROB)
                if existing is None or (
                    raw.get("CTA_IMPORTE_COMPR") is not None
                    and existing.get("CTA_IMPORTE_COMPR") is None
                ):
                    cc_raw_by_key[cc_key] = raw

            # pedido_id: prioridad a la fila (override manual). Si no viene,
            # se intenta resolver via link_store usando la OC del REG_COMP
            # exacto imputado por la OP.
            pedido_id = self._pedido_id_from_op_row(raw)
            if pedido_id is None:
                pedido_id = self._resolve_pedido_id_from_oc_link(raw)
            if pedido_id is not None:
                pedido_ids = grouped_pedido_ids.setdefault(key, [])
                if pedido_id not in pedido_ids:
                    pedido_ids.append(pedido_id)

            # Registrar el internal_id candidato solo para diagnostico. Ya no se
            # envia como fallback: una OP sin pedido_id local podria crear un
            # gasto suelto si la OC no existe en Paxapos.
            oc_ej = self._to_int(raw.get("SG_OC_EJERCICIO"))
            oc_nro = self._to_int(raw.get("SG_OC_NRO"))
            if oc_ej is not None and oc_nro is not None:
                internal_id = f"{oc_ej % 100}-{oc_nro}"
                internals = grouped_pedido_internal_ids.setdefault(key, [])
                if internal_id not in internals:
                    internals.append(internal_id)

                # Rastrear OC source_key para marcar has_op despu\u00e9s del env\u00edo
                oc_uni = self._to_int(raw.get("SG_OC_UNI_COMPRA"))
                if oc_uni is not None:
                    oc_sk = json.dumps(
                        {"ejercicio": oc_ej, "nro_oc": oc_nro, "uni_compra": oc_uni},
                        sort_keys=True,
                    )
                    oc_sks = grouped_oc_source_keys.setdefault(key, [])
                    if oc_sk not in oc_sks:
                        oc_sks.append(oc_sk)

            estado = str(raw.get("ESTADO_OP", "")).strip().upper()
            if estado != "C":
                skipped_estado[estado or "(vacio)"] = skipped_estado.get(estado or "(vacio)", 0) + 1
                continue
            confirmado = str(raw.get("CONFIRMADO", "")).strip().upper()
            if confirmado != "S":
                skipped_confirmado[confirmado or "(vacio)"] = skipped_confirmado.get(confirmado or "(vacio)", 0) + 1
                continue
            fecha_confirm = self._format_date_only(raw.get("FECH_CONFIRM") or "")
            if not fecha_confirm:
                skipped_no_fech_confirm += 1
                continue

            sk = json.dumps({"ejercicio": ejercicio, "nro_op": nro_op}, sort_keys=True)
            existing_op = self._link_store.get_link("orden_pago", sk)
            if existing_op and existing_op.get("remote_id"):
                skipped_existing_keys.add(key)
                continue

            if key in grouped:
                continue

            # Guardar raw para extras en persist_links
            raw_by_source_key[sk] = raw

            # Resolver proveedor_id del Egreso. Regla canonica:
            # Egreso.proveedor_id = ORDEN_PAGO.COD_PROV (a quien efectivamente
            # se le paga; puede ser cesionario en casos UTE/cesion de credito).
            # NO confundir con el emisor de la factura (OPI_COD_PROV) ni con
            # el proveedor de la OC original (SG_OC_COD_PROV) — esos son del
            # Gasto y del Pedido respectivamente, y Paxapos los maneja como
            # entidades distintas linkeadas via Gasto.pedido_id y HABTM.
            # Fallbacks por si COD_PROV de la OP viene NULL en RAFAM (raro).
            remote_prov_id: int | None = None
            for cod_prov in (raw.get("COD_PROV"), raw.get("OPI_COD_PROV"), raw.get("SG_OC_COD_PROV")):
                if cod_prov is None or str(cod_prov).strip() == "":
                    continue
                remote_prov = self._link_store.get_remote_id("proveedores", str(cod_prov).strip())
                if remote_prov:
                    remote_prov_id = int(remote_prov)
                    break

            importe = raw.get("IMPORTE_TOTAL")
            # Validar IMPORTE_TOTAL antes de crear el Egreso. Si es NULL,
            # no parseable o <=0 NO se exporta: en RAFAM esto suele ser una
            # OP de ajuste contable o anulacion (CONFIRMADO=S, estado enviable
            # con importe 0). Si las dejaramos pasar, se crean Egresos en
            # cero vinculados al mismo Gasto, mostrando "varios pagos" para
            # un mismo comprobante (1 con importe, otros en 0).
            if importe is None:
                skipped_importe_invalido["null"] = skipped_importe_invalido.get("null", 0) + 1
                logger.warning(
                    "Migrator [orden_pago] OP %s-%s omitida: IMPORTE_TOTAL es NULL en RAFAM",
                    ejercicio, nro_op,
                )
                continue
            try:
                total = round(float(importe), 2)
            except (TypeError, ValueError):
                skipped_importe_invalido["no_parseable"] = skipped_importe_invalido.get("no_parseable", 0) + 1
                logger.warning(
                    "Migrator [orden_pago] OP %s-%s omitida: IMPORTE_TOTAL %r no parseable",
                    ejercicio, nro_op, importe,
                )
                continue
            if total <= 0:
                skipped_importe_invalido["<=0"] = skipped_importe_invalido.get("<=0", 0) + 1
                logger.warning(
                    "Migrator [orden_pago] OP %s-%s omitida: IMPORTE_TOTAL=%s (probable ajuste contable o anulacion)",
                    ejercicio, nro_op, total,
                )
                continue

            egreso: dict = {
                "identificador_pago": f"RAFAM-OP-{ejercicio}-{nro_op}",
                "total": total,
                "tipo_de_pago_id": self._resolve_tipo_pago_id(raw),
                "estado": 3,
                "fecha": fecha_confirm,
            }

            concepto = raw.get("CONCEPTO") or raw.get("OBSERVACIONES")
            if concepto and str(concepto).strip():
                egreso["observacion"] = str(concepto).strip()[:255]

            grouped[key] = {
                "external_id": {"ejercicio": ejercicio, "nro_op": nro_op},
                "importe_total": total,
                "Egreso": egreso,
            }
            if remote_prov_id is not None:
                grouped[key]["proveedor_id"] = remote_prov_id

            # Guardar IMPORTE_LIQUIDO para importe_neto/neto_transferido
            importe_liquido = raw.get("IMPORTE_LIQUIDO")
            if importe_liquido is not None:
                try:
                    neto = round(float(importe_liquido), 2)
                    if neto >= 0:
                        grouped[key]["_importe_liquido"] = neto
                except (TypeError, ValueError):
                    pass

        # Fetch deducciones por OP individual (ORDEN_PAGO_DEDUC por (EJERCICIO, NRO_OP))
        deducciones_by_op: dict[tuple[int, int], list[dict]] = {}
        if grouped and self._source_repo is not None:
            op_keys_for_deduc = list(grouped.keys())
            result = self._source_repo.fetch_deducciones_for_ops(op_keys_for_deduc)
            if result is not None:
                deducciones_by_op = result

        ordenes_pago = []
        included_cc_keys: list[tuple[str, str, str]] = []
        included_cc_key_set: set[tuple[str, str, str]] = set()
        cc_key_to_pedido_id: dict[tuple[str, str, str], int] = {}
        skipped_no_gasto = 0
        skipped_no_opi = 0
        skipped_no_comprobante = 0
        skipped_no_oc_canonica = 0
        skipped_no_oc_link = 0
        skipped_multiple_oc = 0
        warned_facturas_exceed_oc = 0
        for key, op in grouped.items():
            cc_nros = grouped_cc_nros.get(key, [])
            if not cc_nros:
                skipped_no_gasto += 1
                if key not in grouped_has_opi:
                    skipped_no_opi += 1
                    logger.debug(
                        "Migrator [orden_pago] OP %s-%s omitida: sin ORDEN_PAGO_IMPUT",
                        key[0], key[1],
                    )
                else:
                    skipped_no_comprobante += 1
                    logger.debug(
                        "Migrator [orden_pago] OP %s-%s omitida: sin OPI_NRO_COMPROB",
                        key[0], key[1],
                    )
                continue

            # Asignar gasto_nro_comprobante (string o array)
            if len(cc_nros) == 1:
                op["gasto_nro_comprobante"] = cc_nros[0]
            else:
                op["gasto_nro_comprobante"] = cc_nros

            pedido_ids = grouped_pedido_ids.get(key, [])
            if len(pedido_ids) == 1:
                pedido_id = pedido_ids[0]
                op["pedido_id"] = pedido_id
            elif len(pedido_ids) > 1:
                skipped_multiple_oc += 1
                logger.warning(
                    "Migrator [orden_pago] OP %s-%s omitida: multiples OCs/pedido_id recibidos (%s)",
                    key[0], key[1], pedido_ids,
                )
                continue
            else:
                oc_source_keys = grouped_oc_source_keys.get(key, [])
                internal_ids = grouped_pedido_internal_ids.get(key, [])
                if not oc_source_keys:
                    skipped_no_oc_canonica += 1
                    logger.debug(
                        "Migrator [orden_pago] OP %s-%s omitida: sin OC canonica en "
                        "REG_COMP imputado por ORDEN_PAGO_IMPUT (pedido_internal_id candidatos=%s)",
                        key[0], key[1], internal_ids,
                    )
                    continue

                skipped_no_oc_link += 1
                logger.debug(
                    "Migrator [orden_pago] OP %s-%s omitida: sin OC migrada en link_store "
                    "(oc_source_keys=%s, pedido_internal_id candidatos=%s)",
                    key[0], key[1], oc_source_keys, internal_ids,
                )
                continue

            for cc_key in grouped_cc_keys.get(key, []):
                if cc_key not in included_cc_key_set:
                    included_cc_key_set.add(cc_key)
                    included_cc_keys.append(cc_key)
                cc_key_to_pedido_id.setdefault(cc_key, pedido_id)

            # Mapear deducciones (de ORDEN_PAGO_DEDUC por NRO_OP)
            ret_payload = []
            for ded in deducciones_by_op.get(key, []):
                mapped = self._map_deduccion_dict(ded, key[0], key[1])
                if mapped is not None:
                    ret_payload.append(mapped)
            if ret_payload:
                # Validar que la suma de retenciones no supere el total del Egreso.
                # RAFAM puede tener deducciones acumuladas que exceden el importe de
                # la OP individual (dato inconsistente upstream). Paxapos rechaza
                # estas OPs con error, así que las dejamos sin retenciones y logeamos.
                total_egreso = op["Egreso"]["total"]
                suma_retenciones = sum(r["monto_retenido"] for r in ret_payload)
                if suma_retenciones > total_egreso:
                    logger.warning(
                        "Migrator [orden_pago] OP %s-%s: retenciones ($%.2f) superan total ($%.2f). "
                        "Descartando retenciones para evitar rechazo de Paxapos.",
                        key[0], key[1], suma_retenciones, total_egreso,
                    )
                else:
                    op["retenciones"] = ret_payload

            # importe_neto/neto_transferido = IMPORTE_LIQUIDO de RAFAM (si disponible)
            importe_liquido = op.pop("_importe_liquido", None)
            if importe_liquido is not None:
                op["importe_neto"] = importe_liquido
                op["Egreso"]["neto_transferido"] = importe_liquido

            # ── Validación: suma facturas vs total OC ─────────────────────
            # Si la suma de los importes de las facturas imputadas a esta OP
            # supera el total de la OC vinculada, emitir WARNING (dato
            # inconsistente upstream — una OC de $X nunca debería tener
            # facturas que sumen más que $X).
            oc_sks = grouped_oc_source_keys.get(key, [])
            if oc_sks and grouped_cc_keys.get(key):
                suma_facturas = 0.0
                for ck in grouped_cc_keys[key]:
                    cr = cc_raw_by_key.get(ck)
                    if cr and cr.get("CTA_IMPORTE_COMPR") is not None:
                        try:
                            suma_facturas += round(float(cr["CTA_IMPORTE_COMPR"]), 2)
                        except (TypeError, ValueError):
                            pass
                if suma_facturas > 0:
                    for oc_sk in oc_sks:
                        oc_link = self._link_store.get_link("orden_compra", oc_sk)
                        if oc_link and oc_link.get("importe_tot"):
                            try:
                                oc_total = round(float(oc_link["importe_tot"]), 2)
                            except (TypeError, ValueError):
                                continue
                            if suma_facturas > oc_total:
                                warned_facturas_exceed_oc += 1
                                logger.warning(
                                    "Migrator [orden_pago] OP %s-%s: suma facturas ($%.2f) "
                                    "supera total OC ($%.2f). Comprobantes: %s. OC: %s",
                                    key[0], key[1], suma_facturas, oc_total,
                                    cc_nros, oc_sk,
                                )

            ordenes_pago.append(op)

        if skipped_no_gasto:
            logger.warning(
                "Migrator [orden_pago]: %d OPs omitidas sin gasto vinculado "
                "(sin ORDEN_PAGO_IMPUT=%d, sin OPI_NRO_COMPROB=%d)",
                skipped_no_gasto, skipped_no_opi, skipped_no_comprobante,
            )
        if skipped_no_oc_canonica:
            logger.warning(
                "Migrator [orden_pago]: %d OPs omitidas sin OC canonica en RAFAM; "
                "no se crean pagos ni gastos sueltos",
                skipped_no_oc_canonica,
            )
        if skipped_no_oc_link:
            logger.warning(
                "Migrator [orden_pago]: %d OPs omitidas sin OC migrada/linkeada; "
                "no se crean pagos ni gastos sueltos",
                skipped_no_oc_link,
            )
        if skipped_multiple_oc:
            logger.warning(
                "Migrator [orden_pago]: %d OPs omitidas por multiples OCs en un mismo pago; "
                "se requiere mapeo por gasto antes de enviarlas",
                skipped_multiple_oc,
            )
        if warned_facturas_exceed_oc:
            logger.warning(
                "Migrator [orden_pago]: %d OPs con suma de facturas que supera el total de la OC vinculada",
                warned_facturas_exceed_oc,
            )
        if skipped_estado:
            logger.info("Migrator [orden_pago]: OPs omitidas por estado: %s", skipped_estado)
        if skipped_confirmado:
            logger.info("Migrator [orden_pago]: OPs omitidas por CONFIRMADO: %s", skipped_confirmado)
        if skipped_no_fech_confirm:
            logger.info("Migrator [orden_pago]: %d OPs omitidas sin FECH_CONFIRM", skipped_no_fech_confirm)
        if skipped_importe_invalido:
            logger.warning(
                "Migrator [orden_pago]: OPs omitidas por IMPORTE_TOTAL invalido: %s. "
                "Esto evita crear Egresos en $0 que ensucian el panel de pagos.",
                skipped_importe_invalido,
            )
        if skipped_existing_keys:
            logger.info("Migrator [orden_pago]: %d OPs omitidas por link local existente", len(skipped_existing_keys))
        if self._retencion_skipped_no_catalog:
            logger.warning(
                "Migrator [orden_pago]: %d retenciones omitidas porque tipos_retencion lookup esta vacio. "
                "Cargar account_tipo_impuestos en el tenant Paxapos.",
                self._retencion_skipped_no_catalog,
            )
            self._retencion_skipped_no_catalog = 0
        if self._retencion_skipped_no_match:
            logger.warning(
                "Migrator [orden_pago]: retenciones omitidas sin match en lookup: %s",
                self._retencion_skipped_no_match,
            )
            self._retencion_skipped_no_match = {}

        if not ordenes_pago:
            logger.info("Migrator [orden_pago]: lote vacío luego del mapeo")
            return

        # Construir gastos[] con datos completos desde CTA_COMPROB para que
        # Paxapos pueda crear el Gasto si aún no existe (auto_create_gasto del
        # endpoint solo arma un stub mínimo). El upsert en Paxapos dedup por
        # proveedor_id + factura_nro + punto_de_venta, así que enviar gastos
        # ya migrados es no-op.
        gastos_payload: list[dict] = []
        seen_dedup_keys: set[tuple] = set()
        skipped_gastos_incomplete = 0
        for cc_key in included_cc_keys:
            cc_raw = cc_raw_by_key.get(cc_key)
            if cc_raw is None:
                continue
            cc_raw_for_gasto = dict(cc_raw)
            pedido_id = cc_key_to_pedido_id.get(cc_key)
            if pedido_id is not None:
                cc_raw_for_gasto["_PAXAPOS_PEDIDO_ID"] = pedido_id
            gasto, dedup_key = self._build_gasto_from_op_row(cc_raw_for_gasto)
            if gasto is None:
                skipped_gastos_incomplete += 1
                continue
            if dedup_key in seen_dedup_keys:
                continue
            seen_dedup_keys.add(dedup_key)
            gastos_payload.append(gasto)
        if skipped_gastos_incomplete:
            logger.info(
                "Migrator [orden_pago]: %d comprobantes sin datos suficientes para auto-crear gasto",
                skipped_gastos_incomplete,
            )

        payload = {
            "dry_run": self._dry_run,
            "options": self._payload_options(),
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": gastos_payload,
            "ordenes_pago": ordenes_pago,
        }

        url = self._import_url
        logger.debug(
            "Migrator request [orden_pago] POST %s dry_run=%s ops=%d omitidas=%d gastos=%d",
            url, self._dry_run, len(ordenes_pago), skipped_no_gasto, len(gastos_payload),
        )
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("ordenes_pago", {}) if isinstance(stats, dict) else {}
        ok_count = section_stats.get("ok", 0)
        error_count = section_stats.get("error", 0)

        self._persist_links("orden_pago", parsed, raw_by_source_key)
        self._raise_on_migrator_errors(parsed)

        # ── Marcar OCs asociadas con has_op ───────────────────────────────
        # Para cada OP enviada con éxito, flaggear sus OCs vinculadas para que
        # no se eliminen de Paxapos si la OC pasa a estado A en RAFAM.
        op_results = (parsed.get("results", {}) or {}).get("ordenes_pago", [])
        if isinstance(op_results, list):
            marked_oc_sks: set[str] = set()
            for result in op_results:
                if not isinstance(result, dict) or not result.get("success"):
                    continue
                ext = result.get("external_id") or {}
                ej = ext.get("ejercicio")
                nro = ext.get("nro_op")
                if ej is None or nro is None:
                    continue
                op_key = (int(ej), int(nro))
                for oc_sk in grouped_oc_source_keys.get(op_key, []):
                    if oc_sk not in marked_oc_sks:
                        self._link_store.mark_oc_has_op(oc_sk)
                        marked_oc_sks.add(oc_sk)
            if marked_oc_sks:
                logger.info(
                    "Migrator [orden_pago]: %d OCs marcadas con has_op",
                    len(marked_oc_sks),
                )

        # Nota: si hubo OPs omitidas por falta de CC_NRO, se registran como warning
        # arriba pero NO se levanta excepción: las OPs enviables se procesaron OK,
        # y los reintentos se manejan via pending_state_field=N + reprocess_days=30
        # configurado en ENTITY_CONFIGS['orden_pago'].
        logger.info(
            "Migrator OK [orden_pago]: %d ok, %d error, ops=%d, omitidas=%d, dry_run=%s",
            ok_count, error_count, len(ordenes_pago), skipped_no_gasto, self._dry_run,
        )

    def _map_row(self, entity: str, raw: dict) -> dict | None:
        if entity == "proveedores":
            return map_proveedor_migrator_row(raw)
        return None

    def _map_ped_item(self, raw: dict) -> dict | None:
        mercaderia_external_ref = self._mercaderia_external_ref_ped_item(raw)
        if mercaderia_external_ref is None:
            return None

        cantidad = raw.get("CANTIDAD")
        if cantidad is None:
            return None

        item = {
            "mercaderia_external_ref": mercaderia_external_ref,
            "cantidad": float(cantidad),
            "unidad_de_medida_id": self._resolve_unidad_medida_id(raw),
        }

        # precio_unitario: Paxapos lo multiplica por cantidad y guarda el total en PedidoMercaderia.precio.
        if raw.get("COSTO_UNI") is not None:
            item["precio_unitario"] = round(float(raw.get("COSTO_UNI")), 2)

        descripcion = raw.get("DESCRIP_BIE")
        if descripcion:
            item["descripcion"] = str(descripcion)[:255]
            item["observacion"] = str(descripcion)[:255]

        # centro_costo_id via link_store (JURISDICCION de PED_ITEMS → centro_costo Paxapos)
        centro_costo_id = self._resolve_centro_costo_id(raw.get("JURISDICCION"))
        if centro_costo_id is not None:
            item["centro_costo_id"] = centro_costo_id

        return item

    def _mercaderia_external_ref_ped_item(self, raw: dict) -> dict | None:
        ejercicio = self._to_int(raw.get("EJERCICIO"))
        num_ped = self._to_int(raw.get("NUM_PED"))
        orden = self._to_int(raw.get("ORDEN"))
        clase = self._to_int(raw.get("CLASE"))
        tipo = self._to_int(raw.get("TIPO"))
        inciso = self._to_int(raw.get("INCISO"))
        par_prin = self._to_int(raw.get("PAR_PRIN"))
        par_parc = self._to_int(raw.get("PAR_PARC"))

        if ejercicio is None or num_ped is None or orden is None:
            return None

        ref = {
            "source": "rafam",
            "entity": "ped_items",
            "ejercicio": ejercicio,
            "num_ped": num_ped,
            "orden": orden,
        }
        if clase is not None:
            ref["clase"] = clase
        if tipo is not None:
            ref["tipo"] = tipo
        if inciso is not None:
            ref["inciso"] = inciso
        if par_prin is not None:
            ref["par_prin"] = par_prin
        if par_parc is not None:
            ref["par_parc"] = par_parc
        return ref

    def _map_oc_item(self, raw: dict) -> dict | None:
        mercaderia_external_ref = self._mercaderia_external_ref_oc_item(raw)
        if mercaderia_external_ref is None:
            return None

        cantidad = raw.get("CANTIDAD")
        if cantidad is None:
            return None

        item = {
            "cantidad": float(cantidad),
            "unidad_de_medida_id": self._resolve_unidad_medida_id(raw),
        }

        # precio_unitario: Paxapos lo multiplica por cantidad y guarda el total en PedidoMercaderia.precio.
        if raw.get("IMP_UNITARIO") is not None:
            item["precio_unitario"] = round(float(raw.get("IMP_UNITARIO")), 2)

        if raw.get("CANT_RECIB") is not None:
            item["recibida_cantidad"] = float(raw.get("CANT_RECIB"))

        # Enviar como `name` (no `descripcion`) para que Paxapos nombre la mercadería
        # auto-creada correctamente.  `descripcion` no se envía porque se duplica
        # en la UI del item; `name` solo alimenta _buildDeterministicMercaderiaName().
        descripcion = raw.get("DESCRIPCION")
        if descripcion:
            item["name"] = str(descripcion).strip()[:255]

        # centro_costo_id via link_store (JURISDICCION de SOLIC_GASTOS JOIN → centro_costo Paxapos)
        centro_costo_id = self._resolve_centro_costo_id(raw.get("SG_JURISDICCION"))
        if centro_costo_id is not None:
            item["centro_costo_id"] = centro_costo_id

        return item

    def _resolve_tipo_factura_id(self, tipo_doc) -> int | None:
        """Mapea un codigo RAFAM CTA_COMPROB.TIPO al tipo_factura.id de Paxapos.

        Estrategia:
        1) Mapping directo a ID via RAFAM_TIPO_COMPROB_TO_PAXAPOS_ID (fuente de verdad).
        2) Fallback a lookup por codename/name del tenant (por si el catalogo difiere).
        3) Default fijo (RAFAM_TIPO_COMPROB_DEFAULT_ID = 7 "Otros") o env override.
        """
        if tipo_doc:
            from .gateway_mapper import (
                RAFAM_TIPO_COMPROB_TO_PAXAPOS_ID,
                RAFAM_TIPO_COMPROB_DEFAULT_ID,
            )
            code = str(tipo_doc).strip().upper()
            mapped_id = RAFAM_TIPO_COMPROB_TO_PAXAPOS_ID.get(code)
            if mapped_id is not None:
                return mapped_id
            # Fallback: lookup en catalogo del tenant por codename / name
            text = self._normalize_text(tipo_doc)
            by_codename = self._tipos_factura_by_codename.get(text)
            if by_codename and self._to_int(by_codename.get("id")) is not None:
                return int(by_codename.get("id"))
            by_name = self._tipos_factura_by_name.get(text)
            if by_name and self._to_int(by_name.get("id")) is not None:
                return int(by_name.get("id"))
            # Default mapper si nada matchea
            if self._default_tipo_factura_id is not None:
                return self._default_tipo_factura_id
            return RAFAM_TIPO_COMPROB_DEFAULT_ID
        return self._default_tipo_factura_id

    def _resolve_tipo_pago_id(self, raw: dict | None = None) -> int:
        """Mapea ORDEN_PAGO.TIPO_CANCE al tipo_de_pago.id de Paxapos.

        Mapeo via RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_ID; default 1 (Transferencia bancaria).
        """
        if raw:
            from .gateway_mapper import (
                RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_ID,
                RAFAM_TIPO_CANCE_DEFAULT_PAGO_ID,
            )
            tipo_cance = str(raw.get("TIPO_CANCE") or "").strip().upper()
            mapped_id = RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_ID.get(tipo_cance)
            if mapped_id is not None:
                return mapped_id
            return RAFAM_TIPO_CANCE_DEFAULT_PAGO_ID
        return self._default_tipo_pago_id

    def _map_retencion(self, raw: dict, ejercicio: int, nro_op: int) -> dict | None:
        """Mapea una retencion RAFAM cruda (claves RET_*) al formato Paxapos.

        Wrapper conveniente sobre `_map_retencion_dict`: traduce los nombres de
        columna RAFAM (RET_COD_RET / RET_IMPORTE / RET_DESCRIPCION) al dict
        canonico esperado y agrega `tipo` (alias normalizado: ganancias/iibb/
        suss/iva) al payload resultante.
        """
        cod_ret = raw.get("RET_COD_RET") if raw.get("RET_COD_RET") is not None else raw.get("COD_RET")
        importe = raw.get("RET_IMPORTE") if raw.get("RET_IMPORTE") is not None else raw.get("IMPORTE")
        descripcion = raw.get("RET_DESCRIPCION") if raw.get("RET_DESCRIPCION") is not None else raw.get("DESCRIPCION")

        if cod_ret is None or importe is None:
            return None

        ret_dict = {"cod_ret": cod_ret, "importe": importe, "descripcion": descripcion or ""}
        result = self._map_retencion_dict(ret_dict, ejercicio, nro_op)
        if result is None:
            return None

        alias = self._retencion_alias(descripcion or str(cod_ret))
        if alias:
            result["tipo"] = alias
        return result

    def _map_retencion_dict(self, ret: dict, ejercicio: int, nro_op: int) -> dict | None:
        """Mapea una retencion (dict con cod_ret/importe/descripcion) al formato Paxapos.

        Pre-resuelve tipo_impuesto_id contra el catalogo del tenant (lookups.tipos_retencion).
        Si el catalogo esta vacio o no hay match, OMITE la retencion (con contador para warning)
        en vez de mandar al servidor para que falle.
        """
        cod_ret = ret.get("cod_ret")
        importe = ret.get("importe")
        if cod_ret is None or importe is None:
            return None

        cod_text = str(cod_ret).strip()
        if not cod_text:
            return None

        try:
            monto_retenido = float(importe)
        except (TypeError, ValueError):
            return None
        if monto_retenido == 0:
            return None

        descripcion = str(ret.get("descripcion") or "").strip()

        tipo_retencion_id = self._resolve_tipo_retencion_id(cod_text, descripcion)
        if tipo_retencion_id is None:
            # Intentar via alias (ganancias/iibb/suss/iva) → buscar en catalogo
            alias = self._retencion_alias(descripcion or cod_text)
            if alias:
                tipo_retencion_id = self._resolve_tipo_retencion_id_by_alias(alias)

        if tipo_retencion_id is None:
            if not self._tipos_retencion:
                self._retencion_skipped_no_catalog += 1
            else:
                key = descripcion or f"COD_RET={cod_text}"
                self._retencion_skipped_no_match[key] = self._retencion_skipped_no_match.get(key, 0) + 1
            return None

        retencion: dict = {
            "external_id": {
                "ejercicio": ejercicio,
                "nro_op": nro_op,
                "cod_ret": cod_text,
            },
            "monto_retenido": monto_retenido,
            "numero_certificado": f"RAFAM-RET-{ejercicio}-{nro_op}-{cod_text}",
            "tipo_impuesto_id": tipo_retencion_id,
        }

        if descripcion:
            retencion["observacion"] = f"Retencion RAFAM {descripcion} OP {ejercicio}/{nro_op}"

        return retencion

    def _map_deduccion_dict(self, ded: dict, ejercicio: int, nro_op: int) -> dict | None:
        """Mapea una deduccion de ORDEN_PAGO_DEDUC al formato Paxapos retenciones.

        Usa codigo_deduc/importe_reten/descripcion para resolver tipo_impuesto_id.
        """
        codigo_deduc = ded.get("codigo_deduc")
        importe_reten = ded.get("importe_reten")
        if codigo_deduc is None or importe_reten is None:
            return None

        cod_text = str(codigo_deduc).strip()
        if not cod_text:
            return None

        try:
            monto_retenido = float(importe_reten)
        except (TypeError, ValueError):
            return None
        if monto_retenido == 0:
            return None

        descripcion = str(ded.get("descripcion") or "").strip()

        tipo_retencion_id = self._resolve_tipo_retencion_id(cod_text, descripcion)
        if tipo_retencion_id is None:
            alias = self._retencion_alias(descripcion or cod_text)
            if alias:
                tipo_retencion_id = self._resolve_tipo_retencion_id_by_alias(alias)

        if tipo_retencion_id is None:
            if not self._tipos_retencion:
                self._retencion_skipped_no_catalog += 1
            else:
                key = descripcion or f"CODIGO_DEDUC={cod_text}"
                self._retencion_skipped_no_match[key] = self._retencion_skipped_no_match.get(key, 0) + 1
            return None

        retencion: dict = {
            "external_id": {
                "ejercicio": ejercicio,
                "nro_op": nro_op,
                "codigo_deduc": cod_text,
            },
            "monto_retenido": monto_retenido,
            "numero_certificado": f"RAFAM-RET-{ejercicio}-{nro_op}-{cod_text}",
            "tipo_impuesto_id": tipo_retencion_id,
        }

        # Alicuota si está disponible
        alicuota = ded.get("alicuota")
        if alicuota is not None:
            try:
                alicuota_val = float(alicuota)
                if alicuota_val > 0:
                    retencion["alicuota"] = alicuota_val
            except (TypeError, ValueError):
                pass

        # Certificado de deducción
        comprob_deduc = ded.get("comprob_deduc")
        if comprob_deduc is not None and str(comprob_deduc).strip():
            retencion["numero_certificado"] = str(comprob_deduc).strip()

        if descripcion:
            retencion["observacion"] = f"Deduccion RAFAM {descripcion} OP {ejercicio}/{nro_op}"

        return retencion

    def _resolve_tipo_retencion_id_by_alias(self, alias: str) -> int | None:
        """Busca un tipo_impuesto en lookups por alias normalizado (ganancias/iibb/suss/iva).

        Match por name normalizado conteniendo el alias.
        """
        if not alias or not self._tipos_retencion:
            return None
        target_tokens = {
            "ganancias": ("ganancia",),
            "iibb": ("iibb", "ingresos brutos", "ingreso bruto"),
            "suss": ("suss", "seguridad social"),
            "iva": ("iva",),
        }.get(alias, (alias,))

        for tr in self._tipos_retencion:
            name_norm = self._normalize_text(tr.get("name") or "")
            if not name_norm:
                continue
            for tok in target_tokens:
                if self._normalize_text(tok) in name_norm:
                    tid = self._to_int(tr.get("id"))
                    if tid is not None:
                        return tid
        return None

    def _resolve_tipo_retencion_id(self, cod_ret, descripcion) -> int | None:
        cod_text = str(cod_ret).strip() if cod_ret is not None else ""
        if cod_text:
            remote = self._link_store.get_remote_id("tipo_retencion", cod_text)
            if remote and self._to_int(remote) is not None:
                return int(remote)

        for value, index in (
            (cod_text, self._tipos_retencion_by_codigo),
            (cod_text, self._tipos_retencion_by_codename),
            (descripcion, self._tipos_retencion_by_name),
        ):
            text = self._normalize_text(value)
            if not text:
                continue
            row = index.get(text)
            if row and self._to_int(row.get("id")) is not None:
                return int(row.get("id"))
        return None

    def _resolve_centro_costo_id(self, jurisdiccion) -> int | None:
        if jurisdiccion is None:
            return None
        text = str(jurisdiccion).strip()
        if not text:
            return None
        return resolve_centro_costo_id(text)

    @staticmethod
    def _retencion_alias(value) -> str | None:
        text = MigratorExporter._normalize_text(value)
        if not text:
            return None
        if "ganancia" in text:
            return "ganancias"
        if "iibb" in text or ("ingreso" in text and "bruto" in text):
            return "iibb"
        if "suss" in text or "seguridad social" in text or "jubil" in text:
            return "suss"
        if "iva" in text:
            return "iva"
        return None

    @staticmethod
    def _gasto_external_id(ejercicio: int, deleg_solic: int, nro_solic: int) -> dict:
        return {
            "ejercicio": ejercicio,
            "deleg_solic": deleg_solic,
            "nro_solic": nro_solic,
        }

    @staticmethod
    def _gasto_legacy_ref(ejercicio: int, deleg_solic: int, nro_solic: int) -> str:
        return f"SG-{ejercicio}-{deleg_solic}-{nro_solic}"

    def _gasto_ref_from_external_id(self, external_id: dict) -> str:
        if not isinstance(external_id, dict):
            return ""
        rafam_ref = external_id.get("rafam_ref")
        if rafam_ref:
            return str(rafam_ref)
        ejercicio = self._to_int(external_id.get("ejercicio"))
        deleg_solic = self._to_int(external_id.get("deleg_solic"))
        nro_solic = self._to_int(external_id.get("nro_solic"))
        if ejercicio is None or deleg_solic is None or nro_solic is None:
            return ""
        return self._gasto_legacy_ref(ejercicio, deleg_solic, nro_solic)

    def _gasto_external_id_from_ref(self, rafam_ref: str) -> dict | None:
        parts = str(rafam_ref).split("-")
        if len(parts) != 4 or parts[0] != "SG":
            return None
        ejercicio = self._to_int(parts[1])
        deleg_solic = self._to_int(parts[2])
        nro_solic = self._to_int(parts[3])
        if ejercicio is None or deleg_solic is None or nro_solic is None:
            return None
        return self._gasto_external_id(ejercicio, deleg_solic, nro_solic)

    def _gasto_source_keys_from_ref(self, rafam_ref: str) -> list[str]:
        keys = []
        external_id = self._gasto_external_id_from_ref(rafam_ref)
        if external_id is not None:
            keys.append(json.dumps(external_id, sort_keys=True))
        keys.append(json.dumps({"rafam_ref": rafam_ref}, sort_keys=True))
        return keys

    @staticmethod
    def _split_ref_set(value) -> set[str]:
        if not value:
            return set()
        return {part.strip() for part in str(value).split(",") if part.strip()}

    def _get_gasto_remote_id(self, rafam_ref: str) -> str | None:
        for source_key in self._gasto_source_keys_from_ref(rafam_ref):
            remote = self._link_store.get_remote_id("gasto", source_key)
            if remote:
                return remote
        return None

    @staticmethod
    def _format_date_only(value) -> str:
        """Extrae solo YYYY-MM-DD de un string fecha (puede incluir hora)."""
        if not value:
            return ""
        text = str(value).strip()
        if len(text) >= 10:
            date_part = text[:10]
            if len(date_part) == 10 and date_part[4] == "-" and date_part[7] == "-":
                return date_part
        return ""

    @staticmethod
    def _parse_money(value) -> float | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

    def _resolve_unidad_medida_id(self, raw: dict) -> int:
        # Intentar resolver via link_store (si ya se mapeó previamente)
        uni_med = raw.get("UNI_MED")
        if uni_med is not None:
            uni_med_str = str(uni_med).strip()
            if uni_med_str:
                remote = self._link_store.get_remote_id("unidad_medida", uni_med_str)
                if remote and self._to_int(remote) is not None:
                    return int(remote)
        # Default = 5 (Unidad) — id en compras_unidad_de_medidas del tenant.
        from .gateway_mapper import _UM_DEFAULT
        return _UM_DEFAULT



    def _mercaderia_external_ref_oc_item(self, raw: dict) -> dict | None:
        ejercicio = self._to_int(raw.get("EJERCICIO"))
        uni_compra = self._to_int(raw.get("UNI_COMPRA"))
        nro_oc = self._to_int(raw.get("NRO_OC"))
        item_oc = self._to_int(raw.get("ITEM_OC"))

        if ejercicio is None or uni_compra is None or nro_oc is None or item_oc is None:
            return None

        ref = {
            "source": "rafam",
            "entity": "oc_items",
            "ejercicio": ejercicio,
            "uni_compra": uni_compra,
            "nro_oc": nro_oc,
            "item_oc": item_oc,
        }

        deleg_solic = self._to_int(raw.get("DELEG_SOLIC"))
        nro_solic = self._to_int(raw.get("NRO_SOLIC"))
        item_real = self._to_int(raw.get("ITEM_REAL"))
        if deleg_solic is not None:
            ref["deleg_solic"] = deleg_solic
        if nro_solic is not None:
            ref["nro_solic"] = nro_solic
        if item_real is not None:
            ref["item_real"] = item_real
        return ref

    def _track_unresolved_item(self, description, proveedor) -> None:
        desc_key = self._normalize_text(description)
        if not desc_key:
            desc_key = "(sin descripcion)"
        prov_key = str(self._to_int(proveedor)) if self._to_int(proveedor) is not None else "(sin proveedor)"
        key = f"{prov_key}::{desc_key}"
        self._missing_mercaderia_matches[key] = self._missing_mercaderia_matches.get(key, 0) + 1

    def _log_unresolved_summary(self, entity: str) -> None:
        if not self._missing_mercaderia_matches:
            return
        top = sorted(self._missing_mercaderia_matches.items(), key=lambda kv: kv[1], reverse=True)[:10]
        summary = ", ".join(f"{k} x{v}" for k, v in top)
        logger.warning(
            "Migrator [%s] sin match de mercaderia (top 10): %s",
            entity,
            summary,
        )

    @staticmethod
    def _compose_oc_observacion(raw: dict) -> str | None:
        """Return real RAFAM observation or None. Never fabricate a traza string."""
        obs = raw.get("OC_OBSERVACIONES")
        if obs and str(obs).strip():
            return str(obs).strip()[:255]
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Api-Key": self._api_key,
            "X-Tenant-Id": self._tenant,
            "User-Agent": "rafam-sync/1.0",
        }

    def _post_json(self, url: str, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        # Debug opcional: si DUMP_PAYLOAD esta seteado y APP_ENV != prod, vuelca
        # request+response a un archivo. Campos sensibles (cuit, tokens) son
        # enmascarados antes de escribir.
        dump_path = _dump_payload_path()
        if dump_path:
            try:
                serialized = json.dumps(payload, ensure_ascii=False, indent=2)
                redacted = _redact_payload_for_dump(serialized)
                with open(dump_path, "ab") as fh:
                    fh.write(("\n=== POST " + url + " ===\n").encode("utf-8"))
                    fh.write(redacted.encode("utf-8"))
                    fh.write(b"\n")
            except OSError:
                pass
        req = request.Request(url=url, data=data, headers=self._headers(), method="POST")
        ssl_context = None
        if not self._verify_ssl:
            ssl_context = ssl._create_unverified_context()

        try:
            with _http_request_with_retries(req, timeout=self._timeout, ssl_context=ssl_context) as resp:
                status = resp.getcode()
                final_url = resp.geturl()
                content_type = (resp.headers.get("Content-Type") or "").lower()
                body = resp.read().decode("utf-8", errors="replace")

                logger.debug(
                    "Migrator response status=%s content_type=%s final_url=%s",
                    status,
                    content_type,
                    final_url,
                )

                if status < 200 or status >= 300:
                    raise RuntimeError(f"HTTP {status}: {body[:500]}")

                if "json" not in content_type:
                    raise RuntimeError(f"Respuesta no JSON (Content-Type={content_type})")

                parsed = json.loads(body) if body else {}
                if isinstance(parsed, dict) and parsed.get("errors"):
                    logger.debug("Migrator response errors=%s", parsed.get("errors"))
                if dump_path:
                    try:
                        serialized_resp = json.dumps(parsed, ensure_ascii=False, indent=2)
                        redacted_resp = _redact_payload_for_dump(serialized_resp)
                        with open(dump_path, "ab") as fh:
                            fh.write(b"--- RESPONSE ---\n")
                            fh.write(redacted_resp.encode("utf-8"))
                            fh.write(b"\n")
                    except OSError:
                        pass
                return parsed
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"URL error: {exc.reason}") from exc

    @staticmethod
    def _raise_on_migrator_errors(parsed: dict) -> None:
        """
        Procesa la respuesta del migrator y reporta errores parciales.

        Comportamiento por defecto (NO ESTRICTO): los errores parciales por fila
        (validacion, datos invalidos, etc.) NO levantan excepcion. Las filas OK
        del batch ya fueron persistidas; reintentar el batch entero solo
        reprocesaria las filas validas (potencialmente generando duplicados o
        cargando trabajo al backend) y las filas invalidas seguirian fallando.
        Solo logueamos los errores con detalle para que el operador los corrija
        en el origen (ej: CUIT mal cargado en RAFAM).

        Comportamiento ESTRICTO (opt-in via RAFAM_STRICT_PARTIAL_ERRORS=true):
        levanta RuntimeError si hay cualquier error parcial. Util para tests
        o entornos donde se quiere abortar ante el primer error.

        En ambos modos los errores se logean con full detail (errors[] y stats).
        """
        if not isinstance(parsed, dict):
            return

        strict = _env_bool("RAFAM_STRICT_PARTIAL_ERRORS", False)

        has_errors = False
        errors = parsed.get("errors")
        if isinstance(errors, list) and errors:
            # Loguear TODOS los errores (no solo sample) para diagnostico en prod.
            # En general son pocos y vale la pena tener trazabilidad completa.
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
        for section, section_stats in stats.items():
            if not isinstance(section_stats, dict):
                continue
            error_count = section_stats.get("error", 0)
            try:
                error_count = int(error_count)
            except (TypeError, ValueError):
                error_count = 0
            if error_count > 0:
                failed.append(f"{section}={error_count}")

        if failed:
            log_fn = logger.error if strict else logger.warning
            log_fn(
                "Migrator stats: %s fila(s) fallaron pero el batch continuo. "
                "Las filas OK ya fueron persistidas.",
                ", ".join(failed),
            )
            has_errors = True

        if has_errors and strict:
            details = ", ".join(failed) if failed else "ver errors en respuesta"
            raise RuntimeError(f"Migrator devolvio errores parciales: {details}")

    def _persist_links(self, entity: str, parsed: dict, raw_by_source_key: dict[str, dict]) -> None:
        if self._dry_run or not isinstance(parsed, dict):
            return

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
            self._link_store.save_link(
                entity="proveedores",
                source_key=str(source_key),
                remote_id=str(remote_id),
                cuit=cuit,
                cod_estado=cod_estado,
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
    def _source_key(entity: str, raw: dict) -> str | None:
        if entity == "proveedores":
            value = raw.get("COD_PROV")
            return str(value) if value is not None else None
        return None

    @staticmethod
    def _normalize_cuit(value) -> str | None:
        if value is None:
            return None
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        return digits if len(digits) == 11 else None

    @staticmethod
    def _lookup_list(payload: dict, key: str) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
        lookups = payload.get("lookups")
        if isinstance(lookups, dict):
            nested = lookups.get(key)
            if isinstance(nested, list):
                return [v for v in nested if isinstance(v, dict)]
        return []

    @staticmethod
    def _normalize_text(value) -> str:
        if value is None:
            return ""
        text = str(value).strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        compact = "".join(ch if ch.isalnum() else " " for ch in text)
        return " ".join(compact.split())

    @staticmethod
    def _build_single_index(rows: list[dict], field: str) -> dict[str, dict]:
        idx: dict[str, dict] = {}
        for row in rows:
            key = MigratorExporter._normalize_text(row.get(field))
            if not key:
                continue
            idx[key] = row
        return idx

    @staticmethod
    def _to_int(value) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def close(self) -> None:
        self._link_store.close()


# ─── Factory ─────────────────────────────────────────────────────────────────

def build_exporter(mode: str, force_update: bool = False, dry_run: bool = False) -> BaseExporter:
    """
    mode: 'csv' | 'noop' | 'gateway'
    """
    if mode == "csv":
        return CsvExporter()
    if mode == "noop":
        return NoopExporter()
    if mode == "gateway":
        return GatewayExporter(force_update=force_update)
    if mode == "migrator":
        return MigratorExporter(dry_run=dry_run)
    raise ValueError(f"Modo de exportación desconocido: '{mode}'. Opciones: csv, noop, gateway, migrator")


def fetch_migrator_spec() -> dict:
    return _fetch_migrator_json(endpoint_env="PAXAPOS_RAFAM_SPEC_PATH", default_endpoint="rafam/migracion/spec.json")


def fetch_migrator_lookups(only: list[str] | None = None) -> dict:
    filtered = [item.strip() for item in (only or []) if item and item.strip()]

    # Si no se especifica seccion, intentamos el endpoint completo primero.
    if not filtered:
        try:
            return _fetch_migrator_json(
                endpoint_env="PAXAPOS_RAFAM_LOOKUPS_PATH",
                default_endpoint="rafam/migracion/lookups.json",
            )
        except Exception:
            # Fallback robusto: consultar por seccion para evitar que una seccion rota
            # bloquee todas las demas.
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

    # Si hay una sola seccion, mantenemos comportamiento estricto.
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
    base_url = _paxapos_url()
    tenant = _paxapos_tenant()

    api_key = os.getenv("PAXAPOS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Falta PAXAPOS_API_KEY en .env para consultar migrator")

    timeout = int(os.getenv("PAXAPOS_TIMEOUT_SECONDS", "20"))
    verify_ssl = _env_bool("PAXAPOS_VERIFY_SSL", default="true")
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
        ssl_context = ssl._create_unverified_context()

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
    """Lee env var como bool. default puede ser str (ej: 'true') o bool."""
    if isinstance(default, bool):
        default = "true" if default else "false"
    value = os.getenv(name, default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _paxapos_url() -> str:
    base_url = os.getenv("PAXAPOS_URL", "").strip().rstrip("/")
    if not base_url:
        raise ValueError("Falta PAXAPOS_URL en .env para destino Paxapos")
    return base_url


def _paxapos_tenant() -> str:
    tenant = os.getenv("PAXAPOS_TENANT", "").strip().strip("/")
    if not tenant:
        raise ValueError("Falta PAXAPOS_TENANT en .env para destino Paxapos")
    return tenant


def _migrator_endpoint(endpoint_env: str, default_endpoint: str) -> str:
    endpoint = os.getenv(endpoint_env, default_endpoint).strip()
    parsed = parse.urlparse(endpoint)
    if parsed.scheme or parsed.netloc:
        raise ValueError(
            f"{endpoint_env} debe ser un path relativo; configurar host en PAXAPOS_URL y tenant en PAXAPOS_TENANT"
        )
    endpoint = endpoint.strip("/")
    if not endpoint:
        raise ValueError(f"{endpoint_env} no puede estar vacío")
    return endpoint


def _build_migrator_url(base_url: str, tenant: str, endpoint: str) -> str:
    return f"{base_url.rstrip('/')}/{tenant.strip('/')}/{endpoint.strip('/')}"
