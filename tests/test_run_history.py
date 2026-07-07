import pytest

from src import run_history


@pytest.fixture
def hist(tmp_path, monkeypatch):
    path = tmp_path / "run_history.jsonl"
    monkeypatch.setenv("RAFAM_RUN_HISTORY_PATH", str(path))
    return path


def _summary(success, start="2026-07-07 10:00:00", end="2026-07-07 10:03:00", dur="00:03:00"):
    return {
        "hostname": "srv",
        "start_time": start,
        "end_time": end,
        "duration_formatted": dur,
        "success": success,
        "error_msg": None if success else "fallo",
    }


def _entity(name, success=True, records=100, migrator_error=None):
    return {
        "entity": name,
        "mode": "INCREMENTAL",
        "success": success,
        "records_ok": records,
        "batches_ok": 2,
        "batches_failed": 0 if success else 1,
        "duration_secs": 5.0,
        "query_duration_secs": 1.0,
        "error_msg": None if success else "error de entidad",
        "error_type": None if success else "RuntimeError",
        "error_location": None if success else "src/exporter.py:198",
        "migrator_error": migrator_error,
        "error_trace": None if success else "traceback...",
    }


def test_record_and_load(hist):
    run_history.record_run(_summary(True), [_entity("proveedores")])
    run_history.record_run(_summary(True, start="2026-07-08 10:00:00", end="2026-07-08 10:01:00"),
                           [_entity("proveedores", records=50)])

    all_runs = run_history.load_runs()
    assert len(all_runs) == 2

    day1 = run_history.load_runs("2026-07-07")
    assert len(day1) == 1
    assert day1[0]["entities"][0]["records_ok"] == 100


def test_aggregate_runs_ok(hist):
    run_history.record_run(_summary(True), [_entity("proveedores", records=100)])
    run_history.record_run(_summary(True, start="2026-07-07 10:10:00", end="2026-07-07 10:12:00", dur="00:02:00"),
                           [_entity("proveedores", records=50)])

    runs = run_history.load_runs("2026-07-07")
    summary, metrics = run_history.aggregate_runs(runs, "2026-07-07")

    assert summary["success"] is True
    assert summary["subject"] == "Resumen diario RAFAM 2026-07-07 — OK"
    # 3min + 2min = 5min
    assert summary["duration_formatted"] == "00:05:00"
    assert len(metrics) == 1
    assert metrics[0]["records_ok"] == 150


def test_aggregate_runs_con_errores(hist):
    run_history.record_run(_summary(True), [_entity("proveedores")])
    run_history.record_run(
        _summary(False, start="2026-07-07 10:10:00", end="2026-07-07 10:12:00"),
        [_entity("orden_pago", success=False, migrator_error="HTTP 422: proveedor inactivo")],
    )

    runs = run_history.load_runs("2026-07-07")
    summary, metrics = run_history.aggregate_runs(runs, "2026-07-07")

    assert summary["success"] is False
    assert "CON ERRORES" in summary["subject"]
    assert "orden_pago" in summary["error_msg"]
    op = next(m for m in metrics if m["entity"] == "orden_pago")
    assert op["success"] is False
    assert op["migrator_error"] == "HTTP 422: proveedor inactivo"


def test_prune_reported(hist):
    run_history.record_run(_summary(True), [_entity("proveedores")])
    run_history.record_run(
        _summary(True, start="2026-07-08 10:00:00", end="2026-07-08 10:01:00"),
        [_entity("proveedores")],
    )

    remaining = run_history.prune_reported("2026-07-07")
    assert remaining == 1
    left = run_history.load_runs()
    assert len(left) == 1
    assert left[0]["start_time"].startswith("2026-07-08")


def test_load_runs_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("RAFAM_RUN_HISTORY_PATH", str(tmp_path / "nope.jsonl"))
    assert run_history.load_runs() == []
    assert run_history.prune_reported("2026-07-07") == 0
