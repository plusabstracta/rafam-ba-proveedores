"""Cierre de cuentas: ningun registro leido queda sin ID de Paxapos y sin motivo.

Cada registro que el cron lee de RAFAM termina con ID de Paxapos, en la cola
de reintentos (con su motivo) o contado como fuera de alcance. Lo que no
encaja (el script lo leyo y no hizo nada, Paxapos respondio OK sin ID o no
respondio) se encola igual y avisa, en vez de perderse en silencio.
"""

from __future__ import annotations

import json
import logging

import pytest

from main import _sync_entity
from src.checkpoint_store import CheckpointStore
from src.entity_link_store import EntityLinkStore
from src.exporter import BaseExporter
from src.record_events import (
    GROUP_EN_PAXAPOS,
    GROUP_ESPERA,
    GROUP_FALLO,
    GROUP_FUERA,
    RecordEventSink,
    RecordOutcome,
)
from src.record_ledger import RunLedger, close_entity
from src.retry_store import (
    REASON_BACKEND_REJECTED,
    REASON_DEPENDENCY_MISSING,
    REASON_VALIDATION_CLIENT,
    RESOLVED_OUT_OF_SCOPE,
    RetryStore,
)
from src.sync_engine import SyncEngine


def _op(nro: int) -> str:
    return json.dumps({"ejercicio": 2026, "nro_op": nro}, sort_keys=True)


_COLS = ["EJERCICIO", "NRO_OP", "FECH_CONFIRM"]


def _rows(*nros):
    return [(2026, n, f"2026-09-{10 + i:02d} 00:00:00") for i, n in enumerate(nros)]


@pytest.fixture
def stores(tmp_path):
    db = str(tmp_path / "state.db")
    retry = RetryStore(db_path=db)
    links = EntityLinkStore(db_path=db)
    yield retry, links
    retry.close()
    links.close()


def _queue(retry, entity="orden_pago"):
    return {
        i.external_id: (i.reason_code, i.reason_detail, i.error_message)
        for i in retry.list_items(entity=entity)
    }


# ─── close_entity ────────────────────────────────────────────────────────────


