"""change_sync.py — Servicio de detección y re-envío de registros modificados.

Orquesta el flujo completo de sync-changes:
    1. Lee los links locales de SQLite (entidades ya migradas)
    2. Consulta las filas correspondientes de RAFAM (Oracle) en batches
    3. Mapea payloads y calcula hashes
    4. Compara contra hashes almacenados
    5. Envía los registros modificados via exporter

Extrae la lógica de negocio que antes estaba en main.py/_sync_entity_changes()
para separar CLI de dominio (SRP).
"""

import json
import logging
from typing import Any

from .change_detection import ChangeDetectionResult, compute_payload_hash
from .entity_link_store import EntityLinkStore
from .exporter import BaseExporter
from .gateway_mapper import map_proveedor_migrator_row
from .source_repository import SourceRepository

logger = logging.getLogger(__name__)


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


class ChangeSyncService:
    """Servicio de detección y re-envío de cambios en registros ya migrados."""

    # Batch sizes para consultas a RAFAM. Proveedores usa IN(...) — Oracle
    # tiene límite de 1000 elementos. OC usa OR(AND(...)) — no aplica límite
    # IN pero sí queremos mantener queries manejables.
    _PROVEEDORES_BATCH_SIZE = 500
    _OC_BATCH_SIZE = 200

    def __init__(
        self,
        source_repo: SourceRepository,
        exporter: BaseExporter,
        link_store: EntityLinkStore,
    ):
        self._source_repo = source_repo
        self._exporter = exporter
        self._link_store = link_store

    def sync_entity(
        self,
        entity: str,
        *,
        backfill_only: bool = False,
        dry_run: bool = False,
    ) -> bool:
        """Detecta y re-envía registros modificados para una entidad.

        Returns True si la sincronización fue exitosa, False si hubo error.
        """
        if entity == "proveedores":
            return self._sync_proveedores(backfill_only=backfill_only, dry_run=dry_run)
        elif entity == "oc_items":
            return self._sync_oc_items(backfill_only=backfill_only, dry_run=dry_run)
        else:
            logger.error("Entidad no soportada para sync-changes: %s", entity)
            return False

    # ── Proveedores ──────────────────────────────────────────────────────

    def _sync_proveedores(self, *, backfill_only: bool, dry_run: bool) -> bool:
        entity = "proveedores"
        logger.info("[SYNC-CHANGES] Iniciando detección de cambios para '%s'", entity)

        links = self._link_store.get_all_links("proveedores")
        if not links:
            logger.info("[SYNC-CHANGES] No hay enlaces locales registrados para '%s'.", entity)
            return True

        result = ChangeDetectionResult(entity=entity, total_scanned=len(links))

        # Extraer keys
        cod_provs: list[int] = []
        link_by_source_key: dict[str, dict] = {}
        for link in links:
            try:
                cod_provs.append(int(link["source_key"]))
                link_by_source_key[str(link["source_key"])] = link
            except ValueError:
                continue

        if not cod_provs:
            return True

        # Fetch en batches (respeta límite de 1000 de Oracle IN)
        all_rows: list[tuple] = []
        columns: list[str] = []
        for i in range(0, len(cod_provs), self._PROVEEDORES_BATCH_SIZE):
            chunk = cod_provs[i : i + self._PROVEEDORES_BATCH_SIZE]
            cols, rows = self._source_repo.fetch_proveedores_by_keys(chunk)
            if not columns and cols:
                columns = cols
            all_rows.extend(rows)

        # Mapear, hashear, comparar
        to_send: list[tuple] = []
        raw_by_source_key: dict[str, dict] = {}
        payload_hashes: dict[str, str] = {}

        for row in all_rows:
            raw = dict(zip(columns, row))
            mapped = map_proveedor_migrator_row(raw)
            if not mapped:
                continue
            source_key = str(raw.get("COD_PROV"))
            link = link_by_source_key.get(source_key)
            if not link:
                continue

            current_hash = compute_payload_hash(mapped.get("Proveedor", {}))
            stored_hash = link.get("payload_hash")

            if stored_hash is None:
                result.new_keys.append(source_key)
            elif stored_hash != current_hash:
                result.changed_keys.append(source_key)
            else:
                result.unchanged_keys.append(source_key)
                continue  # Sin cambios, skip

            if backfill_only:
                if not dry_run:
                    self._link_store.save_link(
                        entity="proveedores",
                        source_key=source_key,
                        remote_id=link["remote_id"],
                        cuit=link["cuit"],
                        cod_estado=link["cod_estado"],
                        payload_hash=current_hash,
                    )
            else:
                to_send.append(row)
                raw_by_source_key[source_key] = raw
                payload_hashes[source_key] = current_hash

        if backfill_only:
            logger.info(
                "[SYNC-CHANGES] Backfill completo para '%s': %d hashes actualizados de %d analizados (dry_run=%s)",
                entity, len(result.new_keys) + len(result.changed_keys), len(links), dry_run,
            )
            return True

        if not to_send:
            logger.info("[SYNC-CHANGES] No se detectaron cambios en '%s' (analizados=%d).", entity, len(links))
            return True

        logger.info(
            "[SYNC-CHANGES] Detectados %d cambios en '%s' (nuevos=%d, modificados=%d de %d analizados). Re-enviando...",
            len(to_send), entity, len(result.new_keys), len(result.changed_keys), len(links),
        )

        if dry_run:
            logger.info("[DRY RUN] Se hubieran re-enviado %d proveedores.", len(to_send))
            return True

        try:
            self._exporter.set_payload_hashes("proveedores", payload_hashes)
            self._exporter.write_batch("proveedores", columns, to_send)
        except Exception as exc:
            logger.error("[SYNC-CHANGES] Falló el re-envío de proveedores: %s", exc)
            return False

        return True

    # ── OC Items ─────────────────────────────────────────────────────────

    def _sync_oc_items(self, *, backfill_only: bool, dry_run: bool) -> bool:
        entity = "oc_items"
        logger.info("[SYNC-CHANGES] Iniciando detección de cambios para '%s'", entity)

        links = self._link_store.get_all_links("orden_compra")
        if not links:
            logger.info("[SYNC-CHANGES] No hay enlaces locales registrados para '%s'.", entity)
            return True

        result = ChangeDetectionResult(entity=entity, total_scanned=len(links))

        # Extraer keys
        oc_keys: list[dict] = []
        link_by_source_key: dict[str, dict] = {}
        for link in links:
            try:
                k = json.loads(link["source_key"])
                if all(x in k for x in ["ejercicio", "uni_compra", "nro_oc"]):
                    oc_keys.append(k)
                    link_by_source_key[link["source_key"]] = link
            except (ValueError, TypeError, json.JSONDecodeError):
                continue

        if not oc_keys:
            return True

        # Fetch en batches
        all_rows: list[tuple] = []
        columns: list[str] = []
        for i in range(0, len(oc_keys), self._OC_BATCH_SIZE):
            chunk = oc_keys[i : i + self._OC_BATCH_SIZE]
            cols, rows = self._source_repo.fetch_oc_items_by_keys(chunk)
            if not columns and cols:
                columns = cols
            all_rows.extend(rows)

        # Agrupar OC filas en payloads (cabecera + items)
        if hasattr(self._exporter, "_group_oc_rows"):
            grouped, grouped_raw, grouped_gasto_refs, unresolved_items = self._exporter._group_oc_rows(columns, all_rows)
        else:
            from .exporter import MigratorExporter
            temp_exporter = MigratorExporter(dry_run=True)
            grouped, grouped_raw, grouped_gasto_refs, unresolved_items = temp_exporter._group_oc_rows(columns, all_rows)

        # Hashear, comparar
        to_send: list[tuple] = []
        raw_by_source_key: dict[str, dict] = {}
        payload_hashes: dict[str, str] = {}

        for key, oc_data in grouped.items():
            source_key = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            link = link_by_source_key.get(source_key)
            if not link:
                continue

            current_hash = compute_payload_hash(oc_data)
            stored_hash = link.get("payload_hash")

            if stored_hash is None:
                result.new_keys.append(source_key)
            elif stored_hash != current_hash:
                result.changed_keys.append(source_key)
            else:
                result.unchanged_keys.append(source_key)
                continue  # Sin cambios, skip

            if backfill_only:
                if not dry_run:
                    self._link_store.save_link(
                        entity="orden_compra",
                        source_key=source_key,
                        remote_id=link["remote_id"],
                        estado_oc=link["estado_oc"],
                        fech_confirm=link["fech_confirm"],
                        cod_prov=link["cod_prov"],
                        importe_tot=link["importe_tot"],
                        gasto_refs=link["gasto_refs"],
                        gasto_linked_refs=link["gasto_linked_refs"],
                        paxapos_gasto_ids=link.get("paxapos_gasto_ids", ""),
                        payload_hash=current_hash,
                    )
            else:
                # Recolectar filas crudas de esta OC
                for row in all_rows:
                    raw = dict(zip(columns, row))
                    if (_to_int(raw.get("EJERCICIO")) == key[0] and
                        _to_int(raw.get("UNI_COMPRA")) == key[1] and
                        _to_int(raw.get("NRO_OC")) == key[2]):
                        to_send.append(row)

                raw_by_source_key[source_key] = grouped_raw[key]
                gasto_refs_list = grouped_gasto_refs.get(key, [])
                raw_by_source_key[source_key]["_GASTO_REFS"] = ",".join(gasto_refs_list) if gasto_refs_list else ""
                raw_by_source_key[source_key]["_GASTO_LINKED_REFS"] = link.get("gasto_linked_refs", "")
                payload_hashes[source_key] = current_hash

        if backfill_only:
            logger.info(
                "[SYNC-CHANGES] Backfill completo para '%s': %d hashes actualizados de %d analizados (dry_run=%s)",
                entity, len(result.new_keys) + len(result.changed_keys), len(links), dry_run,
            )
            return True

        if not to_send:
            logger.info("[SYNC-CHANGES] No se detectaron cambios en '%s' (analizados=%d).", entity, len(links))
            return True

        logger.info(
            "[SYNC-CHANGES] Detectados %d cambios en '%s' (nuevos=%d, modificados=%d de %d analizados). Re-enviando...",
            len(result.new_keys) + len(result.changed_keys), entity,
            len(result.new_keys), len(result.changed_keys), len(links),
        )

        if dry_run:
            logger.info("[DRY RUN] Se hubieran re-enviado %d filas de items de OC.", len(to_send))
            return True

        try:
            self._exporter.set_payload_hashes("oc_items", payload_hashes)
            self._exporter.write_batch("oc_items", columns, to_send)
        except Exception as exc:
            logger.error("[SYNC-CHANGES] Falló el re-envío de oc_items: %s", exc)
            return False

        return True
