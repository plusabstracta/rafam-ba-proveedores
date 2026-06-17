"""batch_grouping.py â LÃ³gica de agrupamiento de batches por business key.

Cuando una entidad tiene filas que comparten una clave compuesta (ej: una OC
con N items), no podemos cortarlas a mitad de grupo porque el receptor espera
la OC completa. Este mÃ³dulo garantiza que cada batch enviado contenga todos
los items de un grupo sin partirlos entre batches consecutivos.

Pattern: Pure function â sin side effects, sin estado, input/output determinÃ­stico.
"""

from __future__ import annotations

from typing import Any, Generator

# Campos de agrupamiento por entidad. Si una entidad aparece acá,
# sus rows se agrupan por esta clave compuesta y nunca se parten
# entre batches.
GROUPED_BATCH_FIELDS: dict[str, list[str]] = {
    "oc_items": ["EJERCICIO", "UNI_COMPRA", "NRO_OC"],
    "orden_pago": ["EJERCICIO", "NRO_OP"],
    "retenciones": ["EJERCICIO", "NRO_OP"],
}

# Maps entity config names to the link store entity they write to.
# Usado por cmd_reset para saber qué links borrar cuando se resetea
# una entidad.
ENTITY_LINK_NAMES: dict[str, str] = {
    "proveedores": "proveedores",
    "oc_items": "orden_compra",
    "solic_gastos": "gasto",
    "orden_pago": "orden_pago",
    "retenciones": "retenciones",
}


def iter_grouped_batches(
    result: Any,
    columns: list[str],
    group_fields: list[str],
    batch_size: int,
) -> Generator[list[tuple], None, None]:
    """Yield batches sin partir filas que comparten la misma business key.

    Cuando varias filas de Oracle tienen la misma (EJERCICIO, NRO_OC, UNI_COMPRA),
    son items de la misma OC. El receptor espera la OC completa, asÃ­ que este
    generador acumula todas las filas del mismo grupo y las emite juntas.

    Si algÃºn group_field no estÃ¡ en columns, fallback a fetchmany simple.

    Args:
        result: SQLAlchemy CursorResult o similar con .fetchmany().
        columns: Lista de nombres de columnas.
        group_fields: Campos que forman la business key.
        batch_size: TamaÃ±o mÃ¡ximo del batch (puede exceder si el grupo es grande).
    """
    col_idx = {name.upper(): i for i, name in enumerate(columns)}
    group_indexes = [col_idx.get(field.upper()) for field in group_fields]

    # Si algÃºn campo de agrupamiento no existe en las columnas,
    # fallback a batches simples (no podemos agrupar).
    if any(index is None for index in group_indexes):
        while True:
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            yield [tuple(row) for row in rows]
        return

    pending: list[tuple] = []
    current_group: list[tuple] = []
    current_key = None

    while True:
        rows = result.fetchmany(batch_size)
        if not rows:
            break

        for raw_row in rows:
            row = tuple(raw_row)
            key = tuple(row[index] for index in group_indexes if index is not None)
            if current_group and key != current_key:
                if pending and len(pending) + len(current_group) > batch_size:
                    yield pending
                    pending = []
                pending.extend(current_group)
                current_group = []

            current_key = key
            current_group.append(row)

    if current_group:
        if pending and len(pending) + len(current_group) > batch_size:
            yield pending
            pending = []
        pending.extend(current_group)

    if pending:
        yield pending
