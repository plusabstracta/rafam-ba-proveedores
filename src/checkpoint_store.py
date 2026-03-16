import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Checkpoint

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "state" / "checkpoint.db"

_DT_FMT = "%Y-%m-%d %H:%M:%S"

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS sync_checkpoints (
        entity        TEXT PRIMARY KEY,
        last_id       INTEGER,
        last_ts       TEXT,
        last_run      TEXT,
        records_sent  INTEGER DEFAULT 0,
        status        TEXT    DEFAULT 'ok'
    )
"""

_UPSERT_SQL = """
    INSERT INTO sync_checkpoints
        (entity, last_id, last_ts, last_run, records_sent, status)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(entity) DO UPDATE SET
        last_id      = excluded.last_id,
        last_ts      = excluded.last_ts,
        last_run     = excluded.last_run,
        records_sent = excluded.records_sent,
        status       = excluded.status
"""


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.strptime(value, _DT_FMT) if value else None


def _fmt_dt(value: Optional[datetime]) -> Optional[str]:
    return value.strftime(_DT_FMT) if value else None


def _row_to_checkpoint(row: sqlite3.Row) -> Checkpoint:
    return Checkpoint(
        entity=row["entity"],
        last_id=row["last_id"],
        last_ts=_parse_dt(row["last_ts"]),
        last_run=_parse_dt(row["last_run"]),
        records_sent=row["records_sent"] or 0,
        status=row["status"] or "ok",
    )


class CheckpointStore:
    """SQLite-backed persistence layer for sync checkpoints.

    Maintains a single connection for its lifetime. Use as a context manager
    or call close() explicitly when done.
    """

    def __init__(self, db_path: Path = _DEFAULT_DB):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._create_connection()
        self._conn.execute(_CREATE_SQL)
        self._conn.commit()

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def get(self, entity: str) -> Checkpoint:
        row = self._conn.execute(
            "SELECT * FROM sync_checkpoints WHERE entity = ?", [entity]
        ).fetchone()
        return _row_to_checkpoint(row) if row else Checkpoint(entity=entity)

    def save(self, checkpoint: Checkpoint) -> None:
        self._conn.execute(
            _UPSERT_SQL,
            [
                checkpoint.entity,
                checkpoint.last_id,
                _fmt_dt(checkpoint.last_ts),
                _fmt_dt(checkpoint.last_run),
                checkpoint.records_sent,
                checkpoint.status,
            ],
        )
        self._conn.commit()

    def reset(self, entity: str) -> None:
        self._conn.execute(
            "DELETE FROM sync_checkpoints WHERE entity = ?", [entity]
        )
        self._conn.commit()

    def all_checkpoints(self) -> list[Checkpoint]:
        rows = self._conn.execute(
            "SELECT * FROM sync_checkpoints ORDER BY entity"
        ).fetchall()
        return [_row_to_checkpoint(r) for r in rows]
