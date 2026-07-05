"""change_detection.py — Detección de cambios en registros ya migrados.

Compara el payload actual de un registro RAFAM contra el hash del payload
que se envió la última vez (almacenado en link_proveedores.payload_hash).
Si difiere, el registro se re-envía al endpoint importar.json con upsert=true.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChangeDetectionResult:
    """Resultado de detección de cambios para una entidad."""
    entity: str
    changed_keys: list[str] = field(default_factory=list)
    new_keys: list[str] = field(default_factory=list)
    unchanged_keys: list[str] = field(default_factory=list)
    total_scanned: int = 0


HASH_VERSION = "v1"


def compute_payload_hash(payload: dict) -> str:
    """Hash determinístico SHA256 del payload normalizado, versionado.

    Formato: ``v1:<32-hex-chars>`` (prefijo de versión + 128 bits).
    El prefijo permite distinguir "cambió el dato en RAFAM" de "cambié
    mi lógica de mapeo" — al incrementar HASH_VERSION todos los hashes
    divergen y el primer sync-changes hace un resync controlado.
    """
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"{HASH_VERSION}:{digest}"
