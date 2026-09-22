"""Cobertura del endurecimiento del circuito OC/OP/retenciones (F1+).

Cubre tres garantias pedidas explicitamente por el operador:

1. Ningun rechazo del migrator se pierde sin pasar por `retry_queue`: un error
   de fila que no se puede identificar (external_id ausente/incompleto) hace
   que el batch se trate como fallido -- el checkpoint se congela en vez de
   avanzar sobre una fila sin red de reintento.
2. Los errores de la seccion "gastos" embebida en el payload de `orden_pago`
   se encolan bajo la entidad correcta (`solic_gastos`), no se descartan.
3. El detalle legible (OC/OP/retencion/gasto/proveedor) llega a logs, al mail
   y al forzado manual (`retry-queue --send-now`).
"""

from __future__ import annotations

import argparse
import json
import os
from unittest.mock import patch

import pytest

import main as main_module
from src.exporter import MigratorExporter
from src.retry_labels import describe_retry_key
from src.retry_store import RetryStore, STATUS_PENDING


def _migrator(monkeypatch, tmp_path):
    monkeypatch.setenv("PAXAPOS_URL", "https://example.test")
    monkeypatch.setenv("PAXAPOS_TENANT", "tenant")
    monkeypatch.setenv("PAXAPOS_API_KEY", "key")
    monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "links.db"))
    monkeypatch.setenv("PAXAPOS_VERIFY_SSL", "true")
    with patch("src.exporter.fetch_migrator_lookups", return_value={"lookups": {}}):
        return MigratorExporter(dry_run=False)