class TestCloseEntity:
    def test_cada_registro_sin_id_termina_en_la_cola_o_contado(self, stores, caplog):
        retry, links = stores
        sink = RecordEventSink()
        ledger = RunLedger("orden_pago")
        ledger.see_rows(_COLS, _rows(1, 2, 3, 4, 5, 6, 7, 8))

        links.save_link(entity="orden_pago", source_key=_op(1), remote_id="901")          # migrada
        sink.skip("orden_pago", _op(2), "IMPORTE_TOTAL NULL", group=GROUP_FALLO, detail="invalid_amount")
        sink.skip("orden_pago", _op(3), "OC aun no migrada", group=GROUP_ESPERA, detail="order_not_migrated")
        sink.skip("orden_pago", _op(4), "proveedor excluido", group=GROUP_FUERA, detail="excluded_provider")
        ledger.add_outcomes([RecordOutcome(entity="orden_pago", key=_op(5), ok=True, mode="create")])
        ledger.add_sent([("orden_pago", _op(5)), ("orden_pago", _op(6))])
        # _op(7): leida y nada mas -> sin motivo.
        retry.enqueue("orden_pago", _op(8), REASON_BACKEND_REJECTED, "ya estaba rechazada")

        with caplog.at_level(logging.ERROR):
            result = close_entity(ledger, sink=sink, retry_store=retry, link_store=links)

        queue = _queue(retry)
        assert queue[_op(2)][:2] == (REASON_VALIDATION_CLIENT, "invalid_amount")
        assert queue[_op(3)][:2] == (REASON_DEPENDENCY_MISSING, "order_not_migrated")
        assert queue[_op(5)][:2] == (REASON_BACKEND_REJECTED, "ok_without_id")
        assert queue[_op(6)][:2] == (REASON_BACKEND_REJECTED, "no_response")
        assert queue[_op(7)][:2] == (REASON_VALIDATION_CLIENT, "unexplained")
        assert queue[_op(8)][2] == "ya estaba rechazada", "lo que ya estaba en la cola no se toca"
        assert _op(1) not in queue and _op(4) not in queue

        assert result["read"] == 8
        assert result["with_id"] == 1
        assert result["without_id"] == 7
        assert result["in_queue"] == 1
        assert result["queued_fallo"] == 1
        assert result["queued_espera"] == 1
        assert result["unexplained"] == 3
        assert result["fuera"] == 1
        assert result["fuera_detail"]["excluded_provider"]["examples"] == ["OP 2026-4"]
        assert "OP 2026-7" in caplog.text

    def test_fallo_y_sin_motivo_avisan_y_la_espera_no(self, stores):
        retry, links = stores
        sink = RecordEventSink()
        ledger = RunLedger("orden_pago")
        ledger.see_rows(_COLS, _rows(2, 3, 7))
        sink.skip("orden_pago", _op(2), "IMPORTE_TOTAL NULL", group=GROUP_FALLO, detail="invalid_amount")
        sink.skip("orden_pago", _op(3), "OC aun no migrada", group=GROUP_ESPERA, detail="order_not_migrated")

        close_entity(ledger, sink=sink, retry_store=retry, link_store=links)

        assert {i.external_id for i in retry.pending_alerts()} == {_op(2), _op(7)}

    def test_batch_caido_no_se_evalua(self, stores):
        retry, links = stores
        ledger = RunLedger("orden_pago")
        keys = ledger.see_rows(_COLS, _rows(1, 2))
        ledger.mark_failed(keys)

        result = close_entity(ledger, sink=RecordEventSink(), retry_store=retry, link_store=links)

        assert result["not_evaluated"] == 2
        assert retry.list_items() == []

    def test_en_cola_y_ahora_fuera_de_alcance_se_cierra(self, stores):
        retry, links = stores
        sink = RecordEventSink()
        retry.enqueue("orden_pago", _op(3), REASON_DEPENDENCY_MISSING, "OC aun no migrada")
        since = retry.now()
        ledger = RunLedger("orden_pago")
        ledger.see_rows(_COLS, _rows(3))
        sink.skip("orden_pago", _op(3), "OP no presupuestaria", group=GROUP_FUERA, detail="non_budget_payment")

        close_entity(ledger, sink=sink, retry_store=retry, link_store=links)

        assert retry.list_items() == []
        assert [r["how"] for r in retry.resolved_since(since)] == [RESOLVED_OUT_OF_SCOPE]

    def test_ya_en_paxapos_no_se_encola(self, stores):
        retry, links = stores
        sink = RecordEventSink()
        ledger = RunLedger("solic_gastos")
        sg = {"EJERCICIO": 2026, "DELEG_SOLIC": 1, "NRO_SOLIC": 58}
        ledger.see_rows(list(sg), [tuple(sg.values())])
        sink.skip(
            "solic_gastos", {"ejercicio": 2026, "deleg_solic": 1, "nro_solic": 58},
            "el gasto ya esta completo", group=GROUP_EN_PAXAPOS, detail="already_complete",
        )

        result = close_entity(ledger, sink=sink, retry_store=retry, link_store=links)

        assert result["en_paxapos"] == 1
        assert retry.list_items() == []

    def test_proveedor_excluido_cuenta_como_fuera_de_alcance(self, stores, monkeypatch):
        retry, links = stores
        monkeypatch.setattr("src.record_ledger.is_cod_prov_excluded", lambda cod: str(cod) == "77")
        ledger = RunLedger("proveedores")
        ledger.see_rows(["COD_PROV"], [(77,)])

        result = close_entity(ledger, sink=RecordEventSink(), retry_store=retry, link_store=links)

        assert result["fuera"] == 1
        assert retry.list_items() == []

    def test_gasto_multi_comprobante_y_retencion_sin_id_cuentan_como_migrados(self, stores):
        retry, links = stores
        links.save_link(
            entity="gasto",
            source_key=json.dumps({"ejercicio": 2026, "deleg_solic": 1, "nro_solic": 58, "nro_comprob": "1-2"},
                                  sort_keys=True),
            remote_id="77",
        )
        links.save_link(entity="retenciones", source_key=_op(9), remote_id="", fingerprint="abc")

        sg = RunLedger("solic_gastos")
        sg.see_rows(["EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC"], [(2026, 1, 58)])
        ret = RunLedger("retenciones")
        ret.see_rows(_COLS, _rows(9))

        assert close_entity(sg, sink=RecordEventSink(), retry_store=retry, link_store=links)["with_id"] == 1
        assert close_entity(ret, sink=RecordEventSink(), retry_store=retry, link_store=links)["with_id"] == 1
        assert retry.list_items() == []


