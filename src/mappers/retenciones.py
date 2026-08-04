"""retenciones.py â Mapper para entidad RETENCIONES (F3 standalone).

Recorre OP confirmadas, trae deducciones desde ORDEN_PAGO_DEDUC y
emite la secciÃ³n top-level `retenciones` del migrator Paxapos.
"""

from __future__ import annotations

import hashlib
import json
import logging

from ..retry_store import REASON_DEPENDENCY_MISSING
from ..utils import normalize_text, to_int
from ..validation import validate_amount

logger = logging.getLogger(__name__)


class RetencionesMapper:
    """Mapper para retenciones standalone (F3)."""

    def __init__(self, *, link_store, lookup_resolver, source_repo=None, retry_store=None):
        self._link_store = link_store
        self._lookup = lookup_resolver
        self._source_repo = source_repo
        self._retry_store = retry_store
        # Contadores de retenciones descartadas
        self._retencion_skipped_no_catalog: int = 0
        self._retencion_skipped_no_match: dict[str, int] = {}

    def build_payload(
        self,
        columns: list[str],
        rows: list[tuple],
        *,
        dry_run: bool,
        payload_options: dict,
    ) -> tuple[dict | None, dict[str, tuple[str, int]]]:
        """Construye el payload de retenciones para POST al migrator.

        Returns:
            (payload, pending_fingerprints) o (None, {}) si no hay datos.
            pending_fingerprints: {op_sk: (fingerprint, count)} para idempotencia.
        """
        if self._source_repo is None:
            logger.error(
                "Migrator [retenciones]: source_repo no adjunto; no se pueden traer deducciones."
            )
            return None, {}

        # 1. Claves OP unicas del batch
        op_keys: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for row in rows:
            raw = dict(zip(columns, row))
            ejercicio = to_int(raw.get("EJERCICIO"))
            nro_op = to_int(raw.get("NRO_OP"))
            if ejercicio is None or nro_op is None:
                continue
            key = (ejercicio, nro_op)
            if key not in seen:
                seen.add(key)
                op_keys.append(key)

        if not op_keys:
            logger.info("Migrator [retenciones]: batch sin OPs validas")
            return None, {}

        # 2. Traer deducciones por OP
        deducciones_by_op = self._source_repo.fetch_deducciones_for_ops(op_keys)
        if deducciones_by_op is None:
            logger.error(
                "Migrator [retenciones]: ORDEN_PAGO_DEDUC no disponible; batch omitido."
            )
            return None, {}

        # 3. Construir payload
        retenciones_payload: list[dict] = []
        pending_fingerprints: dict[str, tuple[str, int]] = {}
        skipped_no_link = 0
        skipped_no_deduc = 0
        skipped_unchanged = 0

        for ejercicio, nro_op in op_keys:
            deducciones = deducciones_by_op.get((ejercicio, nro_op), [])
            if not deducciones:
                skipped_no_deduc += 1
                continue

            op_sk = json.dumps({"ejercicio": ejercicio, "nro_op": nro_op}, sort_keys=True)
            op_link = self._link_store.get_link("orden_pago", op_sk)
            if not op_link or not op_link.get("remote_id"):
                skipped_no_link += 1
                if self._retry_store is not None and not dry_run:
                    self._retry_store.enqueue(
                        "retenciones",
                        op_sk,
                        REASON_DEPENDENCY_MISSING,
                        f"OP {ejercicio}-{nro_op} aun no migrada en Paxapos",
                    )
                continue

            mapped: list[dict] = []
            for ded in deducciones:
                ret = self._map_deduccion_dict(ded, ejercicio, nro_op)
                if ret is not None:
                    mapped.append(ret)
            if not mapped:
                # Hay deducciones pero ninguna mapeo (tipicamente el catalogo
                # tipos_retencion fallo al cargarse o no matchea). Encolar para
                # que la proxima corrida las reinyecte: sin esto el cursor
                # avanza y estas retenciones se pierden en silencio.
                if self._retry_store is not None and not dry_run:
                    self._retry_store.enqueue(
                        "retenciones",
                        op_sk,
                        REASON_DEPENDENCY_MISSING,
                        f"OP {ejercicio}-{nro_op}: {len(deducciones)} deduccion(es) sin tipo de retencion resoluble",
                    )
                continue

            # Idempotencia
            fingerprint = _retenciones_fingerprint(mapped)
            ret_link = self._link_store.get_link("retenciones", op_sk)
            if ret_link and ret_link.get("fingerprint") == fingerprint:
                skipped_unchanged += 1
                continue

            pending_fingerprints[op_sk] = (fingerprint, len(mapped))
            retenciones_payload.append({
                "external_id": {"ejercicio": ejercicio, "nro_op": nro_op},
                "orden_pago_external_id": {"ejercicio": ejercicio, "nro_op": nro_op},
                "retenciones": mapped,
            })

        if skipped_no_link or skipped_no_deduc or skipped_unchanged:
            logger.info(
                "Migrator [retenciones]: %d OP sin link (encoladas), %d sin deducciones, "
                "%d ya migradas sin cambios (skip)",
                skipped_no_link, skipped_no_deduc, skipped_unchanged,
            )

        self._flush_retencion_skip_counters("retenciones")

        if not retenciones_payload:
            logger.info("Migrator [retenciones]: nada para enviar en este batch")
            return None, {}

        payload = {
            "dry_run": dry_run,
            "options": payload_options,
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": [],
            "ordenes_pago": [],
            "retenciones": retenciones_payload,
        }
        return payload, pending_fingerprints

    def _map_deduccion_dict(self, ded: dict, ejercicio: int, nro_op: int) -> dict | None:
        """Mapea una deducciÃ³n de ORDEN_PAGO_DEDUC al formato Paxapos."""
        codigo_deduc = ded.get("codigo_deduc")
        importe_reten = ded.get("importe_reten")
        if codigo_deduc is None or importe_reten is None:
            return None

        cod_text = str(codigo_deduc).strip()
        if not cod_text:
            return None

        res_monto = validate_amount(
            importe_reten,
            field="importe_reten",
            allow_zero=False,
            allow_negative=False,
            required=True,
        )
        if not res_monto.ok:
            return None
        monto_retenido = res_monto.value

        descripcion = str(ded.get("descripcion") or "").strip()

        tipo_retencion_id = self._lookup.resolve_tipo_retencion_id(cod_text, descripcion)
        if tipo_retencion_id is None:
            alias = self._lookup.retencion_alias(descripcion or cod_text)
            if alias:
                tipo_retencion_id = self._lookup.resolve_tipo_retencion_id_by_alias(alias)

        if tipo_retencion_id is None:
            if not self._lookup.tipos_retencion:
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

        alicuota = ded.get("alicuota")
        if alicuota is not None:
            res_alicuota = validate_amount(
                alicuota,
                field="alicuota",
                allow_zero=False,
                allow_negative=False,
                required=False,
            )
            if res_alicuota.ok and res_alicuota.value is not None:
                retencion["alicuota"] = res_alicuota.value

        comprob_deduc = ded.get("comprob_deduc")
        if comprob_deduc is not None and str(comprob_deduc).strip():
            retencion["numero_certificado"] = str(comprob_deduc).strip()

        if descripcion:
            retencion["observacion"] = f"Deduccion RAFAM {descripcion} OP {ejercicio}/{nro_op}"

        return retencion

    def _flush_retencion_skip_counters(self, entity_label: str) -> None:
        if self._retencion_skipped_no_catalog:
            logger.warning(
                "Migrator [%s]: %d retenciones omitidas porque tipos_retencion lookup esta vacio. "
                "Cargar account_tipo_impuestos en el tenant Paxapos.",
                entity_label,
                self._retencion_skipped_no_catalog,
            )
            self._retencion_skipped_no_catalog = 0
        if self._retencion_skipped_no_match:
            logger.warning(
                "Migrator [%s]: retenciones omitidas sin match en lookup: %s",
                entity_label,
                self._retencion_skipped_no_match,
            )
            self._retencion_skipped_no_match = {}

    def log_stats(self, parsed: dict, dry_run: bool) -> None:
        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("retenciones", {}) if isinstance(stats, dict) else {}
        logger.info(
            "Migrator OK [retenciones]: %d ok, %d error, dry_run=%s",
            section_stats.get("ok", 0),
            section_stats.get("error", 0),
            dry_run,
        )


