import re
from datetime import datetime
from typing import Optional

from .checkpoint_store import CheckpointStore
from .models import Checkpoint, EntityConfig, SyncResult

_SCHEMA = "OWNER_RAFAM"

# ─── Entity configurations ────────────────────────────────────────────────────
# TODO: Confirm actual column names by running scripts/explore_schema.py against
#       the production DB. Fields marked with # ? are best guesses pending verification.

ENTITY_CONFIGS: dict[str, EntityConfig] = {
    "jurisdicciones": EntityConfig(
        name="jurisdicciones",
        base_query=f"SELECT * FROM {_SCHEMA}.JURISDICCIONES",
        full_load=True,  # small reference table — always full scan
    ),
    "proveedores": EntityConfig(
        name="proveedores",
        base_query=f"SELECT * FROM {_SCHEMA}.PROVEEDORES",
        ts_field="FECHA_MODIFICACION",  # TODO: confirm column name
    ),
    "pedidos": EntityConfig(
        name="pedidos",
        base_query=f"SELECT * FROM {_SCHEMA}.PEDIDOS",
        ts_field="FECHA_PEDIDO",  # TODO: confirm; use FECHA_MODIFICACION if it exists
    ),
    "ped_items": EntityConfig(
        name="ped_items",
        base_query=f"SELECT * FROM {_SCHEMA}.PED_ITEMS",
        full_load=True,  # no reliable cursor column yet — confirm with explore_schema.py
    ),
    "solic_gastos": EntityConfig(
        name="solic_gastos",
        base_query=f"SELECT * FROM {_SCHEMA}.SOLIC_GASTOS",
        ts_field="FECHA_ALTA",  # TODO: confirm column name
    ),
    "orden_compra": EntityConfig(
        name="orden_compra",
        base_query=f"""
            SELECT oc.*, prov.CUIT, prov.COD_ESTADO AS ESTADO_PROVEEDOR
            FROM {_SCHEMA}.ORDEN_COMPRA oc
            LEFT JOIN {_SCHEMA}.PROVEEDORES prov ON oc.COD_PROV = prov.COD_PROV
        """,
        ts_field="oc.FECH_OC",  # qualified with alias — appended directly to JOIN query
    ),
    "oc_items": EntityConfig(
        name="oc_items",
        base_query=f"SELECT * FROM {_SCHEMA}.OC_ITEMS",
        full_load=True,  # no date/timestamp column in table
    ),
    "orden_pago": EntityConfig(
        name="orden_pago",
        base_query=f"SELECT * FROM {_SCHEMA}.ORDEN_PAGO",
        ts_field="FECHA_OP",  # TODO: confirm column name
        # Re-process pending payments from the last 30 days in case their
        # state changed from N→C or N→A after they were first synced.
        extra_condition="ESTADO_OP = 'N' AND FECHA_OP > SYSDATE - 30",
    ),
}


