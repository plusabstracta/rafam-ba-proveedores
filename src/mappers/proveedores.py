"""proveedores.py â€” Mapper para entidad PROVEEDORES.

Transforma filas crudas de RAFAM PROVEEDORES al formato del migrator
Paxapos y persiste entity links a partir de la respuesta del API.
"""

from __future__ import annotations

import logging

from ..gateway_mapper import map_proveedor_migrator_row
from ..change_detection import compute_payload_hash
from ..utils import normalize_cuit

logger = logging.getLogger(__name__)


def map_rows(
    columns: list[str],
    rows: list[tuple],
    link_store: Any | None = None,
) -> tuple[list[dict], dict[str, dict]]:
    """Transforma filas RAFAM PROVEEDORES al formato migrator.

    Returns:
        (mapped_proveedores, raw_by_source_key)
    """
    proveedores: list[dict] = []
    raw_by_source_key: dict[str, dict] = {}

    for row in rows:
        raw = dict(zip(columns, row))
        payload_row = map_proveedor_migrator_row(raw)
        if payload_row is None:
            continue
        source_key = _source_key(raw)
        if source_key is not None:
            raw_by_source_key[source_key] = raw
            if link_store:
                remote_id = link_store.get_remote_id("proveedores", source_key)
                if remote_id:
                    # Inyectar el ID de Paxapos existente para actualizarlo
                    payload_row["Proveedor"]["id"] = int(remote_id)
        proveedores.append(payload_row)

    return proveedores, raw_by_source_key


def build_payload(
    columns: list[str],
    rows: list[tuple],
    *,
    dry_run: bool,
    payload_options: dict,
    link_store: Any | None = None,
) -> tuple[dict | None, dict[str, dict]]:
    """Construye el payload completo para POST al migrator.

    Returns:
        (payload, raw_by_source_key) o (None, {}) si no hay datos.
    """
    from typing import Any
    proveedores, raw_by_source_key = map_rows(columns, rows, link_store=link_store)

    if not proveedores:
        logger.info("Migrator [proveedores]: lote vacio luego del mapeo")
        return None, {}

    payload = {
        "dry_run": dry_run,
        "options": payload_options,
        "proveedores": proveedores,
        "pedidos": [],
        "ordenes_compra": [],
        "gastos": [],
        "ordenes_pago": [],
    }
    return payload, raw_by_source_key


def persist_links(parsed: dict, raw_by_source_key: dict[str, dict], link_store) -> None:
    """Persiste entity links de proveedores desde la respuesta del API."""
    if not isinstance(parsed, dict):
        return
    results = parsed.get("results", {})
    if not isinstance(results, dict):
        return

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
        cuit = normalize_cuit(raw.get("CUIT")) if raw else None
        cod_estado = str(raw.get("COD_ESTADO")) if raw and raw.get("COD_ESTADO") is not None else None
        payload_hash = None
        if raw:
            mapped = map_proveedor_migrator_row(raw)
            if mapped:
                payload_hash = compute_payload_hash(mapped.get("Proveedor", {}))
        link_store.save_link(
            entity="proveedores",
            source_key=str(source_key),
            remote_id=str(remote_id),
            cuit=cuit,
            cod_estado=cod_estado,
            payload_hash=payload_hash,
        )


def log_stats(parsed: dict, dry_run: bool) -> None:
    """Loguea estadÃ­sticas de la pasada."""
    stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
    section_stats = stats.get("proveedores", {}) if isinstance(stats, dict) else {}
    logger.info(
        "Migrator OK [proveedores]: %d ok, %d error, dry_run=%s",
        section_stats.get("ok", 0),
        section_stats.get("error", 0),
        dry_run,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _source_key(raw: dict) -> str | None:
    """Extrae la clave de negocio de un row de proveedores."""
    value = raw.get("COD_PROV")
    return str(value) if value is not None else None


# Sección de resultado en la respuesta del API
RESULT_SECTION = "proveedores"
