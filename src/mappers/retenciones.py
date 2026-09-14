"""retenciones.py â Mapper para entidad RETENCIONES (F3 standalone).

Recorre OP confirmadas, trae deducciones desde ORDEN_PAGO_DEDUC y
emite la secciÃ³n top-level `retenciones` del migrator Paxapos.
"""

from __future__ import annotations

import hashlib
import json
import logging

from ..config import is_cod_prov_excluded
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
        self._retencion_skipped_non_tax: dict[str, float] = {}

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
        prov_by_key: dict[tuple[int, int], object] = {}
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
                prov_by_key[key] = raw.get("COD_PROV")

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
        skipped_permanent = 0
        skipped_excluded = 0

        # Igual que oc_items (paxapos#489): una OP dentro de la ventana de
        # reproceso vuelve a entrar en cada corrida; sin esta exclusion una
        # retencion 'permanent' se reenviaba (y fallaba) 144 veces por dia.
        permanent_keys: set[str] = set()
        if self._retry_store is not None:
            try:
                permanent_keys = self._retry_store.permanent_external_ids("retenciones")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Migrator [retenciones]: no se pudo leer permanent_external_ids: %s", exc)

        for ejercicio, nro_op in op_keys:
            op_sk = json.dumps({"ejercicio": ejercicio, "nro_op": nro_op}, sort_keys=True)
            if op_sk in permanent_keys:
                skipped_permanent += 1
                continue
            if is_cod_prov_excluded(prov_by_key.get((ejercicio, nro_op))):
                # Misma blocklist que orden_pago (sueldos, IPS, IOMA, cajas chicas):
                # sus deducciones no son retenciones a proveedores. Cerrar la cola
                # si quedo encolada antes de la exclusion.
                skipped_excluded += 1
                self._resolve_retry(op_sk, dry_run)
                continue

            deducciones = deducciones_by_op.get((ejercicio, nro_op), [])
            if not deducciones:
                skipped_no_deduc += 1
                # Sin deducciones no hay nada que migrar: si estaba en la cola
                # (p.ej. por un tipo de retencion no resuelto), cerrarla.
                self._resolve_retry(op_sk, dry_run)
                continue

            op_link = self._link_store.get_link("orden_pago", op_sk)
            if not op_link or not op_link.get("remote_id"):
                skipped_no_link += 1
                if self._retry_store is not None and not dry_run:
                    self._retry_store.enqueue(
                        "retenciones",
                        op_sk,
                        REASON_DEPENDENCY_MISSING,
                        f"OP {ejercicio}-{nro_op} aun no migrada en Paxapos",
                        reason_detail="payment_not_migrated",
                    )
                continue
            if op_link.get("deleted_at"):
                # El Egreso destino fue borrado en Paxapos (baja manual, terminal
                # por contrato): no hay a que aplicarle las retenciones.
                skipped_permanent += 1
                continue

            mapped: list[dict] = []
            for ded in deducciones:
                ret = self._map_deduccion_dict(ded, ejercicio, nro_op)
                if ret is not None:
                    mapped.append(ret)
            if not mapped:
                # Hay deducciones pero ninguna mapeo. Dos causas distintas:
                #  - todas son TIPO_DEDUC='O' (IPS, IOMA, sindicato, garantia...):
                #    no son retenciones impositivas y Paxapos no las modela; no
                #    hay nada que "resolver" del lado del catalogo;
                #  - hay alguna 'I' que el catalogo tipos_retencion no matchea
                #    (o el lookup fallo al cargarse): eso si es un pendiente real.
                # Ambas se encolan (para no perderlas si el catalogo cambia) pero
                # con reason_detail distinto para que el reporte no las mezcle.
                if self._retry_store is not None and not dry_run:
                    if _all_non_tax(deducciones):
                        detail = "non_tax_deduction"
                        msg = (
                            f"OP {ejercicio}-{nro_op}: {len(deducciones)} deduccion(es) no impositivas "
                            f"(TIPO_DEDUC=O: {_describe(deducciones)}); Paxapos no las modela como retencion"
                        )
                    else:
                        detail = "retention_type_unresolved"
                        msg = f"OP {ejercicio}-{nro_op}: {len(deducciones)} deduccion(es) sin tipo de retencion resoluble"
                    self._retry_store.enqueue(
                        "retenciones",
                        op_sk,
                        REASON_DEPENDENCY_MISSING,
                        msg,
                        reason_detail=detail,
                    )
                continue

            # Idempotencia
            fingerprint = _retenciones_fingerprint(mapped)
            ret_link = self._link_store.get_link("retenciones", op_sk)
            if ret_link and ret_link.get("fingerprint") == fingerprint:
                skipped_unchanged += 1
                # Ya migrada y al dia: si venia de la cola de reintentos (152
                # entradas legacy quedaron asi desde agosto), cerrarla.
                self._resolve_retry(op_sk, dry_run)
                continue

            pending_fingerprints[op_sk] = (fingerprint, len(mapped))
            retenciones_payload.append({
                "external_id": {"ejercicio": ejercicio, "nro_op": nro_op},
                # egreso_id resuelve el destino por id directo; el backend cae a
                # identificador_pago solo si no viene. Si el Egreso ya no existe
                # responde egreso_not_found y el exporter invalida el link.
                "egreso_id": to_int(op_link.get("remote_id")),
                "orden_pago_external_id": {"ejercicio": ejercicio, "nro_op": nro_op},
                "retenciones": mapped,
            })

        if skipped_no_link or skipped_no_deduc or skipped_unchanged or skipped_permanent or skipped_excluded:
            logger.info(
                "Migrator [retenciones]: %d OP sin link (encoladas), %d sin deducciones, "
                "%d ya migradas sin cambios (skip), %d permanent (no se reenvian), %d de proveedores excluidos",
                skipped_no_link, skipped_no_deduc, skipped_unchanged, skipped_permanent, skipped_excluded,
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

    def _resolve_retry(self, op_sk: str, dry_run: bool) -> None:
        """Saca la OP de la cola de retenciones (nada pendiente para ella)."""
        if self._retry_store is None or dry_run:
            return
        try:
            self._retry_store.resolve("retenciones", op_sk)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Migrator [retenciones]: no se pudo resolver %s en la cola: %s", op_sk, exc)

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
            key = descripcion or f"CODIGO_DEDUC={cod_text}"
            if str(ded.get("tipo_deduc") or "").strip().upper() == "O":
                # No impositiva: se omite a proposito, pero se acumula el importe
                # porque Paxapos recalcula neto_transferido solo con lo enviado.
                self._retencion_skipped_non_tax[key] = self._retencion_skipped_non_tax.get(key, 0.0) + float(monto_retenido)
            elif not self._lookup.tipos_retencion:
                self._retencion_skipped_no_catalog += 1
            else:
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
        if self._retencion_skipped_non_tax:
            logger.info(
                "Migrator [%s]: deducciones no impositivas (TIPO_DEDUC=O) omitidas, importe por concepto: %s",
                entity_label,
                {k: round(v, 2) for k, v in self._retencion_skipped_non_tax.items()},
            )
            self._retencion_skipped_non_tax = {}

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

def _all_non_tax(deducciones: list[dict]) -> bool:
    """True si todas las deducciones son TIPO_DEDUC='O' (ninguna impositiva)."""
    tipos = {str(d.get("tipo_deduc") or "").strip().upper() for d in deducciones}
    return bool(tipos) and tipos == {"O"}


def _describe(deducciones: list[dict], limit: int = 4) -> str:
    names = []
    for d in deducciones:
        name = " ".join(str(d.get("descripcion") or d.get("codigo_deduc") or "").split())
        if name and name not in names:
            names.append(name)
    extra = f" +{len(names) - limit}" if len(names) > limit else ""
    return ", ".join(names[:limit]) + extra


def _retenciones_fingerprint(mapped: list[dict]) -> str:
    """Hash estable del conjunto de retenciones enviadas."""
    items = sorted(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in mapped)
    raw = "\n".join(items)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# SecciÃ³n de resultado en la respuesta del API
RESULT_SECTION = "retenciones"
