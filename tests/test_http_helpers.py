"""Tests para los helpers HTTP del exporter: retries y redacción de dumps."""

from __future__ import annotations

import io
import json
from unittest.mock import patch
from urllib import error, request

import pytest

from src.exporter import (
    _SENSITIVE_FIELDS,
    _dump_payload_path,
    _http_request_with_retries,
    _redact_payload_for_dump,
)


class _FakeResponse:
    def __init__(self, body: bytes = b"{}", status: int = 200, headers: dict | None = None):
        self._body = body
        self._status = status
        self.headers = headers or {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def getcode(self):
        return self._status

    def geturl(self):
        return "https://example/x"

    def read(self):
        return self._body


def _req(url: str = "https://example/x") -> request.Request:
    return request.Request(url=url, method="GET")


class TestHttpRetries:
    def test_succeeds_first_try(self):
        with patch("src.http_client._open_request", return_value=_FakeResponse()) as mock:
            with _http_request_with_retries(_req(), timeout=5):
                pass
            assert mock.call_count == 1

    def test_retries_on_url_error(self):
        calls = [error.URLError("net down"), error.URLError("dns"), _FakeResponse()]

        def side(*_a, **_kw):
            v = calls.pop(0)
            if isinstance(v, Exception):
                raise v
            return v

        with patch("src.http_client._open_request", side_effect=side), patch(
            "src.exporter.time.sleep"
        ):
            with _http_request_with_retries(_req(), timeout=5, max_attempts=3, base_backoff=0.01):
                pass
        assert calls == []  # se consumieron los 3

    def test_retries_on_timeout_error(self):
        calls = [TimeoutError("The read operation timed out"), _FakeResponse()]

        def side(*_a, **_kw):
            value = calls.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        with patch("src.http_client._open_request", side_effect=side), patch(
            "src.http_client.time.sleep"
        ):
            with _http_request_with_retries(
                _req(), timeout=5, max_attempts=3, base_backoff=0.01
            ):
                pass
        assert calls == []

    def test_retries_on_503_then_succeeds(self):
        first = error.HTTPError("u", 503, "busy", {}, io.BytesIO(b""))
        calls = [first, _FakeResponse()]

        def side(*_a, **_kw):
            v = calls.pop(0)
            if isinstance(v, Exception):
                raise v
            return v

        with patch("src.http_client._open_request", side_effect=side), patch(
            "src.exporter.time.sleep"
        ):
            with _http_request_with_retries(_req(), timeout=5, max_attempts=3, base_backoff=0.01):
                pass
        assert calls == []

    def test_does_not_retry_on_400(self):
        exc = error.HTTPError("u", 400, "bad", {}, io.BytesIO(b""))
        with patch("src.http_client._open_request", side_effect=exc), patch(
            "src.exporter.time.sleep"
        ):
            with pytest.raises(error.HTTPError):
                _http_request_with_retries(_req(), timeout=5, max_attempts=3, base_backoff=0.01)

    def test_does_not_retry_on_401(self):
        exc = error.HTTPError("u", 401, "unauth", {}, io.BytesIO(b""))
        with patch("src.http_client._open_request", side_effect=exc), patch(
            "src.exporter.time.sleep"
        ):
            with pytest.raises(error.HTTPError):
                _http_request_with_retries(_req(), timeout=5, max_attempts=3, base_backoff=0.01)

    def test_raises_after_max_attempts(self):
        exc = error.URLError("net down")
        with patch("src.http_client._open_request", side_effect=exc), patch(
            "src.exporter.time.sleep"
        ):
            with pytest.raises(error.URLError):
                _http_request_with_retries(_req(), timeout=5, max_attempts=2, base_backoff=0.01)


class TestRedactPayload:
    def test_redacts_cuit(self):
        payload = json.dumps({"cuit": "20-12345678-9", "name": "Acme"})
        out = _redact_payload_for_dump(payload)
        assert "20-12345678-9" not in out
        assert "***REDACTED***" in out
        assert "Acme" in out  # otros campos quedan

    def test_redacts_token(self):
        payload = '{"token":"secret123","data":1}'
        out = _redact_payload_for_dump(payload)
        assert "secret123" not in out
        assert "***REDACTED***" in out

    def test_redacts_api_key(self):
        payload = '{"x-api-key":"abc"}'
        out = _redact_payload_for_dump(payload)
        assert "abc" not in out

    def test_passthrough_no_secrets(self):
        payload = '{"importe": 100, "nombre": "X"}'
        assert _redact_payload_for_dump(payload) == payload

    def test_pattern_case_insensitive(self):
        assert _SENSITIVE_FIELDS.search('"CUIT":"x"')
        assert _SENSITIVE_FIELDS.search('"Authorization":"x"')


class TestDumpPayloadPath:
    def test_no_env_returns_none(self, monkeypatch):
        monkeypatch.delenv("DUMP_PAYLOAD", raising=False)
        assert _dump_payload_path() is None

    def test_dev_returns_path(self, monkeypatch):
        monkeypatch.setenv("DUMP_PAYLOAD", "/tmp/d.txt")
        monkeypatch.setenv("APP_ENV", "dev")
        assert _dump_payload_path() == "/tmp/d.txt"

    def test_prod_blocks_dump_by_default(self, monkeypatch):
        monkeypatch.setenv("DUMP_PAYLOAD", "/tmp/d.txt")
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.delenv("DUMP_PAYLOAD_FORCE", raising=False)
        assert _dump_payload_path() is None

    def test_prod_with_force_allows_dump(self, monkeypatch):
        monkeypatch.setenv("DUMP_PAYLOAD", "/tmp/d.txt")
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("DUMP_PAYLOAD_FORCE", "1")
        assert _dump_payload_path() == "/tmp/d.txt"
