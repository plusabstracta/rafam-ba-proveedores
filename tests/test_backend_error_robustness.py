"""Robustez frente a las respuestas de error de Paxapos (reportes sep-2026).

Tres sintomas del mail diario que estos tests fijan:

1. ``account_gasto_itemes doesn't exist`` (tenant sin migrar) se contaba como
   rechazo de datos de cada OP/gasto, gastaba intentos de la fila y el pipeline
   seguia martillando el backend batch tras batch.
2. Una retencion cuya OP fue borrada en Paxapos (``egreso_not_found``) fallaba
   el batch entero (seccion 100% fallida), congelaba el watermark y se
   reenviaba en cada corrida: 376 intentos en 3 dias, todos iguales.
3. Las bajas de OC confirmadas se reenviaban en cada corrida (1.728 por dia).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.backend_errors import BackendInfraError, classify_backend_error, is_dependency_error
from src.exporter import MigratorExporter
from src.mappers.oc_items import persist_links as oc_persist_links
from src.retry_store import (
    REASON_BACKEND_REJECTED,
    REASON_BACKEND_UNAVAILABLE,
    REASON_DEPENDENCY_MISSING,
    STATUS_PENDING,
    STATUS_PERMANENT,
    RetryStore,
)

_SQL_ERR = {
    "section": "gastos",
    "external_id": {"ejercicio": 2026, "nro_op": 1},
    "message": "SQLSTATE[42S02]: Base table or view not found: 1146 Table "
               "'paxapos_madariaga.account_gasto_itemes' doesn't exist",
}
_EGRESO_NOT_FOUND = {
    "section": "retenciones",
    "external_id": {"ejercicio": 2026, "nro_op": 100},
    "message": "Orden de pago destino no encontrada; se reintentara cuando la OP exista",
    "code": "egreso_not_found",
}
_VALIDATION = {
    "section": "ordenes_compra",
    "external_id": {"ejercicio": 2026, "uni_compra": 1, "nro_oc": 5},
    "message": "Error de validacion",
    "validationErrors": {"Pedido": {"total": ["requerido"]}},
}


class TestClassifyBackendError:
    def test_sql_es_infra_sin_contar_intentos(self):
        assert classify_backend_error(_SQL_ERR) == (REASON_BACKEND_UNAVAILABLE, "backend_infra")

    def test_egreso_not_found_es_dependencia(self):
        assert classify_backend_error(_EGRESO_NOT_FOUND) == (REASON_DEPENDENCY_MISSING, "egreso_not_found")
        assert is_dependency_error({"message": "OC aun no fue migrada; se reintentara"})

    def test_validacion_sigue_siendo_rechazo(self):
        assert classify_backend_error(_VALIDATION) == (REASON_BACKEND_REJECTED, "validation_error")

    def test_no_existe_generico_no_es_dependencia(self):
        # "clasificacion_id 7 no existe" es config invalida: debe agotar intentos.
        code, _ = classify_backend_error({"section": "gastos", "message": "clasificacion_id 7 no existe"})
        assert code == REASON_BACKEND_REJECTED


class TestRaiseOnMigratorErrors:
    def test_error_sql_levanta_backend_infra_aunque_haya_filas_ok(self):
        parsed = {
            "stats": {"gastos": {"ok": 3, "error": 1}},
            "errors": [_SQL_ERR],
        }
        with pytest.raises(BackendInfraError, match="infraestructura"):
            MigratorExporter._raise_on_migrator_errors(parsed, rows_tracked=True)

    def test_seccion_100_fallida_rastreable_no_falla_el_batch(self):
        parsed = {
            "stats": {"retenciones": {"ok": 0, "error": 1}},
            "errors": [_EGRESO_NOT_FOUND],
        }
        MigratorExporter._raise_on_migrator_errors(parsed, rows_tracked=True)

    def test_seccion_100_fallida_sin_cola_sigue_fallando(self):
        parsed = {
            "stats": {"retenciones": {"ok": 0, "error": 1}},
            "errors": [_EGRESO_NOT_FOUND],
        }
        with pytest.raises(RuntimeError, match="todas las filas"):
            MigratorExporter._raise_on_migrator_errors(parsed, rows_tracked=False)

    def test_seccion_100_fallida_sin_external_id_falla(self):
        parsed = {
            "stats": {"gastos": {"ok": 0, "error": 2}},
            "errors": [{"section": "gastos", "message": "fallo sin id"}],
        }
        with pytest.raises(RuntimeError, match="todas las filas"):
            MigratorExporter._raise_on_migrator_errors(parsed, rows_tracked=True)


class TestRetryStoreNuevosReasons:
    def test_backend_unavailable_no_suma_intentos(self, tmp_path):
        store = RetryStore(db_path=str(tmp_path / "r.db"), max_attempts=2)
        for _ in range(5):
            store.enqueue("orden_pago", "op-1", REASON_BACKEND_UNAVAILABLE, "sql roto")
        item = store.list_items("orden_pago")[0]
        assert item.status == STATUS_PENDING
        assert item.attempts == 1
        store.close()

    def test_mark_permanent_es_directo_y_recuperable(self, tmp_path):
        store = RetryStore(db_path=str(tmp_path / "r.db"))
        store.mark_permanent("retenciones", "op-1", REASON_BACKEND_REJECTED, "borrada", reason_detail="destination_deleted")
        item = store.list_items("retenciones")[0]
        assert item.status == STATUS_PERMANENT
        assert item.reason_detail == "destination_deleted"
        assert store.pending_external_ids("retenciones") == set()
        assert store.permanent_external_ids("retenciones") == {"op-1"}
        assert store.requeue("retenciones") == 1
        assert store.pending_external_ids("retenciones") == {"op-1"}
        store.close()


# ── Flujo completo retenciones con Egreso borrado en Paxapos ────────────────

def _migrator(monkeypatch, tmp_path):
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
            "tipos_retencion": [{"id": "103", "codigo": "3", "name": "Retencion ganancias"}],
        }
    }
    with patch("src.exporter.fetch_migrator_lookups", return_value=lookup_payload):
        return MigratorExporter(dry_run=False)


class _FakeSourceRepo:
    def __init__(self, deducciones_by_op):
        self._deducciones_by_op = deducciones_by_op

    def fetch_deducciones_for_ops(self, op_keys):
        return self._deducciones_by_op


_RET_COLUMNS = ["EJERCICIO", "NRO_OP"]
_OP_SK = json.dumps({"ejercicio": 2026, "nro_op": 100}, sort_keys=True)


def _egreso_not_found_post(calls: list):
    def _post(url, payload):
        calls.append(payload)
        return {
            "success": False,
            "stats": {"retenciones": {"ok": 0, "error": 1}},
            "results": {"retenciones": []},
            "errors": [_EGRESO_NOT_FOUND],
        }

    return _post


class TestRetencionesEgresoBorrado:
    def test_envia_egreso_id_del_link(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        exporter.attach_retry_store(RetryStore(db_path=str(tmp_path / "retry.db")))
        exporter._link_store.save_link("orden_pago", _OP_SK, "5001")
        exporter.attach_source(_FakeSourceRepo({(2026, 100): [{"codigo_deduc": "3", "importe_reten": 10.0}]}))

        calls: list = []
        with patch.object(exporter, "_post_json", side_effect=_egreso_not_found_post(calls)):
            exporter.write_batch("retenciones", _RET_COLUMNS, [(2026, 100)])

        assert calls[0]["retenciones"][0]["egreso_id"] == 5001

    def test_egreso_borrado_no_falla_el_batch_y_pasa_a_permanent(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter.attach_retry_store(retry)
        exporter._link_store.save_link("orden_pago", _OP_SK, "5001")
        exporter.attach_source(_FakeSourceRepo({(2026, 100): [{"codigo_deduc": "3", "importe_reten": 10.0}]}))

        calls: list = []
        with patch.object(exporter, "_post_json", side_effect=_egreso_not_found_post(calls)):
            # Antes: RuntimeError "todas las filas de una seccion" -> batch fallido.
            exporter.write_batch("retenciones", _RET_COLUMNS, [(2026, 100)])
            # Segunda corrida: la OP quedo marcada borrada -> no se vuelve a POSTear.
            exporter.write_batch("retenciones", _RET_COLUMNS, [(2026, 100)])

        assert len(calls) == 1
        item = retry.list_items("retenciones")[0]
        assert item.status == STATUS_PERMANENT
        assert item.reason_detail == "destination_deleted"
        assert item.attempts == 1
        op_link = exporter._link_store.get_link("orden_pago", _OP_SK)
        assert op_link["remote_id"] == "5001"
        assert op_link["deleted_at"]
        metrics = exporter.get_last_batch_migrator_metrics()
        assert metrics["errors"] == 0
        retry.close()

    def test_dependencia_se_reporta_como_deferred_no_error(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        exporter.attach_retry_store(RetryStore(db_path=str(tmp_path / "retry.db")))
        exporter._link_store.save_link("orden_pago", _OP_SK, "5001")
        exporter.attach_source(_FakeSourceRepo({(2026, 100): [{"codigo_deduc": "3", "importe_reten": 10.0}]}))

        with patch.object(exporter, "_post_json", side_effect=_egreso_not_found_post([])):
            exporter.write_batch("retenciones", _RET_COLUMNS, [(2026, 100)])

        metrics = exporter.get_last_batch_migrator_metrics()
        assert metrics["sent"] == 1
        assert metrics["deferred"] == 1
        assert metrics["errors"] == 0

    def test_retencion_permanent_no_se_reenvia(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter.attach_retry_store(retry)
        exporter._link_store.save_link("orden_pago", _OP_SK, "5001")
        exporter.attach_source(_FakeSourceRepo({(2026, 100): [{"codigo_deduc": "3", "importe_reten": 10.0}]}))
        retry.mark_permanent("retenciones", _OP_SK, REASON_BACKEND_REJECTED, "rechazo")

        with patch.object(exporter, "_post_json") as post:
            exporter.write_batch("retenciones", _RET_COLUMNS, [(2026, 100)])
            post.assert_not_called()
        retry.close()

    def test_op_sin_deducciones_ni_cambios_cierra_la_cola(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter.attach_retry_store(retry)
        retry.enqueue("retenciones", _OP_SK, REASON_DEPENDENCY_MISSING, "legacy")
        exporter._link_store.save_link("orden_pago", _OP_SK, "5001")
        exporter.attach_source(_FakeSourceRepo({}))

        with patch.object(exporter, "_post_json") as post:
            exporter.write_batch("retenciones", _RET_COLUMNS, [(2026, 100)])
            post.assert_not_called()

        assert retry.pending_external_ids("retenciones") == set()
        retry.close()

    def test_deducciones_no_impositivas_se_encolan_con_detalle_propio(self, monkeypatch, tmp_path):
        """IPS/IOMA/garantia (TIPO_DEDUC=O) no son retenciones para Paxapos: no es
        un problema de catalogo, y el reporte debe distinguirlo de 'unresolved'."""
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter.attach_retry_store(retry)
        exporter._link_store.save_link("orden_pago", _OP_SK, "5001")
        exporter.attach_source(_FakeSourceRepo({(2026, 100): [
            {"codigo_deduc": "4", "importe_reten": 10.0, "descripcion": "Garantia", "tipo_deduc": "O"},
            {"codigo_deduc": "1", "importe_reten": 5.0, "descripcion": "RETENCIONES I.P.S.", "tipo_deduc": "O"},
        ]}))

        with patch.object(exporter, "_post_json") as post:
            exporter.write_batch("retenciones", _RET_COLUMNS, [(2026, 100)])
            post.assert_not_called()

        item = retry.list_items("retenciones")[0]
        assert item.reason_code == REASON_DEPENDENCY_MISSING
        assert item.reason_detail == "non_tax_deduction"
        assert "Garantia" in item.error_message
        retry.close()

    def test_impositiva_sin_match_sigue_siendo_unresolved(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter.attach_retry_store(retry)
        exporter._link_store.save_link("orden_pago", _OP_SK, "5001")
        # cod 318 'Profesiones Liberales' es I pero no tiene alias ni match por nombre.
        exporter.attach_source(_FakeSourceRepo({(2026, 100): [
            {"codigo_deduc": "318", "importe_reten": 10.0, "descripcion": "Profesiones Liberales", "tipo_deduc": "I"},
            {"codigo_deduc": "4", "importe_reten": 5.0, "descripcion": "Garantia", "tipo_deduc": "O"},
        ]}))

        with patch.object(exporter, "_post_json") as post:
            exporter.write_batch("retenciones", _RET_COLUMNS, [(2026, 100)])
            post.assert_not_called()

        assert retry.list_items("retenciones")[0].reason_detail == "retention_type_unresolved"
        retry.close()


# ── Infra del backend en la cola ─────────────────────────────────────────────

class TestInfraEnCola:
    def test_sql_error_encola_sin_castigar_la_fila(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"), max_attempts=2)
        exporter.attach_retry_store(retry)
        parsed = {"stats": {"gastos": {"ok": 0, "error": 1}}, "errors": [_SQL_ERR]}
        for _ in range(3):
            exporter._record_batch_outcomes("solic_gastos", parsed)
        item = retry.list_items("solic_gastos")[0]
        assert item.reason_code == REASON_BACKEND_UNAVAILABLE
        assert item.status == STATUS_PENDING
        retry.close()


# ── Bajas de OC idempotentes ─────────────────────────────────────────────────

class _LinkStub:
    def __init__(self):
        self.saved: list[dict] = []

    def save_link(self, **kwargs):
        self.saved.append(kwargs)


class TestBajasOcIdempotentes:
    @pytest.mark.parametrize("mode", ["soft_delete", "already_deleted", "skipped_not_found"])
    def test_persist_marca_deleted_at_en_baja(self, mode):
        store = _LinkStub()
        parsed = {
            "results": {
                "ordenes_compra": [
                    {"success": True, "mode": mode, "id": 77,
                     "external_id": {"ejercicio": 2026, "uni_compra": 1, "nro_oc": 9}}
                ]
            }
        }
        oc_persist_links(parsed, {}, store)
        assert store.saved[0]["deleted_at"]

    def test_persist_limpia_deleted_at_en_alta(self):
        store = _LinkStub()
        parsed = {
            "results": {
                "ordenes_compra": [
                    {"success": True, "mode": "create", "id": 77,
                     "external_id": {"ejercicio": 2026, "uni_compra": 1, "nro_oc": 9}}
                ]
            }
        }
        oc_persist_links(parsed, {}, store)
        assert store.saved[0]["deleted_at"] is None

    def test_baja_confirmada_no_se_reenvia(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        exporter.attach_retry_store(RetryStore(db_path=str(tmp_path / "retry.db")))
        exporter._link_store.save_link("proveedores", "5", "9001")
        columns = [
            "EJERCICIO", "UNI_COMPRA", "NRO_OC", "COD_PROV",
            "OC_FECH_OC", "OC_OBSERVACIONES", "OC_ESTADO_OC", "OC_FECH_CONFIRM", "OC_IMPORTE_TOT",
            "SG_JURISDICCION",
            "ITEM_OC", "DELEG_SOLIC", "NRO_SOLIC", "DESCRIPCION", "CANTIDAD", "IMP_UNITARIO", "CANT_RECIB",
        ]
        row_anulada = (
            2026, 1, 3130, 5,
            "2026-08-01", "OC", "A", "2026-08-02", 1000.0,
            None,
            1, 10, 20, "Item", 2.0, 500.0, 2.0,
        )
        oc_sk = json.dumps({"ejercicio": 2026, "nro_oc": 3130, "uni_compra": 1}, sort_keys=True)
        exporter._link_store.save_link("orden_compra", oc_sk, "8001", estado_oc="R")

        calls: list = []

        def _post(url, payload):
            calls.append(payload)
            ext = payload["ordenes_compra"][0]["external_id"]
            return {
                "stats": {"ordenes_compra": {"ok": 1, "error": 0}},
                "results": {"ordenes_compra": [
                    {"success": True, "mode": "soft_delete", "id": 8001, "external_id": ext}
                ]},
                "errors": [],
            }

        with patch.object(exporter, "_post_json", side_effect=_post):
            exporter.write_batch("oc_items", columns, [row_anulada])
            exporter.write_batch("oc_items", columns, [row_anulada])

        assert len(calls) == 1
        assert calls[0]["ordenes_compra"][0]["Pedido"]["deleted"] == 1
        link = exporter._link_store.get_link("orden_compra", oc_sk)
        assert link["estado_oc"] == "A" and link["deleted_at"]
