from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Checkpoint:
    """Tracks sync progress for a single entity."""

    entity: str
    last_id: Optional[int] = None
    last_ts: Optional[datetime] = None
    last_run: Optional[datetime] = None
    records_sent: int = 0
    status: str = "ok"

    @property
    def is_fresh(self) -> bool:
        """True when no prior run exists for this entity → triggers full load."""
        return self.last_id is None and self.last_ts is None and self.last_run is None


@dataclass
class EntityConfig:
    """Metadata used to build SQLAlchemy queries for a RAFAM entity."""

    name: str
    table_name: str
    id_field: Optional[str] = None          # integer cursor column
    ts_field: Optional[str] = None          # timestamp cursor column
    full_load: bool = False                 # always full scan (small/static tables)
    pending_state_field: Optional[str] = None
    pending_state_value: Optional[str] = None
    pending_reprocess_days: Optional[int] = None


@dataclass
class SyncResult:
    """Result of a single entity sync run."""

    entity: str
    records_sent: int
    success: bool
    last_id: Optional[int] = None
    last_ts: Optional[datetime] = None
    error: Optional[str] = None
