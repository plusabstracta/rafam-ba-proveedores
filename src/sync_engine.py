from datetime import datetime, timezone
from typing import Optional

from .checkpoint_store import CheckpointStore
from .config import ENTITY_CONFIGS
from .models import Checkpoint, EntityConfig


class SyncEngine:
    """
    Incremental sync engine backed by a SQLite checkpoint store.

    The engine does NOT execute queries directly — callers fetch rows from
    SQLAlchemy statements and report results via mark_success() / mark_error().
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
        """Advance the checkpoint after a successful sync run.

        El cursor es monotonico: solo avanza si el valor observado es mayor al
        persistido. Sin esta guarda, una corrida cuyas unicas filas sean
        reinyecciones viejas de la cola de reintentos rebobinaria el watermark
        y la corrida siguiente re-escanearia (y re-enviaria) meses de datos.
        """
        existing = self._store.get(entity)
        new_id = existing.last_id
        if last_id is not None and (existing.last_id is None or last_id > existing.last_id):
            new_id = last_id
        new_ts = existing.last_ts
        norm_existing_ts = self._normalize_utc(existing.last_ts)
        norm_new_ts = self._normalize_utc(last_ts)
        if norm_new_ts is not None and (norm_existing_ts is None or norm_new_ts > norm_existing_ts):
            new_ts = norm_new_ts
        self._store.save(
            Checkpoint(
                entity=entity,
                last_id=new_id,
                last_ts=new_ts,
                last_run=datetime.now(timezone.utc),
                records_sent=count,
                status="ok",
            )
        )

    def advance_partial(
        self,
        entity: str,
        last_id: Optional[int],
        last_ts: Optional[datetime],
        records_added: int,
    ) -> None:
        """Persist watermark progress after a successful batch.

        A diferencia de `mark_success`, esto se invoca POR BATCH durante una
        corrida en curso. Si el proceso muere a mitad (kill, OOM, network),
        el siguiente run reanuda desde el ultimo batch confirmado en vez de
        rebobinar al inicio. El status se deja como `running`.

        El cursor solo avanza si los nuevos valores son >= a los persistidos
        (proteccion ante batches con cursor menor por orden de scan).
        """
        existing = self._store.get(entity)
        new_id = existing.last_id
        if last_id is not None and (existing.last_id is None or last_id > existing.last_id):
            new_id = last_id
        new_ts = existing.last_ts
        # Normalizar ambos a UTC-aware antes de comparar para evitar el clasico
        # TypeError 'can't compare offset-naive and offset-aware datetimes'.
        norm_existing_ts = self._normalize_utc(existing.last_ts)
        norm_new_ts = self._normalize_utc(last_ts)
        if norm_new_ts is not None and (norm_existing_ts is None or norm_new_ts > norm_existing_ts):
            new_ts = norm_new_ts
        self._store.save(
            Checkpoint(
                entity=entity,
                last_id=new_id,
                last_ts=new_ts,
                last_run=datetime.now(timezone.utc),
                records_sent=(existing.records_sent or 0) + records_added,
                status="running",
            )
        )

    def mark_error(self, entity: str, error: str) -> None:
        """Record an error WITHOUT advancing the cursor (safe to retry)."""
        cp = self._store.get(entity)
        cp.status = f"error: {error[:200]}"
        cp.last_run = datetime.now(timezone.utc)
        self._store.save(cp)

    @staticmethod
    def _normalize_utc(value):
        """Convierte datetime naive (asumido UTC) o aware a aware-UTC. None -> None."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return None

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
            key = cfg.ts_field.upper()
            if key in col_idx:
                vals = [r[col_idx[key]] for r in rows if r[col_idx[key]] is not None]
                if vals:
                    # Normalizar a datetime ANTES de max() — mezclar str+datetime
                    # rompe la comparacion en Python 3.
                    parsed = [self._coerce_datetime(v) for v in vals]
                    parsed = [p for p in parsed if p is not None]
                    if parsed:
                        last_ts = max(parsed)

        return last_id, last_ts

    @staticmethod
    def _coerce_datetime(value) -> Optional[datetime]:
        """Convierte datetime/str a datetime aware en UTC. Tolera ISO con/sin tz, microsegundos y formatos legacy."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            return SyncEngine._parse_ts(value)
        return None

    @staticmethod
    def _parse_ts(value: str) -> Optional[datetime]:
        """Parse comunes: ISO 8601 (con o sin tz/microsegundos) y formatos legacy."""
        text = value.strip()
        if not text:
            return None
        # ISO con/sin tz, con/sin microsegundos. fromisoformat acepta 'YYYY-MM-DD HH:MM:SS[.ffffff][+HH:MM]'.
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
