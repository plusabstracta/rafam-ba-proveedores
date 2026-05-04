import os
from pathlib import Path

import oracledb
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_STATE_DIR = Path(__file__).resolve().parent.parent / "state"


def create_source_engine() -> Engine:
    """Build SQLAlchemy engine for RAFAM source DB.

    Supported backends:
    - Oracle: RAFAM_SOURCE_BACKEND=oracle (default)
    - SQLite: RAFAM_SOURCE_BACKEND=sqlite (for local development from CSV snapshots)
    """
    backend = os.getenv("RAFAM_SOURCE_BACKEND", "oracle").lower()

    if backend == "sqlite":
        sqlite_path = os.getenv("RAFAM_SOURCE_SQLITE_DB_PATH", str(_STATE_DIR / "dev_rafam.db"))
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(f"sqlite+pysqlite:///{sqlite_path}", future=True)

    if backend != "oracle":
        raise ValueError(f"RAFAM_SOURCE_BACKEND no soportado: '{backend}'. Usar oracle|sqlite")

    host = os.getenv("RAFAM_SOURCE_HOST", "10.10.91.241")
    port = int(os.getenv("RAFAM_SOURCE_PORT", "1521"))
    service = os.getenv("RAFAM_SOURCE_SERVICE", "BDRAFAM")
    user = os.getenv("RAFAM_SOURCE_USER")
    password = os.getenv("RAFAM_SOURCE_PASSWORD")

    if not user or not password:
        raise ValueError("Faltan RAFAM_SOURCE_USER/RAFAM_SOURCE_PASSWORD para Oracle")

    # Thick mode requerido para Oracle < 12.2. Mirrors explore_schema.py.
    oracle_client_dir = os.getenv("ORACLE_CLIENT_DIR")
    oracledb.init_oracle_client(lib_dir=oracle_client_dir or None)

    url = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service}"
    return create_engine(url, future=True)


def create_checkpoint_engine() -> Engine:
    """Build SQLAlchemy engine for checkpoint persistence."""
    db_path = os.getenv("LOCAL_STATE_DB_PATH", str(_STATE_DIR / "checkpoint.db"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