# ─── Corrida completa (_sync_entity) ─────────────────────────────────────────


class _Result:
    def __init__(self, columns, rows):
        self._columns = columns
        self._rows = list(rows)

    def keys(self):
        return list(self._columns)

    def fetchmany(self, n):
        chunk, self._rows = self._rows[:n], self._rows[n:]
        return chunk


class _Source:
    def __init__(self, rows):
        self.rows = rows
        self.retry_keys = None

    def fetch_entity(self, entity, checkpoint, retry_keys=None):
        self.retry_keys = retry_keys
        return _Result(_COLS, self.rows)


class _Exporter(BaseExporter):
    """Simula al mapper + receptor: migra las OP pares, omite la 3 (espera) y
    no hace nada con la 5 (el caso que antes se perdia en silencio)."""

    def __init__(self, links, sink):
        self.links = links
        self.sink = sink
        self._outcomes = []
        self._sent = set()

    def write_batch(self, entity, columns, rows):
        self._outcomes, self._sent = [], set()
        for row in rows:
            nro = dict(zip(columns, row))["NRO_OP"]
            if nro % 2 == 0:
                self._sent.add(("orden_pago", _op(nro)))
                self._outcomes.append(RecordOutcome(entity="orden_pago", key=_op(nro), ok=True, mode="create"))
                self.links.save_link(entity="orden_pago", source_key=_op(nro), remote_id=str(1000 + nro))
            elif nro == 3:
                self.sink.skip("orden_pago", _op(nro), "OC aun no migrada", group=GROUP_ESPERA,
                               detail="order_not_migrated")

    def get_last_batch_outcomes(self):
        return list(self._outcomes)

    def get_last_batch_sent_keys(self):
        return set(self._sent)

    def get_last_batch_migrator_metrics(self):
        return {"sent": len(self._sent), "saved": len(self._sent)}


def test_corrida_cierra_cuentas_y_reintenta_permanent_vencidos(tmp_path, stores):
    retry, links = stores
    sink = RecordEventSink()
    engine = SyncEngine(CheckpointStore(db_url=f"sqlite+pysqlite:///{tmp_path / 'cp.db'}"))
    # Una OP 'permanent' cuyo reintento ya vencio vuelve a entrar sola.
    for _ in range(retry.max_attempts):
        retry.enqueue("orden_pago", _op(40), REASON_BACKEND_REJECTED, "rechazada")
    retry._conn.execute("UPDATE retry_queue SET next_retry_after = datetime('now', '-1 minutes')")
    retry._conn.commit()

    source = _Source(_rows(2, 3, 4, 5, 40))
    ok, _err, metrics = _sync_entity(
        source, engine, _Exporter(links, sink), "orden_pago",
        batch_size=10, limit=None, dry_run=False, retry_store=retry,
        sink=sink, link_store=links,
    )

    assert ok is True
    assert _op(40) in source.retry_keys, "el permanent vencido se reinyecta en la query"
    assert metrics["permanent_retried"] == 1
    ledger = metrics["ledger"]
    assert ledger["read"] == 5
    assert ledger["with_id"] == 3          # 2, 4 y 40 (se migro en el reintento)
    assert ledger["queued_espera"] == 1     # 3
    assert ledger["unexplained"] == 1       # 5
    queue = _queue(retry)
    assert set(queue) == {_op(3), _op(5), _op(40)}
    assert queue[_op(5)][:2] == (REASON_VALIDATION_CLIENT, "unexplained")


def test_corrida_sin_sink_no_cierra_cuentas(tmp_path, stores):
    retry, links = stores
    engine = SyncEngine(CheckpointStore(db_url=f"sqlite+pysqlite:///{tmp_path / 'cp.db'}"))
    ok, _err, metrics = _sync_entity(
        _Source(_rows(5)), engine, _Exporter(links, RecordEventSink()), "orden_pago",
        batch_size=10, limit=None, dry_run=False, retry_store=retry,
    )
    assert ok is True
    assert metrics["ledger"] is None
    assert retry.list_items() == []


