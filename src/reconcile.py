"""reconcile.py — Reconciliacion read-only RAFAM vs estado migrado (F4).

Compara, por entidad logica, el universo de origen en RAFAM contra lo que se
migro localmente (link store) y lo que quedo en la cola de reintentos. El
objetivo es detectar *drift*: filas que no estan migradas NI registradas como
pendientes/permanentes — es decir, perdidas silenciosas, justo lo que la
arquitectura fila-a-fila busca evitar.

NO escribe nada (decision del usuario: opcion A, script standalone read-only).
"""

from __future__ import annotations

from dataclasses import dataclass

from .entity_link_store import EntityLinkStore
from .retry_store import RetryStore, STATUS_PENDING, STATUS_PERMANENT
from .source_repository import SourceRepository

# Definicion de cada entidad reconciliable:
#   label            → nombre legible
#   source_table     → tabla RAFAM de origen
#   distinct_fields  → claves de negocio para contar unidades migradas (None = filas)
#   link_entity      → entidad en el link store
#   retry_entity     → entidad en la cola de reintentos (= config entity)
#   ejercicio_filtered → si aplica el filtro RAFAM_EJERCICIO_MIN
@dataclass(frozen=True)
class ReconcileTarget:
    label: str
    source_table: str
    distinct_fields: list[str] | None
    link_entity: str
    retry_entity: str
    ejercicio_filtered: bool


RECONCILE_TARGETS: list[ReconcileTarget] = [
    ReconcileTarget("proveedores", "PROVEEDORES", None, "proveedores", "proveedores", False),
    ReconcileTarget(
        "ordenes_compra",
        "ORDEN_COMPRA",
        ["EJERCICIO", "UNI_COMPRA", "NRO_OC"],
        "orden_compra",
        "oc_items",
        True,
    ),
    ReconcileTarget(
        "ordenes_pago",
        "ORDEN_PAGO",
        ["EJERCICIO", "NRO_OP"],
        "orden_pago",
        "orden_pago",
        True,
    ),
]


@dataclass(frozen=True)
class ReconcileRow:
    label: str
    source_count: int
    migrated_count: int
    retry_pending: int
    retry_permanent: int

    @property
    def drift(self) -> int:
        """Filas de origen no migradas y no registradas en la cola.

        drift > 0 → posible perdida silenciosa (investigar).
        drift < 0 → mas links que origen (reprocesos/duplicados de clave).
        """
        return self.source_count - self.migrated_count - self.retry_pending - self.retry_permanent


def reconcile(
    source_repo: SourceRepository,
    link_store: EntityLinkStore,
    retry_store: RetryStore,
    *,
    ejercicio_min: int | None = None,
    targets: list[ReconcileTarget] | None = None,
) -> list[ReconcileRow]:
    targets = targets if targets is not None else RECONCILE_TARGETS
    retry_counts = retry_store.counts_by_entity()
    rows: list[ReconcileRow] = []

    for target in targets:
        source_count = source_repo.count_rows(
            target.source_table,
            distinct_fields=target.distinct_fields,
            ejercicio_min=ejercicio_min if target.ejercicio_filtered else None,
        )
        migrated_count = link_store.count(target.link_entity)
        entity_retry = retry_counts.get(target.retry_entity, {})
        rows.append(
            ReconcileRow(
                label=target.label,
                source_count=source_count,
                migrated_count=migrated_count,
                retry_pending=entity_retry.get(STATUS_PENDING, 0),
                retry_permanent=entity_retry.get(STATUS_PERMANENT, 0),
            )
        )

    return rows


def format_report(rows: list[ReconcileRow]) -> str:
    header = "{:<16} {:>10} {:>10} {:>10} {:>10} {:>10}".format(
        "Entidad", "Origen", "Migrado", "Pend.", "Perm.", "Drift"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            "{:<16} {:>10} {:>10} {:>10} {:>10} {:>10}".format(
                row.label,
                row.source_count,
                row.migrated_count,
                row.retry_pending,
                row.retry_permanent,
                row.drift,
            )
        )
    return "\n".join(lines)


def has_drift(rows: list[ReconcileRow]) -> bool:
    return any(row.drift != 0 for row in rows)
