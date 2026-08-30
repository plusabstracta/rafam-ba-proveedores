"""auth_circuit_breaker.py — Corte local ante 401/403 sostenidos del migrator.

Contexto (paxapos#361): un cliente RAFAM con credencial faltante/incorrecta
quedó pegando ~2 req/min contra `lookups.json` durante 2h (240 requests, todas
403) porque cada invocación de cron/proceso reintentaba desde cero sin memoria
de que la corrida anterior ya había fallado por auth. Un reintento NUNCA
arregla una credencial mala — solo ensucia logs y quema el rate-limit del WAF
(mismo patrón que baneó otros clientes de la plataforma, ver runbook de
CrowdSec). La respuesta correcta ante 401/403 es CORTAR, no reintentar.

Este módulo agrega un circuit breaker persistido en disco (sobrevive entre
invocaciones de proceso — el pipeline corre como comandos de cron cortos, no
como daemon) que:
  - Ante 401/403, abre el circuito con backoff exponencial acotado.
  - Mientras el circuito está abierto, `check()` corta ANTES de armar/enviar
    el request: cero llamadas de red, cero entradas nuevas en el log de 403
    del backend.
  - Ante un 2xx, cierra el circuito (reset total).

Se engancha en los dos puntos donde convergen TODAS las llamadas HTTP al
migrator: `PaxaposHttpClient._execute_json_request` (import) y
`exporter._fetch_migrator_json` (spec/lookups/resolver_*).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Códigos que consideramos "falla de autenticación" — un retry no la arregla,
# hace falta que alguien corrija la credencial. Los demás 4xx (400, 404, 422,
# etc.) son errores de negocio/validación y no tocan este breaker.
AUTH_FAILURE_STATUS = frozenset({401, 403})

_DEFAULT_PATH = "state/migrator_auth_circuit.json"

# Backoff exponencial acotado: 5 min, 10, 20, 40 min, tope en 60 min. Evita
# tanto el loop ciego (backoff=0) como un corte tan largo que un fix legítimo
# de la api_key tarde horas en surtir efecto.
BASE_COOLDOWN_SECONDS = 300
MAX_COOLDOWN_SECONDS = 3600
# Tras esta cantidad de fallas consecutivas ya estamos en el tope; no tiene
# sentido seguir calculando potencias cada vez más grandes.
_MAX_TRACKED_FAILURES = 10


class AuthCircuitOpenError(RuntimeError):
    """El circuito de auth está abierto: no se envía el request.

    Subclase de RuntimeError a propósito — todo el manejo de errores existente
    en main.py/exporter.py (`except Exception`/`except RuntimeError`) sigue
    capturándolo y reportándolo sin cambios; solo cambia que la excepción
    aparece SIN haber tocado la red.
    """


def _path() -> Path:
    return Path(os.getenv("RAFAM_AUTH_CIRCUIT_PATH", _DEFAULT_PATH))


def _load() -> dict:
    path = _path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        logger.warning("auth_circuit_breaker: estado corrupto en %s, se ignora", path)
        return {}


def _save(data: dict) -> None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Escritura atómica (tmp + rename) — evita dejar el archivo de estado
        # truncado/corrupto si el proceso muere a mitad de escritura (el lock
        # de cron no protege este archivo).
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp_path, path)
    except OSError:
        # No poder persistir el breaker no debe tumbar la corrida: peor caso,
        # se pierde la memoria del corte y se vuelve al comportamiento previo
        # (sin circuit breaker) para ESTA corrida.
        logger.warning("auth_circuit_breaker: no se pudo escribir estado en %s", path, exc_info=True)


def check(context: str = "") -> None:
    """Levanta AuthCircuitOpenError si el circuito sigue abierto. No hace red."""
    data = _load()
    opened_until = data.get("opened_until")
    if not opened_until:
        return
    now = time.time()
    if now >= opened_until:
        return
    remaining = int(opened_until - now)
    failures = data.get("consecutive_failures", 0)
    suffix = f" ({context})" if context else ""
    raise AuthCircuitOpenError(
        f"Circuito de auth abierto{suffix}: {failures} fallas 401/403 consecutivas. "
        f"No se reintenta hasta dentro de {remaining}s. Verificar PAXAPOS_API_KEY "
        f"(AGENT_API_KEY del lado del backend) antes de que vuelva a intentarse."
    )


def record_failure(status: int, context: str = "") -> None:
    """Registra un 401/403 y abre/extiende el circuito con backoff exponencial."""
    if status not in AUTH_FAILURE_STATUS:
        return
    data = _load()
    failures = min(int(data.get("consecutive_failures", 0)) + 1, _MAX_TRACKED_FAILURES)
    cooldown = min(BASE_COOLDOWN_SECONDS * (2 ** (failures - 1)), MAX_COOLDOWN_SECONDS)
    opened_until = time.time() + cooldown
    _save(
        {
            "consecutive_failures": failures,
            "last_status": status,
            "last_failure_ts": time.time(),
            "opened_until": opened_until,
        }
    )
    suffix = f" ({context})" if context else ""
    logger.warning(
        "auth_circuit_breaker: HTTP %s%s — falla #%d, circuito abierto por %ds. "
        "Reintentar antes de eso no tiene sentido: revisar PAXAPOS_API_KEY.",
        status, suffix, failures, cooldown,
    )


def record_success() -> None:
    """Cierra el circuito. Llamar tras cualquier respuesta 2xx del migrator."""
    path = _path()
    if not path.exists():
        return
    try:
        path.unlink()
    except OSError:
        logger.warning("auth_circuit_breaker: no se pudo limpiar estado en %s", path, exc_info=True)
