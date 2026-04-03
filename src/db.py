import os
from pathlib import Path

import oracledb
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_STATE_DIR = Path(__file__).resolve().parent.parent / "state"


def create_source_engine() -> Engine:
    """Build SQLAlchemy engine for RAFAM source DB.

    Supported backends:
    - Oracle: DB_BACKEND=oracle (default)
    - SQLite: DB_BACKEND=sqlite (for local development from CSV snapshots)
    """
    backend = os.getenv("DB_BACKEND", "oracle").lower()

    if backend == "sqlite":
        sqlite_path = os.getenv("SQLITE_DB_PATH", str(_STATE_DIR / "dev_rafam.db"))
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(f"sqlite+pysqlite:///{sqlite_path}", future=True)

    if backend != "oracle":
        raise ValueError(f"DB_BACKEND no soportado: '{backend}'. Usar oracle|sqlite")

    host = os.getenv("DB_HOST", "10.10.91.241")
    port = int(os.getenv("DB_PORT", 1521))
    service = os.getenv("DB_SERVICE", "BDRAFAM")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not user or not password:
        raise ValueError("Faltan DB_USER / DB_PASSWORD para Oracle")

    # Thick mode requerido para Oracle < 12.2. Mirrors explore_schema.py.
    oracle_client_dir = os.getenv("ORACLE_CLIENT_DIR")
    oracledb.init_oracle_client(lib_dir=oracle_client_dir or None)

    url = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service}"
    return create_engine(url, future=True)


def create_checkpoint_engine() -> Engine:
    """Build SQLAlchemy engine for checkpoint persistence."""
    db_path = os.getenv("CHECKPOINT_DB_PATH", str(_STATE_DIR / "checkpoint.db"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
