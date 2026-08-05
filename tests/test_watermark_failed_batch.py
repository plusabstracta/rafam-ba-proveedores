"""Regresion: el watermark NO debe avanzar por encima de un batch fallido.

Escenario real: corrida con N batches ordenados por timestamp; el batch #2
falla por un error transitorio (HTTP 500/timeout) y el #3 sale OK. Si el
watermark avanzara con el batch #3, las filas del batch #2 quedarian por
detras del cursor y no volverian a entrar nunca (perdida silenciosa).
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

from main import _effective_batch_size, _sync_entity
from src.checkpoint_store import CheckpointStore
from src.exporter import BaseExporter
from src.models import EntityConfig
from src.source_repository import SourceRepository
from src.sync_engine import SyncEngine


class _FailSecondBatchExporter(BaseExporter):
    """Exporter fake: el segundo batch lanza; el resto pasa."""

    def __init__(self):
        self.batches = []

    def write_batch(self, entity, columns, rows):
        self.batches.append(rows)
        if len(self.batches) == 2:
            raise RuntimeError("HTTP 503: receptor caido (transitorio)")


@pytest.fixture
def source_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE ITEMS (
                ID INTEGER PRIMARY KEY,
                UPDATED_AT DATETIME
            )
        """))
        for i in range(1, 7):
            conn.execute(text(f"INSERT INTO ITEMS VALUES ({i}, '2026-03-0{i} 00:00:00')"))
        conn.commit()
    return engine


def _make_sync_engine(tmp_path, configs):
    store = CheckpointStore(db_url=f"sqlite+pysqlite:///{tmp_path / 'cp.db'}")
    return SyncEngine(store, configs)


def test_oc_items_caps_requested_batch_size(monkeypatch):
    monkeypatch.delenv("RAFAM_OC_MAX_BATCH_ROWS", raising=False)

    assert _effective_batch_size("oc_items", 500) == 100
    assert _effective_batch_size("oc_items", 50) == 50


def test_oc_items_batch_cap_can_be_configured(monkeypatch):
    monkeypatch.setenv("RAFAM_OC_MAX_BATCH_ROWS", "80")

    assert _effective_batch_size("oc_items", 500) == 80


def test_batch_size_for_other_entities_is_unchanged(monkeypatch):
    monkeypatch.setenv("RAFAM_OC_MAX_BATCH_ROWS", "80")

    assert _effective_batch_size("proveedores", 500) == 500


def test_watermark_se_congela_tras_batch_fallido(tmp_path, source_engine):
    cfg = EntityConfig(name="items", table_name="ITEMS", ts_field="UPDATED_AT")
    configs = {"items": cfg}
    engine = _make_sync_engine(tmp_path, configs)
    exporter = _FailSecondBatchExporter()

    with source_engine.connect() as conn:
        repo = SourceRepository(conn)
        with patch.dict("src.config.ENTITY_CONFIGS", configs, clear=False):
            ok, error_msg, metrics = _sync_entity(
                repo, engine, exporter, "items",
                batch_size=2, limit=None, dry_run=False,
            )

    # 3 batches de 2 filas; el #2 fallo
    assert len(exporter.batches) == 3
    assert ok is False
    assert metrics["batches_failed"] == 1

    checkpoint = engine.get_checkpoint("items")
    # El watermark debe quedar en el ultimo batch ANTERIOR al fallo (filas
    # 1-2, ts 2026-03-02), nunca en el batch #3 (ts 2026-03-06): las filas
    # 3-4 del batch fallido deben re-entrar en la proxima corrida.
    assert checkpoint.last_ts is not None
    assert checkpoint.last_ts <= datetime(2026, 3, 2)
    assert "error" in (checkpoint.status or "")


def test_watermark_avanza_normal_sin_fallos(tmp_path, source_engine):
    cfg = EntityConfig(name="items", table_name="ITEMS", ts_field="UPDATED_AT")
    configs = {"items": cfg}
    engine = _make_sync_engine(tmp_path, configs)

    class _OkExporter(BaseExporter):
        def write_batch(self, entity, columns, rows):
            pass

    with source_engine.connect() as conn:
        repo = SourceRepository(conn)
        with patch.dict("src.config.ENTITY_CONFIGS", configs, clear=False):
            ok, error_msg, metrics = _sync_entity(
                repo, engine, _OkExporter(), "items",
                batch_size=2, limit=None, dry_run=False,
            )

    assert ok is True
    checkpoint = engine.get_checkpoint("items")
    assert checkpoint.last_ts is not None
    assert checkpoint.last_ts >= datetime(2026, 3, 6)
    assert checkpoint.status == "ok"
