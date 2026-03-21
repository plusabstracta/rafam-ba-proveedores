"""
exporter.py — Destinos de salida intercambiables para los datos extraídos de Oracle.

Interfaz común:
    exporter.write_batch(entity, columns, rows)
    exporter.close()

Implementaciones:
    CsvExporter   — escribe archivos CSV en output/
    NoopExporter  — descarta los datos (modo dry-run / solo checkpoints)

Cuando se implemente el gateway Paxapos, se agrega GatewayExporter aquí
y se cambia una sola línea en main.py.
"""

import csv
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import IO

logger = logging.getLogger(__name__)


class BaseExporter(ABC):
    @abstractmethod
    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        """Procesa un lote de filas para la entidad dada."""

    def close(self) -> None:
        """Llamado una vez al finalizar todas las entidades. Override si necesario."""


# ─── CSV ─────────────────────────────────────────────────────────────────────

class CsvExporter(BaseExporter):
    """
    Escribe un archivo CSV por entidad en output/.
    Todos los lotes de la misma entidad se acumulan en el mismo archivo.
    El archivo se crea (o sobreescribe) al enviar el primer lote.
    """

    def __init__(self, output_dir: str | Path = "output"):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._writers: dict[str, csv.writer] = {}
        self._files:   dict[str, IO[str]]     = {}
        self._timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _get_writer(self, entity: str, columns: list[str]) -> csv.writer:
        if entity not in self._writers:
            path = self._output_dir / f"{entity}_{self._timestamp}.csv"
            f = open(path, "w", newline="", encoding="utf-8")
            writer = csv.writer(f)
            writer.writerow(columns)
            self._files[entity]   = f
            self._writers[entity] = writer
            logger.info("Archivo creado: %s", path)
        return self._writers[entity]

    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        writer = self._get_writer(entity, columns)
        writer.writerows(rows)
        # Flush after each batch so partial data is visible if the run is interrupted
        self._files[entity].flush()

    def close(self) -> None:
        for f in self._files.values():
            f.close()
        self._files.clear()
        self._writers.clear()


# ─── Noop (dry-run) ──────────────────────────────────────────────────────────

class NoopExporter(BaseExporter):
    """Descarta los datos. Útil para correr solo la lógica de checkpoints."""

    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        pass


# ─── Factory ─────────────────────────────────────────────────────────────────

def build_exporter(mode: str) -> BaseExporter:
    """
    mode: 'csv' | 'noop'
    Cuando se implemente Paxapos, agregar: 'gateway'
    """
    if mode == "csv":
        return CsvExporter()
    if mode == "noop":
        return NoopExporter()
    raise ValueError(f"Modo de exportación desconocido: '{mode}'. Opciones: csv, noop")
