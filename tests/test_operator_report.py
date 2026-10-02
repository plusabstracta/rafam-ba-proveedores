"""Resumen diario: la lista PARA REVISAR EN RAFAM y el CSV para el operador."""

from __future__ import annotations

import csv
import io
import json
from argparse import Namespace
from datetime import date

import pytest

import main
from src import notifier, run_history
from src.operator_report import build_operator_report, local_day_bounds_utc, operator_csv
from src.retry_store import (
    REASON_BACKEND_REJECTED,
    REASON_DEPENDENCY_MISSING,
    REASON_VALIDATION_CLIENT,
    RetryStore,
)

_OP = json.dumps({"ejercicio": 2026, "nro_op": 1023}, sort_keys=True)
_OC = json.dumps({"ejercicio": 2026, "nro_oc": 55, "uni_compra": 1}, sort_keys=True)


def _age(store, key, days):
    store._conn.execute(
        "UPDATE retry_queue SET first_seen = datetime('now', ?) WHERE external_id = ?", (f"-{days} days", key),
    )
    store._conn.commit()


@pytest.fixture
def store(tmp_path):
    s = RetryStore(db_path=str(tmp_path / "state.db"), max_attempts=2, permanent_retry_hours=6, wait_alert_days=3)
    yield s
    s.close()


def _fill(store):
    # Rechazo de Paxapos que ya agoto los intentos (permanent con reintento agendado).
    for _ in range(2):
        store.enqueue("oc_items", _OC, REASON_BACKEND_REJECTED, "Error guardando Pedido | proveedor inactivo",
                      reason_detail="validation_error")
    # Dato invalido en RAFAM, de hoy.
    store.enqueue("orden_pago", _OP, REASON_VALIDATION_CLIENT, "no se envio: IMPORTE_TOTAL NULL",
                  reason_detail="invalid_amount")
    # Espera vencida y espera normal.
    store.enqueue("retenciones", "r-vieja", REASON_DEPENDENCY_MISSING, "OP 2026-9 aun no migrada")
    _age(store, "r-vieja", 5)
    store.enqueue("retenciones", "r-nueva", REASON_DEPENDENCY_MISSING, "OP 2026-10 aun no migrada")
    # Algo que se destrabo hoy.
    store.enqueue("orden_pago", "op-arreglada", REASON_BACKEND_REJECTED, "rechazada")
    store.resolve("orden_pago", "op-arreglada")


def test_reporte_arma_la_lista_del_operador(store):
    _fill(store)

    report = build_operator_report(store, day=date.today(), body_limit=50)

    rows = {r["registro"]: r for r in report["attention"]}
    assert set(rows) == {"OC 2026-1-55", "OP 2026-1023", "retenciones r-vieja"}
    assert rows["OC 2026-1-55"]["estado"] == "permanent"
    assert rows["OC 2026-1-55"]["proximo_reintento"] not in ("", "proxima corrida")
    assert rows["OP 2026-1023"]["estado"] == "pendiente"
    assert rows["retenciones r-vieja"]["estado"] == "espera vencida"
    assert rows["retenciones r-vieja"]["dias"] == 5
    assert 'resend --entity orden_pago --key "OP 2026-1023"' in rows["OP 2026-1023"]["reenviar"]
    assert report["waiting"] == {"retenciones": 1}
    assert report["new_today"] == 2
    assert [r["external_id"] for r in report["resolved"]] == ["op-arreglada"]


def test_csv_tiene_todo_aunque_el_cuerpo_este_acotado(store):
    for n in range(4):
        store.enqueue("orden_pago", json.dumps({"ejercicio": 2026, "nro_op": n}), REASON_VALIDATION_CLIENT, "x")
    report = build_operator_report(store, day=date.today(), body_limit=2)

    data = operator_csv(report)
    assert data.startswith("﻿"), "BOM para que Excel lo abra en UTF-8"
    rows = list(csv.DictReader(io.StringIO(data.lstrip("﻿")), delimiter=";"))
    assert len(rows) == 4
    assert rows[0]["entidad"] == "orden_pago"
    assert rows[0]["registro"] == "OP 2026-0"

    lines: list[str] = []
    from src.operator_report import render_operator_section

    render_operator_section(lines, report, sep="=", sub="-")
    body = "\n".join(lines)
    assert "... y 2 mas (ver el CSV adjunto)" in body


def test_mail_diario_muestra_la_lista_y_adjunta_el_csv(store, monkeypatch):
    _fill(store)
    report = build_operator_report(store, day=date.today(), body_limit=50)
    monkeypatch.setattr(notifier, "_is_enabled", lambda: True)
    sent = {}

    def _send(subject, body, **kwargs):
        sent.update(subject=subject, body=body, **kwargs)
        return True

    monkeypatch.setattr(notifier, "send_notification", _send)
    entity_metrics = [{
        "entity": "oc_items", "mode": "DIARIO", "success": True, "runs": 2, "duration_secs": 10.0,
        "permanent_retried": 3,
        "ledger_new": {"queued_fallo": 1, "queued_espera": 0, "unexplained": 1},
        "ledger_last": {"fuera_detail": {
            "cancelled_never_migrated": {"count": 103, "label": "OC anulada en RAFAM que nunca se migro",
                                         "examples": ["OC 2026-1-7"]},
        }},
    }]

    assert notifier.notify_run_report({"operator": report, "duration_formatted": "00:01:00"}, entity_metrics)

    body = sent["body"]
    assert body.index("PARA REVISAR EN RAFAM") < body.index("RESUMEN GLOBAL"), "lo primero que se ve"
    assert "OC 2026-1-55 — Paxapos lo rechazo — PERMANENT" in body
    assert "proveedor inactivo" in body
    assert "retenciones r-vieja — espera vencida" in body
    assert "En espera normal" in body
    assert "DESTRABADOS HOY" in body and "Se migraron: 1" in body
    assert "Para revisar en RAFAM   : 3" in body
    assert "'permanent' reintentados solos: 3" in body
    assert "Sin ID de Paxapos (nuevos a la cola): 1 fallo(s), 0 espera(s), 1 sin motivo" in body
    assert "OC anulada en RAFAM que nunca se migro: 103  (ej: OC 2026-1-7)" in body
    (filename, content, subtype), = sent["attachments"]
    assert filename == f"rafam_registros_a_revisar_{date.today().isoformat()}.csv"
    assert subtype == "csv"
    assert "OC 2026-1-55" in content