# ─── Corrida real del cron (exporter y mappers reales, Paxapos simulado) ─────


def test_cron_proveedores_ningun_registro_queda_sin_id_y_sin_motivo(tmp_path, monkeypatch):
    from argparse import Namespace

    from sqlalchemy import create_engine, text

    import main as main_module
    from src import run_history
    from tests.test_resend import _migrator

    state_db = tmp_path / "state.db"
    monkeypatch.setenv("RAFAM_RUN_HISTORY_PATH", str(tmp_path / "runs.jsonl"))
    monkeypatch.setenv("RAFAM_INCIDENTS_PATH", str(tmp_path / "incidents.json"))
    monkeypatch.setenv("NOTIFY_ENABLED", "false")
    source = create_engine(f"sqlite+pysqlite:///{tmp_path / 'rafam.db'}")
    with source.connect() as conn:
        conn.execute(text(
            "CREATE TABLE PROVEEDORES (COD_PROV INTEGER PRIMARY KEY, FANTASIA TEXT, "
            "RAZON_SOCIAL TEXT, FECHA_ULT_COMP DATETIME)"
        ))
        rows = [
            (100, "Prov OK", "Prov OK SA", "2026-01-10"),
            (200, "Prov rechazado", "Prov R SA", "2026-01-11"),
            (300, "Prov sin id", "Prov S SA", "2026-01-12"),
            (400, None, None, "2026-01-13"),               # sin nombre: dato invalido
            (600, "Prov sin respuesta", "Prov N SA", "2026-01-14"),
            (50001, "Telefonica", "Telefonica", "2026-01-15"),  # excluido por config
        ]
        for row in rows:
            conn.execute(text("INSERT INTO PROVEEDORES VALUES (:a, :b, :c, :d)"), dict(zip("abcd", row)))
        conn.commit()

    exporter = _migrator(monkeypatch, tmp_path)   # LOCAL_STATE_DB_PATH -> tmp/links.db
    monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(state_db))
    exporter._link_store = EntityLinkStore(db_path=str(state_db))

    def _post(url, payload):
        results, errors = [], []
        for p in payload["proveedores"]:
            cod = p["external_id"]["cod_prov"]
            if cod == 200:
                errors.append({"section": "proveedores", "external_id": p["external_id"],
                               "message": "Error guardando proveedor",
                               "validationErrors": {"cuit": ["El CUIT ya existe"]}})
            elif cod == 300:
                results.append({"success": True, "mode": "create", "external_id": p["external_id"]})
            elif cod == 600:
                continue
            else:
                results.append({"success": True, "mode": "create", "external_id": p["external_id"], "id": 7000 + cod})
        return {"stats": {"proveedores": {"ok": len(results), "error": len(errors)}},
                "results": {"proveedores": results}, "errors": errors}

    exporter._post_json = _post
    monkeypatch.setattr(main_module, "create_source_engine", lambda: source)
    monkeypatch.setattr(main_module, "build_exporter", lambda dry_run=False: exporter)

    main_module._cmd_run_locked(Namespace(entity="proveedores", dry_run=False, batch_size=500, limit=None))

    retry = RetryStore(db_path=str(state_db))
    queue = {i.external_id: (i.reason_code, i.reason_detail) for i in retry.list_items("proveedores")}
    retry.close()
    # 100 se migro (tiene ID) y 50001 esta excluido: no van a la cola. Todo el
    # resto termina en la cola con su motivo, incluidos los dos casos que
    # antes se perdian en silencio (OK sin ID y enviado sin respuesta).
    assert set(queue) == {"200", "300", "400", "600"}
    assert queue["200"][0] == REASON_BACKEND_REJECTED          # rechazo de Paxapos
    assert queue["300"] == (REASON_BACKEND_REJECTED, "ok_without_id")
    assert queue["400"] == (REASON_VALIDATION_CLIENT, "invalid_row")
    assert queue["600"] == (REASON_BACKEND_REJECTED, "no_response")

    [run] = run_history.load_runs()
    ledger = run["entities"][0]["ledger"]
    assert ledger["read"] == 6
    assert ledger["with_id"] == 1
    assert ledger["fuera"] == 1
    assert ledger["unexplained"] == 2
