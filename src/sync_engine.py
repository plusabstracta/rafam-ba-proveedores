from datetime import datetime, timezone
from typing import Optional

from .checkpoint_store import CheckpointStore
from .config import ENTITY_CONFIGS
from .models import Checkpoint, EntityConfig


class SyncEngine:
    """
    Incremental sync engine backed by a SQLite checkpoint store.

    The engine does NOT execute queries directly — callers fetch rows from
    SQLAlchemy statements and report results via mark_success() / mark_error().
    """

    def __init__(
        self,
        store: CheckpointStore,
        configs: Optional[dict[str, EntityConfig]] = None,
    ):
        self._store = store
        self._configs = configs if configs is not None else ENTITY_CONFIGS

    # ─── Checkpoint API ───────────────────────────────────────────────────────

    def get_checkpoint(self, entity: str) -> Checkpoint:
        return self._store.get(entity)

    def save_checkpoint(self, entity: str, checkpoint: Checkpoint) -> None:
        self._store.save(checkpoint)

    def reset_checkpoint(self, entity: str) -> None:
        """Force a full reload on the next run for this entity."""
        self._store.reset(entity)

    def mark_success(
        self,
        entity: str,
        last_id: Optional[int],
        last_ts: Optional[datetime],
        count: int,
    ) -> None:
        """Advance the checkpoint after a successful sync run."""
        existing = self._store.get(entity)
        self._store.save(
            Checkpoint(
                entity=entity,
                # Only advance if a new value was observed; keep old value otherwise.
                last_id=last_id if last_id is not None else existing.last_id,
                last_ts=last_ts if last_ts is not None else existing.last_ts,
                last_run=datetime.now(timezone.utc),
                records_sent=count,
                status="ok",
            )
        )

    def mark_error(self, entity: str, error: str) -> None:
        """Record an error WITHOUT advancing the cursor (safe to retry)."""
        cp = self._store.get(entity)
        cp.status = f"error: {error[:200]}"
        cp.last_run = datetime.now(timezone.utc)
        self._store.save(cp)

    # ─── Utility ─────────────────────────────────────────────────────────────

    def extract_cursor_values(
        self,
        columns: list[str],
        rows: list[tuple],
        entity: str,
    ) -> tuple[Optional[int], Optional[datetime]]:
        """
        Scans fetched rows and returns the max (last_id, last_ts) to use as
        the new checkpoint cursor values. Returns (None, None) if rows is empty.
        """
        if not rows:
            return None, None

        cfg = self._configs.get(entity)
        if cfg is None:
            return None, None

        col_idx = {name.upper(): i for i, name in enumerate(columns)}
        last_id: Optional[int] = None
        last_ts: Optional[datetime] = None

        if cfg.id_field:
            key = cfg.id_field.upper()
            if key in col_idx:
                vals = [r[col_idx[key]] for r in rows if r[col_idx[key]] is not None]
                if vals:
                    last_id = int(max(vals))

        if cfg.ts_field:
            key = cfg.ts_field.upper()
            if key in col_idx:
                vals = [r[col_idx[key]] for r in rows if r[col_idx[key]] is not None]
                if vals:
                    raw = max(vals)
                    if isinstance(raw, datetime):
                        last_ts = raw
                    elif isinstance(raw, str):
                        last_ts = self._parse_ts(raw)

        return last_id, last_ts

    @staticmethod
    def _parse_ts(value: str) -> Optional[datetime]:
        """Parse common timestamp string formats from SQLite TEXT columns."""
        text = value.strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None