def test_send_notification_adjunta_archivos(monkeypatch):
    monkeypatch.setenv("NOTIFY_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("NOTIFY_SMTP_PORT", "587")
    monkeypatch.setenv("NOTIFY_FROM", "rafam@test")
    monkeypatch.setenv("NOTIFY_TO", "ops@test")
    captured = {}

    class _SMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def ehlo(self):
            pass

        def starttls(self, context=None):
            pass

        def sendmail(self, from_addr, to, raw):
            captured["raw"] = raw

    monkeypatch.setattr(notifier.smtplib, "SMTP", _SMTP)
    assert notifier.send_notification("asunto", "cuerpo", attachments=[("lista.csv", "a;b\r\n1;2\r\n", "csv")])
    raw = captured["raw"]
    assert "multipart/mixed" in raw
    assert 'filename="lista.csv"' in raw


def test_daily_report_manda_la_lista_y_poda_el_historial(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(db))
    monkeypatch.setenv("RAFAM_RUN_HISTORY_PATH", str(tmp_path / "runs.jsonl"))
    today = date.today().isoformat()
    run_history.record_run(
        {"start_time": f"{today} 10:00:00", "end_time": f"{today} 10:01:00", "duration_formatted": "00:01:00",
         "success": True},
        [{"entity": "orden_pago", "success": True, "duration_secs": 60.0,
          "ledger": {"queued_fallo": 1, "queued_espera": 0, "unexplained": 0, "fuera_detail": {}}}],
    )
    store = RetryStore(db_path=str(db))
    store.enqueue("orden_pago", _OP, REASON_VALIDATION_CLIENT, "no se envio: IMPORTE_TOTAL NULL")
    store.close()

    captured = {}
    monkeypatch.setattr(
        notifier, "notify_run_report",
        lambda summary, metrics, dry_run=False: captured.update(summary=summary, metrics=metrics) or True,
    )

    main.cmd_daily_report(Namespace(date=today))

    operator = captured["summary"]["operator"]
    assert [r["registro"] for r in operator["attention"]] == ["OP 2026-1023"]
    assert captured["metrics"][0]["ledger_new"]["queued_fallo"] == 1
    assert run_history.load_runs(today) == [], "el historial reportado se purga"


def test_limites_del_dia_local_en_utc():
    start, end = local_day_bounds_utc(date(2026, 10, 2))
    assert start < end
    assert len(start) == len("2026-10-02 00:00:00")


def test_id_de_paxapos_en_la_lista_y_en_el_mail_del_registro(store, tmp_path, monkeypatch):
    """Pedido del operador: el aviso tiene que traer clave RAFAM, ID Paxapos,
    entidad y error. El ID existe cuando lo que fallo es una actualizacion."""
    from src import record_alerts
    from src.entity_link_store import EntityLinkStore

    links = EntityLinkStore(db_path=str(tmp_path / "state.db"))
    links.save_link(entity="orden_compra", source_key=_OC, remote_id="4321")
    store.enqueue("oc_items", _OC, REASON_BACKEND_REJECTED, "Error guardando Pedido", reason_detail="validation_error")
    store.enqueue("orden_pago", _OP, REASON_VALIDATION_CLIENT, "IMPORTE_TOTAL NULL")

    report = build_operator_report(store, day=date.today(), body_limit=50, link_store=links)
    ids = {r["registro"]: r["id_paxapos"] for r in report["attention"]}
    assert ids == {"OC 2026-1-55": "4321", "OP 2026-1023": ""}

    monkeypatch.setenv("NOTIFY_RECORD_ALERTS", "true")
    monkeypatch.setattr(notifier, "notifications_enabled", lambda: True)
    bodies = []
    monkeypatch.setattr(
        notifier, "send_notification", lambda subject, body, **kw: bodies.append(body) or True,
    )
    assert record_alerts.flush_record_alerts(store, link_store=links) == 2
    oc_body = next(b for b in bodies if "OC 2026-1-55" in b)
    assert "ID Paxapos     : 4321 (ya existe en Paxapos: fallo la actualizacion)" in oc_body
    assert f"Clave RAFAM    : {_OC}" in oc_body
    assert "Entidad        : oc_items" in oc_body
    assert "Error guardando Pedido" in oc_body
    op_body = next(b for b in bodies if "OP 2026-1023" in b)
    assert "ID Paxapos     : — (todavia no existe en Paxapos)" in op_body
    links.close()
