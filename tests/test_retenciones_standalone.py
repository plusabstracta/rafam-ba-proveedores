from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.exporter import MigratorExporter
from src.retry_store import REASON_DEPENDENCY_MISSING, RetryStore


def _migrator(monkeypatch, tmp_path, *, dry_run=False):
    monkeypatch.setenv("PAXAPOS_URL", "https://example.test")
    monkeypatch.setenv("PAXAPOS_TENANT", "tenant")
    monkeypatch.setenv("PAXAPOS_API_KEY", "key")
    monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "migrator_links.db"))
    monkeypatch.setenv("PAXAPOS_VERIFY_SSL", "true")
    lookup_payload = {
        "lookups": {
            "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
            "tipos_factura": [{"id": "2", "name": "A", "codename": "factura_a"}],
            "tipos_de_pago": [{"id": "4", "name": "Transferencia bancaria"}],
            "tipos_retencion": [
                {"id": "103", "codigo": "3", "name": "Retencion ganancias"},
                {"id": "102", "codigo": "6", "name": "Retencion IVA"},
            ],
        }
    }
    with patch("src.exporter.fetch_migrator_lookups", return_value=lookup_payload):
        return MigratorExporter(dry_run=dry_run)


class _FakeSourceRepo:
    def __init__(self, deducciones_by_op):
        self._deducciones_by_op = deducciones_by_op
        self.requested_keys = None

    def fetch_deducciones_for_ops(self, op_keys):
        self.requested_keys = list(op_keys)
        return self._deducciones_by_op


_COLUMNS = ["EJERCICIO", "NRO_OP"]


