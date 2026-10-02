"""record_alerts.py — Mail por cada registro que no llego a Paxapos.

El mail diario resume el dia; esto avisa en el momento, al final de cada
corrida: que registro es (OC/OP/retencion/gasto/proveedor), que respondio
Paxapos o por que no se envio, y el comando `resend` listo para copiar.

* Si en la corrida hay UN registro para avisar: un mail solo de ese registro.
* Si hay mas de uno: UN mail con todos, en una tabla con una fila por
  registro y una columna por dato (`notifier.notify_record_failures_table`).

Que alerta (``retry_store.ALERT_REASONS``): rechazos de Paxapos, registros
omitidos por datos invalidos, registros aislados de un batch caido y
registros leidos sin ID y sin motivo. Esperar una dependencia (OC/OP/proveedor
aun no migrado) alerta solo si la espera supera RAFAM_WAIT_ALERT_DAYS dias
(default 5).

Cuando (``RetryStore.pending_alerts``): al entrar a la cola, al pasar a
'permanent', al vencer una espera y, despues de un reenvio manual
(`requeue`), si vuelve a fallar.
Las filas se marcan como avisadas solo si el mail salio: con el SMTP caido se
reintenta en la proxima corrida.

Configuracion:
    NOTIFY_RECORD_ALERTS          true/false (default true; requiere NOTIFY_* configurado)
    NOTIFY_RECORD_ALERT_MAX_ROWS  filas de la tabla del mail agrupado (default 500;
                                  0 = sin tope); el resto se resume por causa al pie.
    NOTIFY_ALERT_TO               destinatarios (default NOTIFY_TO)
"""

from __future__ import annotations

import logging
import os

from . import notifier

logger = logging.getLogger(__name__)


def record_alerts_enabled() -> bool:
    raw = os.getenv("NOTIFY_RECORD_ALERTS", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"} and notifier.notifications_enabled()


def _alert_kind(item) -> str:
    """Estado con el que queda marcada la fila avisada ('stale' para una espera)."""
    kind = getattr(item, "alert_kind", None)
    return kind if isinstance(kind, str) else item.status


def flush_record_alerts(retry_store, link_store=None) -> int:
    """Manda los avisos pendientes (1 mail, o 1 agrupado si son varios).
    Devuelve cuantos registros se avisaron.

    Con ``link_store`` el mail incluye el ID de Paxapos cuando el registro ya
    existe alli (fallo una actualizacion, no un alta).
    """
    if not record_alerts_enabled():
        return 0
    items = retry_store.pending_alerts()
    if not items:
        return 0
    if link_store is not None:
        from .record_ledger import with_paxapos_ids

        items = with_paxapos_ids(items, link_store)

    if len(items) == 1:
        sent = notifier.notify_record_failure(items[0], max_attempts=retry_store.max_attempts)
    else:
        sent = notifier.notify_record_failures_table(items, max_attempts=retry_store.max_attempts)
    if not sent:
        # SMTP caido o mal configurado: no se marca nada y se reintenta en la
        # proxima corrida.
        logger.warning(
            "Alertas por registro: no se pudo enviar el mail; quedan %d pendientes para la proxima corrida.",
            len(items),
        )
        return 0
    for item in items:
        retry_store.mark_alerted(item.entity, item.external_id, _alert_kind(item))
    logger.info(
        "Alertas por registro enviadas: %d registro(s) en %s",
        len(items), "1 mail" if len(items) == 1 else "1 mail agrupado",
    )
    return len(items)
