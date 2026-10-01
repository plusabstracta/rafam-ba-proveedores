"""Fase 3 — un batch caido se parte hasta aislar el registro que lo rompe.

1. Biseccion pura: aisla solo lo que falla SOLO, corta con el backend caido o
   cuando no pasa ningun sub-batch, respeta el tope de requests.
2. BatchIsolator: encola el aislado como batch_failed, no castiga registros sin
   evidencia, manda solo al ya conocido, un intento por batch, sleep solo
   despues de un POST.
3. _sync_entity: el watermark avanza con el batch recuperado y queda congelado
   si el backend falla con todo.
4. Incidentes: un mail por incidente (no por corrida), otro al normalizarse.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text

import main as main_module
from src import incident_alerts, notifier
from src.backend_errors import BackendInfraError
from src.batch_isolation import (
    BatchIsolator,
    bisect_keys,
    failure_detail,
    is_infra_failure,
)
from src.checkpoint_store import CheckpointStore
from src.config import ENTITY_CONFIGS
from src.exporter import BaseExporter
from src.retry_store import (
    REASON_BACKEND_REJECTED,
    REASON_BATCH_FAILED,
    REASON_DEPENDENCY_MISSING,
    REASON_VALIDATION_CLIENT,
    STATUS_PENDING,
    RetryItem,
    RetryStore,
)
from src.run_history import aggregate_runs
from src.source_repository import SourceRepository
from src.sync_engine import SyncEngine

_HTTP_500 = "HTTP 500: Internal Server Error"
_COLUMNS = ["COD_PROV", "FANTASIA", "RAZON_SOCIAL", "FECHA_ULT_COMP"]


def _rows(*cods):
    return [(cod, f"Prov {cod}", f"Prov {cod} SA", f"2026-01-{i + 10:02d}") for i, cod in enumerate(cods)]


class _FakeExporter(BaseExporter):
    """Exporter de proveedores sin HTTP: falla segun las claves del batch."""

    def __init__(self, *, boom=(), fail_all=False, infra=(), unchanged=(), on_write=None):
        self.posts: list[list[int]] = []
        self.boom = set(boom)
        self.fail_all = fail_all
        self.infra = set(infra)
        self.unchanged = set(unchanged)
        self.on_write = on_write
        self._sent = 0

    def write_batch(self, entity, columns, rows):
        cods = [dict(zip(columns, row))["COD_PROV"] for row in rows]
        self.posts.append(cods)
        if self.on_write is not None:
            self.on_write(cods)
        self._sent = len([c for c in cods if c not in self.unchanged])
        if self.infra & set(cods):
            raise BackendInfraError("SQLSTATE[42S02]: Base table or view not found")
        if self.fail_all or self.boom & set(cods):
            raise RuntimeError(_HTTP_500)

    def get_last_batch_migrator_metrics(self):
        return {"sent": self._sent, "saved": self._sent, "errors": 0}


@pytest.fixture
def retry(tmp_path):
    store = RetryStore(db_path=str(tmp_path / "retry.db"))
    yield store
    store.close()


# ─── 1. Biseccion ─────────────────────────────────────────────────────────────


def _sender(bad=(), infra_on=None):
    calls: list[list] = []

    def send(subset):
        calls.append(list(subset))
        if infra_on is not None and infra_on in subset:
            return BackendInfraError("SQLSTATE[HY000]: too many connections")
        if set(subset) & set(bad):
            return RuntimeError(_HTTP_500)
        return None

    return send, calls


class TestBisect:
    def test_aisla_un_registro_con_pocos_requests(self):
        send, calls = _sender(bad={"f"})
        res = bisect_keys(list("abcdefgh"), send, max_requests=32)
        assert set(res.isolated) == {"f"}
        assert sorted(res.ok) == list("abcdegh")
        assert res.success_seen and not res.systemic and not res.unresolved
        assert res.requests == len(calls) == 6  # 2 * log2(8)

    def test_dos_registros_en_mitades_distintas(self):
        send, _ = _sender(bad={"a", "h"})
        res = bisect_keys(list("abcdefgh"), send, max_requests=32)
        assert set(res.isolated) == {"a", "h"}
        assert not res.systemic

    def test_si_no_pasa_nada_es_el_backend(self):
        send, calls = _sender(bad=set("abcdefgh"))
        res = bisect_keys(list("abcdefgh"), send, max_requests=32)
        assert res.systemic
        assert len(calls) == 4, "corta apenas ve que falla todo"
        assert not res.success_seen

    def test_dos_registros_que_fallan_los_dos_tambien_es_sistemico(self):
        send, _ = _sender(bad={"a", "b"})
        res = bisect_keys(["a", "b"], send, max_requests=32)
        assert res.systemic and set(res.isolated) == {"a", "b"}

    def test_backend_caido_a_mitad_corta(self):
        send, calls = _sender(bad={"b"}, infra_on="a")
        res = bisect_keys(list("abcd"), send, max_requests=32)
        assert isinstance(res.infra_exc, BackendInfraError)
        assert "a" in res.unresolved
        assert not res.isolated

    def test_tope_de_requests(self):
        send, calls = _sender(bad={"p"})
        res = bisect_keys([f"k{i}" for i in range(15)] + ["p"], send, max_requests=3)
        assert len(calls) == 3
        assert res.unresolved
        assert not res.isolated


class TestClasificacion:
    @pytest.mark.parametrize("exc", [
        BackendInfraError("SQLSTATE"),
        TimeoutError("timed out"),
        ConnectionResetError("reset"),
        RuntimeError("HTTP 503: Service Unavailable"),
        RuntimeError("HTTP 401: Unauthorized"),
        RuntimeError("URL error: [Errno 111] Connection refused"),
        RuntimeError("Respuesta no JSON (Content-Type=text/html)"),
    ])
    def test_infra(self, exc):
        assert is_infra_failure(exc)

    @pytest.mark.parametrize("exc", [
        RuntimeError(_HTTP_500),
        RuntimeError("HTTP 413: Payload Too Large"),
        RuntimeError("1 error(es) del migrator para 'orden_pago' sin external_id utilizable"),
        KeyError("NRO_OP"),
        json.JSONDecodeError("Expecting value", "", 0),
    ])
    def test_de_un_registro(self, exc):
        assert not is_infra_failure(exc)

    def test_detalle_para_la_cola(self):
        assert failure_detail(RuntimeError(_HTTP_500)) == "http_500"
        assert failure_detail(KeyError("X")) == "script_error"
        assert failure_detail(json.JSONDecodeError("x", "", 0)) == "invalid_response"
        assert failure_detail(RuntimeError("2 error(es) sin external_id utilizable")) == "untracked_errors"


# ─── 2. RetryStore: un intento por batch, resolve por clave base ─────────────


class TestRetryStore:
    def test_un_intento_por_scope(self, retry):
        with retry.attempt_scope():
            retry.enqueue("proveedores", "7", REASON_VALIDATION_CLIENT, "x")
            retry.enqueue("proveedores", "7", REASON_VALIDATION_CLIENT, "x")
            retry.enqueue("proveedores", "7", REASON_BATCH_FAILED, "boom")
        [item] = retry.list_items("proveedores")
        assert item.attempts == 1
        assert item.reason_code == REASON_BATCH_FAILED, "el ultimo motivo queda"
        with retry.attempt_scope():
            retry.enqueue("proveedores", "7", REASON_BATCH_FAILED, "boom")
            retry.enqueue("proveedores", "7", REASON_BATCH_FAILED, "boom")
        assert retry.list_items("proveedores")[0].attempts == 2

    def test_sin_scope_cuenta_cada_enqueue(self, retry):
        for _ in range(3):
            retry.enqueue("proveedores", "7", REASON_BACKEND_REJECTED, "x")
        assert retry.list_items("proveedores")[0].attempts == 3

    def test_dependencia_no_consume_el_intento_del_scope(self, retry):
        retry.enqueue("proveedores", "7", REASON_BACKEND_REJECTED, "x")
        with retry.attempt_scope():
            retry.enqueue("proveedores", "7", REASON_DEPENDENCY_MISSING, "espera")
            retry.enqueue("proveedores", "7", REASON_BACKEND_REJECTED, "x")
        assert retry.list_items("proveedores")[0].attempts == 2

    def test_gasto_multi_comprobante_resuelve_el_aislado_por_clave_base(self, retry):
        base = json.dumps({"deleg_solic": 1, "ejercicio": 2026, "nro_solic": 9}, sort_keys=True)
        full = json.dumps({"deleg_solic": 1, "ejercicio": 2026, "nro_solic": 9, "nro_comprob": "A-1"}, sort_keys=True)
        other = json.dumps({"deleg_solic": 1, "ejercicio": 2026, "nro_solic": 9, "nro_comprob": "A-2"}, sort_keys=True)
        retry.enqueue("solic_gastos", base, REASON_BATCH_FAILED, "HTTP 500")
        retry.enqueue("solic_gastos", other, REASON_BACKEND_REJECTED, "rechazado")
        retry.resolve("solic_gastos", full)
        assert [it.external_id for it in retry.list_items("solic_gastos")] == [other]


# ─── 3. BatchIsolator ─────────────────────────────────────────────────────────


class TestIsolator:
    def test_aisla_y_encola_el_que_rompe_el_batch(self, retry):
        exporter = _FakeExporter(boom={200})
        isolator = BatchIsolator(exporter, "proveedores", retry_store=retry)
        result = isolator.write(_COLUMNS, _rows(100, 200, 300))
        assert result.ok and result.recovered
        assert set(result.isolated) == {"200"}
        assert exporter.posts == [[100, 200, 300], [100, 200], [300], [100], [200]]
        [item] = retry.list_items("proveedores")
        assert (item.external_id, item.reason_code, item.reason_detail, item.attempts) == (
            "200", REASON_BATCH_FAILED, "http_500", 1,
        )
        assert (isolator.records_isolated, isolator.batches_recovered, isolator.extra_requests) == (1, 1, 4)

    def test_backend_caido_no_biseca(self, retry):
        exporter = _FakeExporter(infra={100})
        result = BatchIsolator(exporter, "proveedores", retry_store=retry).write(_COLUMNS, _rows(100, 200))
        assert not result.ok and result.infra
        assert exporter.posts == [[100, 200]]
        assert retry.list_items("proveedores") == []

    def test_si_falla_todo_no_culpa_a_ningun_registro(self, retry):
        exporter = _FakeExporter(fail_all=True)
        result = BatchIsolator(exporter, "proveedores", retry_store=retry).write(_COLUMNS, _rows(100, 200, 300, 400))
        assert not result.ok and result.infra
        assert retry.list_items("proveedores") == []

    def test_registro_solo_sin_evidencia_queda_caido(self, retry):
        exporter = _FakeExporter(boom={100})
        isolator = BatchIsolator(exporter, "proveedores", retry_store=retry)
        result = isolator.write(_COLUMNS, _rows(100))
        assert not result.ok and not result.infra
        assert result.unresolved == ["100"]
        assert retry.list_items("proveedores") == []

    def test_registro_solo_se_aisla_si_el_backend_ya_respondio(self, retry):
        exporter = _FakeExporter(boom={200})
        isolator = BatchIsolator(exporter, "proveedores", retry_store=retry)
        assert isolator.write(_COLUMNS, _rows(100)).ok
        result = isolator.write(_COLUMNS, _rows(200))
        assert result.recovered and set(result.isolated) == {"200"}

    def test_registro_solo_que_ya_venia_fallando_se_aisla(self, retry):
        retry.enqueue("proveedores", "100", REASON_BACKEND_REJECTED, "CUIT invalido")
        exporter = _FakeExporter(boom={100})
        result = BatchIsolator(exporter, "proveedores", retry_store=retry).write(_COLUMNS, _rows(100))
        assert result.recovered
        assert retry.list_items("proveedores")[0].reason_code == REASON_BATCH_FAILED

    def test_el_ya_aislado_va_solo_y_no_rompe_el_batch(self, retry):
        retry.enqueue("proveedores", "200", REASON_BATCH_FAILED, _HTTP_500)
        exporter = _FakeExporter(boom={200})
        isolator = BatchIsolator(exporter, "proveedores", retry_store=retry)
        result = isolator.write(_COLUMNS, _rows(100, 200, 300))
        assert result.recovered
        assert exporter.posts == [[100, 300], [200]]
        assert retry.list_items("proveedores")[0].attempts == 2

    def test_el_ya_aislado_que_ahora_pasa_sale_de_la_cola(self, retry):
        retry.enqueue("proveedores", "200", REASON_BATCH_FAILED, _HTTP_500)

        class _Resolving(_FakeExporter):
            def write_batch(self, entity, columns, rows):
                super().write_batch(entity, columns, rows)
                for row in rows:
                    retry.resolve(entity, str(row[0]))

        result = BatchIsolator(_Resolving(), "proveedores", retry_store=retry).write(_COLUMNS, _rows(100, 200))
        assert result.ok and not result.recovered
        assert retry.list_items("proveedores") == []

    def test_el_ya_aislado_que_el_mapper_ya_no_manda_sale_de_la_cola(self, retry):
        retry.enqueue("proveedores", "200", REASON_BATCH_FAILED, _HTTP_500)
        exporter = _FakeExporter(unchanged={200})
        result = BatchIsolator(exporter, "proveedores", retry_store=retry).write(_COLUMNS, _rows(100, 200))
        assert result.ok
        assert retry.list_items("proveedores") == []

    def test_un_invalido_suma_un_solo_intento_aunque_se_biseque(self, retry):
        retry.enqueue("proveedores", "300", REASON_VALIDATION_CLIENT, "sin nombre")

        def _mapper_encola(cods):
            if 300 in cods:
                retry.enqueue("proveedores", "300", REASON_VALIDATION_CLIENT, "sin nombre")

        exporter = _FakeExporter(boom={200}, on_write=_mapper_encola)
        BatchIsolator(exporter, "proveedores", retry_store=retry).write(_COLUMNS, _rows(100, 200, 300, 400))
        assert sum(300 in post for post in exporter.posts) > 1, "300 se remapeo varias veces"
        item = {it.external_id: it for it in retry.list_items("proveedores")}["300"]
        assert item.attempts == 2

    def test_sin_cola_no_biseca_y_el_batch_queda_caido(self):
        exporter = _FakeExporter(boom={200})
        result = BatchIsolator(exporter, "proveedores", retry_store=None).write(_COLUMNS, _rows(100, 200, 300))
        assert not result.ok
        assert len(exporter.posts) == 1

    def test_en_dry_run_aisla_sin_cola(self):
        exporter = _FakeExporter(boom={200})
        result = BatchIsolator(exporter, "proveedores", retry_store=None, dry_run=True).write(
            _COLUMNS, _rows(100, 200, 300),
        )
        assert result.recovered and set(result.isolated) == {"200"}

    def test_entidad_sin_clave_no_biseca(self, retry):
        exporter = _FakeExporter(boom={200})
        result = BatchIsolator(exporter, "clasificaciones", retry_store=retry).write(_COLUMNS, _rows(100, 200))
        assert not result.ok
        assert len(exporter.posts) == 1

    def test_sleep_solo_despues_de_un_post(self, retry, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr("src.batch_isolation.time.sleep", sleeps.append)
        exporter = _FakeExporter(unchanged={100, 200})
        isolator = BatchIsolator(exporter, "proveedores", retry_store=retry, delay=2.0)
        isolator.write(_COLUMNS, _rows(100))  # sin cambios: no hay POST
        isolator.write(_COLUMNS, _rows(200))  # sin cambios: no espera
        isolator.write(_COLUMNS, _rows(300))  # POST (sin espera: el anterior no posteo)
        isolator.write(_COLUMNS, _rows(400))  # espera: el anterior posteo
        assert sleeps == [2.0]


# ─── 4. _sync_entity ──────────────────────────────────────────────────────────


@pytest.fixture
def proveedores_db(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'rafam.db'}")
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE PROVEEDORES (COD_PROV INTEGER PRIMARY KEY, FANTASIA TEXT, "
            "RAZON_SOCIAL TEXT, FECHA_ULT_COMP DATETIME)"
        ))
        for cod, fantasia, razon, fecha in _rows(100, 200, 300, 400, 500, 600):
            conn.execute(
                text("INSERT INTO PROVEEDORES VALUES (:a, :b, :c, :d)"),
                {"a": cod, "b": fantasia, "c": razon, "d": f"{fecha} 00:00:00"},
            )
        conn.commit()
    return engine


def _run(tmp_path, source_engine, exporter, retry, batch_size=3):
    store = CheckpointStore(db_url=f"sqlite+pysqlite:///{tmp_path / 'cp.db'}")
    engine = SyncEngine(store, {"proveedores": ENTITY_CONFIGS["proveedores"]})
    with source_engine.connect() as conn:
        ok, msg, metrics = main_module._sync_entity(
            SourceRepository(conn), engine, exporter, "proveedores",
            batch_size=batch_size, limit=None, dry_run=False, retry_store=retry,
        )
    return ok, msg, metrics, engine.get_checkpoint("proveedores")


class TestSyncEntity:
    def test_un_registro_roto_no_congela_el_watermark(self, tmp_path, proveedores_db, retry, monkeypatch):
        monkeypatch.setenv("RAFAM_SYNC_BATCH_DELAY_SECONDS", "0")
        ok, msg, metrics, cp = _run(tmp_path, proveedores_db, _FakeExporter(boom={200}), retry)
        assert metrics["batches_failed"] == 0
        assert (metrics["batches_recovered"], metrics["records_isolated"], metrics["bisect_requests"]) == (1, 1, 4)
        assert metrics["incident_kind"] is None
        # La entidad queda "con errores" (hay un registro en la cola) pero el
        # cursor avanzo: el aislado se reinyecta desde la cola.
        assert ok is False and "aislaron" in msg
        assert cp.last_ts is not None and cp.last_ts.day == 15
        [item] = retry.list_items("proveedores")
        assert (item.external_id, item.reason_code) == ("200", REASON_BATCH_FAILED)

    def test_corrida_siguiente_manda_solo_al_aislado(self, tmp_path, proveedores_db, retry, monkeypatch):
        monkeypatch.setenv("RAFAM_SYNC_BATCH_DELAY_SECONDS", "0")
        _run(tmp_path, proveedores_db, _FakeExporter(boom={200}), retry)
        exporter = _FakeExporter(boom={200})
        _, _, metrics, _ = _run(tmp_path, proveedores_db, exporter, retry)
        assert [200] in exporter.posts
        assert not any(200 in post and len(post) > 1 for post in exporter.posts)
        assert metrics["batches_failed"] == 0
        assert retry.list_items("proveedores")[0].attempts == 2

    def test_paxapos_falla_con_todo_congela_y_abre_incidente(self, tmp_path, proveedores_db, retry, monkeypatch):
        monkeypatch.setenv("RAFAM_SYNC_BATCH_DELAY_SECONDS", "0")
        monkeypatch.setenv("RAFAM_INFRA_ABORT_AFTER", "2")
        exporter = _FakeExporter(fail_all=True)
        ok, msg, metrics, cp = _run(tmp_path, proveedores_db, exporter, retry)
        assert ok is False
        assert metrics["batches_failed"] == 2
        assert metrics["error_kind"] == "backend_infra"
        assert metrics["incident_kind"] == "backend"
        assert retry.list_items("proveedores") == [], "no se culpa a ningun registro"
        assert cp.last_ts is None

    def test_batch_sin_aislar_abre_incidente_con_las_claves(self, tmp_path, proveedores_db, retry, monkeypatch):
        monkeypatch.setenv("RAFAM_SYNC_BATCH_DELAY_SECONDS", "0")
        ok, _, metrics, cp = _run(tmp_path, proveedores_db, _FakeExporter(boom={100}), retry, batch_size=1)
        assert metrics["batches_failed"] == 1
        assert metrics["incident_kind"] == "batch"
        assert metrics["incident_keys"] == ["Proveedor COD_PROV=100"]
        assert cp.last_ts is None, "el primer batch fallo: el cursor no avanza"

    def test_backend_caido_no_biseca(self, tmp_path, proveedores_db, retry, monkeypatch):
        monkeypatch.setenv("RAFAM_SYNC_BATCH_DELAY_SECONDS", "0")
        exporter = _FakeExporter(infra={200})
        _, _, metrics, _ = _run(tmp_path, proveedores_db, exporter, retry)
        assert exporter.posts == [[100, 200, 300], [400, 500, 600]]
        assert metrics["incident_kind"] == "backend"
        assert metrics["bisect_requests"] == 0

    def test_tope_cero_desactiva_la_biseccion(self, tmp_path, proveedores_db, retry, monkeypatch):
        monkeypatch.setenv("RAFAM_SYNC_BATCH_DELAY_SECONDS", "0")
        monkeypatch.setenv("RAFAM_BISECT_MAX_REQUESTS", "0")
        exporter = _FakeExporter(boom={200})
        _, _, metrics, _ = _run(tmp_path, proveedores_db, exporter, retry)
        assert len(exporter.posts) == 2
        assert metrics["batches_failed"] == 1


# ─── 5. Incidentes ────────────────────────────────────────────────────────────


@pytest.fixture
def incidents(tmp_path, monkeypatch):
    monkeypatch.setenv("RAFAM_INCIDENTS_PATH", str(tmp_path / "alert_incidents.json"))
    monkeypatch.setenv("NOTIFY_INCIDENT_ALERTS", "true")
    monkeypatch.delenv("NOTIFY_INCIDENT_AFTER_RUNS", raising=False)
    monkeypatch.setattr(notifier, "notifications_enabled", lambda: True)
    mails: list[tuple[str, str, dict]] = []

    def _open(entity, incident):
        mails.append(("open", entity, dict(incident)))
        return True

    def _resolved(entity, incident, *, resolved_at):
        mails.append(("resolved", entity, dict(incident)))
        return True

    monkeypatch.setattr(notifier, "notify_incident", _open)
    monkeypatch.setattr(notifier, "notify_incident_resolved", _resolved)
    return mails


def _obs(entity="orden_pago", kind="backend", detail="SQLSTATE[42S02]"):
    return {"entity": entity, "kind": kind, "detail": detail}


class TestIncidentes:
    def test_avisa_una_vez_a_la_segunda_corrida_y_al_normalizarse(self, incidents):
        assert incident_alerts.update_incidents([_obs()]) == 0, "una corrida suelta no avisa"
        assert incident_alerts.update_incidents([_obs()]) == 1
        assert incident_alerts.update_incidents([_obs()]) == 0, "mientras siga abierto no se repite"
        assert [m[0] for m in incidents] == ["open"]
        assert incidents[0][2]["runs"] == 2
        assert incident_alerts.update_incidents([_obs(kind=None)]) == 1
        assert [m[0] for m in incidents] == ["open", "resolved"]
        assert incident_alerts.load_incidents() == {}

    def test_falla_suelta_no_manda_nada(self, incidents):
        incident_alerts.update_incidents([_obs()])
        incident_alerts.update_incidents([_obs(kind=None)])
        assert incidents == []
        assert incident_alerts.load_incidents() == {}

    def test_mail_caido_se_reintenta(self, incidents, monkeypatch):
        monkeypatch.setattr(notifier, "notify_incident", lambda entity, incident: False)
        incident_alerts.update_incidents([_obs()])
        incident_alerts.update_incidents([_obs()])
        assert not incident_alerts.load_incidents()["orden_pago"]["notified_at"]
        monkeypatch.setattr(notifier, "notify_incident", lambda entity, incident: True)
        assert incident_alerts.update_incidents([_obs()]) == 1

    def test_entidades_que_no_corrieron_no_se_tocan(self, incidents):
        incident_alerts.update_incidents([_obs("orden_pago")])
        incident_alerts.update_incidents([_obs("retenciones", kind=None)])
        assert "orden_pago" in incident_alerts.load_incidents()

    def test_umbral_configurable(self, incidents, monkeypatch):
        monkeypatch.setenv("NOTIFY_INCIDENT_AFTER_RUNS", "1")
        assert incident_alerts.update_incidents([_obs()]) == 1

    def test_estado_corrupto_se_ignora(self, incidents, tmp_path):
        (tmp_path / "alert_incidents.json").write_text("{no es json")
        incident_alerts.update_incidents([_obs()])
        assert incident_alerts.load_incidents()["orden_pago"]["runs"] == 1

    def test_corrida_caida_es_un_incidente(self, incidents, monkeypatch):
        monkeypatch.setenv("NOTIFY_INCIDENT_AFTER_RUNS", "1")
        sent = main_module._update_incidents([], run_error="OperationalError: ORA-12541")
        assert sent == 1
        assert incidents[0][1] == "corrida"
        assert "ORA-12541" in incidents[0][2]["detail"]

    def test_metricas_de_la_entidad_se_traducen(self, incidents, monkeypatch):
        monkeypatch.setenv("NOTIFY_INCIDENT_AFTER_RUNS", "1")
        metrics = [
            {"entity": "oc_items", "incident_kind": "batch", "incident_detail": _HTTP_500,
             "incident_keys": ["OC 2026-1-100"]},
            {"entity": "proveedores", "incident_kind": None},
        ]
        assert main_module._update_incidents(metrics) == 1
        [(_, entity, incident)] = incidents
        assert entity == "oc_items" and incident["keys"] == ["OC 2026-1-100"]

    def test_un_error_actualizando_no_rompe_la_corrida(self, monkeypatch):
        def _explota(_obs):
            raise OSError("disco lleno")

        monkeypatch.setattr(main_module, "update_incidents", _explota)
        assert main_module._update_incidents([]) == 0


# ─── 6. Contenido de los mails y del resumen diario ──────────────────────────


@pytest.fixture
def captured(monkeypatch):
    mails: list[tuple[str, str]] = []

    def _send(subject, body, **_kwargs):
        mails.append((subject, body))
        return True

    monkeypatch.setattr(notifier, "send_notification", _send)
    return mails


class TestMails:
    def test_mail_de_incidente_de_batch(self, captured):
        notifier.notify_incident("oc_items", {
            "kind": "batch", "since": "2026-10-01 12:00:00", "runs": 2,
            "detail": _HTTP_500, "keys": ["OC 2026-1-100"],
        })
        [(subject, body)] = captured
        assert subject.startswith("oc_items: NO SE ESTA SINCRONIZANDO")
        assert 'resend --entity oc_items --key "OC 2026-1-100" --dry-run' in body
        assert "No se pierde nada" in body
        assert "run --entity oc_items" in body

    def test_mail_de_normalizacion(self, captured):
        notifier.notify_incident_resolved(
            "orden_pago", {"kind": "backend", "since": "2026-10-01 12:00:00", "runs": 3},
            resolved_at="2026-10-01 13:00:00",
        )
        [(subject, body)] = captured
        assert "normalizado" in subject
        assert "VOLVIO A SINCRONIZAR" in body

    def test_mail_por_registro_aislado_explica_que_paso(self, captured):
        item = RetryItem(
            entity="proveedores", external_id="200", reason_code=REASON_BATCH_FAILED,
            reason_detail="http_500", error_message=_HTTP_500, attempts=1, status=STATUS_PENDING,
            first_seen="2026-10-01 12:00:00", last_attempt="2026-10-01 12:00:00",
        )
        notifier.notify_record_failure(item, max_attempts=10)
        [(subject, body)] = captured
        assert subject == "Proveedor COD_PROV=200: fallo el envio (aislado de un batch caido)"
        assert "se partio hasta encontrar que este registro falla" in body
        assert "SOLO (los demas se enviaron bien)" in body
        assert 'resend --entity proveedores --key "Proveedor COD_PROV=200"' in body

    def test_resumen_diario_muestra_los_recuperados(self, captured, monkeypatch):
        monkeypatch.setattr(notifier, "_is_enabled", lambda: True)
        runs = [{
            "duration_formatted": "00:01:00", "success": False, "incident_alerts_sent": 1,
            "entities": [{
                "entity": "orden_pago", "success": False, "batches_ok": 3, "batches_failed": 0,
                "batches_recovered": 1, "records_isolated": 2, "bisect_requests": 9,
            }],
        }]
        summary, metrics = aggregate_runs(runs, "2026-10-01")
        assert summary["incident_alerts_sent"] == 1
        assert metrics[0]["records_isolated"] == 2
        notifier.notify_run_report(summary, metrics)
        [(_, body)] = captured
        assert "Batches caidos recuperados: 1  (2 registro(s) aislado(s) en la cola, 9 request(s) extra)" in body
        assert "Avisos de incidente enviados: 1" in body
        assert "Batches recuperados     : 1" in body
