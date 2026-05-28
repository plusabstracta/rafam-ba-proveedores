from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

from src.db import create_checkpoint_engine, create_source_engine
from src.entity_link_store import EntityLinkStore


class TestDbFactories:
    def test_create_source_engine_sqlite_uses_configured_path(self, monkeypatch, tmp_path):
        db_path = tmp_path / "source.db"
        monkeypatch.setenv("RAFAM_SOURCE_BACKEND", "sqlite")
        monkeypatch.setenv("RAFAM_SOURCE_SQLITE_DB_PATH", str(db_path))

        engine = create_source_engine()
        with engine.connect() as conn:
            assert conn.execute(text("select 1")).scalar() == 1

        assert db_path.exists()

    def test_create_source_engine_rejects_invalid_backend(self, monkeypatch):
        monkeypatch.setenv("RAFAM_SOURCE_BACKEND", "postgres")

        with pytest.raises(ValueError, match=r"oracle\|sqlite"):
            create_source_engine()

    def test_create_source_engine_oracle_requires_credentials(self, monkeypatch):
        monkeypatch.setenv("RAFAM_SOURCE_BACKEND", "oracle")
        monkeypatch.delenv("RAFAM_SOURCE_USER", raising=False)
        monkeypatch.delenv("RAFAM_SOURCE_PASSWORD", raising=False)

        with pytest.raises(ValueError, match="RAFAM_SOURCE_USER"):
            create_source_engine()

    def test_create_source_engine_oracle_builds_expected_url(self, monkeypatch):
        monkeypatch.setenv("RAFAM_SOURCE_BACKEND", "oracle")
        monkeypatch.setenv("RAFAM_SOURCE_HOST", "db.local")
        monkeypatch.setenv("RAFAM_SOURCE_PORT", "1522")
        monkeypatch.setenv("RAFAM_SOURCE_SERVICE", "RAFAM")
        monkeypatch.setenv("RAFAM_SOURCE_USER", "user")
        monkeypatch.setenv("RAFAM_SOURCE_PASSWORD", "pass")
        monkeypatch.setenv("ORACLE_CLIENT_DIR", "/opt/oracle")

        sentinel = object()
        with patch("src.db.oracledb.init_oracle_client") as init_client, patch(
            "src.db.create_engine", return_value=sentinel
        ) as create_engine_mock:
            assert create_source_engine() is sentinel

        init_client.assert_called_once_with(lib_dir="/opt/oracle")
        assert create_engine_mock.call_args.args[0] == "oracle+oracledb://user:pass@db.local:1522/?service_name=RAFAM"
        assert create_engine_mock.call_args.kwargs == {"future": True}

    def test_create_checkpoint_engine_uses_local_state_path(self, monkeypatch, tmp_path):
        db_path = tmp_path / "nested" / "checkpoint.db"
        monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(db_path))

        engine = create_checkpoint_engine()
        with engine.connect() as conn:
            assert conn.execute(text("select 1")).scalar() == 1

        assert db_path.exists()


class TestEntityLinkStoreExtraPaths:
    def test_save_get_clear_and_unknown_extras_are_ignored(self, tmp_path):
        store = EntityLinkStore(
            db_path=str(tmp_path / "links.db"),
            schemas={"custom": ["known"], "other": []},
        )
        store.save_link("custom", "a", "1", known="ok", ignored="no")

        link = store.get_link("custom", "a")
        assert link["remote_id"] == "1"
        assert link["known"] == "ok"
        assert "ignored" not in link
        assert store.get_remote_id("custom", "missing") is None

        store.save_link("other", "b", "2")
        assert store.clear_entity("custom") == 1
        assert store.get_link("custom", "a") is None
        assert store.clear_all() == {"custom": 0, "other": 1}
        store.close()

    def test_forward_migration_adds_new_schema_columns(self, tmp_path):
        db_path = tmp_path / "links.db"
        first = EntityLinkStore(db_path=str(db_path), schemas={"custom": ["old_col"]})
        first.save_link("custom", "a", "1", old_col="old")
        first.close()

        second = EntityLinkStore(db_path=str(db_path), schemas={"custom": ["old_col", "new_col"]})
        second.save_link("custom", "a", "2", new_col="new")

        link = second.get_link("custom", "a")
        assert link["remote_id"] == "2"
        assert link["old_col"] == "old"
        assert link["new_col"] == "new"
        second.close()

    def test_get_sent_oc_gasto_refs_splits_non_empty_refs(self, tmp_path):
        store = EntityLinkStore(db_path=str(tmp_path / "links.db"))
        store.save_link(
            "orden_compra",
            "oc-1",
            "10",
            gasto_refs="SG-2026-1-1, SG-2026-1-2, ",
        )
        store.save_link("orden_compra", "oc-2", "", gasto_refs="SG-2026-1-3")
        store.save_link("orden_compra", "oc-3", "11", gasto_refs="")

        assert store.get_sent_oc_gasto_refs() == {"SG-2026-1-1", "SG-2026-1-2"}
        store.close()


def test_entity_link_store_default_path_from_env(monkeypatch, tmp_path):
    db_path = tmp_path / "env_links.db"
    monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(db_path))
    store = EntityLinkStore()
    store.save_link("proveedores", "1", "10", cuit="20123456783")

    assert store.get_link("proveedores", "1")["cuit"] == "20123456783"
    store.close()
    assert db_path.exists()