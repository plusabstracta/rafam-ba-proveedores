"""Tests para PaxaposHttpClient: armado de headers y corte ante 401/403 (paxapos#361).

Cubre:
  - build_auth_headers: unico lugar que decide los headers de auth — todas
    las llamadas del cliente (import via PaxaposHttpClient, spec/lookups/
    resolver_* via exporter._fetch_migrator_json) pasan por aca.
  - Que un 403 real deje el circuit breaker abierto y que la SIGUIENTE
    llamada corte antes de tocar la red (no vuelve a invocar _open_request).
"""

from __future__ import annotations

import io
from urllib import error
from unittest.mock import patch

import pytest

from src import auth_circuit_breaker as breaker
from src.http_client import PaxaposHttpClient, build_auth_headers


class TestBuildAuthHeaders:
    def test_includes_api_key_when_present(self):
        headers = build_auth_headers(api_key="secret123", tenant="acme")
        assert headers["X-Api-Key"] == "secret123"
        assert headers["X-Tenant-Id"] == "acme"
        assert headers["Accept"] == "application/json"
        assert "User-Agent" in headers

    def test_omits_api_key_when_missing(self):
        headers = build_auth_headers(api_key="", tenant="acme")
        assert "X-Api-Key" not in headers

    def test_omits_api_key_when_none(self):
        headers = build_auth_headers(api_key=None, tenant="acme")
        assert "X-Api-Key" not in headers

    def test_content_type_optional(self):
        without = build_auth_headers(api_key="k", tenant="t")
        assert "Content-Type" not in without
        with_ct = build_auth_headers(api_key="k", tenant="t", content_type="application/json")
        assert with_ct["Content-Type"] == "application/json"


class _FakeResponse:
    def __init__(self, body: bytes = b"{}", status: int = 200):
        self._body = body
        self._status = status
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def getcode(self):
        return self._status

    def geturl(self):
        return "https://example.test/tenant/rafam/migracion/lookups.json"

    def read(self):
        return self._body


def _client(monkeypatch, **overrides):
    monkeypatch.setenv("PAXAPOS_URL", "https://example.test")
    monkeypatch.setenv("PAXAPOS_TENANT", "tenant")
    monkeypatch.setenv("PAXAPOS_API_KEY", overrides.pop("api_key", "the-real-key"))
    monkeypatch.setenv("PAXAPOS_VERIFY_SSL", "true")
    return PaxaposHttpClient(**overrides)


class TestAntiLoopOn403:
    def test_403_opens_circuit_and_next_call_short_circuits(self, monkeypatch):
        client = _client(monkeypatch)
        forbidden = error.HTTPError("u", 403, "forbidden", {}, io.BytesIO(b'{"error":"bad key"}'))

        with patch("src.http_client._open_request", side_effect=forbidden) as mock_open:
            with pytest.raises(RuntimeError, match="HTTP 403"):
                client.get_json("rafam/migracion/lookups.json")
            assert mock_open.call_count == 1

        # Segunda llamada: el circuito quedo abierto tras el 403 anterior.
        # NO debe tocar la red — _open_request no se invoca de nuevo.
        with patch("src.http_client._open_request") as mock_open_2:
            with pytest.raises(breaker.AuthCircuitOpenError):
                client.get_json("rafam/migracion/lookups.json")
            mock_open_2.assert_not_called()

    def test_401_also_opens_circuit(self, monkeypatch):
        client = _client(monkeypatch)
        unauthorized = error.HTTPError("u", 401, "unauthorized", {}, io.BytesIO(b""))
        with patch("src.http_client._open_request", side_effect=unauthorized):
            with pytest.raises(RuntimeError, match="HTTP 401"):
                client.get_json("rafam/migracion/lookups.json")

        with patch("src.http_client._open_request") as mock_open_2:
            with pytest.raises(breaker.AuthCircuitOpenError):
                client.post_json("rafam/migracion/importar.json", {"x": 1})
            mock_open_2.assert_not_called()

    def test_successful_call_keeps_circuit_closed(self, monkeypatch):
        client = _client(monkeypatch)
        with patch("src.http_client._open_request", return_value=_FakeResponse()):
            result = client.get_json("rafam/migracion/lookups.json")
        assert result == {}
        breaker.check()  # no debe lanzar

    def test_success_after_failure_resets_circuit(self, monkeypatch):
        client = _client(monkeypatch)
        forbidden = error.HTTPError("u", 403, "forbidden", {}, io.BytesIO(b""))
        with patch("src.http_client._open_request", side_effect=forbidden):
            with pytest.raises(RuntimeError):
                client.get_json("rafam/migracion/lookups.json")

        # Simulamos que ya paso el cooldown (sin esperar de verdad) y que la
        # api_key ahora es correcta: el circuito debe cerrarse de nuevo.
        import json as _json

        data = _json.loads(breaker._path().read_text())
        data["opened_until"] = 0
        breaker._path().write_text(_json.dumps(data))

        with patch("src.http_client._open_request", return_value=_FakeResponse()):
            client.get_json("rafam/migracion/lookups.json")

        breaker.check()  # circuito cerrado tras el 2xx

    def test_non_auth_http_error_does_not_open_circuit(self, monkeypatch):
        client = _client(monkeypatch)
        bad_request = error.HTTPError("u", 400, "bad request", {}, io.BytesIO(b""))
        with patch("src.http_client._open_request", side_effect=bad_request):
            with pytest.raises(RuntimeError, match="HTTP 400"):
                client.get_json("rafam/migracion/lookups.json")

        # Un 400 es un error de negocio/validacion, no de auth: la SIGUIENTE
        # llamada debe poder intentarse igual (el breaker no la corta).
        with patch("src.http_client._open_request", return_value=_FakeResponse()) as mock_open:
            client.get_json("rafam/migracion/lookups.json")
            mock_open.assert_called_once()
