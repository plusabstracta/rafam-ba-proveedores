from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.checkpoint_store import CheckpointStore
from src.models import Checkpoint, EntityConfig
from src.sync_engine import SyncEngine


def _engine(tmp_path, configs=None):
    store = CheckpointStore(db_url=f"sqlite+pysqlite:///{tmp_path / 'sync.db'}")
    default_configs = {
        "items": EntityConfig(
            name="items",
            table_name="ITEMS",
            id_field="ID",
            ts_field="UPDATED_AT",
        )
    }
    return SyncEngine(store, configs or default_configs)


def test_save_and_reset_checkpoint_delegate_to_store(tmp_path):
    engine = _engine(tmp_path)
    checkpoint = Checkpoint(entity="items", last_id=5)

    engine.save_checkpoint("items", checkpoint)
    assert engine.get_checkpoint("items").last_id == 5
    engine.reset_checkpoint("items")
    assert engine.get_checkpoint("items").is_fresh


def test_mark_success_preserves_existing_cursor_when_values_missing(tmp_path):
    engine = _engine(tmp_path)
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    engine.mark_success("items", 10, ts, 2)
    engine.mark_success("items", None, None, 0)

    checkpoint = engine.get_checkpoint("items")
    assert checkpoint.last_id == 10
    assert checkpoint.last_ts == ts.replace(tzinfo=None)
    assert checkpoint.records_sent == 0


def test_advance_partial_advances_only_forward_and_accumulates_records(tmp_path):
    engine = _engine(tmp_path)
    base = datetime(2026, 1, 1, 12, 0, 0)
    engine.mark_success("items", 10, base.replace(tzinfo=timezone.utc), 3)

    engine.advance_partial("items", 8, base - timedelta(days=1), 4)
    checkpoint = engine.get_checkpoint("items")
    assert checkpoint.last_id == 10
    assert checkpoint.last_ts == base
    assert checkpoint.records_sent == 7
    assert checkpoint.status == "running"

    later = datetime(2026, 1, 2, 8, 30, 0)
    engine.advance_partial("items", 12, later, 5)
    checkpoint = engine.get_checkpoint("items")
    assert checkpoint.last_id == 12
    assert checkpoint.last_ts == later
    assert checkpoint.records_sent == 12


def test_normalize_and_parse_datetime_variants():
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    naive = datetime(2026, 1, 1)

    assert SyncEngine._normalize_utc(None) is None
    assert SyncEngine._normalize_utc(aware) == aware
    assert SyncEngine._normalize_utc(naive) == naive.replace(tzinfo=timezone.utc)
    assert SyncEngine._normalize_utc("bad") is None
    assert SyncEngine._coerce_datetime("2026-01-01T10:00:00Z").tzinfo is not None
    assert SyncEngine._coerce_datetime("2026-01-01 10:00:00").tzinfo is not None
    assert SyncEngine._coerce_datetime("2026-01-01").tzinfo is not None
    assert SyncEngine._coerce_datetime("not a date") is None
    assert SyncEngine._coerce_datetime(1) is None
    assert SyncEngine._parse_ts("   ") is None


def test_extract_cursor_values_handles_empty_unknown_missing_and_string_dates(tmp_path):
    engine = _engine(tmp_path)

    assert engine.extract_cursor_values(["ID"], [], "items") == (None, None)
    assert engine.extract_cursor_values(["ID"], [(1,)], "unknown") == (None, None)
    assert engine.extract_cursor_values(["OTHER"], [(1,)], "items") == (None, None)

    last_id, last_ts = engine.extract_cursor_values(
        ["id", "updated_at"],
        [("10", "2026-01-01"), ("20", "2026-01-02T03:04:05Z"), (None, "bad")],
        "items",
    )
    assert last_id == 20
    assert last_ts == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)