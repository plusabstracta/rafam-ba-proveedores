"""record_ledger.py — Cierre de cuentas por entidad y corrida.

Regla: todo registro que el script lee de RAFAM tiene que terminar la corrida
en uno de estos lugares:

1. con ID de Paxapos (link local);
2. en la cola de reintentos (`retry_queue`), con su motivo;
3. con un motivo de "fuera de alcance" (una regla de negocio dice que no se
   migra) o "ya esta en Paxapos": se cuentan para el mail diario.

Lo que no cae en ninguno es un registro que se perderia en silencio. Aca se lo
encola igual, con el mejor motivo disponible, y avisa por mail:

* el mapper lo omitio con un motivo de ``fallo``  -> validation_client;
* el mapper lo omitio porque ``espera`` a otro    -> dependency_missing
  (no cuenta intentos; avisa si la espera supera RAFAM_WAIT_ALERT_DAYS);
* Paxapos respondio OK pero sin ID                -> backend_rejected/ok_without_id;
* se envio y la respuesta no lo menciona          -> backend_rejected/no_response;
* nada de lo anterior (bug del script)            -> validation_client/unexplained.

Los registros de un batch que fallo entero no se evaluan: el watermark queda
congelado y se vuelven a leer en la proxima corrida.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, replace

from .config import is_cod_prov_excluded
from .record_events import GROUP_EN_PAXAPOS, GROUP_ESPERA, GROUP_FALLO, GROUP_FUERA, RecordEventSink
from .retry_labels import describe_retry_key, record_base_key, row_key_fn
from .retry_store import (
    REASON_BACKEND_REJECTED,
    REASON_DEPENDENCY_MISSING,
    REASON_VALIDATION_CLIENT,
    RESOLVED_MIGRATED,
    RESOLVED_OUT_OF_SCOPE,
)

logger = logging.getLogger(__name__)

# Entidad de la corrida -> tabla de links (`EntityLinkStore`) con el ID de Paxapos.
LINK_ENTITY = {
    "proveedores": "proveedores",
    "oc_items": "orden_compra",
    "solic_gastos": "gasto",
    "orden_pago": "orden_pago",
    "retenciones": "retenciones",
}
LEDGER_ENTITIES = frozenset(LINK_ENTITY)

# Retenciones no tienen ID propio en Paxapos (se aplican sobre el Egreso): el
# link con su fingerprint es la prueba de que se migraron.
_LINK_IS_ENOUGH = frozenset({"retenciones"})

# Descripcion corta de cada motivo "fuera de alcance" para el mail diario.
FUERA_LABELS = {
    "excluded_provider": "proveedor excluido por configuracion",
    "cancelled_never_migrated": "OC anulada en RAFAM que nunca se migro",
    "payment_not_confirmed": "OP sin confirmar/pagar en RAFAM",
    "non_positive_amount": "OP con importe en $0 o negativo (ajuste/anulacion)",
    "non_budget_payment": "OP no presupuestaria sin imputacion",
    "no_deductions": "OP sin deducciones (no hay retenciones que migrar)",
    "non_tax_deductions": "deducciones no impositivas (IPS, IOMA, sindicato...)",
    "destination_deleted": "el Egreso fue borrado a mano en Paxapos",
    "cancelled": "solicitud anulada en RAFAM",
    "no_receipt_yet": "solicitud todavia sin factura cargada en RAFAM",
    "order_not_sent": "solicitud de una OC que no esta en Paxapos (se controla en oc_items)",
    "no_paxapos_gasto": "factura que el proveedor aun no subio (el gasto lo crea la OP al pagarse)",
}

_EXAMPLES = 5


def _normalize_reason(reason: str) -> str:
    """Motivo sin numeros ni comando sugerido (para agrupar)."""
    reason = reason.split("; primero:", 1)[0]
    return re.sub(r"\d[\d.-]*", "#", reason)


@dataclass
class RunLedger:
    """Lo que paso con cada registro de UNA entidad en UNA corrida."""

    entity: str
    seen: dict = field(default_factory=dict)          # clave base -> None (orden de lectura)
    failed: set = field(default_factory=set)          # claves de batches caidos
    ok_keys: dict = field(default_factory=dict)       # clave -> modo de la respuesta OK
    error_keys: set = field(default_factory=set)      # clave -> Paxapos la rechazo
    sent: set = field(default_factory=set)            # claves que viajaron en un POST
    proveedor_excluded: set = field(default_factory=set)

    def see_rows(self, columns: list[str], rows: list[tuple]) -> list[str]:
        """Registra las claves del batch y las devuelve (en orden, sin repetir)."""
        keys: list[str] = []
        local: set[str] = set()
        key_of = row_key_fn(self.entity, columns)
        if key_of is None:
            return keys
        for row in rows:
            key = key_of(row)
            if key is None or key in local:
                continue
            local.add(key)
            keys.append(key)
            self.seen.setdefault(key, None)
            if self.entity == "proveedores" and is_cod_prov_excluded(key):
                self.proveedor_excluded.add(key)
        return keys

    def mark_failed(self, keys) -> None:
        self.failed.update(k for k in keys if k is not None)

    def add_outcomes(self, outcomes) -> None:
        for outcome in outcomes or ():
            if outcome.entity != self.entity:
                continue
            base = outcome.base_key
            if base is None:
                continue
            if outcome.ok:
                self.ok_keys[base] = outcome.mode or "?"
            else:
                self.error_keys.add(base)

    def add_sent(self, keys) -> None:
        for entity, base in keys or ():
            if entity == self.entity:
                self.sent.add(base)


def paxapos_id_for(entity: str, external_id: str, link_store) -> str | None:
    """ID de Paxapos de un registro de la cola, si ya existe alli (o None)."""
    link_entity = LINK_ENTITY.get(entity)
    if link_entity is None or link_store is None:
        return None
    candidates = [str(external_id)]
    base = record_base_key(entity, external_id)
    if base is not None and base not in candidates:
        candidates.append(base)
    for key in candidates:
        try:
            link = link_store.get_link(link_entity, key)
        except Exception:  # noqa: BLE001 - el ID es informativo
            return None
        remote_id = str((link or {}).get("remote_id") or "").strip()
        if remote_id:
            return remote_id
    return None


def with_paxapos_ids(items, link_store) -> list:
    """Copia de los RetryItem con ``paxapos_id`` completo (para los mails)."""
    if link_store is None:
        return list(items)
    return [
        replace(item, paxapos_id=paxapos_id_for(item.entity, item.external_id, link_store))
        for item in items
    ]


def _keys_with_paxapos_id(entity: str, link_store) -> set[str]:
    link_entity = LINK_ENTITY[entity]
    keys: set[str] = set()
    for link in link_store.get_all_links(link_entity):
        if entity not in _LINK_IS_ENOUGH and not str(link.get("remote_id") or "").strip():
            continue
        source_key = link.get("source_key")
        base = record_base_key(entity, source_key)
        if base is None and entity == "solic_gastos":
            # Alias legacy {"rafam_ref": "SG-<ej>-<deleg>-<nro>"}.
            try:
                ref = json.loads(source_key).get("rafam_ref")
            except (TypeError, ValueError, AttributeError):
                ref = None
            parts = str(ref or "").split("-")
            if len(parts) == 4 and parts[0] == "SG":
                base = record_base_key(
                    entity, {"ejercicio": parts[1], "deleg_solic": parts[2], "nro_solic": parts[3]},
                )
        if base is not None:
            keys.add(base)
    return keys


def _queue_by_base(entity: str, retry_store) -> dict[str, list]:
    out: dict[str, list] = {}
    for item in retry_store.list_items(entity=entity):
        base = record_base_key(entity, item.external_id)
        if base is not None:
            out.setdefault(base, []).append(item)
    return out


def close_entity(
    ledger: RunLedger,
    *,
    sink: RecordEventSink | None,
    retry_store,
    link_store,
) -> dict:
    """Cierra las cuentas de la entidad. Devuelve el resumen para las metricas."""
    entity = ledger.entity
    result = {
        "read": len(ledger.seen),
        "not_evaluated": 0,
        "with_id": 0,
        "without_id": 0,
        "in_queue": 0,
        "queued_fallo": 0,
        "queued_espera": 0,
        "unexplained": 0,
        "en_paxapos": 0,
        "fuera": 0,
        "fuera_detail": {},
        "unexplained_keys": [],
    }
    if not ledger.seen:
        return result

    with_id = _keys_with_paxapos_id(entity, link_store)
    queued = _queue_by_base(entity, retry_store)

    for key in ledger.seen:
        if key in ledger.failed:
            result["not_evaluated"] += 1
            continue
        if key in with_id:
            result["with_id"] += 1
            continue
        result["without_id"] += 1
        note = sink.note_for(entity, key) if sink is not None else None
        if note is None and entity == "proveedores" and key in ledger.proveedor_excluded:
            note_group, note_detail, note_reason = GROUP_FUERA, "excluded_provider", "proveedor excluido por configuracion"
        elif note is not None:
            note_group, note_detail, note_reason = note.group, note.detail, note.reason
        else:
            note_group = note_detail = note_reason = None

        if key in queued:
            result["in_queue"] += 1
            # Ya no corresponde migrarlo (o ya esta en Paxapos): la fila de la
            # cola quedo vieja.
            if note_group in (GROUP_FUERA, GROUP_EN_PAXAPOS):
                how = RESOLVED_OUT_OF_SCOPE if note_group == GROUP_FUERA else RESOLVED_MIGRATED
                for item in queued[key]:
                    retry_store.resolve(entity, item.external_id, how=how)
            continue

        if note_group == GROUP_FUERA:
            result["fuera"] += 1
            detail = note_detail or _normalize_reason(note_reason or "sin detalle")
            bucket = result["fuera_detail"].setdefault(
                detail,
                {"count": 0, "label": FUERA_LABELS.get(detail, _normalize_reason(note_reason or detail)), "examples": []},
            )
            bucket["count"] += 1
            if len(bucket["examples"]) < _EXAMPLES:
                bucket["examples"].append(describe_retry_key(entity, key))
            continue
        if note_group == GROUP_EN_PAXAPOS:
            result["en_paxapos"] += 1
            continue
        if note_group == GROUP_FALLO:
            retry_store.enqueue(
                entity, key, REASON_VALIDATION_CLIENT, f"no se envio: {note_reason}",
                reason_detail=note_detail or "script_skip",
            )
            result["queued_fallo"] += 1
            continue
        if note_group == GROUP_ESPERA:
            retry_store.enqueue(
                entity, key, REASON_DEPENDENCY_MISSING, f"en espera: {note_reason}",
                reason_detail=note_detail or "waiting",
            )
            result["queued_espera"] += 1
            continue

        # Sin motivo registrado: nunca se pierde en silencio.
        if key in ledger.ok_keys:
            message = (
                f"Paxapos respondio OK (modo={ledger.ok_keys[key]}) pero sin ID: "
                "el registro no quedo vinculado"
            )
            reason_code, detail = REASON_BACKEND_REJECTED, "ok_without_id"
        elif key in ledger.sent:
            message = "se envio a Paxapos pero la respuesta no trajo resultado para este registro"
            reason_code, detail = REASON_BACKEND_REJECTED, "no_response"
        else:
            message = (
                "el script leyo el registro de RAFAM pero no lo envio ni registro el motivo "
                "(revisar el log de la corrida: es un caso que el script no contempla)"
            )
            reason_code, detail = REASON_VALIDATION_CLIENT, "unexplained"
        retry_store.enqueue(entity, key, reason_code, message, reason_detail=detail)
        result["unexplained"] += 1
        if len(result["unexplained_keys"]) < 10:
            result["unexplained_keys"].append(describe_retry_key(entity, key))

    logger.info(
        "[cierre] %s: %d leido(s), %d con ID de Paxapos, %d sin ID -> %d ya en la cola, "
        "%d fallo(s) nuevo(s), %d espera(s) nueva(s), %d fuera de alcance, %d ya en Paxapos, "
        "%d sin motivo%s",
        entity, result["read"], result["with_id"], result["without_id"], result["in_queue"],
        result["queued_fallo"], result["queued_espera"], result["fuera"], result["en_paxapos"],
        result["unexplained"],
        f" ({result['not_evaluated']} de batches caidos se releen en la proxima corrida)"
        if result["not_evaluated"] else "",
    )
    if result["unexplained"]:
        logger.error(
            "[cierre] %s: %d registro(s) sin ID de Paxapos y sin motivo: %s",
            entity, result["unexplained"], ", ".join(result["unexplained_keys"]),
        )
    return result
