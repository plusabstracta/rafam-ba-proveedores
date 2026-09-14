"""retry_store.py — Cola de reintentos para filas incompletas/rechazadas (F1).

Garantiza que ninguna fila se pierda: las que se omiten en el cliente (por
validacion de boundary o por dependencia aun no migrada) y las que el receptor
rechaza (207 con error por fila) se encolan aqui y se reintentan en cada
corrida hasta completarse. El watermark del checkpoint puede avanzar con
seguridad porque lo pendiente queda registrado en esta cola, no en el cursor.

Decision de diseno (4-jun-2026): manejo fila-a-fila — un batch de 500 NO se
cancela por 1 fila mala; la fila mala va a la cola y el resto se procesa.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TABLE = "retry_queue"

# reason_code: clasifica por que la fila no se pudo migrar todavia.
REASON_VALIDATION_CLIENT = "validation_client"      # rechazada por validation.py
REASON_DEPENDENCY_MISSING = "dependency_missing"    # FK/OC aun no migrada
REASON_BACKEND_REJECTED = "backend_rejected"        # 207: error por fila en el receptor
REASON_BACKEND_UNAVAILABLE = "backend_unavailable"  # SQL/PHP roto en el receptor; la fila esta bien

STATUS_PENDING = "pending"
STATUS_PERMANENT = "permanent"

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


class RetryStore:
    """Persistencia de la cola de reintentos (una tabla, multi-entidad)."""

    def __init__(
        self,
        db_path: str | None = None,
        *,
        conn: sqlite3.Connection | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ):
        self._max_attempts = max_attempts
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

        if existing is None:
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
        else:
            if reason_code in _NO_ATTEMPT_COUNT_REASONS:
                attempts = existing["attempts"] or 0
                status = STATUS_PENDING
            else:
                attempts = (existing["attempts"] or 0) + 1
                status = STATUS_PERMANENT if attempts >= self._max_attempts else STATUS_PENDING
            if status == STATUS_PERMANENT and existing["status"] != STATUS_PERMANENT:
                # paxapos#489: logueamos la transicion UNA sola vez (aca, no en
                # cada corrida). De aca en mas los callers que arman el payload
                # deben consultar permanent_external_ids() y dejar de reenviar
                # esta fila; si vuelven a loguear en cada corrida repetimos el
                # mismo bug (loop infinito de ruido) solo que del lado local.
                logger.warning(
                    "[retry_store] %s %s pasa a 'permanent' tras %d intentos — "
                    "no se reintenta mas (recuperable con requeue()); ultimo error: %s",
                    entity, external_id, attempts, error_message,
                )
            self._conn.execute(
                f"""
                UPDATE {_TABLE}
                         SET reason_code = ?, reason_detail = ?, error_message = ?, attempts = ?,
                       last_attempt = datetime('now'), status = ?,
                       payload_snapshot = COALESCE(?, payload_snapshot)
                 WHERE entity = ? AND external_id = ?
                """,
                (
                    reason_code,
                    reason_detail,
                    error_message,
                    attempts,
                    status,
                    payload_snapshot,
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
        para llegar al mismo lugar solo genera ruido y trafico. Recuperable con
        ``requeue()`` igual que cualquier permanent.
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
                 first_seen, last_attempt, status)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?)
            ON CONFLICT(entity, external_id) DO UPDATE SET
                reason_code = excluded.reason_code,
                reason_detail = excluded.reason_detail,
                error_message = excluded.error_message,
                attempts = excluded.attempts,
                last_attempt = excluded.last_attempt,
                status = excluded.status
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
            "[retry_store] %s %s marcado 'permanent' (terminal): %s",
            entity, external_id, error_message,
        )

    def resolve(self, entity: str, external_id: str) -> None:
        """Marca una fila como resuelta (la elimina de la cola).

        Se invoca cuando la fila finalmente se migra OK en una corrida.
        """
        self._conn.execute(
            f"DELETE FROM {_TABLE} WHERE entity = ? AND external_id = ?",
            (entity, str(external_id)),
        )
        self._commit()

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

        cursor = self._conn.execute(
            f"UPDATE {_TABLE} SET status = ?, attempts = 0, next_retry_after = NULL "
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

    def pending_external_ids(self, entity: str) -> set[str]:
        """IDs pendientes (status='pending') para reinyectar en la proxima corrida."""
        rows = self._conn.execute(
            f"SELECT external_id FROM {_TABLE} WHERE entity = ? AND status = ?",
            (entity, STATUS_PENDING),
        ).fetchall()
        return {row["external_id"] for row in rows}

    def permanent_external_ids(self, entity: str) -> set[str]:
        """IDs 'permanent' para EXCLUIR de una query full_load (paxapos#489).

        Las entidades incrementales dejan de reintentar un 'permanent' solo
        porque `pending_external_ids` no lo reinyecta y el watermark ya avanzo.
        Una entidad full_load (ej. oc_items) no tiene ese freno natural: escanea
        TODA la tabla en cada corrida, asi que sin esta exclusion explicita una
        fila rechazada para siempre se reenviaria para siempre.
        """
        rows = self._conn.execute(
            f"SELECT external_id FROM {_TABLE} WHERE entity = ? AND status = ?",
            (entity, STATUS_PERMANENT),
        ).fetchall()
        return {row["external_id"] for row in rows}

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
            f"SELECT entity, external_id, reason_code, reason_detail, error_message, attempts, "
            f"status, first_seen, last_attempt, payload_snapshot "
            f"FROM {_TABLE} {where} ORDER BY entity, external_id",
            params,
        ).fetchall()
        return [
            RetryItem(
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
            )
            for row in rows
        ]

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
