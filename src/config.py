"""Entity configurations for the RAFAM incremental sync engine.

The query layer builds SQLAlchemy expressions from this metadata, avoiding
hand-written SQL in application code.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from .models import EntityConfig

# load_dotenv() MUST run before reading env vars, because this module is
# imported before main.py calls load_dotenv().  It's idempotent so safe
# to call multiple times.
# Use explicit path because find_dotenv() from src/ may not locate the
# project root .env depending on python-dotenv version.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

SCHEMA = "OWNER_RAFAM"

_raw_ejercicio_min = os.getenv("RAFAM_EJERCICIO_MIN", "0").strip()
try:
    _EJERCICIO_MIN = int(_raw_ejercicio_min) if _raw_ejercicio_min else None
except ValueError:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "RAFAM_EJERCICIO_MIN invalido: %r — ignorado (sin filtro de ejercicio)",
        _raw_ejercicio_min,
    )
    _EJERCICIO_MIN = None
_EJERCICIO_MIN = _EJERCICIO_MIN or None
_EJERCICIO_MIN_ENTITIES = {
    "pedidos",
    "ped_items",
    "orden_compra",
    "oc_items",
    "solic_gastos",
    "orden_pago",
}


def _ejercicio_min_for(entity: str) -> int | None:
    return _EJERCICIO_MIN if entity in _EJERCICIO_MIN_ENTITIES else None

ENTITY_CONFIGS: dict[str, EntityConfig] = {
    "proveedores": EntityConfig(
        name="proveedores",
        table_name="PROVEEDORES",
        ts_field="FECHA_ULT_COMP",
    ),
    "pedidos": EntityConfig(
        name="pedidos",
        table_name="PEDIDOS",
        ts_field="FECH_EMI",
        ejercicio_min=_ejercicio_min_for("pedidos"),
    ),
    "ped_items": EntityConfig(
        name="ped_items",
        table_name="PED_ITEMS",
        full_load=True,  # no reliable cursor column yet — confirm with explore_schema.py
        ejercicio_min=_ejercicio_min_for("ped_items"),
    ),
    "orden_compra": EntityConfig(
        name="orden_compra",
        table_name="ORDEN_COMPRA",
        ts_field="FECH_OC",
        # Re-process OCs with estado N from recent days to detect N→A transitions.
        pending_state_field="ESTADO_OC",
        pending_state_value="N",
        pending_reprocess_days=30,
        ejercicio_min=_ejercicio_min_for("orden_compra"),
    ),
    "oc_items": EntityConfig(
        name="oc_items",
        table_name="OC_ITEMS",
        full_load=True,  # no date/timestamp column in table
        ejercicio_min=_ejercicio_min_for("oc_items"),
    ),
    "solic_gastos": EntityConfig(
        name="solic_gastos",
        table_name="SOLIC_GASTOS",
        ts_field="FECH_SOLIC",
        # Re-process confirmed gastos from recent days to catch those
        # whose linked OC was sent after the gasto was first processed.
        pending_state_field="ESTADO_SOLIC",
        pending_state_value="C",
        pending_reprocess_days=30,
        ejercicio_min=_ejercicio_min_for("solic_gastos"),
    ),
    "orden_pago": EntityConfig(
        name="orden_pago",
        table_name="ORDEN_PAGO",
        ts_field="FECH_CONFIRM",
        # Re-process confirmed normal payments from recent days in case their
        # linked gastos became available after the first attempt.
        pending_state_field="ESTADO_OP",
        pending_state_value="C",
        pending_reprocess_days=30,
        ejercicio_min=_ejercicio_min_for("orden_pago"),
    ),
}
