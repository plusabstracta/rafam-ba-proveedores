"""
exporter.py — Destinos de salida intercambiables para los datos extraídos de Oracle.

Interfaz común:
    exporter.write_batch(entity, columns, rows)
    exporter.close()

Implementaciones:
    CsvExporter      — escribe archivos CSV en output/
    NoopExporter     — descarta los datos (modo dry-run / solo checkpoints)
    GatewayExporter  — envía filas traducidas al gateway HTTP de Paxapos
"""

import csv
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .Traductor.base import BaseTranslator

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


# ─── Gateway Paxapos ────────────────────────────────────────────────────────

class GatewayExporter(BaseExporter):
    """Envia lotes traducidos al endpoint HTTP de Paxapos."""

    def __init__(
        self,
        base_url: str,
        translators: dict[str, "BaseTranslator"],
        token: str = "",
        verify_ssl: bool = True,
    ):
        if not base_url:
            raise ValueError("GATEWAY_URL es requerido para modo gateway")

        self._base_url = base_url.rstrip("/")
        self._translators = translators
        self._verify_ssl = verify_ssl
        self._session = requests.Session()
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._session.headers.update(headers)

    def _build_url(self, endpoint_path: str) -> str:
        return f"{self._base_url}/{endpoint_path.lstrip('/')}"

    @staticmethod
    def _row_context(columns: list[str], row: tuple) -> str:
        """Build a compact supplier identifier for logs and error traces."""
        raw = {str(k).upper(): v for k, v in zip(columns, row)}
        cod_prov = raw.get("COD_PROV")
        cuit = raw.get("CUIT")
        razon = raw.get("RAZON_SOCIAL")
        return f"COD_PROV={cod_prov!r} | CUIT={cuit!r} | RAZON_SOCIAL={razon!r}"

    def _raise_if_gateway_error(self, entity: str, response: requests.Response) -> None:
        """Raise on HTTP or application-level errors returned by Paxapos."""
        status = response.status_code
        if status == 401:
            raise RuntimeError("Sin autorización (401) — token JWT vencido o no configurado")
        if status == 404:
            raise RuntimeError("Endpoint no encontrado (404) — verificar GATEWAY_URL")
        if status == 422:
            raise RuntimeError(f"Dato rechazado por Paxapos (422): {response.text[:300]}")
        if status >= 500:
            raise RuntimeError(f"Error interno de Paxapos ({status}): {response.text[:200]}")
        if status >= 400:
            raise RuntimeError(f"Paxapos respondió {status}: {response.text[:200]}")

        # Some Paxapos endpoints return HTTP 200 even when validation fails.
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "json" not in content_type:
            return

        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError):
            return

        if not isinstance(payload, dict):
            return

        has_error_flag = bool(payload.get("error"))
        has_validation_errors = bool(payload.get("validationErrors"))
        explicit_failure = payload.get("success") is False

        if has_error_flag or has_validation_errors or explicit_failure:
            raise RuntimeError(f"Paxapos rechazó el registro: {str(payload)[:300]}")

    def write_batch(self, entity: str, columns: list[str], rows: list[tuple]) -> None:
        translator = self._translators.get(entity)
        if translator is None:
            logger.warning("[%s] Sin traductor — lote omitido.", entity)
            return

        url = self._build_url(translator.endpoint_path)
        row_errors: list[str] = []
        total = len(rows)

        for index, row in enumerate(rows, start=1):
            context = self._row_context(columns, row)

            if index == 1 or index % 100 == 0:
                logger.info("[%s] Procesando %d/%d...", entity, index, total)

            try:
                payload = translator.translate(columns, row)
            except ValueError as exc:
                row_errors.append(f"[{index}/{total}] Procesamiento ERROR | {context} | {exc}")
                logger.error("[%s][%d/%d] Procesamiento ERROR | %s | %s", entity, index, total, context, exc)
                continue

            try:
                response = self._session.post(url, json=payload, timeout=30, verify=self._verify_ssl)
            except requests.exceptions.SSLError as exc:
                msg = f"Error SSL — certificado inválido o expirado: {exc}"
                row_errors.append(f"[{index}/{total}] Salida ERROR | {context} | {msg}")
                logger.error("[%s][%d/%d] Salida ERROR | %s | %s", entity, index, total, context, msg)
                continue
            except requests.Timeout:
                msg = "Sin respuesta de Paxapos en 30s — timeout"
                row_errors.append(f"[{index}/{total}] Salida ERROR | {context} | {msg}")
                logger.error("[%s][%d/%d] Salida ERROR | %s | %s", entity, index, total, context, msg)
                continue
            except requests.ConnectionError as exc:
                msg = f"Sin acceso a Paxapos — verificar red o GATEWAY_URL: {exc}"
                row_errors.append(f"[{index}/{total}] Salida ERROR | {context} | {msg}")
                logger.error("[%s][%d/%d] Salida ERROR | %s | %s", entity, index, total, context, msg)
                continue
            except requests.RequestException as exc:
                msg = f"{type(exc).__name__}: {exc}"
                row_errors.append(f"[{index}/{total}] Salida ERROR | {context} | {msg}")
                logger.error("[%s][%d/%d] Salida ERROR | %s | %s", entity, index, total, context, msg)
                continue

            try:
                self._raise_if_gateway_error(entity, response)
            except RuntimeError as exc:
                row_errors.append(f"[{index}/{total}] Salida ERROR | {context} | {exc}")
                logger.error("[%s][%d/%d] Salida ERROR | %s | %s", entity, index, total, context, exc)
                continue

        ok_count = total - len(row_errors)
        if row_errors:
            logger.error("[%s] RESUMEN: %d OK | %d ERROR de %d", entity, ok_count, len(row_errors), total)
            for err in row_errors:
                logger.error("[%s]   %s", entity, err)
        else:
            logger.info("[%s] RESUMEN: %d/%d OK", entity, total, total)

    def close(self) -> None:
        self._session.close()


# ─── Factory ─────────────────────────────────────────────────────────────────

def build_exporter(mode: str) -> BaseExporter:
    """
    mode: 'csv' | 'noop' | 'gateway'
    """
    if mode == "csv":
        return CsvExporter()
    if mode == "noop":
        return NoopExporter()
    if mode == "gateway":
        from .Traductor import TRANSLATOR_REGISTRY

        verify_ssl = os.getenv("GATEWAY_VERIFY_SSL", "true").lower() not in {
            "0",
            "false",
            "no",
            "off",
        }

        return GatewayExporter(
            base_url=os.getenv("GATEWAY_URL", ""),
            translators=TRANSLATOR_REGISTRY,
            token=os.getenv("GATEWAY_JWT_TOKEN", ""),
            verify_ssl=verify_ssl,
        )
    raise ValueError(
        f"Modo de exportación desconocido: '{mode}'. Opciones: csv, noop, gateway"
    )
