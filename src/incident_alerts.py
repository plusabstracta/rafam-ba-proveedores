"""incident_alerts.py — Un mail por incidente cuando una entidad no se sincroniza.

Las alertas por registro (record_alerts.py) cubren UN registro que no llega a
Paxapos. Esto cubre cuando el problema es la entidad entera y no hay registro
que culpar:

* ``backend``: Paxapos o la red caidos (SQLSTATE, timeout, HTTP 502/503, o
  Paxapos falla con TODOS los registros del batch);
* ``batch``:   un batch se cae y no se pudo aislar el registro que lo rompe;
* ``error``:   la entidad (o la corrida entera) no llega a enviar nada.

En los tres casos el watermark queda congelado y las filas se releen solas en
la proxima corrida: no se pierde nada, pero alguien tiene que enterarse.

Se avisa UNA vez al abrir el incidente y otra cuando se normaliza; mientras
siga abierto no se repite. Una falla de una sola corrida (un timeout suelto)
no avisa: tiene que repetirse NOTIFY_INCIDENT_AFTER_RUNS corridas seguidas.
El estado vive en ``state/alert_incidents.json``.

Configuracion:
    NOTIFY_INCIDENT_ALERTS       true/false (default true; requiere NOTIFY_* configurado)
    NOTIFY_INCIDENT_AFTER_RUNS   corridas seguidas con falla antes de avisar (default 2)
    RAFAM_INCIDENTS_PATH         archivo de estado (default state/alert_incidents.json)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from . import notifier

logger = logging.getLogger(__name__)

KIND_BACKEND = "backend"
KIND_BATCH = "batch"
KIND_ERROR = "error"
# Entidad sintetica para la corrida que se cae antes de procesar entidades.
RUN_ENTITY = "corrida"

_DEFAULT_PATH = "state/alert_incidents.json"
_DEFAULT_AFTER_RUNS = 2


def _path() -> Path:
    return Path(os.getenv("RAFAM_INCIDENTS_PATH", _DEFAULT_PATH))


def incident_alerts_enabled() -> bool:
    raw = os.getenv("NOTIFY_INCIDENT_ALERTS", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"} and notifier.notifications_enabled()


def _after_runs() -> int:
    raw = os.getenv("NOTIFY_INCIDENT_AFTER_RUNS", str(_DEFAULT_AFTER_RUNS)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("NOTIFY_INCIDENT_AFTER_RUNS=%r no es valido; se usa %d", raw, _DEFAULT_AFTER_RUNS)
        return _DEFAULT_AFTER_RUNS


def _now_utc() -> str:
    # Mismo formato que retry_queue (UTC), para convertir igual en los mails.
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def load_incidents() -> dict:
    path = _path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("incident_alerts: estado corrupto en %s, se ignora", path)
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def update_incidents(observations: list[dict]) -> int:
    """Actualiza los incidentes con lo que paso en esta corrida.

    ``observations``: ``[{"entity", "kind" (None = sin problema), "detail", "keys"}]``,
    una por entidad que corrio. Las entidades que no corrieron no se tocan.
    Devuelve la cantidad de mails enviados (aperturas + normalizaciones).
    """
    state = load_incidents()
    enabled = incident_alerts_enabled()
    threshold = _after_runs()
    now = _now_utc()
    sent = 0
    changed = False

    for obs in observations:
        entity = str(obs.get("entity") or "?")
        kind = obs.get("kind")
        current = state.get(entity)
        if kind:
            if not isinstance(current, dict):
                current = {"since": now, "runs": 0, "notified_at": None}
                state[entity] = current
            current["runs"] = int(current.get("runs") or 0) + 1
            current["kind"] = kind
            current["last_seen"] = now
            current["detail"] = str(obs.get("detail") or "")[:4000]
            current["keys"] = list(obs.get("keys") or [])[:10]
            changed = True
            if enabled and not current.get("notified_at") and current["runs"] >= threshold:
                if notifier.notify_incident(entity, current):
                    current["notified_at"] = now
                    sent += 1
                else:
                    logger.warning("incident_alerts: no se pudo avisar el incidente de %s; se reintenta en la proxima corrida", entity)
        elif current is not None:
            if isinstance(current, dict) and current.get("notified_at"):
                if enabled and notifier.notify_incident_resolved(entity, current, resolved_at=now):
                    sent += 1
                logger.info("incident_alerts: %s se normalizo (con fallas desde %s)", entity, current.get("since"))
            del state[entity]
            changed = True

    if changed:
        _save(state)
    return sent