class SyncEngine:
    """
    Incremental sync engine backed by a SQLite checkpoint store.

    The engine does NOT execute queries directly — callers fetch rows using
    the SQL returned by build_incremental_query() and report results via
    mark_success() / mark_error().
    """

    def __init__(
        self,
        store: CheckpointStore,
        configs: Optional[dict[str, EntityConfig]] = None,
    ):
        self._store = store
        self._configs = configs if configs is not None else ENTITY_CONFIGS

    # ─── Checkpoint API ───────────────────────────────────────────────────────

    def get_checkpoint(self, entity: str) -> Checkpoint:
        return self._store.get(entity)

    def save_checkpoint(self, entity: str, checkpoint: Checkpoint) -> None:
        self._store.save(checkpoint)

    def reset_checkpoint(self, entity: str) -> None:
        """Force a full reload on the next run for this entity."""
        self._store.reset(entity)

    def mark_success(
        self,
        entity: str,
        last_id: Optional[int],
        last_ts: Optional[datetime],
        count: int,
    ) -> None:
        """Advance the checkpoint after a successful sync run."""
        existing = self._store.get(entity)
        self._store.save(
            Checkpoint(
                entity=entity,
                # Only advance if a new value was observed; keep old value otherwise.
                last_id=last_id if last_id is not None else existing.last_id,
                last_ts=last_ts if last_ts is not None else existing.last_ts,
                last_run=datetime.utcnow(),
                records_sent=count,
                status="ok",
            )
        )

    def mark_error(self, entity: str, error: str) -> None:
        """Record an error WITHOUT advancing the cursor (safe to retry)."""
        cp = self._store.get(entity)
        cp.status = f"error: {error[:200]}"
        cp.last_run = datetime.utcnow()
        self._store.save(cp)

    # ─── Query builder ────────────────────────────────────────────────────────

    def build_incremental_query(
        self, entity: str, base_query: str
    ) -> tuple[str, list]:
        """
        Returns (sql, params) ready to pass to cursor.execute().

        - First run (no checkpoint) or full_load entity → returns base_query unchanged.
        - Subsequent runs → wraps base_query in a CTE and appends a WHERE clause
          using Oracle positional bind variables (:1, :2, …).

        The WHERE clause uses OR so that both new records (by ID) and modified
        records (by timestamp) are captured. extra_condition is also OR-ed in.
        """
        cfg = self._configs.get(entity)
        cp = self._store.get(entity)

        if cfg is None or cfg.full_load or cp.is_fresh:
            return base_query.strip(), []

        conditions: list[str] = []
        params: list = []

        if cfg.id_field and cp.last_id is not None:
            params.append(cp.last_id)
            conditions.append(f"{cfg.id_field} > :{len(params)}")

        if cfg.ts_field and cp.last_ts is not None:
            # Pass datetime object directly — oracledb handles type conversion.
            params.append(cp.last_ts)
            conditions.append(f"{cfg.ts_field} > :{len(params)}")

        if cfg.extra_condition:
            conditions.append(f"({cfg.extra_condition})")

        if not conditions:
            return base_query.strip(), []

        base  = base_query.strip()
        where = "\n   OR ".join(conditions)
        # Append WHERE directly — avoids CTE issues with SELECT * in some Oracle versions.
        # If the base query already has a WHERE (e.g. a pre-filtered view), wrap with AND.
        if re.search(r'\bWHERE\b', base, re.IGNORECASE):
            sql = f"{base}\n   AND ({where})"
        else:
            sql = f"{base}\nWHERE {where}"
        return sql, params

    # ─── Utility ─────────────────────────────────────────────────────────────

    def extract_cursor_values(
        self,
        columns: list[str],
        rows: list[tuple],
        entity: str,
    ) -> tuple[Optional[int], Optional[datetime]]:
        """
        Scans fetched rows and returns the max (last_id, last_ts) to use as
        the new checkpoint cursor values. Returns (None, None) if rows is empty.
        """
        if not rows:
            return None, None

        cfg = self._configs.get(entity)
        if cfg is None:
            return None, None

        col_idx = {name.upper(): i for i, name in enumerate(columns)}
        last_id: Optional[int] = None
        last_ts: Optional[datetime] = None

        if cfg.id_field:
            key = cfg.id_field.upper()
            if key in col_idx:
                vals = [r[col_idx[key]] for r in rows if r[col_idx[key]] is not None]
                if vals:
                    last_id = int(max(vals))

        if cfg.ts_field:
            # Strip table alias if present (e.g. "oc.FECH_OC" → "FECH_OC")
            key = cfg.ts_field.upper().split('.')[-1]
            if key in col_idx:
                vals = [r[col_idx[key]] for r in rows if r[col_idx[key]] is not None]
                if vals:
                    raw = max(vals)
                    last_ts = raw if isinstance(raw, datetime) else None

        return last_id, last_ts