class TestUnrecordedErrorFreezesBatch:
    """El nucleo del fix: un rechazo sin external_id usable no puede colarse
    como batch 'exitoso' -- de lo contrario el checkpoint avanzaria sobre una
    fila que jamas quedo en la cola de reintentos (perdida definitiva)."""

    def test_write_batch_raises_and_no_encola_nada(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter.attach_retry_store(retry)

        bad_parsed = {
            "stats": {"ordenes_pago": {"ok": 0, "error": 1}},
            "results": {"ordenes_pago": []},
            "errors": [{"section": "ordenes_pago", "message": "fallo raro sin id"}],
        }

        def _fake_dispatch(entity, columns, rows):
            exporter._last_parsed = bad_parsed

        monkeypatch.setattr(exporter, "_dispatch_batch", _fake_dispatch)

        with pytest.raises(RuntimeError, match="sin external_id utilizable"):
            exporter.write_batch("orden_pago", ["EJERCICIO", "NRO_OP"], [(2026, 1)])

        # Como no se pudo encolar, no hay forma de recuperarla via
        # retry-queue: por eso el batch DEBE tratarse como fallido.
        assert retry.list_items("orden_pago") == []
        retry.close()

    def test_error_con_external_id_completo_si_encola_y_no_lanza(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter.attach_retry_store(retry)

        ok_parsed = {
            "stats": {"ordenes_pago": {"ok": 0, "error": 1}},
            "results": {"ordenes_pago": []},
            "errors": [{
                "section": "ordenes_pago",
                "external_id": {"ejercicio": 2026, "nro_op": 55},
                "message": "rechazada por validacion",
                "validationErrors": {"Egreso": {"importe": ["requerido"]}},
            }],
        }

        def _fake_dispatch(entity, columns, rows):
            exporter._last_parsed = ok_parsed

        monkeypatch.setattr(exporter, "_dispatch_batch", _fake_dispatch)

        # No debe lanzar: la fila SI se pudo encolar.
        exporter.write_batch("orden_pago", ["EJERCICIO", "NRO_OP"], [(2026, 55)])

        items = retry.list_items("orden_pago")
        assert len(items) == 1
        assert items[0].external_id == json.dumps({"ejercicio": 2026, "nro_op": 55}, sort_keys=True)
        assert items[0].status == STATUS_PENDING
        retry.close()


class TestGastosEmbebidoEnOrdenPago:
    """Antes del fix: un error de la seccion 'gastos' dentro de la respuesta de
    orden_pago no matcheaba la seccion primaria ('ordenes_pago') y se
    descartaba en silencio -- ni bajo 'orden_pago' ni bajo 'solic_gastos'."""

    def test_se_encola_bajo_solic_gastos_no_bajo_orden_pago(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter.attach_retry_store(retry)

        parsed = {
            "stats": {
                "ordenes_pago": {"ok": 1, "error": 0},
                "gastos": {"ok": 0, "error": 1},
            },
            "results": {
                "ordenes_pago": [{
                    "success": True,
                    "external_id": {"ejercicio": 2026, "nro_op": 1},
                    "mode": "create",
                }],
            },
            "errors": [{
                "section": "gastos",
                "external_id": {"ejercicio": 2026, "deleg_solic": 5, "nro_solic": 10},
                "message": "gasto rechazado por validacion",
            }],
        }

        def _fake_dispatch(entity, columns, rows):
            exporter._last_parsed = parsed

        monkeypatch.setattr(exporter, "_dispatch_batch", _fake_dispatch)

        exporter.write_batch("orden_pago", ["EJERCICIO", "NRO_OP"], [(2026, 1)])

        gasto_key = json.dumps(
            {"ejercicio": 2026, "deleg_solic": 5, "nro_solic": 10}, sort_keys=True
        )
        assert [it.external_id for it in retry.list_items("solic_gastos")] == [gasto_key]
        assert retry.list_items("orden_pago") == []
        retry.close()


class TestDescribeRetryKey:
    def test_oc(self):
        key = json.dumps({"ejercicio": 2026, "uni_compra": 3, "nro_oc": 1023}, sort_keys=True)
        assert describe_retry_key("oc_items", key) == "OC 2026-3-1023"

    def test_op(self):
        key = json.dumps({"ejercicio": 2026, "nro_op": 1023}, sort_keys=True)
        assert describe_retry_key("orden_pago", key) == "OP 2026-1023"

    def test_retencion(self):
        key = json.dumps({"ejercicio": 2026, "nro_op": 1023}, sort_keys=True)
        assert describe_retry_key("retenciones", key) == "Retencion de OP 2026-1023"

    def test_gasto(self):
        key = json.dumps({"ejercicio": 2026, "deleg_solic": 5, "nro_solic": 10}, sort_keys=True)
        assert describe_retry_key("solic_gastos", key) == "Gasto/Solicitud 2026-5-10"

    def test_proveedor_json(self):
        key = json.dumps({"cod_prov": 1234}, sort_keys=True)
        assert describe_retry_key("proveedores", key) == "Proveedor COD_PROV=1234"

    def test_proveedor_plano(self):
        assert describe_retry_key("proveedores", "1234") == "Proveedor COD_PROV=1234"

    def test_clasificacion(self):
        key = json.dumps({"codigo": "1.1.6.1"}, sort_keys=True)
        assert describe_retry_key("clasificaciones", key) == "Clasificacion 1.1.6.1"

    def test_forma_desconocida_no_lanza(self):
        assert describe_retry_key("futura_entidad", "no-es-json") == "futura_entidad no-es-json"


class TestEnqueueLogueaAlPrimerEncolado:
    def test_warning_al_encolar_por_primera_vez(self, tmp_path, caplog):
        store = RetryStore(db_path=str(tmp_path / "retry.db"))
        key = json.dumps({"ejercicio": 2026, "nro_op": 42}, sort_keys=True)
        with caplog.at_level("WARNING"):
            store.enqueue("orden_pago", key, "backend_rejected", "rechazada")
        assert any("OP 2026-42" in rec.message for rec in caplog.records)
        store.close()


class TestSendNowCli:
    def test_requiere_entity(self):
        args = argparse.Namespace(
            entity=None, status=None, external_id=None,
            requeue=False, dismiss=False, note=None, send_now=True,
        )
        with pytest.raises(SystemExit):
            main_module.cmd_retry_queue(args)

    def test_dispara_force_send_pending_bajo_lock(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "_LOCK_PATH", tmp_path / "migrator.lock")
        monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "cp.db"))

        calls: list[str] = []

        def _fake_force_send(retry_store, entity, batch_size=500):
            calls.append(entity)

        monkeypatch.setattr(main_module, "_force_send_pending", _fake_force_send)

        args = argparse.Namespace(
            entity="orden_pago", status=None, external_id=None,
            requeue=False, dismiss=False, note=None, send_now=True,
        )
        main_module.cmd_retry_queue(args)
        assert calls == ["orden_pago"]

    def test_dismiss_y_send_now_son_excluyentes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "_LOCK_PATH", tmp_path / "migrator.lock")
        monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "cp.db"))
        args = argparse.Namespace(
            entity="orden_pago", status=None, external_id="x",
            requeue=False, dismiss=True, note="motivo", send_now=True,
        )
        with pytest.raises(SystemExit):
            main_module.cmd_retry_queue(args)
