"""retry_store.py — Cola de reintentos para filas incompletas/rechazadas (F1).

Garantiza que ninguna fila se pierda: las que se omiten en el cliente (por
validacion de boundary o por dependencia aun no migrada) y las que el receptor
rechaza (207 con error por fila) se encolan aqui y se reintentan en cada
corrida hasta completarse. El watermark del checkpoint puede avanzar con
seguridad porque lo pendiente queda registrado en esta cola, no en el cursor.

Decision de diseno (4-jun-2026): manejo fila-a-fila — un batch de 500 NO se
cancela por 1 fila mala; la fila mala va a la cola y el resto se procesa.

Ciclo de vida de una fila:

* ``pending``: se reintenta en cada corrida (cada 10 minutos).
* ``permanent``: agoto ``max_attempts`` intentos seguidos. Ya no se reintenta
  en cada corrida, pero tampoco se abandona: se vuelve a intentar sola cada
  ``RAFAM_PERMANENT_RETRY_HOURS`` horas (``next_retry_after``), asi una
  correccion en RAFAM o en Paxapos se migra sin que nadie corra un comando.
  Excepcion: los rechazos terminales (``mark_permanent``, p.ej. el destino se
  borro a mano en Paxapos) tienen ``auto_retry = 0`` y solo vuelven a mano.

Comparte el mismo archivo SQLite que el resto del estado local
(``LOCAL_STATE_DB_PATH``). Acepta una conexion sqlite3 inyectada para permitir
escrituras atomicas junto con el link store dentro de un mismo batch (F2).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import getpass
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .retry_labels import describe_retry_key, record_base_key

logger = logging.getLogger(__name__)

_TABLE = "retry_queue"
_ITEM_COLUMNS = (
    "entity, external_id, reason_code, reason_detail, error_message, attempts, "
    "status, first_seen, last_attempt, payload_snapshot, alert_state, "
    "next_retry_after, auto_retry"
)
# Historial de lo que sale de la cola (se migro, quedo fuera de alcance, se
# descarto a mano): el mail diario le muestra al operador lo que se destrabo
# (p.ej. despues de corregir el dato en RAFAM). Se poda a los 30 dias.
_RESOLVED_TABLE = "retry_resolved"

# reason_code: clasifica por que la fila no se pudo migrar todavia.
REASON_VALIDATION_CLIENT = "validation_client"      # rechazada por validation.py
REASON_DEPENDENCY_MISSING = "dependency_missing"    # FK/OC aun no migrada
REASON_BACKEND_REJECTED = "backend_rejected"        # 207: error por fila en el receptor
REASON_BACKEND_UNAVAILABLE = "backend_unavailable"  # SQL/PHP roto en el receptor; la fila esta bien
REASON_BATCH_FAILED = "batch_failed"                # aislada de un batch que fallo entero

STATUS_PENDING = "pending"
STATUS_PERMANENT = "permanent"

# Como salio una fila de la cola (`retry_resolved.how`).
RESOLVED_MIGRATED = "migrado"
RESOLVED_OUT_OF_SCOPE = "fuera_de_alcance"
RESOLVED_DISMISSED = "descartado"
# El script ya no lo envia (sin cambios respecto de Paxapos o regla de negocio).
RESOLVED_NOT_SENT = "sin_envio"

# Tras este numero de intentos sin exito, la fila pasa a 'permanent' y se
# reporta en la reconciliacion en vez de reintentarse indefinidamente.
DEFAULT_MAX_ATTEMPTS = 10

# Las filas en espera de una dependencia (OC/gasto aun no migrado) NO cuentan
# intentos: con el pipeline corriendo cada 10 minutos, contar cada corrida como
# "intento" volvia permanent una OP en menos de 2 horas, cuando su OC puede
# confirmarse dias despues. La fila espera lo que haga falta; si la dependencia
# nunca aparece, la reconciliacion la reporta igual (sigue 'pending' en cola).
# Lo mismo aplica cuando el que fallo es el backend (tabla inexistente, fatal
# PHP): castigar a la fila por un deploy incompleto del tenant la volvia
# permanent antes de que alguien arreglara el server.
_NO_ATTEMPT_COUNT_REASONS = frozenset({REASON_DEPENDENCY_MISSING, REASON_BACKEND_UNAVAILABLE})

# Motivos que disparan un mail individual (src/record_alerts.py): algo que no
# se mando por datos invalidos o que Paxapos rechazo. Esperar una dependencia
# no alerta (salvo que la espera se estire, ver WAIT_REASONS); un backend
# caido se avisa una vez por incidente, no por fila.
ALERT_REASONS = frozenset({REASON_BACKEND_REJECTED, REASON_VALIDATION_CLIENT, REASON_BATCH_FAILED})

# Esperas: el registro esta bien pero depende de otro (OC/OP/proveedor aun no
# migrado, OC sin confirmar). Si la espera supera RAFAM_WAIT_ALERT_DAYS dias
# deja de ser normal: avisa una vez (alert_state = ALERT_STATE_STALE) y pasa a
# la lista del operador del mail diario.
WAIT_REASONS = frozenset({REASON_DEPENDENCY_MISSING})
ALERT_STATE_STALE = "stale"

DEFAULT_PERMANENT_RETRY_HOURS = 6.0
DEFAULT_WAIT_ALERT_DAYS = 5.0

# reason_detail de los rechazos terminales (`mark_permanent`): no se
# reintentan solos. Solo se usa para migrar filas viejas al crear auto_retry.
_TERMINAL_DETAILS = ("destination_deleted",)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        logger.warning("%s=%r no es valido; se usa %s", name, raw, default)
        return default


def permanent_retry_hours() -> float:
    """Cada cuantas horas se reintenta solo un 'permanent' (0 = nunca, solo a mano)."""
    return _env_float("RAFAM_PERMANENT_RETRY_HOURS", DEFAULT_PERMANENT_RETRY_HOURS)


def wait_alert_days() -> float:
    """Dias de espera de una dependencia antes de avisar (0 = no avisar)."""
    return _env_float("RAFAM_WAIT_ALERT_DAYS", DEFAULT_WAIT_ALERT_DAYS)


def _sqlite_modifier(hours: float) -> str:
    return f"+{int(round(hours * 3600))} seconds"


@dataclass(frozen=True)
class RetryItem:
    entity: str
    external_id: str
    reason_code: str
    reason_detail: Optional[str]
    error_message: Optional[str]
    attempts: int
    status: str
    first_seen: str
    last_attempt: Optional[str]
    payload_snapshot: Optional[str] = None
    # Ultimo `status` por el que se mando el mail individual (None = nunca).
    alert_state: Optional[str] = None
    # 'permanent': cuando se vuelve a intentar solo (UTC). None = no se reintenta solo.
    next_retry_after: Optional[str] = None
    # 0 = rechazo terminal: no se reintenta solo aunque este 'permanent'.
    auto_retry: int = 1
    # ID en Paxapos si el registro ya existe alli (fallo una actualizacion).
    # No vive en la cola: lo completa quien arma el mail (link store).
    paxapos_id: Optional[str] = None

    @property
    def is_wait(self) -> bool:
        return self.reason_code in WAIT_REASONS

    @property
    def alert_kind(self) -> str:
        """Estado por el que se avisa (y se marca) esta fila."""
        return ALERT_STATE_STALE if self.is_wait else self.status


class RetryStore:
    """Persistencia de la cola de reintentos (una tabla, multi-entidad)."""

    def __init__(
        self,
        db_path: str | None = None,
        *,
        conn: sqlite3.Connection | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        permanent_retry_hours: float | None = None,
        wait_alert_days: float | None = None,
    ):
        self._max_attempts = max_attempts
        # None = leer RAFAM_PERMANENT_RETRY_HOURS / RAFAM_WAIT_ALERT_DAYS en cada uso.
        self._permanent_retry_hours = permanent_retry_hours
        self._wait_alert_days = wait_alert_days
        # Filas que ya sumaron un intento dentro del `attempt_scope` activo.
        self._scope_counted: set[tuple[str, str]] | None = None
        if conn is not None:
            # Conexion compartida (ej. la del EntityLinkStore) → permite que el
            # enqueue/dequeue participe de la misma transaccion del batch.
            self._conn = conn
            self._owns_conn = False
        else:
            if not db_path:
                db_path = os.getenv("LOCAL_STATE_DB_PATH", "state/checkpoint.db")
            path = Path(db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(path), timeout=5.0)
            self._conn.row_factory = sqlite3.Row
            self._owns_conn = True
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.execute("PRAGMA busy_timeout=5000")
            except sqlite3.Error:
                pass
        self._ensure_table()

    # ── internal ──────────────────────────────────────────────────────────

    def _ensure_table(self) -> None:
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                entity TEXT NOT NULL,
                external_id TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                reason_detail TEXT,
                error_message TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                first_seen TEXT NOT NULL,
                last_attempt TEXT,
                next_retry_after TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                payload_snapshot TEXT,
                alert_state TEXT,
                alerted_at TEXT,
                auto_retry INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (entity, external_id)
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in self._conn.execute(f"PRAGMA table_info({_TABLE})").fetchall()
        }
        if "reason_detail" not in existing_columns:
            self._conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN reason_detail TEXT")
        if "alert_state" not in existing_columns:
            self._conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN alert_state TEXT")
            self._conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN alerted_at TEXT")
            # Lo que ya estaba en la cola antes de existir las alertas por
            # registro se da por avisado (ya figuraba en el mail diario): sin
            # esto el primer deploy mandaria un mail por cada fila vieja.
            self._conn.execute(f"UPDATE {_TABLE} SET alert_state = status")
        if "auto_retry" not in existing_columns:
            self._conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN auto_retry INTEGER NOT NULL DEFAULT 1")
            terminal = ", ".join("?" for _ in _TERMINAL_DETAILS)
            self._conn.execute(
                f"UPDATE {_TABLE} SET auto_retry = 0 "
                f"WHERE status = ? AND reason_detail IN ({terminal})",
                (STATUS_PERMANENT, *_TERMINAL_DETAILS),
            )
            # Los 'permanent' de antes quedaban trabados para siempre: se
            # reintentan en la proxima corrida y despues cada
            # RAFAM_PERMANENT_RETRY_HOURS.
            self._conn.execute(
                f"UPDATE {_TABLE} SET next_retry_after = datetime('now') "
                f"WHERE status = ? AND auto_retry = 1",
                (STATUS_PERMANENT,),
            )
            # Esperas que ya estaban vencidas al deployar: van a la lista del
            # mail diario, sin un mail por fila (igual que con alert_state).
            days = self._wait_days()
            if days > 0:
                waits = ", ".join("?" for _ in WAIT_REASONS)
                self._conn.execute(
                    f"UPDATE {_TABLE} SET alert_state = ? "
                    f"WHERE reason_code IN ({waits}) AND first_seen <= datetime('now', ?)",
                    (ALERT_STATE_STALE, *sorted(WAIT_REASONS), f"-{int(round(days * 86400))} seconds"),
                )
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_RESOLVED_TABLE} (
                entity TEXT NOT NULL,
                external_id TEXT NOT NULL,
                reason_code TEXT,
                reason_detail TEXT,
                error_message TEXT,
                status TEXT,
                attempts INTEGER,
                first_seen TEXT,
                alert_state TEXT,
                how TEXT NOT NULL,
                resolved_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_RESOLVED_TABLE}_at ON {_RESOLVED_TABLE} (resolved_at)"
        )
        self._conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_pending "
            f"ON {_TABLE} (entity, status)"
        )
        self._commit()

    def _commit(self) -> None:
        # Si la conexion es compartida (inyectada), el commit lo controla el
        # owner del batch para mantener atomicidad. Si es propia, commit aqui.
        if self._owns_conn:
            self._conn.commit()

    # ── lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()

    # ── escritura ─────────────────────────────────────────────────────────

    @contextmanager
    def attempt_scope(self):
        """Dentro del bloque cada fila suma a lo sumo UN intento.

        Al aislar un batch caido (src/batch_isolation.py) las mismas filas se
        vuelven a mapear y enviar varias veces en la misma corrida; sin esto un
        registro invalido sumaria un intento por cada sub-batch y pasaria a
        'permanent' en una o dos corridas en vez de ``max_attempts``.
        """
        if self._scope_counted is not None:
            yield
            return
        self._scope_counted = set()
        try:
            yield
        finally:
            self._scope_counted = None

    def enqueue(
        self,
        entity: str,
        external_id: str,
        reason_code: str,
        error_message: str | None = None,
        payload_snapshot: str | None = None,
        reason_detail: str | None = None,
    ) -> None:
        """Encola o actualiza una fila pendiente (incrementa attempts).

        Si la fila ya existe se incrementan los intentos; al superar
        ``max_attempts`` pasa a 'permanent' para que la reporte la
        reconciliacion en vez de reintentarse para siempre. Excepcion:
        ``dependency_missing`` no incrementa intentos (ver
        _NO_ATTEMPT_COUNT_REASONS) — esperar una dependencia no es un fallo.
        """
        existing = self._conn.execute(
            f"SELECT attempts, status FROM {_TABLE} WHERE entity = ? AND external_id = ?",
            (entity, str(external_id)),
        ).fetchone()

        scope_key = (entity, str(external_id))
        if existing is None:
            if self._scope_counted is not None:
                self._scope_counted.add(scope_key)
            self._conn.execute(
                f"""
                INSERT INTO {_TABLE}
                    (entity, external_id, reason_code, reason_detail, error_message, attempts,
                     first_seen, last_attempt, status, payload_snapshot)
                VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'), ?, ?)
                """,
                (
                    entity,
                    str(external_id),
                    reason_code,
                    reason_detail,
                    error_message,
                    STATUS_PENDING,
                    payload_snapshot,
                ),
            )
            # WARNING desde el primer encolado (no solo al agotar intentos):
            # el operador tiene que enterarse por log apenas un registro entra
            # a la cola, con el numero de negocio (OC/OP/retencion/gasto), no
            # 10 corridas despues cuando ya paso a 'permanent'.
            logger.warning(
                "[retry_store] %s encolado (entity=%s external_id=%s, motivo=%s/%s): %s",
                describe_retry_key(entity, str(external_id)),
                entity, external_id, reason_code, reason_detail, error_message,
            )
        else:
            if reason_code in _NO_ATTEMPT_COUNT_REASONS:
                attempts = existing["attempts"] or 0
                status = STATUS_PENDING
            elif self._scope_counted is not None and scope_key in self._scope_counted:
                # Ya sumo su intento en este batch (ver attempt_scope).
                attempts = existing["attempts"] or 0
                status = existing["status"]
            else:
                attempts = (existing["attempts"] or 0) + 1
                status = STATUS_PERMANENT if attempts >= self._max_attempts else STATUS_PENDING
                if self._scope_counted is not None:
                    self._scope_counted.add(scope_key)
            if status == STATUS_PERMANENT and existing["status"] != STATUS_PERMANENT:
                # paxapos#489: logueamos la transicion UNA sola vez (aca, no en
                # cada corrida). De aca en mas los callers que arman el payload
                # deben consultar permanent_external_ids() y dejar de reenviar
                # esta fila hasta su proximo reintento automatico; si vuelven a
                # loguear en cada corrida repetimos el mismo bug (loop infinito
                # de ruido) solo que del lado local.
                logger.warning(
                    "[retry_store] %s pasa a 'permanent' tras %d intentos "
                    "(entity=%s external_id=%s) — deja de reintentarse en cada corrida; %s; "
                    "ultimo error: %s",
                    describe_retry_key(entity, str(external_id)),
                    attempts, entity, external_id, self._retry_policy_text(), error_message,
                )
            # 'permanent': proximo reintento automatico. Si la fila ya era
            # permanent y vuelve a fallar en su reintento, se corre otra vez.
            retry_hours = self._retry_hours()
            next_retry = (
                _sqlite_modifier(retry_hours)
                if status == STATUS_PERMANENT and retry_hours > 0
                else None
            )
            self._conn.execute(
                f"""
                UPDATE {_TABLE}
                         SET reason_code = ?, reason_detail = ?, error_message = ?, attempts = ?,
                       last_attempt = datetime('now'), status = ?,
                       payload_snapshot = COALESCE(?, payload_snapshot),
                       next_retry_after = CASE WHEN ? IS NULL THEN NULL ELSE datetime('now', ?) END
                 WHERE entity = ? AND external_id = ?
                """,
                (
                    reason_code,
                    reason_detail,
                    error_message,
                    attempts,
                    status,
                    payload_snapshot,
                    next_retry,
                    next_retry,
                    entity,
                    str(external_id),
                ),
            )
        self._commit()

    def mark_permanent(
        self,
        entity: str,
        external_id: str,
        reason_code: str,
        error_message: str | None = None,
        reason_detail: str | None = None,
    ) -> None:
        """Deja una fila directamente en 'permanent' (rechazo terminal del receptor).

        Para casos donde el contrato del backend dice que no hay que reintentar
        (destino borrado a mano desde la UI): gastar ``max_attempts`` corridas
        para llegar al mismo lugar solo genera ruido y trafico. Tampoco se
        reintenta solo cada RAFAM_PERMANENT_RETRY_HOURS (``auto_retry = 0``):
        el destino no va a volver a existir. Recuperable con ``requeue()``
        (o `resend`) igual que cualquier permanent.
        """
        existing = self._conn.execute(
            f"SELECT attempts FROM {_TABLE} WHERE entity = ? AND external_id = ?",
            (entity, str(external_id)),
        ).fetchone()
        attempts = max(1, (existing["attempts"] or 0) if existing else 1)
        self._conn.execute(
            f"""
            INSERT INTO {_TABLE}
                (entity, external_id, reason_code, reason_detail, error_message, attempts,
                 first_seen, last_attempt, status, auto_retry, next_retry_after)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, 0, NULL)
            ON CONFLICT(entity, external_id) DO UPDATE SET
                reason_code = excluded.reason_code,
                reason_detail = excluded.reason_detail,
                error_message = excluded.error_message,
                attempts = excluded.attempts,
                last_attempt = excluded.last_attempt,
                status = excluded.status,
                auto_retry = 0,
                next_retry_after = NULL
            """,
            (
                entity,
                str(external_id),
                reason_code,
                reason_detail,
                error_message,
                attempts,
                STATUS_PERMANENT,
            ),
        )
        self._commit()
        logger.warning(
            "[retry_store] %s marcado 'permanent' (terminal, entity=%s external_id=%s): %s",
            describe_retry_key(entity, str(external_id)),
            entity, external_id, error_message,
        )

    def resolve(self, entity: str, external_id: str, how: str = RESOLVED_MIGRATED) -> None:
        """Marca una fila como resuelta (la elimina de la cola).

        Se invoca cuando la fila finalmente se migra OK en una corrida
        (``how=RESOLVED_MIGRATED``) o cuando deja de corresponder migrarla
        (``RESOLVED_OUT_OF_SCOPE``: proveedor excluido, OP no presupuestaria...).
        Queda en ``retry_resolved`` para el mail diario.
        """
        self._log_resolved("entity = ? AND external_id = ?", (entity, str(external_id)), how)
        self._conn.execute(
            f"DELETE FROM {_TABLE} WHERE entity = ? AND external_id = ?",
            (entity, str(external_id)),
        )
        # Un gasto con varios comprobantes vuelve con `nro_comprob` en el
        # external_id, pero si se aislo de un batch caido quedo encolado con
        # la clave base de la solicitud.
        base = record_base_key(entity, str(external_id))
        if base is not None and base != str(external_id):
            where = "entity = ? AND external_id = ? AND reason_code = ?"
            params = (entity, base, REASON_BATCH_FAILED)
            self._log_resolved(where, params, how)
            self._conn.execute(f"DELETE FROM {_TABLE} WHERE {where}", params)
        self._commit()

    def resolve_if_reason(
        self, entity: str, external_id: str, reason_code: str, how: str = RESOLVED_MIGRATED,
    ) -> bool:
        """Saca la fila solo si sigue en la cola por ``reason_code``."""
        where = "entity = ? AND external_id = ? AND reason_code = ?"
        params = (entity, str(external_id), reason_code)
        self._log_resolved(where, params, how)
        cursor = self._conn.execute(f"DELETE FROM {_TABLE} WHERE {where}", params)
        self._commit()
        return cursor.rowcount > 0

    def _log_resolved(self, where: str, params: tuple, how: str) -> None:
        """Copia a ``retry_resolved`` las filas que estan por salir de la cola."""
        self._conn.execute(
            f"""
            INSERT INTO {_RESOLVED_TABLE}
                (entity, external_id, reason_code, reason_detail, error_message, status,
                 attempts, first_seen, alert_state, how, resolved_at)
            SELECT entity, external_id, reason_code, reason_detail, error_message, status,
                   attempts, first_seen, alert_state, ?, datetime('now')
              FROM {_TABLE} WHERE {where}
            """,
            (how, *params),
        )

    def requeue(self, entity: str | None = None, external_id: str | None = None) -> int:
        """Devuelve filas 'permanent' a 'pending' con los intentos en cero.

        Necesario cuando el motivo del rechazo se arregla del lado del receptor
        (core#406: el gate de cantidad>0 tiraba la OC entera por un renglon con
        cantidad 0). Sin esto, las filas que ya agotaron ``max_attempts`` quedan
        'permanent' y NUNCA se reinyectan — ``pending_external_ids`` solo mira
        'pending' —, asi que el fix del backend no las desbloquea solo.

        Retorna la cantidad de filas reencoladas.
        """
        clauses = ["status = ?"]
        params: list[str] = [STATUS_PERMANENT]
        if entity is not None:
            clauses.append("entity = ?")
            params.append(entity)
        if external_id is not None:
            clauses.append("external_id = ?")
            params.append(str(external_id))

        # alert_state = NULL: si vuelve a fallar despues del reenvio manual,
        # se avisa de nuevo. auto_retry = 1: un reenvio manual tambien
        # reactiva el reintento automatico de un rechazo terminal.
        cursor = self._conn.execute(
            f"UPDATE {_TABLE} SET status = ?, attempts = 0, next_retry_after = NULL, alert_state = NULL, "
            f"auto_retry = 1 "
            f"WHERE {' AND '.join(clauses)}",
            [STATUS_PENDING] + params,
        )
        self._commit()
        return cursor.rowcount

    def clear_entity(self, entity: str) -> int:
        cursor = self._conn.execute(f"DELETE FROM {_TABLE} WHERE entity = ?", (entity,))
        self._commit()
        return cursor.rowcount

    def clear_all(self) -> int:
        """Borra TODA la cola de reintentos. Retorna cantidad de filas eliminadas."""
        cursor = self._conn.execute(f"DELETE FROM {_TABLE}")
        self._commit()
        return cursor.rowcount

    def dismiss(self, entity: str, external_id: str, note: str) -> bool:
        """Descarta un unico retry confirmado como no accionable."""
        note = " ".join(str(note or "").split())
        if not note:
            raise ValueError("dismiss requiere una nota de auditoria")
        self._log_resolved(
            "entity = ? AND external_id = ?", (entity, str(external_id)), f"{RESOLVED_DISMISSED}: {note}",
        )
        cursor = self._conn.execute(
            f"DELETE FROM {_TABLE} WHERE entity = ? AND external_id = ?",
            (entity, str(external_id)),
        )
        self._commit()
        if cursor.rowcount:
            logger.warning(
                "[retry_store] retry descartado manualmente operator=%s host=%s "
                "entity=%s external_id=%s note=%s",
                getpass.getuser(),
                socket.gethostname(),
                entity,
                external_id,
                note,
            )
            return True
        return False

    # ── lectura ───────────────────────────────────────────────────────────

    # 'permanent' cuyo reintento automatico ya vencio (se reintenta esta corrida).
    _DUE = (
        f"status = '{STATUS_PERMANENT}' AND auto_retry = 1 "
        "AND next_retry_after IS NOT NULL AND next_retry_after <= datetime('now')"
    )

    def pending_external_ids(self, entity: str) -> set[str]:
        """IDs a reinyectar en esta corrida: los 'pending' y los 'permanent' cuyo
        reintento automatico ya vencio (ver ``RAFAM_PERMANENT_RETRY_HOURS``)."""
        rows = self._conn.execute(
            f"SELECT external_id FROM {_TABLE} WHERE entity = ? AND (status = ? OR ({self._DUE}))",
            (entity, STATUS_PENDING),
        ).fetchall()
        return {row["external_id"] for row in rows}

    def due_permanent_external_ids(self, entity: str) -> set[str]:
        """'permanent' que se reintentan solos en esta corrida."""
        rows = self._conn.execute(
            f"SELECT external_id FROM {_TABLE} WHERE entity = ? AND {self._DUE}",
            (entity,),
        ).fetchall()
        return {row["external_id"] for row in rows}

    def permanent_external_ids(self, entity: str) -> set[str]:
        """IDs 'permanent' para EXCLUIR del envio en esta corrida (paxapos#489).

        Las entidades incrementales dejan de reintentar un 'permanent' solo
        porque `pending_external_ids` no lo reinyecta y el watermark ya avanzo.
        Una entidad full_load (ej. oc_items) no tiene ese freno natural: escanea
        TODA la tabla en cada corrida, asi que sin esta exclusion explicita una
        fila rechazada para siempre se reenviaria para siempre.

        No incluye los 'permanent' cuyo reintento automatico ya vencio: esos
        pasan en esta corrida (si vuelven a fallar, el reintento se corre).
        """
        rows = self._conn.execute(
            f"SELECT external_id FROM {_TABLE} WHERE entity = ? AND status = ? AND NOT ({self._DUE})",
            (entity, STATUS_PERMANENT),
        ).fetchall()
        return {row["external_id"] for row in rows}

    def now(self) -> str:
        """Hora actual de SQLite (UTC, mismo formato que las columnas de fecha)."""
        return self._conn.execute("SELECT datetime('now')").fetchone()[0]

    def defer_due_permanents(self, entity: str, as_of: str) -> int:
        """Corre el proximo reintento de los 'permanent' que vencian en ``as_of``
        y siguen en la cola sin haberse reintentado (el mapper no los mando, p.ej.
        porque ya no corresponde). Sin esto se releerian en cada corrida.

        Los que se mandaron y volvieron a fallar ya tienen el reintento corrido
        (``enqueue``); los que se migraron ya no estan en la cola.
        """
        hours = self._retry_hours()
        cursor = self._conn.execute(
            f"UPDATE {_TABLE} SET next_retry_after = CASE WHEN ? IS NULL THEN NULL ELSE datetime('now', ?) END "
            f"WHERE entity = ? AND status = ? AND auto_retry = 1 "
            f"AND next_retry_after IS NOT NULL AND next_retry_after <= ?",
            (
                _sqlite_modifier(hours) if hours > 0 else None,
                _sqlite_modifier(hours) if hours > 0 else None,
                entity,
                STATUS_PERMANENT,
                as_of,
            ),
        )
        self._commit()
        return cursor.rowcount

    def pending_alerts(self) -> list[RetryItem]:
        """Filas que requieren un mail individual y todavia no lo tuvieron.

        Se avisa una vez por estado: al entrar a la cola (pending) y al pasar a
        'permanent'. Una fila que sigue fallando igual en cada corrida no
        vuelve a avisar; `requeue()` resetea el estado para que una nueva
        falla despues de un reenvio manual si avise.

        Las esperas (``WAIT_REASONS``) avisan una sola vez, cuando llevan mas
        de ``RAFAM_WAIT_ALERT_DAYS`` dias en la cola (``alert_state='stale'``).
        """
        reasons = sorted(ALERT_REASONS)
        where = (
            f"(reason_code IN ({', '.join('?' for _ in reasons)}) "
            f"AND (alert_state IS NULL OR alert_state != status))"
        )
        params: list = list(reasons)
        stale_where, stale_params = self._stale_wait_clause()
        if stale_where:
            where += f" OR ({stale_where} AND (alert_state IS NULL OR alert_state != ?))"
            params += [*stale_params, ALERT_STATE_STALE]
        rows = self._conn.execute(
            f"SELECT {_ITEM_COLUMNS} FROM {_TABLE} WHERE {where} "
            f"ORDER BY first_seen, entity, external_id",
            params,
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def mark_alerted(self, entity: str, external_id: str, status: str) -> None:
        """Registra que ya se mando el mail de esta fila para ``status``
        (``RetryItem.alert_kind``: el status, o 'stale' para una espera)."""
        self._conn.execute(
            f"UPDATE {_TABLE} SET alert_state = ?, alerted_at = datetime('now') "
            f"WHERE entity = ? AND external_id = ?",
            (status, entity, str(external_id)),
        )
        self._commit()

    # ── vista del operador (mail diario) ──────────────────────────────────

    def _stale_wait_clause(self) -> tuple[str, list]:
        """WHERE de las esperas vencidas ('' si RAFAM_WAIT_ALERT_DAYS=0)."""
        days = self._wait_days()
        if days <= 0:
            return "", []
        waits = sorted(WAIT_REASONS)
        return (
            f"reason_code IN ({', '.join('?' for _ in waits)}) "
            f"AND first_seen <= datetime('now', ?)",
            [*waits, f"-{int(round(days * 86400))} seconds"],
        )

    def attention_items(self, entities: Optional[list[str]] = None) -> list[RetryItem]:
        """Registros que alguien tiene que mirar: rechazos, datos invalidos,
        batches caidos (pending o permanent) y esperas vencidas. Lo que
        todavia espera dentro del plazo normal no esta aca (ver waiting_items).
        """
        reasons = sorted(ALERT_REASONS)
        where = f"(reason_code IN ({', '.join('?' for _ in reasons)}))"
        params: list = list(reasons)
        stale_where, stale_params = self._stale_wait_clause()
        if stale_where:
            where += f" OR ({stale_where})"
            params += stale_params
        return self._select_items(f"({where})", params, entities)

    def waiting_items(self, entities: Optional[list[str]] = None) -> list[RetryItem]:
        """Esperas dentro del plazo normal (todavia no requieren atencion)."""
        waits = sorted(WAIT_REASONS)
        where = f"reason_code IN ({', '.join('?' for _ in waits)})"
        params: list = list(waits)
        stale_where, stale_params = self._stale_wait_clause()
        if stale_where:
            where += f" AND NOT ({stale_where})"
            params += stale_params
        return self._select_items(where, params, entities)

    def _select_items(self, where: str, params: list, entities: Optional[list[str]]) -> list[RetryItem]:
        if entities is not None:
            if not entities:
                return []
            where += f" AND entity IN ({', '.join('?' for _ in entities)})"
            params = [*params, *entities]
        rows = self._conn.execute(
            f"SELECT {_ITEM_COLUMNS} FROM {_TABLE} WHERE {where} "
            f"ORDER BY first_seen, entity, external_id",
            params,
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def resolved_since(self, since: str, entities: Optional[list[str]] = None) -> list[dict]:
        """Filas que salieron de la cola desde ``since`` (UTC 'YYYY-MM-DD HH:MM:SS')."""
        where = "resolved_at >= ?"
        params: list = [since]
        if entities is not None:
            if not entities:
                return []
            where += f" AND entity IN ({', '.join('?' for _ in entities)})"
            params += list(entities)
        rows = self._conn.execute(
            f"SELECT * FROM {_RESOLVED_TABLE} WHERE {where} ORDER BY resolved_at, entity, external_id",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def prune_resolved(self, keep_days: int = 30) -> int:
        cursor = self._conn.execute(
            f"DELETE FROM {_RESOLVED_TABLE} WHERE resolved_at < datetime('now', ?)",
            (f"-{int(keep_days)} days",),
        )
        self._commit()
        return cursor.rowcount

    # ── configuracion ─────────────────────────────────────────────────────

    def _retry_hours(self) -> float:
        if self._permanent_retry_hours is not None:
            return max(0.0, float(self._permanent_retry_hours))
        return permanent_retry_hours()

    def _wait_days(self) -> float:
        if self._wait_alert_days is not None:
            return max(0.0, float(self._wait_alert_days))
        return wait_alert_days()

    @property
    def permanent_retry_hours(self) -> float:
        return self._retry_hours()

    @property
    def wait_alert_days(self) -> float:
        return self._wait_days()

    def _retry_policy_text(self) -> str:
        hours = self._retry_hours()
        if hours <= 0:
            return "no se reintenta solo (RAFAM_PERMANENT_RETRY_HOURS=0): reenviar a mano"
        return f"se reintenta solo cada {hours:g} h"

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @staticmethod
    def _row_to_item(row) -> RetryItem:
        keys = row.keys()
        return RetryItem(
            entity=row["entity"],
            external_id=row["external_id"],
            reason_code=row["reason_code"],
            reason_detail=row["reason_detail"],
            error_message=row["error_message"],
            attempts=row["attempts"] or 0,
            status=row["status"],
            first_seen=row["first_seen"],
            last_attempt=row["last_attempt"],
            payload_snapshot=row["payload_snapshot"],
            alert_state=row["alert_state"],
            next_retry_after=row["next_retry_after"] if "next_retry_after" in keys else None,
            auto_retry=int(row["auto_retry"]) if "auto_retry" in keys and row["auto_retry"] is not None else 1,
        )

    def list_items(
        self,
        entity: str | None = None,
        status: str | None = None,
        external_id: str | None = None,
    ) -> list[RetryItem]:
        clauses = []
        params: list[str] = []
        if entity is not None:
            clauses.append("entity = ?")
            params.append(entity)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if external_id is not None:
            clauses.append("external_id = ?")
            params.append(str(external_id))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT {_ITEM_COLUMNS} FROM {_TABLE} {where} ORDER BY entity, external_id",
            params,
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def counts_by_entity(
        self, entities: Optional[list[str]] = None
    ) -> dict[str, dict[str, int]]:
        """Resumen {entity: {status: count}} para status/observabilidad.

        Si ``entities`` se pasa, filtra el resultado a esas entidades. Lo usa el
        run de una sola entidad (``--entity X``) para que el log de la cola no
        muestre pendientes de otras entidades ajenas a esa corrida.
        """
        rows = self._conn.execute(
            f"SELECT entity, status, COUNT(*) AS n FROM {_TABLE} GROUP BY entity, status"
        ).fetchall()
        allow = set(entities) if entities is not None else None
        out: dict[str, dict[str, int]] = {}
        for row in rows:
            if allow is not None and row["entity"] not in allow:
                continue
            out.setdefault(row["entity"], {})[row["status"]] = row["n"]
        return out

    def summary_by_reason(self, entities: Optional[list[str]] = None) -> list[dict]:
        """Resumen compacto para historial y notificaciones, sin payloads ni IDs."""
        clauses = []
        params: list[str] = []
        if entities is not None:
            if not entities:
                return []
            clauses.append(f"entity IN ({', '.join('?' for _ in entities)})")
            params.extend(entities)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"""
            SELECT entity, status, reason_code,
                   COALESCE(reason_detail, 'legacy_unspecified') AS reason_detail,
                   COUNT(*) AS count,
                   MIN(first_seen) AS oldest_first_seen,
                   MAX(last_attempt) AS last_attempt,
                   MAX(attempts) AS max_attempts
              FROM {_TABLE}
              {where}
             GROUP BY entity, status, reason_code, COALESCE(reason_detail, 'legacy_unspecified')
             ORDER BY entity, status, reason_code, reason_detail
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
