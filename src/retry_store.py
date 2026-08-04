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

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_TABLE = "retry_queue"

# reason_code: clasifica por que la fila no se pudo migrar todavia.
REASON_VALIDATION_CLIENT = "validation_client"      # rechazada por validation.py
REASON_DEPENDENCY_MISSING = "dependency_missing"    # FK/OC aun no migrada
REASON_BACKEND_REJECTED = "backend_rejected"        # 207: error por fila en el receptor

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
_NO_ATTEMPT_COUNT_REASONS = frozenset({REASON_DEPENDENCY_MISSING})


@dataclass(frozen=True)
class RetryItem:
    entity: str
    external_id: str
    reason_code: str
    error_message: Optional[str]
    attempts: int
    status: str
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
    ) -> None:
        """Encola o actualiza una fila pendiente (incrementa attempts).

        Si la fila ya existe se incrementan los intentos; al superar
        ``max_attempts`` pasa a 'permanent' para que la reporte la
        reconciliacion en vez de reintentarse para siempre. Excepcion:
        ``dependency_missing`` no incrementa intentos (ver
        _NO_ATTEMPT_COUNT_REASONS) — esperar una dependencia no es un fallo.
        """
        existing = self._conn.execute(
            f"SELECT attempts FROM {_TABLE} WHERE entity = ? AND external_id = ?",
            (entity, str(external_id)),
        ).fetchone()

        if existing is None:
            self._conn.execute(
                f"""
                INSERT INTO {_TABLE}
                    (entity, external_id, reason_code, error_message, attempts,
                     first_seen, last_attempt, status, payload_snapshot)
                VALUES (?, ?, ?, ?, 1, datetime('now'), datetime('now'), ?, ?)
                """,
                (
                    entity,
                    str(external_id),
                    reason_code,
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
            self._conn.execute(
                f"""
                UPDATE {_TABLE}
                   SET reason_code = ?, error_message = ?, attempts = ?,
                       last_attempt = datetime('now'), status = ?,
                       payload_snapshot = COALESCE(?, payload_snapshot)
                 WHERE entity = ? AND external_id = ?
                """,
                (
                    reason_code,
                    error_message,
                    attempts,
                    status,
                    payload_snapshot,
                    entity,
                    str(external_id),
                ),
            )
        self._commit()

    def resolve(self, entity: str, external_id: str) -> None:
        """Marca una fila como resuelta (la elimina de la cola).

        Se invoca cuando la fila finalmente se migra OK en una corrida.
        """
        self._conn.execute(
            f"DELETE FROM {_TABLE} WHERE entity = ? AND external_id = ?",
            (entity, str(external_id)),
        )
        self._commit()

    def clear_entity(self, entity: str) -> int:
        cursor = self._conn.execute(f"DELETE FROM {_TABLE} WHERE entity = ?", (entity,))
        self._commit()
        return cursor.rowcount

    def clear_all(self) -> int:
        """Borra TODA la cola de reintentos. Retorna cantidad de filas eliminadas."""
        cursor = self._conn.execute(f"DELETE FROM {_TABLE}")
        self._commit()
        return cursor.rowcount

    # ── lectura ───────────────────────────────────────────────────────────

    def pending_external_ids(self, entity: str) -> set[str]:
        """IDs pendientes (status='pending') para reinyectar en la proxima corrida."""
        rows = self._conn.execute(
            f"SELECT external_id FROM {_TABLE} WHERE entity = ? AND status = ?",
            (entity, STATUS_PENDING),
        ).fetchall()
        return {row["external_id"] for row in rows}

    def list_items(self, entity: str | None = None, status: str | None = None) -> list[RetryItem]:
        clauses = []
        params: list[str] = []
        if entity is not None:
            clauses.append("entity = ?")
            params.append(entity)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT entity, external_id, reason_code, error_message, attempts, "
            f"status, payload_snapshot FROM {_TABLE} {where} ORDER BY entity, external_id",
            params,
        ).fetchall()
        return [
            RetryItem(
                entity=row["entity"],
                external_id=row["external_id"],
                reason_code=row["reason_code"],
                error_message=row["error_message"],
                attempts=row["attempts"] or 0,
                status=row["status"],
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
