"""record_events.py — Resultado por registro de un envio.

El reenvio puntual (`main.py resend`) y el cierre de cuentas de cada corrida
(`src/record_ledger.py`) necesitan saber, para CADA registro leido de RAFAM,
que paso: si Paxapos lo acepto o lo rechazo (`RecordOutcome`, armado por el
exporter desde la respuesta) o si el script ni siquiera lo envio y por que
(`RecordEventSink.skip`, que anotan los mappers en cada regla de negocio que
omite un registro).

Cada omision va con un grupo, que decide que se hace con el registro:

* ``fallo``: dato invalido en RAFAM (o algo que el script no puede resolver).
  Va a la cola de reintentos, avisa por mail y figura en la lista del operador.
* ``espera``: el registro esta bien pero depende de otro (OC/OP/proveedor aun
  no migrado, OC sin confirmar). Va a la cola sin contar intentos; si la
  espera supera RAFAM_WAIT_ALERT_DAYS dias, avisa.
* ``fuera_de_alcance``: una regla de negocio dice que no se migra (proveedor
  excluido, OC anulada que nunca se migro...). Solo se cuenta.
* ``en_paxapos``: ya esta en Paxapos (aunque no haya link local). Nada que hacer.

Los mappers reciben el sink como atributo `_events`; sin sink (tests, uso
directo) `note_skip` no hace nada.
"""

from __future__ import annotations

from dataclasses import dataclass

from .retry_labels import record_base_key

GROUP_FALLO = "fallo"
GROUP_ESPERA = "espera"
GROUP_FUERA = "fuera_de_alcance"
GROUP_EN_PAXAPOS = "en_paxapos"


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


@dataclass(frozen=True)
class SkipNote:
    """Por que un mapper no envio un registro."""

    reason: str
    group: str = GROUP_FALLO
    # Codigo corto para agrupar y para `reason_detail` en la cola.
    detail: str | None = None


class RecordEventSink:
    """Junta los motivos por los que los mappers omiten registros."""

    def __init__(self) -> None:
        self._skips: dict[tuple[str, str], SkipNote] = {}

    def skip(
        self,
        entity: str,
        key,
        reason: str,
        *,
        group: str = GROUP_FALLO,
        detail: str | None = None,
    ) -> None:
        base = record_base_key(entity, key)
        if base is None:
            return
        # El primer motivo es el mas especifico (las reglas se evaluan en orden).
        self._skips.setdefault((entity, base), SkipNote(reason, group, detail))

    def reason_for(self, entity: str, base_key: str) -> str | None:
        note = self._skips.get((entity, base_key))
        return note.reason if note is not None else None

    def note_for(self, entity: str, base_key: str) -> SkipNote | None:
        return self._skips.get((entity, base_key))

    def clear(self, entity: str | None = None) -> None:
        if entity is None:
            self._skips.clear()
            return
        for key in [k for k in self._skips if k[0] == entity]:
            del self._skips[key]


def note_skip(
    sink: RecordEventSink | None,
    entity: str,
    key,
    reason: str,
    *,
    group: str = GROUP_FALLO,
    detail: str | None = None,
) -> None:
    if sink is not None:
        sink.skip(entity, key, reason, group=group, detail=detail)
