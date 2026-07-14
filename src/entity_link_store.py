import os
import sqlite3
from pathlib import Path
from typing import Optional

_TABLE_PREFIX = "link_"

# Extra columns per entity (beyond the base source_key, remote_id, updated_at).
# Override via the ``schemas`` parameter in EntityLinkStore.__init__().
DEFAULT_LINK_SCHEMAS: dict[str, list[str]] = {
    "proveedores": ["cuit", "cod_estado", "payload_hash", "content_hash", "deleted_at"],
    "unidad_medida": ["name", "codigo"],
    "tipo_factura": ["name", "codigo"],
    "tipo_pago": ["name", "codigo"],
    "tipo_retencion": ["name", "codigo"],
    "mercaderia": ["barcode", "nombre_compra"],
    "pedido": [],
    "orden_compra": ["fech_confirm", "estado_oc", "cod_prov", "importe_tot", "gasto_refs", "gasto_linked_refs", "paxapos_gasto_ids", "has_op", "payload_hash", "deleted_at"],
    "gasto": ["estado_solic", "importe_tot", "cod_prov", "deleted_at"],
    "orden_pago": ["estado_op", "confirmado", "fech_confirm", "importe_total", "deleted_at"],
    "retenciones": ["fingerprint", "retenciones_count", "deleted_at"],
    # Clasificador por objeto del gasto (RAFAM 4 niveles -> categorias Paxapos).
    # source_key = codigo compuesto "I.PP.PC.SP"; el vinculo vive aca (fuera de
    # Paxapos) porque la tabla destino no tiene columna de codigo.
    "clasificacion": ["denominacion", "nivel", "parent_codigo", "deleted_at"],
}


