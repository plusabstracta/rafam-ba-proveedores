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
import ssl
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import IO
from urllib import parse
from urllib import error, request

from .entity_link_store import EntityLinkStore
from .gateway_mapper import map_proveedor_migrator_row, map_proveedor_row

logger = logging.getLogger(__name__)


class AlreadyExistsError(Exception):
    """Raised when remote API reports record already exists (idempotent case)."""

    def __init__(self, message: str, parsed: dict | None = None):
        super().__init__(message)
        self.parsed = parsed or {}


class BaseExporter(ABC):
    @abstractmethod
    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        """Procesa un lote de filas para la entidad dada."""

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
        self._base_url = os.getenv("GATEWAY_URL", "").rstrip("/")
        if not self._base_url:
            raise ValueError("Falta GATEWAY_URL en .env para modo gateway")

        self._tenant = os.getenv("GATEWAY_TENANT", "").strip()
        if not self._tenant:
            raise ValueError("Falta GATEWAY_TENANT en .env para modo gateway")

        self._app_env = os.getenv("APP_ENV", "dev").strip().lower()
        self._timeout = int(os.getenv("GATEWAY_TIMEOUT_SECONDS", "20"))
        self._verify_ssl = os.getenv("GATEWAY_VERIFY_SSL", "true").strip().lower() in {"1", "true", "yes", "on"}
        self._jwt = os.getenv("GATEWAY_JWT", "").strip()
        if not self._jwt:
            raise ValueError("Falta GATEWAY_JWT en .env para modo gateway")

        self._entity_endpoints = {
            "proveedores": os.getenv("GATEWAY_ENDPOINT_PROVEEDORES", "account/proveedores.json"),
        }
        self._entity_update_endpoints = {
            "proveedores": os.getenv("GATEWAY_ENDPOINT_PROVEEDORES_UPDATE", "account/proveedores/edit/{id}.json"),
        }
        self._entity_lookup_endpoints = {
            "proveedores": os.getenv("GATEWAY_LOOKUP_PROVEEDORES", "account/proveedores/buscar.json"),
        }
        self._entity_lookup_index_endpoints = {
            "proveedores": os.getenv("GATEWAY_LOOKUP_PROVEEDORES_INDEX", "account/proveedores/index.json"),
        }
        self._lookup_proveedores_enabled = True
        self._force_update = force_update
        self._link_store = EntityLinkStore()

        if not self._verify_ssl:
            logger.warning("GATEWAY_VERIFY_SSL=false: SSL certificate verification deshabilitada para gateway")

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
            with request.urlopen(req, timeout=self._timeout, context=ssl_context) as resp:
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

        with request.urlopen(req, timeout=self._timeout, context=ssl_context) as resp:
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
        self._base_url = os.getenv("MIGRATOR_BASE_URL", "").rstrip("/")
        if not self._base_url:
            raise ValueError("Falta MIGRATOR_BASE_URL en .env para modo migrator")

        self._tenant = os.getenv("MIGRATOR_TENANT", "").strip()
        if not self._tenant:
            raise ValueError("Falta MIGRATOR_TENANT en .env para modo migrator")

        self._api_key = os.getenv("MIGRATOR_API_KEY", "").strip()
        if not self._api_key:
            raise ValueError("Falta MIGRATOR_API_KEY en .env para modo migrator")

        self._timeout = int(os.getenv("MIGRATOR_TIMEOUT_SECONDS", os.getenv("GATEWAY_TIMEOUT_SECONDS", "20")))
        self._verify_ssl = os.getenv("MIGRATOR_VERIFY_SSL", os.getenv("GATEWAY_VERIFY_SSL", "true")).strip().lower() in {"1", "true", "yes", "on"}
        self._import_endpoint = os.getenv("MIGRATOR_IMPORT_ENDPOINT", "rafam/migracion/importar.json").strip().strip("/")
        self._dry_run = dry_run
        self._link_store = EntityLinkStore()
        self._lookup_payload = fetch_migrator_lookups(["unidades_de_medida", "tipos_factura", "tipos_de_pago"])
        self._unidades = self._lookup_list(self._lookup_payload, "unidades_de_medida")
        self._unidades_by_name = self._build_single_index(self._unidades, "name")
        self._default_unidad_id = self._to_int(os.getenv("MIGRATOR_DEFAULT_UNIDAD_ID")) or 1
        self._tipos_factura = self._lookup_list(self._lookup_payload, "tipos_factura")
        self._tipos_factura_by_codename = self._build_single_index(self._tipos_factura, "codename")
        self._tipos_factura_by_name = self._build_single_index(self._tipos_factura, "name")
        self._default_tipo_factura_id = self._to_int(os.getenv("MIGRATOR_DEFAULT_TIPO_FACTURA_ID"))
        self._tipos_de_pago = self._lookup_list(self._lookup_payload, "tipos_de_pago")
        self._tipos_de_pago_by_name = self._build_single_index(self._tipos_de_pago, "name")
        self._default_tipo_pago_id = self._to_int(os.getenv("MIGRATOR_DEFAULT_TIPO_PAGO_ID")) or 1
        self._missing_mercaderia_matches: dict[str, int] = {}

        if not self._verify_ssl:
            logger.warning("MIGRATOR_VERIFY_SSL=false: SSL certificate verification deshabilitada para migrator")
        if isinstance(self._lookup_payload, dict) and self._lookup_payload.get("_partial_errors"):
            logger.warning("Migrator lookups parciales: %s", self._lookup_payload.get("_partial_errors"))

    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        if entity == "jurisdicciones":
            return self._write_batch_jurisdicciones(columns, rows)

        if entity == "proveedores":
            return self._write_batch_proveedores(columns, rows)

        if entity == "ped_items":
            return self._write_batch_ped_items(columns, rows)

        if entity == "oc_items":
            return self._write_batch_oc_items(columns, rows)

        if entity == "solic_gastos":
            return self._write_batch_solic_gastos(columns, rows)

        if entity == "orden_pago":
            return self._write_batch_orden_pago(columns, rows)

        if entity == "pedidos":
            logger.warning(
                "Migrator [%s]: entidad recibida sin items. Para migrar solicitudes usa 'ped_items' (genera pedidos con items).",
                entity,
            )
            return

        raise ValueError("Modo migrator soporta por ahora: jurisdicciones, proveedores, ped_items, oc_items, solic_gastos, orden_pago")

    def _write_batch_jurisdicciones(self, columns: list[str], rows: list[tuple]) -> None:
        rubros = []
        clasificaciones = []

        for row in rows:
            raw = dict(zip(columns, row))
            jurisdiccion = raw.get("JURISDICCION")
            if not jurisdiccion:
                continue
            jurisdiccion = str(jurisdiccion).strip()
            if not jurisdiccion:
                continue

            denominacion = str(raw.get("DENOMINACION") or "").strip() or jurisdiccion
            external_id = {"jurisdiccion": jurisdiccion}

            rubros.append({
                "external_id": external_id,
                "Rubro": {"name": denominacion},
            })
            clasificaciones.append({
                "external_id": external_id,
                "Clasificacion": {"name": denominacion, "parent_id": None},
            })

        if not rubros:
            logger.info("Migrator [jurisdicciones]: lote vacío luego del mapeo")
            return

        payload = {
            "dry_run": self._dry_run,
            "options": {
                "upsert": True,
                "atomic": False,
                "fail_fast": False,
                "send_oc_mail": False,
                "strict_mail": False,
            },
            "rubros": rubros,
            "clasificaciones": clasificaciones,
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": [],
            "ordenes_pago": [],
        }

        url = f"{self._base_url}/{self._import_endpoint}"
        logger.debug(
            "Migrator request [jurisdicciones] POST %s dry_run=%s rubros=%d clasificaciones=%d",
            url, self._dry_run, len(rubros), len(clasificaciones),
        )
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        rubros_stats = stats.get("rubros", {}) if isinstance(stats, dict) else {}
        clas_stats = stats.get("clasificaciones", {}) if isinstance(stats, dict) else {}

        logger.info(
            "Migrator OK [jurisdicciones]: rubros=%d/%d ok, clasificaciones=%d/%d ok, dry_run=%s",
            rubros_stats.get("ok", 0), len(rubros),
            clas_stats.get("ok", 0), len(clasificaciones),
            self._dry_run,
        )
        self._persist_links("jurisdicciones", parsed, {})

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
            "options": {
                "upsert": True,
                "atomic": False,
                "fail_fast": False,
                "send_oc_mail": False,
                "strict_mail": False,
            },
            "proveedores": proveedores,
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": [],
            "ordenes_pago": [],
        }

        url = f"{self._base_url}/{self._import_endpoint}"
        logger.debug("Migrator request [proveedores] POST %s dry_run=%s items=%d", url, self._dry_run, len(proveedores))
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("proveedores", {}) if isinstance(stats, dict) else {}
        ok_count = section_stats.get("ok", 0)
        error_count = section_stats.get("error", 0)

        self._persist_links("proveedores", parsed, raw_by_source_key)
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
            "options": {
                "upsert": True,
                "atomic": False,
                "fail_fast": False,
                "send_oc_mail": False,
                "strict_mail": False,
            },
            "proveedores": [],
            "pedidos": pedidos,
            "ordenes_compra": [],
            "gastos": [],
            "ordenes_pago": [],
        }

        url = f"{self._base_url}/{self._import_endpoint}"
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

        logger.info(
            "Migrator OK [ped_items->pedidos]: %d ok, %d error, pedidos=%d, items_omitidos=%d, dry_run=%s",
            ok_count,
            error_count,
            len(pedidos),
            unresolved_items,
            self._dry_run,
        )
        self._persist_links("ped_items", parsed, {})
        self._log_unresolved_summary("ped_items")

    def _write_batch_oc_items(self, columns: list[str], rows: list[tuple]) -> None:
        grouped: dict[tuple[int, int, int], dict] = {}
        unresolved_items = 0

        for row in rows:
            raw = dict(zip(columns, row))

            ejercicio = self._to_int(raw.get("EJERCICIO"))
            uni_compra = self._to_int(raw.get("UNI_COMPRA"))
            nro_oc = self._to_int(raw.get("NRO_OC"))
            if ejercicio is None or uni_compra is None or nro_oc is None:
                continue

            key = (ejercicio, uni_compra, nro_oc)
            if key not in grouped:
                pedido = {
                    "internal_id": f"rafam-oc-{ejercicio}-{uni_compra}-{nro_oc}",
                    "tipo": "orden_compra",
                    "observacion": self._compose_oc_observacion(raw, ejercicio, uni_compra, nro_oc),
                }
                # Resolver proveedor_id via link_store (RAFAM COD_PROV → Paxapos id)
                cod_prov = raw.get("COD_PROV")
                if cod_prov is not None:
                    remote_prov = self._link_store.get_remote_id("proveedores", str(cod_prov))
                    if remote_prov:
                        pedido["proveedor_id"] = int(remote_prov)
                    else:
                        logger.debug(
                            "Migrator [oc_items] OC %s-%s-%s: proveedor COD_PROV=%s sin link remoto",
                            ejercicio, uni_compra, nro_oc, cod_prov,
                        )

                grouped[key] = {
                    "external_id": {
                        "ejercicio": ejercicio,
                        "uni_compra": uni_compra,
                        "nro_oc": nro_oc,
                    },
                    "Pedido": pedido,
                    "items": [],
                }

            item = self._map_oc_item(raw)
            if item is None:
                unresolved_items += 1
                self._track_unresolved_item(raw.get("DESCRIPCION"), raw.get("COD_PROV"))
                continue
            grouped[key]["items"].append(item)

        ordenes_compra = [p for p in grouped.values() if p["items"]]
        if not ordenes_compra:
            msg = f"Migrator [oc_items]: lote sin items resolubles (omitidos={unresolved_items})"
            if self._dry_run:
                logger.warning(msg)
                return
            raise RuntimeError(msg)

        payload = {
            "dry_run": self._dry_run,
            "options": {
                "upsert": True,
                "atomic": False,
                "fail_fast": False,
                "send_oc_mail": False,
                "strict_mail": False,
            },
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": ordenes_compra,
            "gastos": [],
            "ordenes_pago": [],
        }

        url = f"{self._base_url}/{self._import_endpoint}"
        logger.debug(
            "Migrator request [oc_items] POST %s dry_run=%s ocs=%d items_omitidos=%d",
            url,
            self._dry_run,
            len(ordenes_compra),
            unresolved_items,
        )
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("ordenes_compra", {}) if isinstance(stats, dict) else {}
        ok_count = section_stats.get("ok", 0)
        error_count = section_stats.get("error", 0)

        logger.info(
            "Migrator OK [oc_items->ordenes_compra]: %d ok, %d error, ocs=%d, items_omitidos=%d, dry_run=%s",
            ok_count,
            error_count,
            len(ordenes_compra),
            unresolved_items,
            self._dry_run,
        )
        self._persist_links("oc_items", parsed, {})
        self._log_unresolved_summary("oc_items")

    def _write_batch_solic_gastos(self, columns: list[str], rows: list[tuple]) -> None:
        gastos = []
        for row in rows:
            raw = dict(zip(columns, row))
            gasto = self._map_solic_gasto(raw)
            if gasto is None:
                continue
            gastos.append(gasto)

        if not gastos:
            logger.info("Migrator [solic_gastos]: lote vacío luego del mapeo")
            return

        payload = {
            "dry_run": self._dry_run,
            "options": {
                "upsert": True,
                "atomic": False,
                "fail_fast": False,
                "send_oc_mail": False,
                "strict_mail": False,
            },
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": gastos,
            "ordenes_pago": [],
        }

        url = f"{self._base_url}/{self._import_endpoint}"
        logger.debug(
            "Migrator request [solic_gastos] POST %s dry_run=%s gastos=%d",
            url, self._dry_run, len(gastos),
        )
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("gastos", {}) if isinstance(stats, dict) else {}
        ok_count = section_stats.get("ok", 0)
        error_count = section_stats.get("error", 0)

        logger.info(
            "Migrator OK [solic_gastos->gastos]: %d ok, %d error, gastos=%d, dry_run=%s",
            ok_count, error_count, len(gastos), self._dry_run,
        )
        self._persist_links("solic_gastos", parsed, {})

    def _map_solic_gasto(self, raw: dict) -> dict | None:
        ejercicio = self._to_int(raw.get("EJERCICIO"))
        deleg_solic = self._to_int(raw.get("DELEG_SOLIC"))
        nro_solic = self._to_int(raw.get("NRO_SOLIC"))
        if ejercicio is None or deleg_solic is None or nro_solic is None:
            return None

        importe_str = raw.get("IMPORTE_TOT")
        if importe_str is None:
            return None
        try:
            importe_total = float(importe_str)
        except (TypeError, ValueError):
            return None

        fecha_raw = raw.get("FECH_SOLIC")
        fecha = self._format_date_only(fecha_raw)
        if not fecha:
            return None

        # Excluir anuladas
        if str(raw.get("ESTADO_SOLIC", "")).strip().upper() == "A":
            return None

        rafam_ref = f"SG-{ejercicio}-{deleg_solic}-{nro_solic}"
        gasto_data: dict = {
            "fecha": fecha,
            "importe_total": importe_total,
            "importe_neto": importe_total,  # RAFAM no discrimina IVA
            "punto_de_venta": "RAFAM",
        }

        tipo_factura_id = self._resolve_tipo_factura_id(raw.get("TIPO_DOC"))
        if tipo_factura_id is not None:
            gasto_data["tipo_factura_id"] = tipo_factura_id

        nro_doc = raw.get("NRO_DOC")
        if nro_doc and str(nro_doc).strip() not in ("0", "", "None"):
            gasto_data["factura_nro"] = str(nro_doc).strip().zfill(8)

        # clasificacion_id via EntityLinkStore (requiere haber sincronizado jurisdicciones)
        jurisdiccion = raw.get("JURISDICCION")
        if jurisdiccion is not None:
            cls_key = json.dumps({"jurisdiccion": str(jurisdiccion)}, sort_keys=True)
            cls_link = self._link_store.get_remote_id("clasificacion", cls_key)
            if cls_link:
                gasto_data["clasificacion_id"] = int(cls_link)

        # fecha_vencimiento: FECH_NECESIDAD con fallback a FECH_ENTREGA
        fech_venc = (
            self._format_date_only(raw.get("FECH_NECESIDAD"))
            or self._format_date_only(raw.get("FECH_ENTREGA"))
        )
        if fech_venc:
            gasto_data["fecha_vencimiento"] = fech_venc

        # proveedor_id via EntityLinkStore (COD_PROV traído por LEFT JOIN a ORDEN_PAGO)
        cod_prov = raw.get("OP_COD_PROV")
        if cod_prov is not None:
            remote_prov = self._link_store.get_remote_id("proveedores", str(int(cod_prov)))
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
            "external_id": {"rafam_ref": rafam_ref},
            "Gasto": gasto_data,
        }

    def _write_batch_orden_pago(self, columns: list[str], rows: list[tuple]) -> None:
        # Agrupa por (EJERCICIO, NRO_OP) y acumula las refs de gastos del LEFT JOIN
        grouped: dict[tuple[int, int], dict] = {}
        grouped_gasto_refs: dict[tuple[int, int], list[str]] = {}

        for row in rows:
            raw = dict(zip(columns, row))
            ejercicio = self._to_int(raw.get("EJERCICIO"))
            nro_op = self._to_int(raw.get("NRO_OP"))
            if ejercicio is None or nro_op is None:
                continue

            key = (ejercicio, nro_op)

            # Recolectar ref de gasto desde columnas del LEFT JOIN
            sg_deleg = self._to_int(raw.get("SG_DELEG_SOLIC"))
            sg_nro = self._to_int(raw.get("SG_NRO_SOLIC"))
            if sg_deleg is not None and sg_nro is not None:
                rafam_ref = f"SG-{ejercicio}-{sg_deleg}-{sg_nro}"
                refs = grouped_gasto_refs.setdefault(key, [])
                if rafam_ref not in refs:
                    refs.append(rafam_ref)

            if key in grouped:
                continue

            estado = str(raw.get("ESTADO_OP", "")).strip().upper()
            if estado == "A":  # Anulada: omitir
                continue

            importe = raw.get("IMPORTE_TOTAL")
            try:
                total = float(importe) if importe is not None else 0.0
            except (TypeError, ValueError):
                total = 0.0

            egreso: dict = {
                "identificador_pago": f"RAFAM-OP-{ejercicio}-{nro_op}",
                "total": total,
                "tipo_de_pago_id": self._resolve_tipo_pago_id(),
                "estado": 3 if estado == "C" else 0,
            }

            # Solo marcar como pagada si está confirmada
            if estado == "C":
                fecha = self._format_date_only(raw.get("FECH_CONFIRM") or "") \
                    or self._format_date_only(raw.get("FECH_OP") or "")
                if fecha:
                    egreso["fecha"] = fecha

            concepto = raw.get("CONCEPTO") or raw.get("OBSERVACIONES")
            if concepto and str(concepto).strip():
                egreso["observacion"] = str(concepto).strip()[:255]

            grouped[key] = {
                "external_id": {"ejercicio": ejercicio, "nro_op": nro_op},
                "Egreso": egreso,
            }

        ordenes_pago = []
        skipped_no_gasto = 0
        for key, op in grouped.items():
            gasto_refs = grouped_gasto_refs.get(key, [])
            if not gasto_refs:
                skipped_no_gasto += 1
                logger.debug(
                    "Migrator [orden_pago] OP %s-%s omitida: sin gasto vinculado (verificar NRO_CANCE)",
                    key[0], key[1],
                )
                continue
            # Resolver gasto_ids via link_store (RAFAM rafam_ref → Paxapos gasto id)
            gasto_ids = []
            unresolved_refs = []
            for ref in gasto_refs:
                gasto_key = json.dumps({"rafam_ref": ref}, sort_keys=True)
                remote_gasto = self._link_store.get_remote_id("gasto", gasto_key)
                if remote_gasto:
                    gasto_ids.append(int(remote_gasto))
                else:
                    unresolved_refs.append(ref)

            if not gasto_ids:
                skipped_no_gasto += 1
                logger.debug(
                    "Migrator [orden_pago] OP %s-%s: gastos sin link remoto: %s",
                    key[0], key[1], unresolved_refs,
                )
                continue

            if unresolved_refs:
                logger.warning(
                    "Migrator [orden_pago] OP %s-%s: %d/%d gastos sin link remoto: %s",
                    key[0], key[1], len(unresolved_refs), len(gasto_refs), unresolved_refs,
                )

            op["gasto_ids"] = gasto_ids
            ordenes_pago.append(op)

        if skipped_no_gasto:
            logger.warning(
                "Migrator [orden_pago]: %d OPs omitidas por no tener gasto vinculado vía NRO_CANCE",
                skipped_no_gasto,
            )

        if not ordenes_pago:
            logger.info("Migrator [orden_pago]: lote vacío luego del mapeo")
            return

        payload = {
            "dry_run": self._dry_run,
            "options": {
                "upsert": True,
                "atomic": False,
                "fail_fast": False,
                "send_oc_mail": False,
                "strict_mail": False,
            },
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": [],
            "ordenes_pago": ordenes_pago,
        }

        url = f"{self._base_url}/{self._import_endpoint}"
        logger.debug(
            "Migrator request [orden_pago] POST %s dry_run=%s ops=%d omitidas=%d",
            url, self._dry_run, len(ordenes_pago), skipped_no_gasto,
        )
        parsed = self._post_json(url, payload)

        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("ordenes_pago", {}) if isinstance(stats, dict) else {}
        ok_count = section_stats.get("ok", 0)
        error_count = section_stats.get("error", 0)

        logger.info(
            "Migrator OK [orden_pago]: %d ok, %d error, ops=%d, omitidas=%d, dry_run=%s",
            ok_count, error_count, len(ordenes_pago), skipped_no_gasto, self._dry_run,
        )
        self._persist_links("orden_pago", parsed, {})

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

        if raw.get("COSTO_UNI") is not None:
            item["precio"] = float(raw.get("COSTO_UNI"))

        descripcion = raw.get("DESCRIP_BIE")
        if descripcion:
            item["descripcion"] = str(descripcion)[:255]
            item["observacion"] = str(descripcion)[:255]

        # rubro_id via link_store (JURISDICCION de PED_ITEMS → rubro Paxapos)
        rubro_id = self._resolve_rubro_id(raw)
        if rubro_id is not None:
            item["rubro_id"] = rubro_id

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
            "mercaderia_external_ref": mercaderia_external_ref,
            "cantidad": float(cantidad),
            "unidad_de_medida_id": self._resolve_unidad_medida_id(raw),
        }

        if raw.get("IMP_UNITARIO") is not None:
            item["precio"] = float(raw.get("IMP_UNITARIO"))

        if raw.get("CANT_RECIB") is not None:
            item["recibida_cantidad"] = float(raw.get("CANT_RECIB"))

        descripcion = raw.get("DESCRIPCION")
        if descripcion:
            item["descripcion"] = str(descripcion)[:255]
            item["observacion"] = str(descripcion)[:255]

        # rubro_id via link_store (JURISDICCION de SOLIC_GASTOS JOIN → rubro Paxapos)
        rubro_id = self._resolve_rubro_id(raw, jurisdiccion_key="SG_JURISDICCION")
        if rubro_id is not None:
            item["rubro_id"] = rubro_id

        return item

    def _resolve_tipo_factura_id(self, tipo_doc) -> int | None:
        if tipo_doc:
            text = self._normalize_text(tipo_doc)
            by_codename = self._tipos_factura_by_codename.get(text)
            if by_codename and self._to_int(by_codename.get("id")) is not None:
                return int(by_codename.get("id"))
            by_name = self._tipos_factura_by_name.get(text)
            if by_name and self._to_int(by_name.get("id")) is not None:
                return int(by_name.get("id"))
        return self._default_tipo_factura_id

    def _resolve_tipo_pago_id(self) -> int:
        return self._default_tipo_pago_id

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

    def _resolve_unidad_medida_id(self, raw: dict) -> int:
        value = raw.get("UNI_MED")
        text = self._normalize_text(value)
        if text:
            by_name = self._unidades_by_name.get(text)
            if by_name and self._to_int(by_name.get("id")) is not None:
                return int(by_name.get("id"))
        return self._default_unidad_id

    def _resolve_rubro_id(self, raw: dict, jurisdiccion_key: str = "JURISDICCION") -> int | None:
        """Resuelve rubro_id desde JURISDICCION via entity_link_store."""
        jurisdiccion = raw.get(jurisdiccion_key)
        if jurisdiccion is None:
            return None
        rubro_key = json.dumps({"jurisdiccion": str(jurisdiccion)}, sort_keys=True)
        remote = self._link_store.get_remote_id("rubro", rubro_key)
        if remote:
            return int(remote)
        return None

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
    def _compose_oc_observacion(raw: dict, ejercicio: int, uni_compra: int, nro_oc: int) -> str:
        obs = raw.get("OC_OBSERVACIONES")
        if obs:
            return str(obs)[:255]
        return f"Migrado RAFAM OC {ejercicio}-{uni_compra}-{nro_oc}"

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
        req = request.Request(url=url, data=data, headers=self._headers(), method="POST")
        ssl_context = None
        if not self._verify_ssl:
            ssl_context = ssl._create_unverified_context()

        try:
            with request.urlopen(req, timeout=self._timeout, context=ssl_context) as resp:
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
                return parsed
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"URL error: {exc.reason}") from exc

    def _persist_links(self, entity: str, parsed: dict, raw_by_source_key: dict[str, dict]) -> None:
        if self._dry_run or not isinstance(parsed, dict):
            return

        results = parsed.get("results", {})
        if not isinstance(results, dict):
            return

        if entity == "proveedores":
            self._persist_links_proveedores(results, raw_by_source_key)
        elif entity == "jurisdicciones":
            self._persist_links_jurisdicciones(results)
        elif entity == "ped_items":
            self._persist_links_section(results, "pedidos", "pedido", ["ejercicio", "num_ped"])
        elif entity == "oc_items":
            self._persist_links_section(results, "ordenes_compra", "orden_compra", ["ejercicio", "uni_compra", "nro_oc"])
        elif entity == "solic_gastos":
            self._persist_links_section(results, "gastos", "gasto", None)
        elif entity == "orden_pago":
            self._persist_links_section(results, "ordenes_pago", "orden_pago", ["ejercicio", "nro_op"])

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
            self._link_store.save_link(
                entity="proveedores",
                source_key=str(source_key),
                remote_id=str(remote_id),
                cuit=cuit,
            )

    def _persist_links_jurisdicciones(self, results: dict) -> None:
        """Persiste entity_links para rubros y clasificaciones desde la respuesta de importar.json."""
        rubros = results.get("rubros", [])
        if isinstance(rubros, list):
            for r in rubros:
                if not isinstance(r, dict) or not r.get("success"):
                    continue
                external_id = r.get("external_id") or {}
                if not isinstance(external_id, dict):
                    continue
                jurisdiccion = external_id.get("jurisdiccion")
                remote_id = r.get("id")
                # r.get('id') is not None evita descartar id=0 (falsy)
                if jurisdiccion is None or remote_id is None:
                    continue
                self._link_store.save_link(
                    entity="rubro",
                    source_key=json.dumps({"jurisdiccion": str(jurisdiccion)}, sort_keys=True),
                    remote_id=str(remote_id),
                )

        clasificaciones = results.get("clasificaciones", [])
        if isinstance(clasificaciones, list):
            for c in clasificaciones:
                if not isinstance(c, dict) or not c.get("success"):
                    continue
                external_id = c.get("external_id") or {}
                if not isinstance(external_id, dict):
                    continue
                jurisdiccion = external_id.get("jurisdiccion")
                remote_id = c.get("id")
                if jurisdiccion is None or remote_id is None:
                    continue
                self._link_store.save_link(
                    entity="clasificacion",
                    source_key=json.dumps({"jurisdiccion": str(jurisdiccion)}, sort_keys=True),
                    remote_id=str(remote_id),
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
    return _fetch_migrator_json(endpoint_env="MIGRATOR_SPEC_ENDPOINT", default_endpoint="rafam/migracion/spec.json")


def fetch_migrator_lookups(only: list[str] | None = None) -> dict:
    filtered = [item.strip() for item in (only or []) if item and item.strip()]

    # Si no se especifica seccion, intentamos el endpoint completo primero.
    if not filtered:
        try:
            return _fetch_migrator_json(
                endpoint_env="MIGRATOR_LOOKUPS_ENDPOINT",
                default_endpoint="rafam/migracion/lookups.json",
            )
        except Exception:
            # Fallback robusto: consultar por seccion para evitar que una seccion rota
            # bloquee todas las demas.
            filtered = [
                "mercaderias",
                "unidades_de_medida",
                "tipos_factura",
                "tipos_de_pago",
                "proveedores",
                "gastos",
            ]

    # Si hay una sola seccion, mantenemos comportamiento estricto.
    if len(filtered) == 1:
        return _fetch_migrator_json(
            endpoint_env="MIGRATOR_LOOKUPS_ENDPOINT",
            default_endpoint="rafam/migracion/lookups.json",
            query_params={"only": filtered[0]},
        )

    merged: dict = {}
    partial_errors: dict[str, str] = {}
    for section in filtered:
        try:
            payload = _fetch_migrator_json(
                endpoint_env="MIGRATOR_LOOKUPS_ENDPOINT",
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
    base_url = os.getenv("MIGRATOR_BASE_URL", "").rstrip("/")
    if not base_url:
        raise ValueError("Falta MIGRATOR_BASE_URL en .env para consultar migrator")

    tenant = os.getenv("MIGRATOR_TENANT", "").strip()
    if not tenant:
        raise ValueError("Falta MIGRATOR_TENANT en .env para consultar migrator")

    api_key = os.getenv("MIGRATOR_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Falta MIGRATOR_API_KEY en .env para consultar migrator")

    timeout = int(os.getenv("MIGRATOR_TIMEOUT_SECONDS", os.getenv("GATEWAY_TIMEOUT_SECONDS", "20")))
    verify_ssl = os.getenv("MIGRATOR_VERIFY_SSL", os.getenv("GATEWAY_VERIFY_SSL", "true")).strip().lower() in {"1", "true", "yes", "on"}
    endpoint = os.getenv(endpoint_env, default_endpoint).strip().strip("/")

    headers = {
        "Accept": "application/json",
        "X-Api-Key": api_key,
        "X-Tenant-Id": tenant,
        "User-Agent": "rafam-sync/1.0",
    }
    url = f"{base_url}/{endpoint}"
    if query_params:
        url = f"{url}?{parse.urlencode(query_params)}"
    req = request.Request(url=url, headers=headers, method="GET")
    ssl_context = None
    if not verify_ssl:
        ssl_context = ssl._create_unverified_context()

    try:
        with request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
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
