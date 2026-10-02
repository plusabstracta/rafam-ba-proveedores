"""Fase 2 — un mail por cada registro que no llego a Paxapos.

1. Cuando se avisa: 1ra falla, paso a 'permanent' y nueva falla despues de un
   reenvio manual. Esperar una dependencia no avisa. Las filas que ya estaban
   en la cola al deployar no disparan mails.
2. Robustez del envio: SMTP caido no marca nada (se reintenta), tope por
   corrida con un mail resumen para el excedente.
3. Lo que antes se omitia en silencio ahora queda en la cola (y avisa).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from unittest.mock import patch

import pytest

from src import notifier, record_alerts
from src.exporter import MigratorExporter
from src.retry_store import (
    REASON_BACKEND_REJECTED,
    REASON_DEPENDENCY_MISSING,
    REASON_VALIDATION_CLIENT,
    STATUS_PENDING,
    STATUS_PERMANENT,
    RetryItem,
    RetryStore,
)
from src.run_history import aggregate_runs
from src.utils import utc_sql_to_local

_OP_KEY = json.dumps({"ejercicio": 2026, "nro_op": 1023}, sort_keys=True)
_OP_KEY_2 = json.dumps({"ejercicio": 2026, "nro_op": 1024}, sort_keys=True)
_OP_KEY_3 = json.dumps({"ejercicio": 2026, "nro_op": 1025}, sort_keys=True)


@pytest.fixture
def alerts_on(monkeypatch):
    monkeypatch.setenv("NOTIFY_RECORD_ALERTS", "true")
    monkeypatch.setattr(notifier, "notifications_enabled", lambda: True)


@pytest.fixture
def sent(monkeypatch, alerts_on):
    """Captura los mails individuales y el de excedente (sin SMTP)."""
    mails: list[tuple[str, object]] = []

    def _record(item, *, max_attempts):
        mails.append(("record", item))
        return True

    def _overflow(items):
        mails.append(("overflow", list(items)))
        return True

    monkeypatch.setattr(notifier, "notify_record_failure", _record)
    monkeypatch.setattr(notifier, "notify_record_failures_overflow", _overflow)
    return mails


def _store(tmp_path, **kwargs):
    return RetryStore(db_path=str(tmp_path / "retry.db"), **kwargs)


# ─── 1. Cuando se avisa ───────────────────────────────────────────────────────


class TestCuandoSeAvisa:
    def test_primera_falla_avisa_una_sola_vez(self, tmp_path, sent):
        store = _store(tmp_path)
        store.enqueue("orden_pago", _OP_KEY, REASON_BACKEND_REJECTED, "rechazada")

        assert record_alerts.flush_record_alerts(store) == 1
        assert [kind for kind, _ in sent] == ["record"]
        assert sent[0][1].external_id == _OP_KEY

        # Misma falla en la corrida siguiente: no vuelve a avisar.
        store.enqueue("orden_pago", _OP_KEY, REASON_BACKEND_REJECTED, "rechazada")
        assert record_alerts.flush_record_alerts(store) == 0
        assert len(sent) == 1
        store.close()

    def test_paso_a_permanent_avisa_de_nuevo(self, tmp_path, sent):
        store = _store(tmp_path, max_attempts=2)
        store.enqueue("orden_pago", _OP_KEY, REASON_BACKEND_REJECTED, "rechazada")
        record_alerts.flush_record_alerts(store)
        store.enqueue("orden_pago", _OP_KEY, REASON_BACKEND_REJECTED, "rechazada")
        assert store.list_items("orden_pago")[0].status == STATUS_PERMANENT

        assert record_alerts.flush_record_alerts(store) == 1
        assert sent[-1][1].status == STATUS_PERMANENT
        assert record_alerts.flush_record_alerts(store) == 0
        store.close()

    def test_nueva_falla_despues_de_reenvio_manual_avisa(self, tmp_path, sent):
        store = _store(tmp_path)
        store.mark_permanent("orden_pago", _OP_KEY, REASON_BACKEND_REJECTED, "rechazada")
        record_alerts.flush_record_alerts(store)
        assert len(sent) == 1

        store.requeue("orden_pago", _OP_KEY)            # lo que hace `resend`
        store.enqueue("orden_pago", _OP_KEY, REASON_BACKEND_REJECTED, "sigue rechazada")
        assert record_alerts.flush_record_alerts(store) == 1
        assert sent[-1][1].error_message == "sigue rechazada"
        store.close()

    def test_validacion_del_cliente_avisa_y_dependencia_no(self, tmp_path, sent):
        store = _store(tmp_path)
        store.enqueue("orden_pago", _OP_KEY, REASON_DEPENDENCY_MISSING, "OC aun no migrada")
        store.enqueue("orden_pago", _OP_KEY_2, REASON_VALIDATION_CLIENT, "IMPORTE_TOTAL NULL")
        store.enqueue("orden_pago", _OP_KEY_3, "backend_unavailable", "SQLSTATE[42S02]")

        assert record_alerts.flush_record_alerts(store) == 1
        assert sent[0][1].external_id == _OP_KEY_2
        store.close()

    def test_filas_previas_al_deploy_no_disparan_mails(self, tmp_path, sent):
        """La cola de produccion ya tiene ~96 filas: el primer deploy no puede
        mandar un mail por cada una (ya figuran en el mail diario)."""
        db = tmp_path / "retry.db"
        conn = sqlite3.connect(db)
        conn.execute(
            """
            CREATE TABLE retry_queue (
                entity TEXT NOT NULL, external_id TEXT NOT NULL, reason_code TEXT NOT NULL,
                reason_detail TEXT, error_message TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                first_seen TEXT NOT NULL, last_attempt TEXT, next_retry_after TEXT,
                status TEXT NOT NULL DEFAULT 'pending', payload_snapshot TEXT,
                PRIMARY KEY (entity, external_id)
            )
            """
        )
        conn.execute(
            "INSERT INTO retry_queue (entity, external_id, reason_code, attempts, first_seen, status) "
            "VALUES ('proveedores', '110', 'backend_rejected', 10, '2026-09-18 10:00:00', 'permanent')"
        )
        conn.execute(
            "INSERT INTO retry_queue (entity, external_id, reason_code, attempts, first_seen, status) "
            "VALUES ('solic_gastos', 'x', 'backend_rejected', 1, '2026-09-23 10:00:00', 'pending')"
        )
        conn.commit()
        conn.close()

        store = RetryStore(db_path=str(db))
        assert store.pending_alerts() == []
        assert {it.alert_state for it in store.list_items()} == {"permanent", "pending"}
        assert record_alerts.flush_record_alerts(store) == 0
        # ...pero si una de ellas despues pasa a permanent, si avisa.
        store.mark_permanent("solic_gastos", "x", REASON_BACKEND_REJECTED, "agoto intentos")
        assert record_alerts.flush_record_alerts(store) == 1
        store.close()


# ─── 2. Robustez del envio ────────────────────────────────────────────────────


class TestEnvio:
    def test_smtp_caido_no_marca_y_corta(self, tmp_path, monkeypatch, alerts_on):
        store = _store(tmp_path)
        for key in (_OP_KEY, _OP_KEY_2, _OP_KEY_3):
            store.enqueue("orden_pago", key, REASON_BACKEND_REJECTED, "rechazada")
        intentos = []

        def _falla(item, *, max_attempts):
            intentos.append(item.external_id)
            return False

        monkeypatch.setattr(notifier, "notify_record_failure", _falla)
        assert record_alerts.flush_record_alerts(store) == 0
        assert len(intentos) == 1, "con el SMTP caido no se insiste con cada fila"
        assert len(store.pending_alerts()) == 3, "se reintenta en la proxima corrida"
        store.close()

    def test_tope_por_corrida_manda_un_resumen_con_el_resto(self, tmp_path, monkeypatch, sent):
        monkeypatch.setenv("NOTIFY_RECORD_ALERT_MAX_PER_RUN", "2")
        store = _store(tmp_path)
        for key in (_OP_KEY, _OP_KEY_2, _OP_KEY_3):
            store.enqueue("orden_pago", key, REASON_BACKEND_REJECTED, "rechazada")

        assert record_alerts.flush_record_alerts(store) == 3
        assert [kind for kind, _ in sent] == ["record", "record", "overflow"]
        assert [it.external_id for it in sent[2][1]] == [_OP_KEY_3]
        assert store.pending_alerts() == []
        store.close()

    def test_tope_cero_es_sin_tope(self, tmp_path, monkeypatch, sent):
        monkeypatch.setenv("NOTIFY_RECORD_ALERT_MAX_PER_RUN", "0")
        store = _store(tmp_path)
        for key in (_OP_KEY, _OP_KEY_2, _OP_KEY_3):
            store.enqueue("orden_pago", key, REASON_BACKEND_REJECTED, "rechazada")
        assert record_alerts.flush_record_alerts(store) == 3
        assert [kind for kind, _ in sent] == ["record"] * 3
        store.close()

    def test_deshabilitado_no_manda_ni_marca(self, tmp_path, monkeypatch, sent):
        monkeypatch.setenv("NOTIFY_RECORD_ALERTS", "false")
        store = _store(tmp_path)
        store.enqueue("orden_pago", _OP_KEY, REASON_BACKEND_REJECTED, "rechazada")
        assert record_alerts.flush_record_alerts(store) == 0
        assert sent == []
        assert len(store.pending_alerts()) == 1
        store.close()


class TestContenidoDelMail:
    def _item(self, **overrides):
        base = dict(
            entity="oc_items",
            external_id=json.dumps({"ejercicio": 2026, "nro_oc": 1023, "uni_compra": 3}, sort_keys=True),
            reason_code=REASON_BACKEND_REJECTED,
            reason_detail="validation_error",
            error_message='Error guardando Pedido | validationErrors={"proveedor_id": ["inactivo"]}',
            attempts=1,
            status=STATUS_PENDING,
            first_seen="2026-10-01 13:00:00",
            last_attempt="2026-10-01 13:10:00",
        )
        base.update(overrides)
        return RetryItem(**base)

    def test_mail_del_registro(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_ALERT_TO", "compras@example.test, soporte@example.test")
        with patch.object(notifier, "send_notification", return_value=True) as send:
            assert notifier.notify_record_failure(self._item(), max_attempts=10)
        subject, body = send.call_args.args[:2]
        assert subject == "OC 2026-3-1023: Paxapos lo rechazo"
        assert "inactivo" in body
        assert "intento 1 de 10" in body
        assert 'resend --entity oc_items --key "OC 2026-3-1023"' in body
        assert utc_sql_to_local("2026-10-01 13:00:00") in body
        assert send.call_args.kwargs["recipients"] == ["compras@example.test", "soporte@example.test"]

    def test_mail_de_paso_a_permanent(self):
        item = self._item(
            status=STATUS_PERMANENT, attempts=10, reason_code=REASON_VALIDATION_CLIENT,
            next_retry_after="2026-10-01 19:10:00",
        )
        with patch.object(notifier, "send_notification", return_value=True) as send:
            notifier.notify_record_failure(item, max_attempts=10)
        subject, body = send.call_args.args[:2]
        assert subject.startswith("OC 2026-3-1023: PASO A PERMANENT")
        assert "datos invalidos" in subject
        # 'permanent' ya no es un callejon sin salida: dice cuando se reintenta solo.
        assert "ya no se reintenta en cada corrida pero se vuelve a intentar solo" in body
        assert f"proximo intento {utc_sql_to_local('2026-10-01 19:10:00')}" in body
        assert send.call_args.kwargs["recipients"] is None, "sin NOTIFY_ALERT_TO va a NOTIFY_TO"

    def test_mail_de_permanent_terminal_no_promete_reintento(self):
        item = self._item(status=STATUS_PERMANENT, attempts=1, auto_retry=0)
        with patch.object(notifier, "send_notification", return_value=True) as send:
            notifier.notify_record_failure(item, max_attempts=10)
        body = send.call_args.args[1]
        assert "NO se reintenta solo (rechazo terminal)" in body

    def test_mail_de_espera_vencida(self):
        item = self._item(
            reason_code=REASON_DEPENDENCY_MISSING, reason_detail="order_not_migrated",
            first_seen="2026-01-01 10:00:00",
            error_message="OP 2026-1023: OC aun no migrada en Paxapos",
        )
        with patch.object(notifier, "send_notification", return_value=True) as send:
            notifier.notify_record_failure(item, max_attempts=10)
        subject, body = send.call_args.args[:2]
        assert "que no se puede migrar (espera vencida)" in subject
        assert "OC aun no migrada" in body
        assert "Revisar en RAFAM lo que espera este registro" in body


    def test_mail_de_excedente_agrupa_por_causa(self):
        items = [
            self._item(entity="retenciones", external_id=json.dumps({"ejercicio": 2026, "nro_op": n}),
                       reason_code=REASON_VALIDATION_CLIENT, reason_detail="retention_type_unresolved")
            for n in (1, 2)
        ] + [self._item()]
        with patch.object(notifier, "send_notification", return_value=True) as send:
            notifier.notify_record_failures_overflow(items)
        subject, body = send.call_args.args[:2]
        assert subject.startswith("3 registro(s) mas")
        assert "2 x retenciones — validation_client/retention_type_unresolved" in body
        assert "Retencion de OP 2026-2" in body


def test_utc_sql_to_local_convierte_a_la_zona_del_server(monkeypatch):
    monkeypatch.setenv("TZ", "America/Argentina/Buenos_Aires")
    time.tzset()
    try:
        assert utc_sql_to_local("2026-10-01 13:00:00") == "2026-10-01 10:00:00"
        assert utc_sql_to_local(None) == "—"
        assert utc_sql_to_local("no-es-fecha") == "no-es-fecha"
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_resumen_diario_suma_las_alertas_del_dia():
    runs = [
        {"duration_formatted": "00:00:05", "success": True, "entities": [], "record_alerts_sent": 2},
        {"duration_formatted": "00:00:05", "success": True, "entities": [], "record_alerts_sent": 1},
        {"duration_formatted": "00:00:05", "success": True, "entities": []},
    ]
    summary, _ = aggregate_runs(runs, "2026-10-01")
    assert summary["record_alerts_sent"] == 3

    with patch.object(notifier, "_is_enabled", return_value=True), \
            patch.object(notifier, "send_notification", return_value=True) as send:
        notifier.notify_run_report(summary, [], dry_run=False)
    assert "Alertas por registro enviadas: 3" in send.call_args.args[1]


# ─── 3. Omitidos que antes se perdian en silencio ─────────────────────────────


def _migrator(monkeypatch, tmp_path):
    monkeypatch.setenv("PAXAPOS_URL", "https://example.test")
    monkeypatch.setenv("PAXAPOS_TENANT", "tenant")
    monkeypatch.setenv("PAXAPOS_API_KEY", "key")
    monkeypatch.setenv("PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID", "4")
    monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "links.db"))
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
        exporter = MigratorExporter(dry_run=False)
    retry = RetryStore(db_path=str(tmp_path / "retry.db"))
    exporter.attach_retry_store(retry)
    return exporter, retry


_OC_COLUMNS = [
    "EJERCICIO", "UNI_COMPRA", "NRO_OC", "COD_PROV",
    "OC_FECH_OC", "OC_OBSERVACIONES", "OC_ESTADO_OC", "OC_FECH_CONFIRM", "OC_IMPORTE_TOT",
    "SG_JURISDICCION",
    "ITEM_OC", "DELEG_SOLIC", "NRO_SOLIC", "DESCRIPCION", "CANTIDAD", "IMP_UNITARIO", "CANT_RECIB",
]


def _oc_row(nro_oc, estado="R", cod_prov=5, cantidad=1.0):
    return (
        2026, 1, nro_oc, cod_prov,
        "2026-08-01", "OC", estado, "2026-08-02", 500.0,
        None,
        1, 10, 30, "Item", cantidad, 500.0, 1.0,
    )


class TestOmitidosVanALaCola:
    def test_oc_confirmada_sin_items_mapeables(self, monkeypatch, tmp_path):
        exporter, retry = _migrator(monkeypatch, tmp_path)
        exporter._link_store.save_link("proveedores", "5", "9001")
        with patch.object(exporter, "_post_json") as post:
            # 10: confirmada (R) sin cantidad -> dato roto. 11: sin confirmar -> normal.
            exporter.write_batch(
                "oc_items", _OC_COLUMNS,
                [_oc_row(10, cantidad=None), _oc_row(11, estado="N", cantidad=None)],
            )
            post.assert_not_called()
        [item] = retry.list_items("oc_items")
        assert json.loads(item.external_id)["nro_oc"] == 10
        assert (item.reason_code, item.reason_detail) == (REASON_VALIDATION_CLIENT, "invalid_items")
        retry.close()

    def test_oc_sin_proveedor_encola_al_proveedor(self, monkeypatch, tmp_path):
        exporter, retry = _migrator(monkeypatch, tmp_path)
        with patch.object(exporter, "_post_json") as post:
            exporter.write_batch("oc_items", _OC_COLUMNS, [_oc_row(10, cod_prov=77)])
            post.assert_not_called()
        assert retry.list_items("oc_items") == [], "la OC (full_load) vuelve a entrar sola"
        [prov] = retry.list_items("proveedores")
        assert prov.external_id == "77"
        assert (prov.reason_code, prov.reason_detail) == (REASON_DEPENDENCY_MISSING, "required_by_oc_items")
        retry.close()

    _OP_COLUMNS = [
        "EJERCICIO", "NRO_OP", "ESTADO_OP", "CONFIRMADO", "FECH_CONFIRM",
        "IMPORTE_TOTAL", "CONCEPTO", "COD_PROV",
        "SG_DELEG_SOLIC", "SG_NRO_SOLIC", "OPI_NRO_COMPROB",
    ]

    def _op_row(self, importe, comprob="0001-00000100"):
        return ("2026", "1023", "C", "S", "2026-03-11 00:00:00", importe, "Pago", "555", "1", "100", comprob)

    def test_op_con_importe_nulo_se_encola_una_vez(self, monkeypatch, tmp_path):
        exporter, retry = _migrator(monkeypatch, tmp_path)
        with patch.object(exporter, "_post_json") as post:
            # Dos filas de la misma OP (dos comprobantes imputados).
            exporter.write_batch(
                "orden_pago", self._OP_COLUMNS,
                [self._op_row(None), self._op_row(None, "0001-00000101")],
            )
            post.assert_not_called()
        [item] = retry.list_items("orden_pago")
        assert (item.reason_code, item.reason_detail, item.attempts) == (
            REASON_VALIDATION_CLIENT, "invalid_amount", 1,
        )
        retry.close()

    def test_op_con_importe_cero_solo_se_loguea(self, monkeypatch, tmp_path):
        exporter, retry = _migrator(monkeypatch, tmp_path)
        with patch.object(exporter, "_post_json"):
            exporter.write_batch("orden_pago", self._OP_COLUMNS, [self._op_row("0")])
        assert retry.list_items("orden_pago") == []
        retry.close()

    def test_retenciones_que_superan_el_total_quedan_en_la_cola(self, monkeypatch, tmp_path):
        exporter, retry = _migrator(monkeypatch, tmp_path)
        exporter._link_store.save_link("proveedores", "555", remote_id="42")

        class _Repo:
            def fetch_forma_pago_for_ops(self, keys):
                return {}

            def fetch_deducciones_for_ops(self, keys):
                return {(2026, 1023): [{"codigo_deduc": "3", "importe_reten": 900.0, "descripcion": "Ganancias"}]}

        exporter.attach_source(_Repo())
        sent = []

        def _post(url, payload):
            sent.append(payload)
            ops = payload["ordenes_pago"]
            return {
                "stats": {"ordenes_pago": {"ok": len(ops), "error": 0}},
                "results": {"ordenes_pago": [
                    {"success": True, "mode": "create", "external_id": op["external_id"], "id": 1} for op in ops
                ]},
            }

        with patch.object(exporter, "_post_json", side_effect=_post):
            exporter.write_batch("orden_pago", self._OP_COLUMNS, [self._op_row("500")])
        assert "retenciones" not in sent[0]["ordenes_pago"][0], "la OP sale sin retenciones"
        [item] = retry.list_items("retenciones")
        assert (item.reason_code, item.reason_detail) == (REASON_VALIDATION_CLIENT, "retentions_exceed_total")
        retry.close()

    def test_proveedor_invalido(self, monkeypatch, tmp_path):
        exporter, retry = _migrator(monkeypatch, tmp_path)
        columns = ["COD_PROV", "FANTASIA", "RAZON_SOCIAL"]
        with patch.object(exporter, "_post_json") as post:
            exporter.write_batch("proveedores", columns, [(110, None, None), (50001, None, None)])
            post.assert_not_called()
        [item] = retry.list_items("proveedores")
        assert item.external_id == "110", "un proveedor excluido por configuracion no es un error"
        assert item.reason_code == REASON_VALIDATION_CLIENT
        retry.close()

    def test_gasto_encolado_que_ya_esta_completo_se_cierra(self, monkeypatch, tmp_path):
        from src.mappers.solic_gastos import SolicGastosMapper

        class _Lookup:
            def resolve_tipo_factura_id(self, _v):
                return 2

        class _LinkStore:
            def get_sent_oc_gasto_refs(self):
                return {"SG-2026-1-100"}

            def get_all_links(self, _entity):
                return [{
                    "source_key": json.dumps({"ejercicio": 2026, "nro_oc": 50, "uni_compra": 1}, sort_keys=True),
                    "remote_id": "700",
                    "gasto_refs": "SG-2026-1-100",
                }]

            def get_remote_id(self, _entity, _key):
                return "42"

            def get_link(self, _entity, _key):
                return None

        resolver = {"success": True, "gastos": [{
            "id": 91, "pedido_id": 700, "proveedor_id": 42,
            "factura_nro": "11", "punto_de_venta": "0001", "empty_fields": [],
        }]}
        mapper = SolicGastosMapper(
            link_store=_LinkStore(), lookup_resolver=_Lookup(),
            resolve_gastos_fn=lambda pedido_ids, comprobantes: resolver,
        )
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        mapper._retry_store = retry
        sg_key = json.dumps({"deleg_solic": 1, "ejercicio": 2026, "nro_solic": 100}, sort_keys=True)
        retry.enqueue("solic_gastos", sg_key, REASON_BACKEND_REJECTED, "factura ya cargada")

        columns = [
            "EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC", "FECH_SOLIC", "ESTADO_SOLIC", "IMPORTE_TOT",
            "CTA_COMPROB_COUNT", "CTA_NRO_COMPROB", "CTA_TIPO_COMPROB", "CTA_FECH_COMPROB",
            "CTA_IMPORTE_COMPR", "OC_COD_PROV",
        ]
        row = ("2026", "1", "100", "2026-03-01", "C", "1000", "1", "0001-11", "FA", "2026-03-01", "1000", "77")
        payload, _ = mapper.build_payload(columns, [row], dry_run=False, payload_options={})
        assert payload is None
        assert retry.list_items("solic_gastos") == []
        retry.close()


def test_alertas_no_rompen_la_corrida(tmp_path, monkeypatch):
    import main as main_module

    def _explota(_store):
        raise RuntimeError("smtp roto")

    monkeypatch.setattr(main_module, "flush_record_alerts", _explota)
    store = _store(tmp_path)
    assert main_module._flush_record_alerts(store) == 0
    store.close()


def test_sin_smtp_configurado_no_manda(tmp_path, monkeypatch):
    for var in ("NOTIFY_ENABLED", "NOTIFY_SMTP_HOST"):
        monkeypatch.delenv(var, raising=False)
    store = _store(tmp_path)
    store.enqueue("orden_pago", _OP_KEY, REASON_BACKEND_REJECTED, "rechazada")
    assert not os.getenv("NOTIFY_SMTP_HOST")
    assert record_alerts.flush_record_alerts(store) == 0
    assert len(store.pending_alerts()) == 1
    store.close()
