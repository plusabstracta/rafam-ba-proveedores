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

_EJERCICIO_MIN = int(os.getenv("RAFAM_EJERCICIO_MIN", "0")) or None

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
        ejercicio_min=_EJERCICIO_MIN,
    ),
    "ped_items": EntityConfig(
        name="ped_items",
        table_name="PED_ITEMS",
        full_load=True,  # no reliable cursor column yet — confirm with explore_schema.py
        ejercicio_min=_EJERCICIO_MIN,
    ),
    "orden_compra": EntityConfig(
        name="orden_compra",
        table_name="ORDEN_COMPRA",
        ts_field="FECH_OC",
        # Re-process OCs with estado N from recent days to detect N→A transitions.
        pending_state_field="ESTADO_OC",
        pending_state_value="N",
        pending_reprocess_days=30,
        ejercicio_min=_EJERCICIO_MIN,
    ),
    "oc_items": EntityConfig(
        name="oc_items",
        table_name="OC_ITEMS",
        full_load=True,  # no date/timestamp column in table
        ejercicio_min=_EJERCICIO_MIN,
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
        ejercicio_min=_EJERCICIO_MIN,
    ),
    "orden_pago": EntityConfig(
        name="orden_pago",
        table_name="ORDEN_PAGO",
        ts_field="FECH_CONFIRM",
        # Re-process confirmed normal payments from recent days in case their
        # linked gastos became available after the first attempt.
        pending_state_field="ESTADO_OP",
        pending_state_value="N",
        pending_reprocess_days=30,
        ejercicio_min=_EJERCICIO_MIN,
    ),
}