class EntityLinkStore:
    """Stores RAFAM -> Paxapos ID links — one table per entity.

    Each entity gets its own ``link_<entity>`` table with configurable
    extra columns defined in ``schemas``.
    """

    def __init__(
        self,
        db_path: str | None = None,
        schemas: dict[str, list[str]] | None = None,
    ):
        if not db_path:
            db_path = os.getenv("LOCAL_STATE_DB_PATH", "state/checkpoint.db")
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # timeout=5: tolera locks transitorios. WAL + busy_timeout aplicados
        # explicitamente porque sqlite3.connect() crudo no comparte los pragmas
        # de SQLAlchemy (db.py) — son procesos/conexiones distintas.
        self._conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error:
            pass
        self._schemas = schemas if schemas is not None else DEFAULT_LINK_SCHEMAS
        self._created_tables: set[str] = set()
        self._ensure_all_tables()

    # ── internal ──────────────────────────────────────────────────────────

    def _ensure_all_tables(self) -> None:
        """Pre-create all entity link tables defined in the schema."""
        for entity in self._schemas:
            self._ensure_table(entity)

    def _ensure_table(self, entity: str) -> str:
        """Create ``link_<entity>`` if missing; ALTER TABLE to add new columns."""
        table_name = f"{_TABLE_PREFIX}{entity}"
        if table_name in self._created_tables:
            return table_name

        extra_cols = self._schemas.get(entity, [])
        col_defs = ["source_key TEXT PRIMARY KEY", "remote_id TEXT"]
        for col in extra_cols:
            col_defs.append(f"[{col}] TEXT")
        col_defs.append("updated_at TEXT NOT NULL")

        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS [{table_name}] ({', '.join(col_defs)})"
        )

        # Forward-migration: add columns that exist in schema but not in table.
        existing_cols = {
            row["name"]
            for row in self._conn.execute(f"PRAGMA table_info([{table_name}])").fetchall()
        }
        for col in extra_cols:
            if col not in existing_cols:
                self._conn.execute(f"ALTER TABLE [{table_name}] ADD COLUMN [{col}] TEXT")

        self._conn.commit()
        self._created_tables.add(table_name)
        return table_name

    # ── lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()

    # ── reset ─────────────────────────────────────────────────────────────

    def clear_entity(self, entity: str) -> int:
        """Delete all links for a single entity. Returns rows deleted."""
        table = self._ensure_table(entity)
        cursor = self._conn.execute(f"DELETE FROM [{table}]")
        self._conn.commit()
        return cursor.rowcount

    def clear_all(self) -> dict[str, int]:
        """Delete all links for every entity in the schema. Returns {entity: rows_deleted}."""
        result: dict[str, int] = {}
        for entity in self._schemas:
            result[entity] = self.clear_entity(entity)
        return result

    # ── public API ────────────────────────────────────────────────────────

    def save_link(
        self,
        entity: str,
        source_key: str,
        remote_id: str,
        **extras: str | None,
    ) -> None:
        table = self._ensure_table(entity)
        allowed = set(self._schemas.get(entity, []))
        extra_data = {k: v for k, v in extras.items() if k in allowed}

        cols = ["source_key", "remote_id"] + list(extra_data.keys()) + ["updated_at"]
        value_slots = ["?"] * (len(cols) - 1) + ["datetime('now')"]

        update_parts = ["remote_id = excluded.remote_id", "updated_at = excluded.updated_at"]
        for col in extra_data:
            update_parts.append(f"[{col}] = excluded.[{col}]")

        sql = (
            f"INSERT INTO [{table}] ({', '.join(cols)})"
            f" VALUES ({', '.join(value_slots)})"
            f" ON CONFLICT(source_key) DO UPDATE SET {', '.join(update_parts)}"
        )
        params = [source_key, remote_id] + list(extra_data.values())
        self._conn.execute(sql, params)
        self._conn.commit()

    def get_remote_id(self, entity: str, source_key: str) -> Optional[str]:
        # Entidades fuera del schema: devolver None sin crear la tabla. Evita
        # recrear tablas link obsoletas desde fallbacks de lectura.
        if entity not in self._schemas:
            return None
        table = self._ensure_table(entity)
        row = self._conn.execute(
            f"SELECT remote_id FROM [{table}] WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        if not row:
            return None
        return row["remote_id"]

    def get_link(self, entity: str, source_key: str) -> dict | None:
        """Return the full row as a dict, or None if not found."""
        if entity not in self._schemas:
            return None
        table = self._ensure_table(entity)
        row = self._conn.execute(
            f"SELECT * FROM [{table}] WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def count(self, entity: str) -> int:
        """Cantidad de links migrados para una entidad (para reconciliacion F4)."""
        table = self._ensure_table(entity)
        row = self._conn.execute(f"SELECT COUNT(*) AS n FROM [{table}]").fetchone()
        return int(row["n"]) if row else 0

    def mark_oc_has_op(self, source_key: str) -> None:
        """Flag an OC as having an associated OP (orden de pago)."""
        table = self._ensure_table("orden_compra")
        self._conn.execute(
            f"UPDATE [{table}] SET [has_op] = '1', updated_at = datetime('now') WHERE source_key = ?",
            (source_key,),
        )
        self._conn.commit()

    def get_sent_oc_gasto_refs(self) -> set[str]:
        """Return gasto rafam_refs linked to OCs that have been sent to Paxapos."""
        table = self._ensure_table("orden_compra")
        rows = self._conn.execute(
            f"SELECT gasto_refs FROM [{table}] WHERE remote_id != '' AND gasto_refs != ''"
        ).fetchall()
        refs: set[str] = set()
        for row in rows:
            for ref in row["gasto_refs"].split(","):
                ref = ref.strip()
                if ref:
                    refs.add(ref)
        return refs

    def get_all_links(self, entity: str) -> list[dict]:
        """Return all links for an entity as a list of dicts."""
        if entity not in self._schemas:
            return []
        table = self._ensure_table(entity)
        rows = self._conn.execute(f"SELECT * FROM [{table}]").fetchall()
        return [dict(row) for row in rows]

    def iter_all_links(self, entity: str, *, include_deleted: bool = True) -> list[dict]:
        """Return links for an entity, optionally excluding soft-deleted rows."""
        links = self.get_all_links(entity)
        if include_deleted:
            return links
        return [link for link in links if not link.get("deleted_at")]

    def mark_deleted(self, entity: str, source_key: str) -> None:
        """Soft-delete a migrated link for audit-friendly integrity fixes."""
        table = self._ensure_table(entity)
        self._conn.execute(
            f"UPDATE [{table}] SET deleted_at = datetime('now'), updated_at = datetime('now') WHERE source_key = ?",
            (source_key,),
        )
        self._conn.commit()
