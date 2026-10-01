"""record_alerts.py — Un mail por cada registro que no llego a Paxapos.

El mail diario resume el dia; esto avisa en el momento, con un mail SOLO de
ese registro: que es (OC/OP/retencion/gasto/proveedor), que respondio Paxapos o
por que no se envio, y el comando `resend` listo para copiar.

Que alerta (``retry_store.ALERT_REASONS``): rechazos de Paxapos, registros
omitidos por datos invalidos y registros aislados de un batch caido. Esperar
una dependencia (OC/OP/proveedor aun no migrado) NO alerta.

Cuando (``RetryStore.pending_alerts``): al entrar a la cola, al pasar a
'permanent' y, despues de un reenvio manual (`requeue`), si vuelve a fallar.
La fila se marca como avisada solo si el mail salio: con el SMTP caido se
reintenta en la proxima corrida.

Configuracion:
    NOTIFY_RECORD_ALERTS              true/false (default true; requiere NOTIFY_* configurado)
    NOTIFY_RECORD_ALERT_MAX_PER_RUN   tope de mails individuales por corrida
                                      (default 25; 0 = sin tope). El resto va en
                                      UN mail resumen, para no recibir cientos de
                                      mails si Paxapos rompe algo para todos.
    NOTIFY_ALERT_TO                   destinatarios (default NOTIFY_TO)
"""

from __future__ import annotations

import logging
import os

from . import notifier

logger = logging.getLogger(__name__)

_DEFAULT_MAX_PER_RUN = 25


def record_alerts_enabled() -> bool:
    raw = os.getenv("NOTIFY_RECORD_ALERTS", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"} and notifier.notifications_enabled()


def _max_per_run() -> int:
    raw = os.getenv("NOTIFY_RECORD_ALERT_MAX_PER_RUN", str(_DEFAULT_MAX_PER_RUN)).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning(
            "NOTIFY_RECORD_ALERT_MAX_PER_RUN=%r no es valido; se usa %d", raw, _DEFAULT_MAX_PER_RUN,
        )
        return _DEFAULT_MAX_PER_RUN


def flush_record_alerts(retry_store) -> int:
    """Manda los mails individuales pendientes. Devuelve cuantos registros se avisaron."""
    if not record_alerts_enabled():
        return 0
    items = retry_store.pending_alerts()
    if not items:
        return 0

    cap = _max_per_run()
    individual = items if cap == 0 else items[:cap]
    overflow = [] if cap == 0 else items[cap:]

    alerted = 0
    for item in individual:
        if not notifier.notify_record_failure(item, max_attempts=retry_store.max_attempts):
            # SMTP caido o mal configurado: cortar aca (cada intento puede
            # tardar el timeout entero) y reintentar en la proxima corrida.
            logger.warning(
                "Alertas por registro: no se pudo enviar el mail; quedan %d pendientes para la proxima corrida.",
                len(items) - alerted,
            )
            return alerted
        retry_store.mark_alerted(item.entity, item.external_id, item.status)
        alerted += 1

    if overflow:
        if notifier.notify_record_failures_overflow(overflow):
            for item in overflow:
                retry_store.mark_alerted(item.entity, item.external_id, item.status)
            alerted += len(overflow)
        else:
            logger.warning(
                "Alertas por registro: no se pudo enviar el resumen de %d registro(s) sobre el tope.",
                len(overflow),
            )
    if alerted:
        logger.info("Alertas por registro enviadas: %d", alerted)
    return alerted
