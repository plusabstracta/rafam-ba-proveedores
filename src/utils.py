"""utils.py â Utilidades compartidas para el pipeline RAFAM â Paxapos.

Centraliza funciones puras de parsing / normalizaciÃ³n que antes estaban
dispersas como @staticmethod en MigratorExporter o duplicadas entre
exporter.py y gateway_mapper.py.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

from .validation import validate_amount as _validate_amount, validate_date_only as _validate_date_only


def to_int(value: Any) -> int | None:
    """Convierte a int de forma segura. None si no parseable."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_text(value: Any) -> str:
    """Normaliza texto: lowercase, sin acentos, sin caracteres especiales.

    Usado para matching fuzzy de catalogos (tipos_factura, tipos_retencion).
    """
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    compact = "".join(ch if ch.isalnum() else " " for ch in text)
    return " ".join(compact.split())


def format_date_only(value: Any) -> str:
    """Extrae solo YYYY-MM-DD de un string fecha (puede incluir hora).

    Retorna string vacÃ­o si el valor no tiene formato de fecha reconocible.
    Delega internamente a validate_date_only() para validaciÃ³n centralizada.
    """
    if not value:
        return ""
    result = _validate_date_only(value, required=False)
    return result.value or ""


def parse_money(value: Any) -> float | None:
    """Parsea un valor monetario a float con 2 decimales. None si no parseable.

    Delega internamente a validate_amount() para validaciÃ³n centralizada
    (range check DECIMAL(14,2), NaN/Inf, etc.). Permite negativos y ceros
    para mantener backward-compat con los callers existentes.
    """
    if value is None or str(value).strip() == "":
        return None
    result = _validate_amount(value, required=False, allow_negative=True, allow_zero=True)
    return result.value


def normalize_cuit(value: Any) -> str | None:
    """Normaliza CUIT a 11 digitos. None si invalido."""
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits if len(digits) == 11 else None


def env_bool(name: str, default: str | bool = "true") -> bool:
    """Lee variable de entorno como bool. default puede ser str o bool."""
    if isinstance(default, bool):
        default = "true" if default else "false"
    value = os.getenv(name, default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Patron para redactar campos sensibles en dumps de payload.
_SENSITIVE_FIELDS = re.compile(
    r'"(cuit|password|token|api_key|authorization|jwt|x[-_]api[-_]key)"\s*:\s*"[^"]*"',
    re.IGNORECASE,
)


def redact_payload_for_dump(text: str) -> str:
    """Enmascara CUIT y secrets en string JSON serializado."""
    return _SENSITIVE_FIELDS.sub(lambda m: f'"{m.group(1)}":"***REDACTED***"', text)


def build_single_index(rows: list[dict], field: str) -> dict[str, dict]:
    """Construye indice {normalize_text(row[field]): row} para lookup rapido."""
    idx: dict[str, dict] = {}
    for row in rows:
        key = normalize_text(row.get(field))
        if not key:
            continue
        idx[key] = row
    return idx


def lookup_list(payload: dict, key: str) -> list[dict]:
    """Extrae una lista de dicts de un payload de lookups del migrator."""
    if not isinstance(payload, dict):
        return []
    value = payload.get(key)
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    lookups = payload.get("lookups")
    if isinstance(lookups, dict):
        nested = lookups.get(key)
        if isinstance(nested, list):
            return [v for v in nested if isinstance(v, dict)]
    return []


def split_ref_set(value: Any) -> set[str]:
    """Separa un string CSV de refs en un set limpio."""
    if not value:
        return set()
    return {part.strip() for part in str(value).split(",") if part.strip()}
