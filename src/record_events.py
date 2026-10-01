"""record_events.py — Resultado por registro de un envio (usado por `main.py resend`).

El pipeline normal solo necesita contadores por batch; el reenvio puntual
necesita saber, para CADA clave pedida, que paso: si Paxapos la acepto o la
rechazo (`RecordOutcome`, armado por el exporter desde la respuesta) o si el
script ni siquiera la envio y por que (`RecordEventSink.skip`, que anotan los
mappers en cada regla de negocio que omite un registro).

Los mappers reciben el sink como atributo `_events`; en el pipeline normal es
None y `note_skip` no hace nada.
"""

from __future__ import annotations

from dataclasses import dataclass

from .retry_labels import record_base_key


@dataclass(frozen=True)
class RecordOutcome:
    """Resultado de UNA fila segun la respuesta del migrator."""

    entity: str             # entidad de la cola (gastos embebidos en OP -> solic_gastos)
    key: str                # external_id tal como lo guarda retry_queue
    ok: bool
    mode: str | None = None          # create / update / ... (solo ok)
    remote_id: object = None         # id en Paxapos (solo ok)
    reason_code: str | None = None   # solo error
    reason_detail: str | None = None
    message: str | None = None
    error_code: str | None = None    # `code` crudo del error (ej. egreso_not_found)

    @property
    def base_key(self) -> str | None:
        return record_base_key(self.entity, self.key)


class RecordEventSink:
    """Junta los motivos por los que los mappers omiten registros."""

    def __init__(self) -> None:
        self._skips: dict[tuple[str, str], str] = {}

    def skip(self, entity: str, key, reason: str) -> None:
        base = record_base_key(entity, key)
        if base is None:
            return
        # El primer motivo es el mas especifico (las reglas se evaluan en orden).
        self._skips.setdefault((entity, base), reason)

    def reason_for(self, entity: str, base_key: str) -> str | None:
        return self._skips.get((entity, base_key))


def note_skip(sink: RecordEventSink | None, entity: str, key, reason: str) -> None:
    if sink is not None:
        sink.skip(entity, key, reason)
