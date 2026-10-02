"""'permanent' ya no es un callejon sin salida y las esperas largas avisan.

1. Un 'permanent' deja de reintentarse en cada corrida pero vuelve a
   intentarse solo cada RAFAM_PERMANENT_RETRY_HOURS (salvo rechazo terminal).
2. Una espera de dependencia que supera RAFAM_WAIT_ALERT_DAYS avisa una vez y
   pasa a la lista del operador.
3. Lo que sale de la cola queda en retry_resolved (el mail diario muestra lo
   que se destrabo).
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from src import notifier, record_alerts
from src.batch_isolation import BatchIsolator
from src.retry_store import (
    ALERT_STATE_STALE,
    REASON_BACKEND_REJECTED,
    REASON_BATCH_FAILED,
    REASON_DEPENDENCY_MISSING,
    REASON_VALIDATION_CLIENT,
    RESOLVED_DISMISSED,
    RESOLVED_MIGRATED,
    STATUS_PERMANENT,
    RetryStore,
)

_OP = json.dumps({"ejercicio": 2026, "nro_op": 1023}, sort_keys=True)
_OP2 = json.dumps({"ejercicio": 2026, "nro_op": 1024}, sort_keys=True)


@pytest.fixture
def store(tmp_path):
    s = RetryStore(db_path=str(tmp_path / "state.db"), max_attempts=2, permanent_retry_hours=6, wait_alert_days=3)
    yield s
    s.close()


def _to_permanent(store, entity, key, reason=REASON_BACKEND_REJECTED):
    for _ in range(store.max_attempts):
        store.enqueue(entity, key, reason, "rechazada")
    assert store.list_items(entity, external_id=key)[0].status == STATUS_PERMANENT


def _expire_retry(store, entity, key, minutes_ago=1):
    store._conn.execute(
        "UPDATE retry_queue SET next_retry_after = datetime('now', ?) WHERE entity = ? AND external_id = ?",
        (f"-{minutes_ago} minutes", entity, key),
    )
    store._conn.commit()


def _age(store, entity, key, days):
    store._conn.execute(
        "UPDATE retry_queue SET first_seen = datetime('now', ?) WHERE entity = ? AND external_id = ?",
        (f"-{days} days", entity, key),
    )
    store._conn.commit()


# ─── 1. Reintento automatico de 'permanent' ──────────────────────────────────


class TestReintentoAutomaticoDePermanent:
    def test_al_pasar_a_permanent_agenda_el_proximo_intento(self, store):
        _to_permanent(store, "orden_pago", _OP)
        item = store.list_items("orden_pago")[0]
        assert item.next_retry_after is not None
        assert item.next_retry_after > store.now()
        # Hasta que venza: ni se reinyecta ni pasa el filtro de los mappers.
        assert store.pending_external_ids("orden_pago") == set()
        assert store.permanent_external_ids("orden_pago") == {_OP}
        assert store.due_permanent_external_ids("orden_pago") == set()

    def test_vencido_se_reintenta_en_la_corrida(self, store):
        _to_permanent(store, "orden_pago", _OP)
        _expire_retry(store, "orden_pago", _OP)

        assert store.pending_external_ids("orden_pago") == {_OP}
        assert store.permanent_external_ids("orden_pago") == set()
        assert store.due_permanent_external_ids("orden_pago") == {_OP}

    def test_si_vuelve_a_fallar_sigue_permanent_y_se_corre_el_reintento(self, store):
        _to_permanent(store, "orden_pago", _OP)
        _expire_retry(store, "orden_pago", _OP)

        store.enqueue("orden_pago", _OP, REASON_BACKEND_REJECTED, "sigue rechazada")

        item = store.list_items("orden_pago")[0]
        assert item.status == STATUS_PERMANENT
        assert item.attempts == store.max_attempts + 1
        assert item.next_retry_after > store.now()
        assert store.pending_external_ids("orden_pago") == set()

    def test_si_se_migra_sale_de_la_cola_y_queda_en_el_historial(self, store):
        _to_permanent(store, "orden_pago", _OP)
        since = store.now()
        _expire_retry(store, "orden_pago", _OP)

        store.resolve("orden_pago", _OP)

        assert store.list_items("orden_pago") == []
        resolved = store.resolved_since(since)
        assert [(r["external_id"], r["status"], r["how"]) for r in resolved] == [
            (_OP, STATUS_PERMANENT, RESOLVED_MIGRATED)
        ]

    def test_defer_corre_los_vencidos_que_no_se_mandaron(self, store):
        _to_permanent(store, "orden_pago", _OP)
        _to_permanent(store, "orden_pago", _OP2)
        _expire_retry(store, "orden_pago", _OP, minutes_ago=5)
        as_of = store.now()
        # _OP2 vence DESPUES de arrancar la corrida: no se toca.
        store._conn.execute(
            "UPDATE retry_queue SET next_retry_after = datetime('now', '+1 seconds') WHERE external_id = ?",
            (_OP2,),
        )
        store._conn.commit()

        assert store.defer_due_permanents("orden_pago", as_of) == 1
        assert store.due_permanent_external_ids("orden_pago") == set()
        items = {i.external_id: i for i in store.list_items("orden_pago")}
        assert items[_OP].next_retry_after > as_of

    def test_rechazo_terminal_no_se_reintenta_solo(self, store):
        store.mark_permanent("retenciones", _OP, REASON_BACKEND_REJECTED, "Egreso borrado", "destination_deleted")
        item = store.list_items("retenciones")[0]
        assert item.auto_retry == 0
        # Aunque alguien le ponga una fecha vencida, no se reintenta solo.
        _expire_retry(store, "retenciones", _OP)
        assert store.pending_external_ids("retenciones") == set()
        assert store.permanent_external_ids("retenciones") == {_OP}

    def test_requeue_reactiva_el_reintento_automatico(self, store):
        store.mark_permanent("retenciones", _OP, REASON_BACKEND_REJECTED, "Egreso borrado", "destination_deleted")
        store.requeue("retenciones", _OP)
        _to_permanent(store, "retenciones", _OP)
        assert store.list_items("retenciones")[0].auto_retry == 1

    def test_horas_en_cero_desactiva_el_reintento(self, tmp_path):
        store = RetryStore(db_path=str(tmp_path / "s.db"), max_attempts=2, permanent_retry_hours=0)
        _to_permanent(store, "orden_pago", _OP)
        item = store.list_items("orden_pago")[0]
        assert item.status == STATUS_PERMANENT
        assert item.next_retry_after is None
        assert store.pending_external_ids("orden_pago") == set()
        store.close()

    def test_env_configura_las_horas(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAFAM_PERMANENT_RETRY_HOURS", "48")
        store = RetryStore(db_path=str(tmp_path / "s.db"), max_attempts=2)
        assert store.permanent_retry_hours == 48
        _to_permanent(store, "orden_pago", _OP)
        next_retry = store.list_items("orden_pago")[0].next_retry_after
        in_47h = store._conn.execute("SELECT datetime('now', '+47 hours')").fetchone()[0]
        assert next_retry > in_47h
        store.close()


# ─── Migracion de la cola existente ──────────────────────────────────────────


def test_permanent_previos_al_deploy_se_reintentan_y_esperas_viejas_no_mandan_mail(tmp_path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE retry_queue (
            entity TEXT NOT NULL, external_id TEXT NOT NULL, reason_code TEXT NOT NULL,
            reason_detail TEXT, error_message TEXT, attempts INTEGER NOT NULL DEFAULT 0,
            first_seen TEXT NOT NULL, last_attempt TEXT, next_retry_after TEXT,
            status TEXT NOT NULL DEFAULT 'pending', payload_snapshot TEXT,
            alert_state TEXT, alerted_at TEXT,
            PRIMARY KEY (entity, external_id)
        )
        """
    )
    rows = [
        ("oc_items", "oc-trabada", "backend_rejected", None, 10, "2026-08-01 10:00:00", "permanent", "permanent"),
        ("retenciones", "ret-borrada", "backend_rejected", "destination_deleted", 1, "2026-08-01 10:00:00",
         "permanent", "permanent"),
        ("orden_pago", "op-espera-vieja", "dependency_missing", "order_not_migrated", 1, "2026-08-01 10:00:00",
         "pending", "pending"),
    ]
    conn.executemany(
        "INSERT INTO retry_queue (entity, external_id, reason_code, reason_detail, attempts, first_seen, "
        "status, alert_state) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    store = RetryStore(db_path=str(db), wait_alert_days=3)
    items = {i.external_id: i for i in store.list_items()}
    # La OC trabada desde agosto se reintenta en la proxima corrida.
    assert store.pending_external_ids("oc_items") == {"oc-trabada"}
    # El rechazo terminal no.
    assert items["ret-borrada"].auto_retry == 0
    assert store.pending_external_ids("retenciones") == set()
    # La espera vieja ya figura en el mail diario: no dispara un mail al deployar...
    assert items["op-espera-vieja"].alert_state == ALERT_STATE_STALE
    assert store.pending_alerts() == []
    # ...pero si esta en la lista del operador.
    assert "op-espera-vieja" in {i.external_id for i in store.attention_items()}
    store.close()


# ─── 2. Esperas vencidas ─────────────────────────────────────────────────────


class TestEsperasVencidas:
    def test_espera_corta_no_avisa_y_no_esta_en_la_lista(self, store):
        store.enqueue("orden_pago", _OP, REASON_DEPENDENCY_MISSING, "OC aun no migrada")
        assert store.pending_alerts() == []
        assert store.attention_items() == []
        assert [i.external_id for i in store.waiting_items()] == [_OP]

    def test_espera_de_mas_de_3_dias_avisa_una_sola_vez(self, store, monkeypatch):
        monkeypatch.setenv("NOTIFY_RECORD_ALERTS", "true")
        monkeypatch.setattr(notifier, "notifications_enabled", lambda: True)
        mails = []
        monkeypatch.setattr(
            notifier, "notify_record_failure",
            lambda item, *, max_attempts: mails.append(item) or True,
        )
        store.enqueue("orden_pago", _OP, REASON_DEPENDENCY_MISSING, "OC aun no migrada")
        _age(store, "orden_pago", _OP, days=4)

        assert [i.external_id for i in store.attention_items()] == [_OP]
        assert store.waiting_items() == []
        assert record_alerts.flush_record_alerts(store) == 1
        assert store.list_items("orden_pago")[0].alert_state == ALERT_STATE_STALE
        # La espera sigue (se reencola cada corrida): no vuelve a avisar.
        store.enqueue("orden_pago", _OP, REASON_DEPENDENCY_MISSING, "OC aun no migrada")
        assert record_alerts.flush_record_alerts(store) == 0
        assert len(mails) == 1

    def test_si_la_espera_pasa_a_rechazo_avisa_el_rechazo(self, store):
        store.enqueue("orden_pago", _OP, REASON_DEPENDENCY_MISSING, "OC aun no migrada")
        _age(store, "orden_pago", _OP, days=4)
        store.mark_alerted("orden_pago", _OP, ALERT_STATE_STALE)

        store.enqueue("orden_pago", _OP, REASON_BACKEND_REJECTED, "Paxapos la rechazo")
        assert [i.reason_code for i in store.pending_alerts()] == [REASON_BACKEND_REJECTED]

    def test_dias_en_cero_no_avisa_esperas(self, tmp_path):
        store = RetryStore(db_path=str(tmp_path / "s.db"), wait_alert_days=0)
        store.enqueue("orden_pago", _OP, REASON_DEPENDENCY_MISSING, "OC aun no migrada")
        _age(store, "orden_pago", _OP, days=30)
        assert store.pending_alerts() == []
        assert store.attention_items() == []
        store.close()

    def test_lista_del_operador_incluye_rechazos_y_permanent(self, store):
        store.enqueue("orden_pago", _OP, REASON_VALIDATION_CLIENT, "IMPORTE_TOTAL NULL")
        _to_permanent(store, "oc_items", "oc-1")
        store.enqueue("orden_pago", _OP2, REASON_DEPENDENCY_MISSING, "OC aun no migrada")
        assert {i.external_id for i in store.attention_items()} == {_OP, "oc-1"}
        assert {i.external_id for i in store.attention_items(["oc_items"])} == {"oc-1"}


# ─── 3. Historial de lo que salio de la cola ─────────────────────────────────


def test_historial_registra_como_salio_cada_fila(store):
    since = store.now()
    store.enqueue("orden_pago", _OP, REASON_BACKEND_REJECTED, "rechazada")
    store.enqueue("orden_pago", _OP2, REASON_BACKEND_REJECTED, "rechazada")
    store.resolve("orden_pago", _OP, how="fuera_de_alcance")
    store.dismiss("orden_pago", _OP2, "dato historico")
    # Resolver algo que no estaba en la cola no deja historial.
    store.resolve("orden_pago", "no-estaba")

    hows = {r["external_id"]: r["how"] for r in store.resolved_since(since)}
    assert hows == {_OP: "fuera_de_alcance", _OP2: f"{RESOLVED_DISMISSED}: dato historico"}
    assert store.prune_resolved(keep_days=30) == 0


# ─── BatchIsolator: el batch_failed vencido se manda solo ────────────────────


class _Exporter:
    def __init__(self):
        self.calls = []

    def write_batch(self, entity, columns, rows):
        self.calls.append([dict(zip(columns, r))["NRO_OP"] for r in rows])

    def get_last_batch_migrator_metrics(self):
        return {"sent": 1}


def test_batch_failed_vencido_se_manda_solo(store):
    bad = json.dumps({"ejercicio": 2026, "nro_op": 7}, sort_keys=True)
    _to_permanent(store, "orden_pago", bad, reason=REASON_BATCH_FAILED)

    exporter = _Exporter()
    columns = ["EJERCICIO", "NRO_OP"]
    rows = [(2026, 6), (2026, 7), (2026, 8)]

    # Sin vencer: va con el resto (el mapper lo excluye por permanent).
    BatchIsolator(exporter, "orden_pago", retry_store=store).write(columns, rows)
    assert exporter.calls == [[6, 7, 8]]

    _expire_retry(store, "orden_pago", bad)
    exporter.calls.clear()
    BatchIsolator(exporter, "orden_pago", retry_store=store).write(columns, rows)
    assert exporter.calls == [[6, 8], [7]]
    # Se mando y no fallo: sigue en la cola hasta que la respuesta lo resuelva.
    assert store.list_items("orden_pago", external_id=bad)[0].status == STATUS_PERMANENT
