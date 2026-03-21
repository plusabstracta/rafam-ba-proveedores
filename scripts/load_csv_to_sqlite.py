#!/usr/bin/env python3
"""Load CSV snapshots from output/ into a SQLite DB for local development.

Usage:
    python scripts/load_csv_to_sqlite.py
    python scripts/load_csv_to_sqlite.py --output-db state/dev_rafam.db --csv-dir output
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from sqlalchemy import Column, MetaData, Table, Text, create_engine

_SNAPSHOT_RE = re.compile(r"^(?P<entity>.+)_\d{8}_\d{6}$")


def _latest_csv_by_entity(csv_dir: Path) -> dict[str, Path]:
    latest: dict[str, Path] = {}
    for path in csv_dir.glob("*.csv"):
        match = _SNAPSHOT_RE.match(path.stem)
        if match is None:
            continue
        entity = match.group("entity")
        current = latest.get(entity)
        if current is None or path.name > current.name:
            latest[entity] = path
    return latest


def _create_table_from_csv(metadata: MetaData, entity: str, header: list[str]) -> Table:
    # SQLite typing is permissive. We start as TEXT-like columns to avoid lossy casts.
    return Table(
        entity.upper(),
        metadata,
        *[Column(col, Text) for col in header],
    )


def load_csvs(csv_dir: Path, output_db: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{output_db}", future=True)
    output_db.parent.mkdir(parents=True, exist_ok=True)

    latest = _latest_csv_by_entity(csv_dir)
    if not latest:
        raise RuntimeError(f"No se encontraron CSV en {csv_dir}")

    metadata = MetaData()

    with engine.begin() as conn:
        for entity, path in sorted(latest.items()):
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    continue

                table = _create_table_from_csv(metadata, entity, reader.fieldnames)
                table.drop(conn, checkfirst=True)
                table.create(conn, checkfirst=True)

                rows = [row for row in reader]
                if rows:
                    conn.execute(table.insert(), rows)
                print(f"[{entity}] {len(rows)} filas cargadas desde {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cargar snapshots CSV a SQLite para desarrollo")
    parser.add_argument("--csv-dir", default="output", help="Directorio con CSV exportados")
    parser.add_argument("--output-db", default="state/dev_rafam.db", help="Ruta del archivo SQLite destino")
    args = parser.parse_args()

    load_csvs(Path(args.csv_dir), Path(args.output_db))


if __name__ == "__main__":
    main()
