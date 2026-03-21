import os
import sqlite3
from pathlib import Path
from typing import Optional


class EntityLinkStore:
    """Stores RAFAM -> Paxapos ID links for future update/upsert workflows."""

    def __init__(self, db_path: str | None = None):
        if not db_path:
            db_path = os.getenv("ENTITY_LINK_DB_PATH") or os.getenv("CHECKPOINT_DB_PATH") or "state/checkpoint.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_entity_links (
                entity TEXT NOT NULL,
                source_key TEXT NOT NULL,
                remote_id TEXT,
                cuit TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (entity, source_key)
            )
            """
        )
        self._conn.commit()

    def save_link(self, entity: str, source_key: str, remote_id: str, cuit: Optional[str] = None) -> None:
        self._conn.execute(
            """
            INSERT INTO sync_entity_links (entity, source_key, remote_id, cuit, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(entity, source_key) DO UPDATE SET
                remote_id = excluded.remote_id,
                cuit = excluded.cuit,
                updated_at = excluded.updated_at
            """,
            (entity, source_key, remote_id, cuit),
        )
        self._conn.commit()

    def get_remote_id(self, entity: str, source_key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT remote_id FROM sync_entity_links WHERE entity = ? AND source_key = ?",
            (entity, source_key),
        ).fetchone()
        if not row:
            return None
        return row[0]

    def close(self) -> None:
        self._conn.close()
