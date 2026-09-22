"""paxapos#489 aplicado a clasificaciones (full_load, igual que oc_items).

Antes del fix: `ClasificacionesMapper` no tenia forma de excluir codigos
'permanent' -- `exporter.attach_retry_store` ni siquiera se lo inyectaba. Un
codigo rechazado para siempre por el receptor se hubiera reenviado (y
rechazado) en cada corrida indefinidamente.
"""

from __future__ import annotations

from src.entity_link_store import EntityLinkStore
from src.mappers.clasificaciones import ClasificacionesMapper
from src.retry_store import STATUS_PERMANENT, RetryStore

_COLUMNS = ["INCISO", "PAR_PRIN", "PAR_PARC", "PAR_SUBP", "DENOMINACION"]
_ROW_A = (1, 1, 0, 0, "Personal permanente")
_ROW_B = (1, 2, 0, 0, "Personal temporario")


def _link_store(tmp_path) -> EntityLinkStore:
    return EntityLinkStore(db_path=str(tmp_path / "links.db"))


def test_sin_retry_store_manda_todos_los_nodos(tmp_path):
    mapper = ClasificacionesMapper(link_store=_link_store(tmp_path))
    payload, _ = mapper.build_payload(
        _COLUMNS, [_ROW_A, _ROW_B], dry_run=False, payload_options={},
    )
    codes = {row["external_id"]["codigo"] for row in payload["clasificaciones"]}
    assert codes == {"1.1.0.0", "1.2.0.0"}


def test_excluye_codigo_permanent(tmp_path):
    retry = RetryStore(db_path=str(tmp_path / "retry.db"))
    retry.mark_permanent("clasificaciones", '{"codigo": "1.1.0.0"}', "backend_rejected", "rechazo terminal")
    assert retry.permanent_external_ids("clasificaciones")

    mapper = ClasificacionesMapper(link_store=_link_store(tmp_path), retry_store=retry)
    payload, _ = mapper.build_payload(
        _COLUMNS, [_ROW_A, _ROW_B], dry_run=False, payload_options={},
    )
    codes = {row["external_id"]["codigo"] for row in payload["clasificaciones"]}
    assert codes == {"1.2.0.0"}
    retry.close()


def test_todos_permanent_devuelve_none(tmp_path):
    retry = RetryStore(db_path=str(tmp_path / "retry.db"))
    for code in ("1.1.0.0", "1.2.0.0"):
        retry.mark_permanent("clasificaciones", f'{{"codigo": "{code}"}}', "backend_rejected", "rechazo")

    mapper = ClasificacionesMapper(link_store=_link_store(tmp_path), retry_store=retry)
    payload, raw = mapper.build_payload(
        _COLUMNS, [_ROW_A, _ROW_B], dry_run=False, payload_options={},
    )
    assert payload is None
    assert raw == {}
    retry.close()
