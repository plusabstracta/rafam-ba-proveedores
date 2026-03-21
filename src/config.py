"""Entity configurations for the RAFAM incremental sync engine.

The query layer builds SQLAlchemy expressions from this metadata, avoiding
hand-written SQL in application code.
"""

from .models import EntityConfig

SCHEMA = "OWNER_RAFAM"

ENTITY_CONFIGS: dict[str, EntityConfig] = {
    "jurisdicciones": EntityConfig(
        name="jurisdicciones",
        table_name="JURISDICCIONES",
        full_load=True,  # small reference table — always full scan
    ),
    "proveedores": EntityConfig(
        name="proveedores",
        table_name="PROVEEDORES",
        ts_field="FECHA_ULT_COMP",
    ),
    "pedidos": EntityConfig(
        name="pedidos",
        table_name="PEDIDOS",
        ts_field="FECH_EMI",
    ),
    "ped_items": EntityConfig(
        name="ped_items",
        table_name="PED_ITEMS",
        full_load=True,  # no reliable cursor column yet — confirm with explore_schema.py
    ),
    "solic_gastos": EntityConfig(
        name="solic_gastos",
        table_name="SOLIC_GASTOS",
        ts_field="FECH_SOLIC",
    ),
    "orden_compra": EntityConfig(
        name="orden_compra",
        table_name="ORDEN_COMPRA",
        ts_field="FECH_OC",
    ),
    "oc_items": EntityConfig(
        name="oc_items",
        table_name="OC_ITEMS",
        full_load=True,  # no date/timestamp column in table
    ),
    "orden_pago": EntityConfig(
        name="orden_pago",
        table_name="ORDEN_PAGO",
        ts_field="FECH_OP",
        # Re-process pending payments from recent days in case their
        # state changed from N→C or N→A after they were first synced.
        pending_state_field="ESTADO_OP",
        pending_state_value="N",
        pending_reprocess_days=30,
    ),
}
