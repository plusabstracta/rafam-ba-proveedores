"""batch_isolation.py — Aislar el registro que tira abajo un batch entero.

Un batch que falla entero (HTTP 500, respuesta invalida, el mapper que explota
con un dato raro) congela el watermark de la entidad: la proxima corrida
vuelve a leer las mismas filas, vuelve a fallar, y nadie sabe que registro
lo rompe. Aca el batch se parte en mitades (por clave de negocio: una OC con
sus items, una OP con sus gastos) hasta encontrar el o los registros que
fallan solos:

* lo que pasa en un sub-batch queda migrado normalmente;
* el registro que falla solo va a la cola como ``batch_failed`` (dispara el
  mail por registro de record_alerts.py y se reintenta en cada corrida);
* con todo OK o en la cola, el batch cuenta como recuperado y el watermark
  avanza.

No se biseca cuando el problema no es de un registro: backend/red caidos
(``is_infra_failure``) o cuando NINGUN sub-batch pasa (Paxapos falla con
todo). Ahi el batch queda caido como antes y avisa incident_alerts.py.

Un registro que ya quedo ``batch_failed`` en una corrida anterior se manda
solo (fuera del batch) en las siguientes: no vuelve a romper el batch ni a
gastar requests de biseccion hasta que se arregle o pase a 'permanent'.

Configuracion:
    RAFAM_BISECT_MAX_REQUESTS   requests extra por batch para aislar (default 32; 0 = no bisecar)
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import re
import sqlite3
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Callable

from .auth_circuit_breaker import AuthCircuitOpenError
from .backend_errors import BackendInfraError
from .retry_labels import RESENDABLE_ENTITIES, describe_retry_key, record_base_key, record_key_from_row
from .retry_store import ALERT_REASONS, REASON_BATCH_FAILED, STATUS_PENDING

logger = logging.getLogger(__name__)

_DEFAULT_MAX_REQUESTS = 32
# Sub-batches fallidos sin ningun OK antes de concluir que el problema es el
# backend y no un registro (con un unico registro malo, una de las dos mitades
# del primer corte siempre pasa).
_SYSTEMIC_FAILURES = 4

# Codigos HTTP que hablan del backend/proxy/credenciales, nunca de un registro.
_INFRA_HTTP_STATUS = frozenset({401, 403, 404, 405, 407, 408, 429, 502, 503, 504})
_HTTP_STATUS_RE = re.compile(r"^HTTP (\d{3})\b")


def bisect_max_requests() -> int:
    raw = os.getenv("RAFAM_BISECT_MAX_REQUESTS", str(_DEFAULT_MAX_REQUESTS)).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("RAFAM_BISECT_MAX_REQUESTS=%r no es valido; se usa %d", raw, _DEFAULT_MAX_REQUESTS)
        return _DEFAULT_MAX_REQUESTS


def _http_status(exc: Exception) -> int | None:
    match = _HTTP_STATUS_RE.match(str(exc))
    return int(match.group(1)) if match else None


def is_infra_failure(exc: Exception) -> bool:
    """True si el fallo es del backend, la red o el estado local: no de un registro.

    Con estos errores partir el batch no sirve (fallarian todas las mitades) y
    solo agrega carga a un backend que ya esta mal.
    """
    if isinstance(exc, (BackendInfraError, AuthCircuitOpenError, OSError, http.client.HTTPException, sqlite3.Error)):
        return True
    status = _http_status(exc)
    if status is not None:
        return status in _INFRA_HTTP_STATUS
    msg = str(exc)
    if msg.startswith("URL error") or msg.startswith("Respuesta no JSON"):
        return True
    return "timed out" in msg.lower()


def failure_detail(exc: Exception) -> str:
    """reason_detail para un registro aislado (se ve en la cola y en el mail)."""
    status = _http_status(exc)
    if status is not None:
        return f"http_{status}"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_response"
    msg = str(exc)
    if "sin external_id utilizable" in msg:
        return "untracked_errors"
    if "errores para todas las filas" in msg:
        return "all_rows_rejected"
    if type(exc) is RuntimeError:
        return "batch_error"
    # KeyError/TypeError/ValueError...: el script no pudo armar el registro.
    return "script_error"


def describe_failure(exc: Exception) -> str:
    msg = str(exc).strip()
    if type(exc) is RuntimeError:
        return msg or "RuntimeError"
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


# ─── Biseccion (algoritmo puro) ──────────────────────────────────────────────


@dataclass
class BisectResult:
    ok: list = field(default_factory=list)          # claves cuyo sub-batch paso
    isolated: dict = field(default_factory=dict)    # clave -> excepcion (fallo sola)
    unresolved: list = field(default_factory=list)  # sin resolver (tope, backend caido)
    requests: int = 0
    failures: int = 0
    success_seen: bool = False
    infra_exc: Exception | None = None
    # Ningun sub-batch paso: falla todo, no un registro.
    systemic: bool = False


def bisect_keys(
    keys: list,
    send: Callable[[list], Exception | None],
    *,
    max_requests: int,
) -> BisectResult:
    """Parte ``keys`` (que fallaron juntas) hasta aislar las que fallan solas.

    ``send(subset)`` manda ese sub-batch y devuelve la excepcion o None. Cada
    corte manda las dos mitades y sigue solo por las que fallan, asi que un
    registro malo en N cuesta ~2*log2(N) requests. Un registro se declara
    aislado solo si fallo SOLO (nunca por descarte).
    """
    res = BisectResult()
    stack = [list(keys)]
    while stack:
        subset = stack.pop()
        if res.infra_exc is not None or res.systemic:
            res.unresolved.extend(subset)
            continue
        mid = (len(subset) + 1) // 2
        failed_halves = []
        for half in (subset[:mid], subset[mid:]):
            if not half:
                continue
            if res.infra_exc is not None or res.systemic or res.requests >= max_requests:
                res.unresolved.extend(half)
                continue
            exc = send(half)
            res.requests += 1
            if exc is None:
                res.ok.extend(half)
                res.success_seen = True
                continue
            res.failures += 1
            if is_infra_failure(exc):
                res.infra_exc = exc
                res.unresolved.extend(half)
                continue
            if len(half) == 1:
                res.isolated[half[0]] = exc
            else:
                failed_halves.append(half)
            if not res.success_seen and res.failures >= _SYSTEMIC_FAILURES:
                res.systemic = True
        # Primero la primera mitad (profundidad), para aislar lo antes posible.
        stack.extend(reversed(failed_halves))
    if not res.success_seen and res.failures >= 2:
        res.systemic = True
    return res


# ─── Aislador por entidad ────────────────────────────────────────────────────


@dataclass
class BatchWriteResult:
    # Error que dejo registros sin resolver (None = batch OK o recuperado).
    error: Exception | None = None
    # `error` es del backend/red (o fallo todo): no hay registro que culpar.
    infra: bool = False
    # Claves aisladas -> mensaje (encoladas como batch_failed).
    isolated: dict = field(default_factory=dict)
    # Claves que quedaron sin resolver (el batch sigue caido).
    unresolved: list = field(default_factory=list)
    # Primer error del batch, aunque despues se haya recuperado.
    first_error: Exception | None = None
    # Requests extra (biseccion + registros ya conocidos mandados solos).
    requests: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def recovered(self) -> bool:
        return self.error is None and self.first_error is not None


def group_rows_by_key(entity: str, columns: list[str], rows: list[tuple]) -> dict:
    """{clave base (o None): filas}, en el orden del batch."""
    groups: dict = {}
    for row in rows:
        groups.setdefault(record_key_from_row(entity, dict(zip(columns, row))), []).append(row)
    return groups


class BatchIsolator:
    """Manda los batches de UNA entidad y aisla los registros que los rompen.

    Una instancia por entidad y corrida: acumula la evidencia de que el backend
    responde (``post_ok``) y las metricas (``extra_requests``,
    ``records_isolated``, ``batches_recovered``).

    ``after_write(exc)`` se llama despues de CADA request (batch o sub-batch)
    para que el caller junte metricas o resultados por fila. ``delay`` se
    duerme antes de un request solo si el anterior llego a hacer un POST
    (un batch sin cambios no le pega a Paxapos, no hay por que esperar).
    """

    def __init__(
        self,
        exporter,
        entity: str,
        *,
        retry_store=None,
        dry_run: bool = False,
        max_requests: int | None = None,
        delay: float = 0.0,
        after_write: Callable[[Exception | None], None] | None = None,
    ):
        self._exporter = exporter
        self.entity = entity
        self._retry_store = retry_store
        self._dry_run = dry_run
        self._max_requests = bisect_max_requests() if max_requests is None else max(0, max_requests)
        self._delay = delay
        self._after_write = after_write
        # Sin cola (y fuera de dry-run) no hay donde dejar al aislado: partir
        # el batch solo gastaria requests.
        self.enabled = (
            entity in RESENDABLE_ENTITIES
            and self._max_requests > 0
            and (retry_store is not None or dry_run)
        )
        self.post_ok = False
        self._last_posted = False
        self._queue_sets: tuple[set, set] | None = None
        self.extra_requests = 0
        self.records_isolated = 0
        self.batches_recovered = 0

    # ── API ──────────────────────────────────────────────────────────────

    def write(self, columns: list[str], rows: list[tuple]) -> BatchWriteResult:
        result = BatchWriteResult()
        if not self.enabled:
            exc = self._send(columns, rows)
            if exc is not None:
                result.first_error = result.error = exc
                result.infra = is_infra_failure(exc)
            return result

        groups = group_rows_by_key(self.entity, columns, rows)
        known_bad = self._known_bad()
        solo = [k for k in groups if k is not None and k in known_bad]
        main = [k for k in groups if k is None or k not in known_bad]

        with self._attempt_scope():
            if main:
                exc = self._send_keys(columns, groups, main)
                if exc is not None:
                    result.first_error = exc
                    self._recover(columns, groups, main, exc, result)
            for key in solo:
                if result.infra:
                    result.unresolved.append(key)
                    continue
                result.requests += 1
                exc = self._send_keys(columns, groups, [key])
                if exc is None:
                    if self._last_sent() == 0:
                        # El mapper ya no lo manda (sin cambios, regla de
                        # negocio): ya no rompe nada, no tiene que quedar en la
                        # cola como batch_failed. Si se envio, la respuesta ya
                        # lo resolvio o lo encolo con su motivo real.
                        self._drop_known_bad(key)
                    continue
                if result.first_error is None:
                    result.first_error = exc
                if is_infra_failure(exc):
                    result.error, result.infra = exc, True
                    result.unresolved.append(key)
                else:
                    # Ya venia fallando solo: alcanza como evidencia.
                    self._isolate(key, exc, result)

        self.extra_requests += result.requests
        self.records_isolated += len(result.isolated)
        if result.recovered:
            self.batches_recovered += 1
        return result

    # ── internals ────────────────────────────────────────────────────────

    def _recover(self, columns, groups, keys, exc, result: BatchWriteResult) -> None:
        if is_infra_failure(exc):
            result.error, result.infra = exc, True
            result.unresolved.extend(keys)
            return

        if len(keys) == 1:
            # Sin otro registro con el que comparar: solo se culpa al registro
            # si el backend ya respondio bien en esta corrida o si ese registro
            # ya venia fallando. Si no, puede ser el backend: queda caido.
            key = keys[0]
            if key is not None and (self.post_ok or key in self._failing()):
                self._isolate(key, exc, result)
            else:
                result.error = exc
                result.unresolved.append(key)
            return

        logger.warning(
            "[%s] batch de %d registro(s) fallo entero (%s); se parte para aislar el que falla.",
            self.entity, len(keys), describe_failure(exc)[:300],
        )
        bis = bisect_keys(
            keys,
            lambda subset: self._send_keys(columns, groups, subset),
            max_requests=self._max_requests,
        )
        result.requests += bis.requests
        if bis.infra_exc is not None:
            result.error, result.infra = bis.infra_exc, True
        elif bis.systemic:
            logger.error(
                "[%s] ningun sub-batch paso (%d fallaron): no es un registro, es Paxapos. "
                "El batch queda caido.",
                self.entity, bis.failures,
            )
            result.error, result.infra = exc, True

        failing = self._failing()
        for key, err in bis.isolated.items():
            if key is not None and (bis.success_seen or key in failing):
                self._isolate(key, err, result)
            else:
                result.unresolved.append(key)
                if result.error is None:
                    result.error = err
        if bis.unresolved:
            result.unresolved.extend(bis.unresolved)
            if result.error is None:
                logger.error(
                    "[%s] se agoto el tope de %d requests (RAFAM_BISECT_MAX_REQUESTS) sin aislar "
                    "%d registro(s); el batch queda caido.",
                    self.entity, self._max_requests, len(bis.unresolved),
                )
                result.error = exc

    def _isolate(self, key: str, exc: Exception, result: BatchWriteResult) -> None:
        message = describe_failure(exc)
        result.isolated[key] = message
        self._known_bad().add(key)
        self._failing().add(key)
        logger.error(
            "[%s] %s falla solo y se aisla del batch (queda en la cola como batch_failed): %s",
            self.entity, describe_retry_key(self.entity, key), message[:500],
        )
        if not self._dry_run:
            self._retry_store.enqueue(
                self.entity, key, REASON_BATCH_FAILED, message[:2000],
                reason_detail=failure_detail(exc),
            )

    def _drop_known_bad(self, key: str) -> None:
        self._known_bad().discard(key)
        if self._retry_store is None or self._dry_run:
            return
        try:
            self._retry_store.resolve_if_reason(self.entity, key, REASON_BATCH_FAILED)
        except Exception:  # noqa: BLE001 - se reintenta en la proxima corrida
            logger.warning("[%s] no se pudo sacar %s de la cola", self.entity, key, exc_info=True)

    def _send_keys(self, columns, groups, keys) -> Exception | None:
        return self._send(columns, [row for key in keys for row in groups[key]])

    def _send(self, columns, rows) -> Exception | None:
        if self._last_posted and self._delay > 0:
            time.sleep(self._delay)
        exc = None
        try:
            self._exporter.write_batch(self.entity, columns, rows)
        except Exception as caught:  # noqa: BLE001 - se clasifica arriba
            exc = caught
        sent = self._last_sent()
        # Con error se asume que hubo POST (no se sabe si el fallo fue antes).
        self._last_posted = exc is not None or sent > 0
        if exc is None and sent > 0:
            self.post_ok = True
        if self._after_write is not None:
            self._after_write(exc)
        return exc

    def _last_sent(self) -> int:
        metrics_fn = getattr(self._exporter, "get_last_batch_migrator_metrics", None)
        if not callable(metrics_fn):
            return 0
        try:
            return int((metrics_fn() or {}).get("sent", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _attempt_scope(self):
        scope = getattr(self._retry_store, "attempt_scope", None)
        return scope() if callable(scope) else nullcontext()

    def _load_queue_sets(self) -> tuple[set, set]:
        if self._queue_sets is None:
            known_bad: set = set()
            failing: set = set()
            if self._retry_store is not None:
                try:
                    items = self._retry_store.list_items(entity=self.entity)
                except Exception:  # noqa: BLE001 - sin cola se aisla igual, con menos evidencia
                    logger.warning("[%s] no se pudo leer la cola para aislar batches", self.entity, exc_info=True)
                    items = []
                for item in items:
                    if item.reason_code not in ALERT_REASONS:
                        continue
                    base = record_base_key(self.entity, item.external_id)
                    if base is None:
                        continue
                    failing.add(base)
                    if item.reason_code == REASON_BATCH_FAILED and item.status == STATUS_PENDING:
                        known_bad.add(base)
            self._queue_sets = (known_bad, failing)
        return self._queue_sets

    def _known_bad(self) -> set:
        """Claves 'pending' como batch_failed: se mandan solas."""
        return self._load_queue_sets()[0]

    def _failing(self) -> set:
        """Claves que ya estaban en la cola con un motivo que alerta."""
        return self._load_queue_sets()[1]
