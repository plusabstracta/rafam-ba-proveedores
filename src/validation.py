"""validation.py — Validacion de boundary previa al envio a Paxapos (F0).

Centraliza los controles que evitan mandar datos invalidos al receptor CakePHP
y que el fallo se detecte recien en el servidor. Cada funcion retorna un
``FieldResult`` con el valor saneado o un motivo de rechazo; las filas con
rechazo no rompen el batch — el caller las deriva a la retry_queue.

Controles cubiertos:
  - Importes DECIMAL(14,2): tope de rango y escala (overflow → rechazo, no clamp
    silencioso de magnitud incorrecta).
  - Negativos no permitidos en montos que deben ser >= 0 (totales, retenciones).
  - Presencia de FKs obligatorias (proveedor_id, pedido_id, etc.).
  - Fechas en formato YYYY-MM-DD.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional

# DECIMAL(14,2): 14 digitos significativos en total, 2 de escala.
# → 12 digitos enteros + 2 decimales. Maximo absoluto representable.
DECIMAL_MAX_DIGITS = 14
DECIMAL_SCALE = 2
DECIMAL_MAX_ABS = Decimal("9" * (DECIMAL_MAX_DIGITS - DECIMAL_SCALE) + "." + "9" * DECIMAL_SCALE)
_TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class FieldResult:
    """Resultado de validar un campo.

    - ok=True  → ``value`` contiene el valor saneado listo para enviar.
    - ok=False → ``reason`` explica por que se rechaza (va al error_message
      de la retry_queue).
    """

    ok: bool
    value: Any = None
    reason: Optional[str] = None

    @classmethod
    def accept(cls, value: Any) -> "FieldResult":
        return cls(ok=True, value=value)

    @classmethod
    def reject(cls, reason: str) -> "FieldResult":
        return cls(ok=False, reason=reason)


def validate_amount(
    raw: Any,
    *,
    field: str = "importe",
    allow_negative: bool = False,
    allow_zero: bool = True,
    required: bool = True,
) -> FieldResult:
    """Valida un importe contra el rango DECIMAL(14,2) de Paxapos.

    - Rechaza si excede el rango (overflow) en vez de truncar magnitud.
    - Rechaza negativos salvo ``allow_negative``.
    - Rechaza cero salvo ``allow_zero``.
    - Si no es requerido y viene vacio/None, acepta con value=None.
    Devuelve el valor redondeado a 2 decimales (float) listo para JSON.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if required:
            return FieldResult.reject(f"{field}: requerido y vacio")
        return FieldResult.accept(None)

    try:
        dec = Decimal(str(raw).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return FieldResult.reject(f"{field}: no parseable como numero ({raw!r})")

    if dec.is_nan() or dec.is_infinite():
        return FieldResult.reject(f"{field}: valor no finito ({raw!r})")

    dec = dec.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    if not allow_negative and dec < 0:
        return FieldResult.reject(f"{field}: negativo no permitido ({dec})")

    if not allow_zero and dec == 0:
        return FieldResult.reject(f"{field}: cero no permitido")

    if dec.copy_abs() > DECIMAL_MAX_ABS:
        return FieldResult.reject(
            f"{field}: excede DECIMAL({DECIMAL_MAX_DIGITS},{DECIMAL_SCALE}) "
            f"(|{dec}| > {DECIMAL_MAX_ABS})"
        )

    return FieldResult.accept(float(dec))


def validate_required_fk(raw: Any, *, field: str) -> FieldResult:
    """Valida la presencia de una FK obligatoria (proveedor_id, pedido_id, ...).

    Acepta enteros positivos o strings numericas; rechaza None/vacio/<=0.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return FieldResult.reject(f"{field}: FK obligatoria ausente")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return FieldResult.reject(f"{field}: FK no numerica ({raw!r})")
    if value <= 0:
        return FieldResult.reject(f"{field}: FK invalida ({value})")
    return FieldResult.accept(value)


def validate_date_only(raw: Any, *, field: str = "fecha", required: bool = True) -> FieldResult:
    """Normaliza una fecha a 'YYYY-MM-DD'. Acepta date/datetime o string ISO.

    Rechaza formatos no reconocibles en vez de mandar una cadena vacia que el
    receptor terminaria rechazando.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if required:
            return FieldResult.reject(f"{field}: fecha requerida ausente")
        return FieldResult.accept(None)

    if isinstance(raw, datetime):
        return FieldResult.accept(raw.date().isoformat())
    if isinstance(raw, date):
        return FieldResult.accept(raw.isoformat())

    text = str(raw).strip()
    # Tomar solo la parte de fecha si viene con tiempo ('2026-01-15 00:00:00').
    candidate = text.split("T")[0].split(" ")[0]
    try:
        parsed = datetime.strptime(candidate, "%Y-%m-%d").date()
    except ValueError:
        return FieldResult.reject(f"{field}: formato de fecha invalido ({raw!r}), se espera YYYY-MM-DD")
    return FieldResult.accept(parsed.isoformat())
