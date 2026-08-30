"""conftest.py — fixtures compartidas para la suite de rafam-ba-proveedores."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_auth_circuit_state(monkeypatch, tmp_path):
    """Aisla el estado del circuit breaker de auth (paxapos#361) por test.

    Sin esto, cualquier test que dispare un 401/403 via `_fetch_migrator_json`
    o `PaxaposHttpClient` dejaria el circuito abierto en el archivo real de
    `state/` (default `state/migrator_auth_circuit.json`), contaminando los
    tests siguientes de la misma corrida — y el checkout local de quien corre
    la suite.
    """
    monkeypatch.setenv("RAFAM_AUTH_CIRCUIT_PATH", str(tmp_path / "auth_circuit.json"))
