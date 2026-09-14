"""backend_errors.py — Clasificacion de los errores por fila que devuelve Paxapos.

El receptor (RafamMigracionesController) responde 200 con ``errors[]`` por fila.
No todos esos errores significan lo mismo para el pipeline:

* **Infraestructura** (``SQLSTATE``, tabla inexistente, fatal de PHP): la fila
  esta bien, el backend esta roto. No hay que "gastar" intentos de la fila ni
  seguir martillando el endpoint durante toda la corrida.
* **Dependencia faltante** (``egreso_not_found``, "se reintentara cuando..."):
  la fila espera a otra entidad. Se reinyecta sin contar intentos, igual que
  las dependencias detectadas del lado del cliente.
* **Rechazo real** (validacion, duplicado, etc.): cuenta intentos y pasa a
  ``permanent`` tras ``max_attempts``.

Sin esta distincion (sep-2026) una retencion cuya OP fue borrada en Paxapos
paso a ``permanent`` con 376 intentos y siguio reenviandose en cada corrida,
y un ``account_gasto_itemes doesn't exist`` del tenant se contabilizo como
rechazo de datos de cada OP/gasto del dia.
"""

from __future__ import annotations

from .retry_store import (
    REASON_BACKEND_REJECTED,
    REASON_BACKEND_UNAVAILABLE,
    REASON_DEPENDENCY_MISSING,
)


class BackendInfraError(RuntimeError):
    """El receptor fallo por infraestructura (SQL/PHP), no por los datos enviados."""


# Marcadores (lowercase) de fallos del backend que NO dependen de la fila.
_SYSTEMIC_MARKERS = (
    "sqlstate",
    "base table or view not found",
    "doesn't exist",
    "unknown column",
    "fatal error",
    "allowed memory size",
    "maximum execution time",
    "deadlock found",
    "lock wait timeout",
    "too many connections",
    "connection refused",
    "server has gone away",
    "call to undefined",
    "call to a member function",
    "internal server error",
)

# ``code`` que el receptor devuelve cuando la fila espera otra entidad.
_DEPENDENCY_CODES = frozenset({
    "egreso_not_found",
    "pedido_not_found",
    "gasto_not_found",
    "proveedor_not_found",
    "dependency_missing",
})

# Frases (lowercase) con las que el receptor declara explicitamente que la fila
# debe esperar. A proposito NO incluye "no existe"/"no encontrada" genericos:
# esos tambien describen errores de configuracion (clasificacion_id invalido,
# proveedor sin bloque) que SI deben agotar intentos y pasar a permanent.
_DEPENDENCY_MARKERS = (
    "se reintentara",
    "se reintentará",
    "aun no fue migrad",
    "aún no fue migrad",
    "aun no existe",
    "aún no existe",
)


def _message_of(err: dict | str | None) -> str:
    if isinstance(err, dict):
        return str(err.get("message") or "")
    return str(err or "")


def is_systemic_error(err: dict | str | None) -> bool:
    """True si el error es de infraestructura del backend (no de la fila)."""
    message = _message_of(err).lower()
    if not message:
        return False
    return any(marker in message for marker in _SYSTEMIC_MARKERS)


def is_dependency_error(err: dict | str | None) -> bool:
    """True si el receptor indica que falta una entidad de la que depende la fila."""
    if is_systemic_error(err):
        return False
    if isinstance(err, dict):
        code = str(err.get("code") or "").strip().lower()
        if code in _DEPENDENCY_CODES:
            return True
        if err.get("validationErrors"):
            return False
    message = _message_of(err).lower()
    return any(marker in message for marker in _DEPENDENCY_MARKERS)


def dependency_detail(err: dict | str | None) -> str:
    """reason_detail para una dependencia reportada por el backend."""
    if isinstance(err, dict):
        code = str(err.get("code") or "").strip().lower()
        if code in _DEPENDENCY_CODES:
            return code
    return "destination_missing"


def rejection_detail(err: dict) -> str:
    """reason_detail para un rechazo real (misma heuristica historica del exporter)."""
    if err.get("validationErrors"):
        return "validation_error"
    message = _message_of(err).lower()
    if "duplic" in message or "unique" in message:
        return "duplicate"
    if "sin items" in message or "cantidad" in message:
        return "invalid_items"
    if "proveedor" in message:
        return "provider_error"
    return "backend_rejected"


def classify_backend_error(err: dict) -> tuple[str, str]:
    """Devuelve ``(reason_code, reason_detail)`` para la cola de reintentos."""
    if is_systemic_error(err):
        return REASON_BACKEND_UNAVAILABLE, "backend_infra"
    if is_dependency_error(err):
        return REASON_DEPENDENCY_MISSING, dependency_detail(err)
    return REASON_BACKEND_REJECTED, rejection_detail(err)


def systemic_errors(errors) -> list[dict]:
    """Filtra de ``errors[]`` los que son de infraestructura."""
    if not isinstance(errors, list):
        return []
    return [err for err in errors if is_systemic_error(err)]
