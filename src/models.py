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
    """Describes how to build incremental queries for a single RAFAM entity."""

    name: str
    base_query: str
    id_field: Optional[str] = None          # integer cursor column
    ts_field: Optional[str] = None          # timestamp cursor column
    full_load: bool = False                 # always full scan (small/static tables)
    extra_condition: Optional[str] = None   # raw SQL OR-ed into WHERE (no bind params)


@dataclass
class SyncResult:
    """Result of a single entity sync run."""

    entity: str
    records_sent: int
    success: bool
    last_id: Optional[int] = None
    last_ts: Optional[datetime] = None
    error: Optional[str] = None
