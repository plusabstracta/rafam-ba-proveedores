"""
config.py — Entity configurations for the RAFAM incremental sync engine.

Each EntityConfig describes how to build incremental queries for a RAFAM table,
including cursor fields for change detection and optional extra conditions.

TODO: Confirm actual column names by running scripts/explore_schema.py against
      the production DB. Fields marked with TODO are best guesses pending verification.
"""

from .models import EntityConfig

SCHEMA = "OWNER_RAFAM"

ENTITY_CONFIGS: dict[str, EntityConfig] = {
    "jurisdicciones": EntityConfig(
        name="jurisdicciones",
        base_query=f"SELECT * FROM {SCHEMA}.JURISDICCIONES",
        full_load=True,  # small reference table — always full scan
    ),
    "proveedores": EntityConfig(
        name="proveedores",
        base_query=f"SELECT * FROM {SCHEMA}.PROVEEDORES",
        ts_field="FECHA_ALTA",  # NOT NULL — único timestamp confiable en PROVEEDORES
    ),
    "pedidos": EntityConfig(
        name="pedidos",
        base_query=f"SELECT * FROM {SCHEMA}.PEDIDOS",
        ts_field="FECH_EMI",  # NOT NULL — fecha de emisión del pedido
    ),
    "ped_items": EntityConfig(
        name="ped_items",
        base_query=f"SELECT * FROM {SCHEMA}.PED_ITEMS",
        full_load=True,  # no reliable cursor column yet — confirm with explore_schema.py
    ),
    "solic_gastos": EntityConfig(
        name="solic_gastos",
        base_query=f"SELECT * FROM {SCHEMA}.SOLIC_GASTOS",
        ts_field="FECH_SOLIC",  # NOT NULL — fecha de la solicitud
    ),
    "orden_compra": EntityConfig(
        name="orden_compra",
        base_query=f"""
            SELECT oc.*, prov.CUIT, prov.COD_ESTADO AS ESTADO_PROVEEDOR
            FROM {SCHEMA}.ORDEN_COMPRA oc
            LEFT JOIN {SCHEMA}.PROVEEDORES prov ON oc.COD_PROV = prov.COD_PROV
        """,
        ts_field="oc.FECH_OC",  # qualified with alias — appended directly to JOIN query
    ),
    "oc_items": EntityConfig(
        name="oc_items",
        base_query=f"SELECT * FROM {SCHEMA}.OC_ITEMS",
        full_load=True,  # no date/timestamp column in table
    ),
    "orden_pago": EntityConfig(
        name="orden_pago",
        base_query=f"SELECT * FROM {SCHEMA}.ORDEN_PAGO",
        ts_field="FECH_OP",  # NOT NULL — nombre real confirmado por explore_schema.py
        # Re-process pending payments from the last 30 days in case their
        # state changed from N→C or N→A after they were first synced.
        extra_condition="ESTADO_OP = 'N' AND FECH_OP > SYSDATE - 30",
    ),
}
