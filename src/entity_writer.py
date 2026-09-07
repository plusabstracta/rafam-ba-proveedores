"""entity_writer.py â AbstracciÃ³n por entidad que compone el ciclo write-batch.

Cada EntityWriter encapsula:
  - Un mapper (transforma rows â payload)
  - Un link persister (guarda links post-response)
  - Una funciÃ³n log_stats (reporta estadÃ­sticas)

El ciclo comÃºn es:
  1. mapper.build_payload(columns, rows, ...) â (payload, context)
  2. post_fn(url, payload) â parsed_response
  3. persist_links(parsed, context, link_store, dry_run)
  4. raise_on_errors(parsed)
  5. log_stats(parsed, dry_run)

Pattern: Strategy â cada entidad tiene su writer configurado en factory.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


class MapperProtocol(Protocol):
    """Protocolo que deben implementar los mappers stateful."""

    def build_payload(
        self,
        columns: list[str],
        rows: list[tuple],
        *,
        dry_run: bool,
        payload_options: dict,
    ) -> tuple[dict | None, Any]: ...

    def log_stats(self, parsed: dict, dry_run: bool) -> None: ...


class EntityWriter:
    """Writer genÃ©rico por entidad. Compone mapper + persist + log en un ciclo
    unificado de write_batch.

    Args:
        entity_name: Nombre de la entidad (para logging).
        mapper: Instancia del mapper (provee build_payload + log_stats).
        persist_fn: Callback que persiste links post-response.
            Signature: (parsed, context, link_store, dry_run) -> None
        result_count_fn: FunciÃ³n que extrae el count de items para logging.
            Signature: (payload) -> int
        result_section: Nombre de la secciÃ³n del payload para contar items.
    """

    def __init__(
        self,
        entity_name: str,
        mapper: Any,
        persist_fn: Callable,
        result_section: str = "",
        log_stats_fn: Callable | None = None,
    ):
        self._entity_name = entity_name
        self._mapper = mapper
        self._persist_fn = persist_fn
        self._result_section = result_section
        self._log_stats_fn = log_stats_fn
        self._last_payload_count = 0
        self._last_saved_count = 0
        self._last_error_count = 0
        self._last_outcome_counts = self._empty_outcome_counts()
        self._last_mapper_metrics: dict[str, int] = {}

    @property
    def entity_name(self) -> str:
        return self._entity_name

    @property
    def mapper(self) -> Any:
        return self._mapper

    @property
    def result_section(self) -> str:
        return self._result_section

    @property
    def last_payload_count(self) -> int:
        return self._last_payload_count

    @property
    def last_saved_count(self) -> int:
        return self._last_saved_count

    @property
    def last_error_count(self) -> int:
        return self._last_error_count

    @property
    def last_outcome_counts(self) -> dict[str, int]:
        return dict(self._last_outcome_counts)

    @property
    def last_mapper_metrics(self) -> dict[str, int]:
        return dict(self._last_mapper_metrics)

    def write_batch(
        self,
        columns: list[str],
        rows: list[tuple],
        *,
        dry_run: bool,
        payload_options: dict,
        import_url: str,
        post_fn: Callable[[str, dict], dict],
        link_store: Any,
        raise_on_errors_fn: Callable[[dict], None],
        force_external_ids: set[str] | None = None,
    ) -> dict | None:
        """Ejecuta el ciclo completo: build â POST â persist â validate â log.

        Args:
            columns: Column names del batch.
            rows: Filas del batch.
            dry_run: Si es True, no persiste links.
            payload_options: Opciones comunes del payload.
            import_url: URL del endpoint de importaciÃ³n.
            post_fn: FunciÃ³n que hace el POST JSON.
            link_store: EntityLinkStore para persistir links.
            raise_on_errors_fn: FunciÃ³n que valida errores parciales.

        Returns:
            Dict parseado de la respuesta, o None si no se enviÃ³ nada.
        """
        self._last_payload_count = 0
        self._last_saved_count = 0
        self._last_error_count = 0
        self._last_outcome_counts = self._empty_outcome_counts()
        self._last_mapper_metrics = {}

        import inspect
        sig = inspect.signature(self._mapper.build_payload)
        kwargs = {
            "dry_run": dry_run,
            "payload_options": payload_options,
        }
        if "link_store" in sig.parameters:
            kwargs["link_store"] = link_store
        if "force_external_ids" in sig.parameters:
            kwargs["force_external_ids"] = force_external_ids or set()

        result = self._mapper.build_payload(columns, rows, **kwargs)

        # Los mappers devuelven (payload, context) â el context varÃ­a por entidad.
        if not isinstance(result, tuple) or len(result) < 2:
            return None
        payload, context = result[0], result[1]
        if len(result) >= 3 and isinstance(result[2], dict):
            self._last_mapper_metrics = {
                str(key): self._to_int(value) for key, value in result[2].items()
            }

        if payload is None:
            return None

        # Log pre-POST
        count = self._count_items(payload)
        self._last_payload_count = count
        logger.debug(
            "Migrator request [%s] POST %s dry_run=%s items=%d",
            self._entity_name, import_url, dry_run, count,
        )

        # POST
        parsed = post_fn(import_url, payload)
        self._capture_response_counts(parsed)
        self._capture_result_modes(parsed)

        # Persist links
        self._persist_fn(parsed, context, link_store, dry_run)

        # Validate partial errors
        raise_on_errors_fn(parsed)

        # Log stats â usa log_stats_fn custom si fue configurado,
        # sino delega a mapper.log_stats(parsed, dry_run).
        if self._log_stats_fn is not None:
            self._log_stats_fn(parsed, payload, dry_run)
        else:
            self._mapper.log_stats(parsed, dry_run)

        return parsed

    def _count_items(self, payload: dict) -> int:
        """Extrae la cantidad de items del payload para logging."""
        if self._result_section and isinstance(payload, dict):
            items = payload.get(self._result_section, [])
            return len(items) if isinstance(items, list) else 0
        return 0

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _capture_response_counts(self, parsed: dict | None) -> None:
        if not self._result_section or not isinstance(parsed, dict):
            return
        stats = parsed.get("stats")
        if not isinstance(stats, dict):
            return
        section_stats = stats.get(self._result_section)
        if not isinstance(section_stats, dict):
            return
        self._last_saved_count = self._to_int(section_stats.get("ok", 0))
        self._last_error_count = self._to_int(section_stats.get("error", 0))

    @staticmethod
    def _empty_outcome_counts() -> dict[str, int]:
        return {
            "created": 0,
            "updated": 0,
            "replaced": 0,
            "deleted": 0,
            "skipped": 0,
            "unclassified": 0,
        }

    def _capture_result_modes(self, parsed: dict | None) -> None:
        if not self._result_section or not isinstance(parsed, dict):
            return
        results = parsed.get("results")
        if not isinstance(results, dict):
            return
        section_results = results.get(self._result_section)
        if not isinstance(section_results, list):
            return

        mode_groups = {
            "create": "created",
            "created": "created",
            "update": "updated",
            "replace": "replaced",
            "soft_delete": "deleted",
            "already_deleted": "deleted",
            "existing": "skipped",
            "skip_existing": "skipped",
            "skipped_not_found": "skipped",
            "already_linked": "skipped",
            "already_linked_other": "skipped",
        }
        for result in section_results:
            if not isinstance(result, dict) or not result.get("success"):
                continue
            group = mode_groups.get(str(result.get("mode") or ""), "unclassified")
            self._last_outcome_counts[group] += 1


# ââ Persist function adapters ââââââââââââââââââââââââââââââââââââââââââââ
# Cada entidad tiene un persist_links con signature distinta.
# Estos adapters normalizan a (parsed, context, link_store, dry_run).

def _persist_proveedores(parsed: dict, context: dict, link_store: Any, dry_run: bool) -> None:
    """Adapter: proveedores no persiste en dry_run."""
    if dry_run:
        return
    from .mappers import proveedores as prov_mapper
    prov_mapper.persist_links(parsed, context, link_store)


def _persist_oc_items(parsed: dict, context: dict, link_store: Any, dry_run: bool) -> None:
    """Adapter: oc_items no persiste en dry_run."""
    if dry_run:
        return
    from .mappers.oc_items import persist_links as oc_persist
    oc_persist(parsed, context, link_store)


def _persist_solic_gastos(parsed: dict, context: dict, link_store: Any, dry_run: bool) -> None:
    """Adapter: solic_gastos no persiste en dry_run."""
    if dry_run:
        return
    from .mappers.solic_gastos import persist_links as sg_persist
    sg_persist(parsed, context, link_store)


def _persist_orden_pago(parsed: dict, context: dict, link_store: Any, dry_run: bool) -> None:
    """Adapter: orden_pago usa process_response que incluye persist."""
    from .mappers.orden_pago import OrdenPagoMapper
    # context aquÃ­ es raw_by_source_key; el mapper mismo tiene process_response
    # que ya maneja dry_run internamente.
    # Se llama desde el mapper directamente (ver build_entity_writers).
    pass  # Handled specially â see exporter._write_batch_orden_pago shim


def _persist_retenciones(parsed: dict, context: dict, link_store: Any, dry_run: bool) -> None:
    """Adapter: retenciones tiene pending_fingerprints como context."""
    from .mappers.retenciones import persist_links_retenciones
    persist_links_retenciones(parsed, context, link_store, dry_run)