class TestRetencionesStandalone:
    def test_emits_only_for_migrated_op_and_enqueues_missing(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter.attach_retry_store(retry)

        # OP (2026, 100) migrada; OP (2026, 200) NO migrada.
        exporter._link_store.save_link(
            "orden_pago",
            json.dumps({"ejercicio": 2026, "nro_op": 100}, sort_keys=True),
            "5001",
        )
        deducciones = {
            (2026, 100): [{"codigo_deduc": "3", "importe_reten": 150.0, "descripcion": "Ganancias"}],
            (2026, 200): [{"codigo_deduc": "6", "importe_reten": 80.0, "descripcion": "IVA"}],
        }
        exporter.attach_source(_FakeSourceRepo(deducciones))

        captured = {}

        def fake_post(url, payload):
            captured["payload"] = payload
            return {"stats": {"retenciones": {"ok": 1, "error": 0}}, "results": {"retenciones": []}}

        with patch.object(exporter, "_post_json", side_effect=fake_post):
            exporter._write_batch_retenciones(
                _COLUMNS,
                [(2026, 100), (2026, 200)],
            )

        # Solo la OP migrada va en el payload.
        sent = captured["payload"]["retenciones"]
        assert len(sent) == 1
        assert sent[0]["external_id"] == {"ejercicio": 2026, "nro_op": 100}
        assert sent[0]["orden_pago_external_id"] == {"ejercicio": 2026, "nro_op": 100}
        assert sent[0]["retenciones"][0]["tipo_impuesto_id"] == 103

        # La OP no migrada quedo encolada como dependency_missing.
        pending = retry.pending_external_ids("retenciones")
        assert pending == {json.dumps({"ejercicio": 2026, "nro_op": 200}, sort_keys=True)}
        items = retry.list_items("retenciones")
        assert items[0].reason_code == REASON_DEPENDENCY_MISSING
        retry.close()

    def test_no_post_when_no_migrated_ops(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        deducciones = {(2026, 200): [{"codigo_deduc": "6", "importe_reten": 80.0}]}
        exporter.attach_source(_FakeSourceRepo(deducciones))

        with patch.object(exporter, "_post_json") as post:
            exporter._write_batch_retenciones(_COLUMNS, [(2026, 200)])
            post.assert_not_called()

    def test_skips_when_source_repo_missing(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        with patch.object(exporter, "_post_json") as post:
            exporter._write_batch_retenciones(_COLUMNS, [(2026, 100)])
            post.assert_not_called()

    def test_write_batch_dispatches_retenciones(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        exporter.attach_source(_FakeSourceRepo({}))
        with patch.object(exporter, "_write_batch_retenciones") as wb:
            exporter.write_batch("retenciones", _COLUMNS, [(2026, 100)])
            wb.assert_called_once()

    def test_persists_link_and_skips_unchanged_op(self, monkeypatch, tmp_path):
        """Idempotencia: tras migrar una OP, una segunda corrida sin cambios no reenvia.

        El receptor usa REPLACE (soft-delete + insert) por egreso, asi que
        reenviar las mismas retenciones generaria filas duplicadas. El link
        link_retenciones (con fingerprint) evita ese reenvio.
        """
        exporter = _migrator(monkeypatch, tmp_path)
        op_sk = json.dumps({"ejercicio": 2026, "nro_op": 100}, sort_keys=True)
        exporter._link_store.save_link("orden_pago", op_sk, "5001")
        deducciones = {
            (2026, 100): [{"codigo_deduc": "3", "importe_reten": 150.0, "descripcion": "Ganancias"}],
        }
        exporter.attach_source(_FakeSourceRepo(deducciones))

        def fake_post(url, payload):
            return {
                "stats": {"retenciones": {"ok": 1, "error": 0}},
                "results": {
                    "retenciones": [
                        {"success": True, "external_id": {"ejercicio": 2026, "nro_op": 100}, "id": 5001}
                    ]
                },
            }

        # Primera corrida: envia y persiste el link_retenciones.
        with patch.object(exporter, "_post_json", side_effect=fake_post) as post:
            exporter._write_batch_retenciones(_COLUMNS, [(2026, 100)])
            post.assert_called_once()

        link = exporter._link_store.get_link("retenciones", op_sk)
        assert link is not None
        assert link["remote_id"] == "5001"
        assert link["fingerprint"]
        assert link["retenciones_count"] == "1"

        # Segunda corrida sin cambios: no se reenvia nada (skip por fingerprint).
        with patch.object(exporter, "_post_json") as post2:
            exporter._write_batch_retenciones(_COLUMNS, [(2026, 100)])
            post2.assert_not_called()

    def test_resends_when_deducciones_change(self, monkeypatch, tmp_path):
        """Si las deducciones cambian en RAFAM, el fingerprint difiere y se reenvia."""
        exporter = _migrator(monkeypatch, tmp_path)
        op_sk = json.dumps({"ejercicio": 2026, "nro_op": 100}, sort_keys=True)
        exporter._link_store.save_link("orden_pago", op_sk, "5001")

        def fake_post(url, payload):
            return {
                "stats": {"retenciones": {"ok": 1, "error": 0}},
                "results": {
                    "retenciones": [
                        {"success": True, "external_id": {"ejercicio": 2026, "nro_op": 100}, "id": 5001}
                    ]
                },
            }

        # Primera corrida con importe 150.
        exporter.attach_source(
            _FakeSourceRepo({(2026, 100): [{"codigo_deduc": "3", "importe_reten": 150.0}]})
        )
        with patch.object(exporter, "_post_json", side_effect=fake_post):
            exporter._write_batch_retenciones(_COLUMNS, [(2026, 100)])
        fp1 = exporter._link_store.get_link("retenciones", op_sk)["fingerprint"]

        # Segunda corrida con importe distinto: debe reenviar y actualizar el fingerprint.
        exporter.attach_source(
            _FakeSourceRepo({(2026, 100): [{"codigo_deduc": "3", "importe_reten": 999.0}]})
        )
        with patch.object(exporter, "_post_json", side_effect=fake_post) as post:
            exporter._write_batch_retenciones(_COLUMNS, [(2026, 100)])
            post.assert_called_once()
        fp2 = exporter._link_store.get_link("retenciones", op_sk)["fingerprint"]
        assert fp1 != fp2
