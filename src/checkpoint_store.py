from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .db import create_checkpoint_engine
from .models import Checkpoint

class Base(DeclarativeBase):
    pass


class SyncCheckpointORM(Base):
    __tablename__ = "sync_checkpoints"

    entity: Mapped[str] = mapped_column(String, primary_key=True)
    last_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_ts: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_run: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    records_sent: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="ok")


def _orm_to_checkpoint(row: SyncCheckpointORM) -> Checkpoint:
    return Checkpoint(
        entity=row.entity,
        last_id=row.last_id,
        last_ts=row.last_ts,
        last_run=row.last_run,
        records_sent=row.records_sent or 0,
        status=row.status or "ok",
    )


class CheckpointStore:
    """SQLAlchemy-backed persistence layer for sync checkpoints."""

    def __init__(self, db_url: Optional[str] = None):
        self._engine = create_engine(db_url, future=True) if db_url else create_checkpoint_engine()
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine, future=True)

    def _session(self) -> Session:
        return self._session_factory()

    def close(self) -> None:
        self._engine.dispose()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def get(self, entity: str) -> Checkpoint:
        with self._session() as session:
            row = session.get(SyncCheckpointORM, entity)
            return _orm_to_checkpoint(row) if row else Checkpoint(entity=entity)

    def save(self, checkpoint: Checkpoint) -> None:
        with self._session() as session:
            row = session.get(SyncCheckpointORM, checkpoint.entity)
            if row is None:
                row = SyncCheckpointORM(entity=checkpoint.entity)
            row.last_id = checkpoint.last_id
            row.last_ts = checkpoint.last_ts
            row.last_run = checkpoint.last_run
            row.records_sent = checkpoint.records_sent
            row.status = checkpoint.status
            session.add(row)
            session.commit()

    def reset(self, entity: str) -> None:
        with self._session() as session:
            row = session.get(SyncCheckpointORM, entity)
            if row is not None:
                session.delete(row)
                session.commit()

    def all_checkpoints(self) -> list[Checkpoint]:
        with self._session() as session:
            rows = session.execute(
                select(SyncCheckpointORM).order_by(SyncCheckpointORM.entity)
            ).scalars().all()
            return [_orm_to_checkpoint(row) for row in rows]
