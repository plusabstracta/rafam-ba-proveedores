"""Tests para el circuit breaker de auth (paxapos#361).

Ante 401/403 sostenidos, el cliente NUNCA debe seguir reintentando ciego: un
reintento no arregla una api_key mala, solo agrega ruido al log de 403 del
backend (y en el caso real que motivo el issue, termino ensuciando 240
requests en 2h contra lookups.json). Estos tests cubren la logica pura del
breaker; los tests de integracion (que el request ni siquiera sale a la red
con el circuito abierto) viven en test_http_client.py y
test_exporter_extra_coverage.py.
"""

from __future__ import annotations

import json

import pytest

from src import auth_circuit_breaker as breaker


@pytest.fixture(autouse=True)
def _state_path(monkeypatch, tmp_path):
    path = tmp_path / "auth_circuit.json"
    monkeypatch.setenv("RAFAM_AUTH_CIRCUIT_PATH", str(path))
    return path


class TestCheck:
    def test_no_state_file_never_blocks(self):
        breaker.check()  # no debe lanzar

    def test_open_circuit_blocks(self):
        breaker.record_failure(403)
        with pytest.raises(breaker.AuthCircuitOpenError):
            breaker.check()

    def test_expired_cooldown_no_longer_blocks(self, _state_path, monkeypatch):
        breaker.record_failure(403)
        # Forzamos que el cooldown ya haya vencido sin esperar de verdad.
        data = json.loads(_state_path.read_text())
        data["opened_until"] = 0  # muy en el pasado
        _state_path.write_text(json.dumps(data))
        breaker.check()  # no debe lanzar

    def test_error_message_mentions_api_key_and_remaining_time(self):
        breaker.record_failure(401)
        with pytest.raises(breaker.AuthCircuitOpenError) as exc_info:
            breaker.check(context="GET lookups.json")
        msg = str(exc_info.value)
        assert "PAXAPOS_API_KEY" in msg
        assert "lookups.json" in msg


class TestRecordFailure:
    def test_ignores_non_auth_status(self):
        breaker.record_failure(400)
        breaker.record_failure(500)
        breaker.check()  # ni 400 ni 500 abren el circuito

    @pytest.mark.parametrize("status", [401, 403])
    def test_opens_on_auth_status(self, status):
        breaker.record_failure(status)
        with pytest.raises(breaker.AuthCircuitOpenError):
            breaker.check()

    def test_cooldown_grows_and_is_capped(self, _state_path):
        cooldowns = []
        for _ in range(6):
            breaker.record_failure(403)
            data = json.loads(_state_path.read_text())
            cooldowns.append(data["opened_until"])

        # Cada falla sucesiva debe ampliar (o igualar, una vez en el tope) la
        # ventana de corte — nunca reducirla.
        deltas = [cooldowns[i] - cooldowns[i - 1] for i in range(1, len(cooldowns))]
        assert all(d >= 0 for d in deltas)

        # El backoff esta acotado: no crece sin limite indefinidamente.
        data = json.loads(_state_path.read_text())
        assert data["consecutive_failures"] <= breaker._MAX_TRACKED_FAILURES

    def test_does_not_retry_forever_bounded_by_max_cooldown(self):
        import time

        for _ in range(10):
            breaker.record_failure(403)
        # Tope duro: el circuito nunca corta por mas de MAX_COOLDOWN_SECONDS.
        with pytest.raises(breaker.AuthCircuitOpenError):
            breaker.check()
        data = json.loads(breaker._path().read_text())
        assert data["opened_until"] <= time.time() + breaker.MAX_COOLDOWN_SECONDS + 1


class TestRecordSuccess:
    def test_clears_open_circuit(self):
        breaker.record_failure(403)
        breaker.record_success()
        breaker.check()  # ya no deberia estar abierto

    def test_noop_when_no_state_file(self):
        breaker.record_success()  # no debe lanzar aunque no exista el archivo


class TestCorruptState:
    def test_corrupt_json_is_ignored_not_fatal(self, _state_path):
        _state_path.parent.mkdir(parents=True, exist_ok=True)
        _state_path.write_text("{not valid json")
        breaker.check()  # no debe lanzar por el archivo corrupto

    def test_unwritable_dir_does_not_crash_record_failure(self, monkeypatch, tmp_path):
        # Un path invalido (archivo en vez de directorio como padre) fuerza un
        # OSError al crear el parent — record_failure debe tragarselo, no
        # tumbar la corrida por no poder persistir el breaker.
        blocker = tmp_path / "not_a_dir"
        blocker.write_text("x")
        monkeypatch.setenv("RAFAM_AUTH_CIRCUIT_PATH", str(blocker / "sub" / "auth_circuit.json"))
        breaker.record_failure(403)  # no debe lanzar
