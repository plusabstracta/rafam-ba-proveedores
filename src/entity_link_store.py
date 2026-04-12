import os
import sqlite3
from pathlib import Path
from typing import Optional

_TABLE_PREFIX = "link_"

# Extra columns per entity (beyond the base source_key, remote_id, updated_at).
# Override via the ``schemas`` parameter in EntityLinkStore.__init__().
DEFAULT_LINK_SCHEMAS: dict[str, list[str]] = {
    "proveedores": ["cuit", "cod_estado"],
    "clasificacion": [],
    "rubro": [],
    "pedido": [],
    "orden_compra": ["fech_confirm", "estado_oc", "cod_prov", "importe_tot"],
    "gasto": [],
    "orden_pago": [],
}


class EntityLinkStore:
    """Stores RAFAM -> Paxapos ID links — one table per entity.

    Each entity gets its own ``link_<entity>`` table with configurable
    extra columns defined in ``schemas``.
    """

    def __init__(
        self,
        db_path: str | None = None,
        schemas: dict[str, list[str]] | None = None,
    ):
        if not db_path:
            db_path = os.getenv("ENTITY_LINK_DB_PATH") or os.getenv("CHECKPOINT_DB_PATH") or "state/checkpoint.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._schemas = schemas if schemas is not None else DEFAULT_LINK_SCHEMAS
        self._created_tables: set[str] = set()

    # ── internal ──────────────────────────────────────────────────────────

    def _ensure_table(self, entity: str) -> str:
        """Create ``link_<entity>`` if missing; ALTER TABLE to add new columns."""
        table_name = f"{_TABLE_PREFIX}{entity}"
        if table_name in self._created_tables:
            return table_name

        extra_cols = self._schemas.get(entity, [])
        col_defs = ["source_key TEXT PRIMARY KEY", "remote_id TEXT"]
        for col in extra_cols:
            col_defs.append(f"[{col}] TEXT")
        col_defs.append("updated_at TEXT NOT NULL")

        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS [{table_name}] ({', '.join(col_defs)})"
        )

        # Forward-migration: add columns that exist in schema but not in table.
        existing_cols = {
            row["name"]
            for row in self._conn.execute(f"PRAGMA table_info([{table_name}])").fetchall()
        }
        for col in extra_cols:
            if col not in existing_cols:
                self._conn.execute(f"ALTER TABLE [{table_name}] ADD COLUMN [{col}] TEXT")

        self._conn.commit()
        self._created_tables.add(table_name)
        return table_name

    # ── lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()

    # ── public API ────────────────────────────────────────────────────────

    def save_link(
        self,
        entity: str,
        source_key: str,
        remote_id: str,
        **extras: str | None,
    ) -> None:
        table = self._ensure_table(entity)
        allowed = set(self._schemas.get(entity, []))
        extra_data = {k: v for k, v in extras.items() if k in allowed}

        cols = ["source_key", "remote_id"] + list(extra_data.keys()) + ["updated_at"]
        value_slots = ["?"] * (len(cols) - 1) + ["datetime('now')"]

        update_parts = ["remote_id = excluded.remote_id", "updated_at = excluded.updated_at"]
        for col in extra_data:
            update_parts.append(f"[{col}] = excluded.[{col}]")

        sql = (
            f"INSERT INTO [{table}] ({', '.join(cols)})"
            f" VALUES ({', '.join(value_slots)})"
            f" ON CONFLICT(source_key) DO UPDATE SET {', '.join(update_parts)}"
        )
        params = [source_key, remote_id] + list(extra_data.values())
        self._conn.execute(sql, params)
        self._conn.commit()

    def get_remote_id(self, entity: str, source_key: str) -> Optional[str]:
        table = self._ensure_table(entity)
        row = self._conn.execute(
            f"SELECT remote_id FROM [{table}] WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        if not row:
            return None
        return row["remote_id"]

    def get_link(self, entity: str, source_key: str) -> dict | None:
        """Return the full row as a dict, or None if not found."""
        table = self._ensure_table(entity)
        row = self._conn.execute(
            f"SELECT * FROM [{table}] WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        if not row:
            return None
        return dict(row)