# ââ Persist Links ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def persist_links_retenciones(
    parsed: dict, pending_fingerprints: dict[str, tuple[str, int]], link_store, dry_run: bool
) -> None:
    """Guarda link_retenciones por OP migrada con Ã©xito (idempotencia F4)."""
    if dry_run or not isinstance(parsed, dict):
        return
    results = parsed.get("results", {})
    if not isinstance(results, dict):
        return
    section = results.get("retenciones", [])
    if not isinstance(section, list):
        return

    for result in section:
        if not isinstance(result, dict) or not result.get("success"):
            continue
        external_id = result.get("external_id") or {}
        if not isinstance(external_id, dict):
            continue
        key_dict = {k: external_id[k] for k in ("ejercicio", "nro_op") if k in external_id}
        if len(key_dict) != 2:
            continue
        source_key = json.dumps(key_dict, sort_keys=True)
        fp_entry = pending_fingerprints.get(source_key)
        if fp_entry is None:
            continue
        fingerprint, count = fp_entry
        remote_id = result.get("id")
        link_store.save_link(
            entity="retenciones",
            source_key=source_key,
            remote_id=str(remote_id) if remote_id is not None else "",
            fingerprint=fingerprint,
            retenciones_count=str(count),
        )


# ââ Helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _retenciones_fingerprint(mapped: list[dict]) -> str:
    """Hash estable del conjunto de retenciones enviadas."""
    items = sorted(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in mapped)
    raw = "\n".join(items)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# SecciÃ³n de resultado en la respuesta del API
RESULT_SECTION = "retenciones"
