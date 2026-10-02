"""retry_labels.py — Etiquetas legibles para las claves de retry_queue (F1).

`retry_store`/`exporter._outcome_key` guardan la clave de negocio como JSON
compacto (o el COD_PROV crudo para proveedores) — comodo para programas,
ilegible para un operador que necesita saber, a simple vista, de que OC, OP,
retencion, gasto, clasificacion o proveedor se trata. Este modulo traduce esa
clave al mismo vocabulario que usa RAFAM (ejercicio-numero), y lo reusan los
logs (`WARNING` al encolar), el mail diario y `main.py retry-queue`.

Tolerante por diseno: una forma de clave desconocida (entidad nueva, cambio de
contrato) nunca rompe el log/mail — cae a mostrar el JSON/valor crudo.
"""

from __future__ import annotations

import json


def describe_retry_key(entity: str, external_id: str) -> str:
    """Devuelve un label legible para una clave de retry_queue.

    ``entity`` es el nombre de entidad tal como se guarda en retry_queue
    (puede diferir de la entidad CLI que disparo el batch, ej. "solic_gastos"
    para gastos embebidos en el payload de orden_pago). ``external_id`` es el
    valor crudo de la columna ``external_id`` de retry_queue.
    """
    if external_id is None:
        return f"{entity} <sin identificador>"

    data = None
    try:
        data = json.loads(external_id)
    except (TypeError, ValueError):
        data = None

    if isinstance(data, dict):
        ejercicio = data.get("ejercicio")
        if "uni_compra" in data and "nro_oc" in data:
            return f"OC {ejercicio}-{data.get('uni_compra')}-{data.get('nro_oc')}"
        if "nro_op" in data:
            prefix = "Retencion de OP" if entity == "retenciones" else "OP"
            return f"{prefix} {ejercicio}-{data.get('nro_op')}"
        if "deleg_solic" in data and "nro_solic" in data:
            return f"Gasto/Solicitud {ejercicio}-{data.get('deleg_solic')}-{data.get('nro_solic')}"
        if "codigo" in data:
            return f"Clasificacion {data.get('codigo')}"
        if "cod_prov" in data:
            return f"Proveedor COD_PROV={data.get('cod_prov')}"
        # Forma desconocida (contrato nuevo/entidad futura): mostrar el JSON
        # crudo es mejor que ocultar la clave.
        return f"{entity} {json.dumps(data, sort_keys=True, ensure_ascii=False)}"

    # No es JSON: hoy solo proveedores usa external_id plano (str(COD_PROV)).
    if entity == "proveedores":
        return f"Proveedor COD_PROV={external_id}"
    return f"{entity} {external_id}"


# ── Clave canonica de registro (resend) ──────────────────────────────────────
#
# `main.py resend` necesita ir y volver entre tres representaciones de la misma
# clave de negocio: lo que tipea/pega el operador (label del mail, "2026-3-1023",
# JSON crudo de la cola), la fila de RAFAM y el external_id que devuelve
# Paxapos. `record_base_key` es el punto de encuentro: el mismo formato que
# usa retry_queue, sin campos extra (las SG multi-comprobante agregan
# `nro_comprob` al external_id, pero el registro RAFAM es la solicitud).

# Campos de la clave por entidad (nombre en el JSON de la cola).
_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "oc_items": ("ejercicio", "uni_compra", "nro_oc"),
    "orden_pago": ("ejercicio", "nro_op"),
    "retenciones": ("ejercicio", "nro_op"),
    "solic_gastos": ("ejercicio", "deleg_solic", "nro_solic"),
    "proveedores": ("cod_prov",),
}

# Columnas RAFAM equivalentes, en el mismo orden que _KEY_FIELDS.
_ROW_COLUMNS: dict[str, tuple[str, ...]] = {
    "oc_items": ("EJERCICIO", "UNI_COMPRA", "NRO_OC"),
    "orden_pago": ("EJERCICIO", "NRO_OP"),
    "retenciones": ("EJERCICIO", "NRO_OP"),
    "solic_gastos": ("EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC"),
    "proveedores": ("COD_PROV",),
}

# Prefijos de `describe_retry_key`, para aceptar el label pegado del mail.
# Ordenados del mas largo al mas corto ("Retencion de OP" antes que "OP").
_LABEL_PREFIXES = (
    "proveedor cod_prov=",
    "retencion de op ",
    "gasto/solicitud ",
    "proveedor ",
    "oc ",
    "op ",
)

RESENDABLE_ENTITIES = tuple(_KEY_FIELDS)


def _key_example(entity: str) -> str:
    return {
        "oc_items": "2026-3-1023 (ejercicio-uni_compra-nro_oc) o 'OC 2026-3-1023'",
        "orden_pago": "2026-1023 (ejercicio-nro_op) o 'OP 2026-1023'",
        "retenciones": "2026-1023 (ejercicio-nro_op) o 'Retencion de OP 2026-1023'",
        "solic_gastos": "2026-1-58 (ejercicio-deleg_solic-nro_solic) o 'Gasto/Solicitud 2026-1-58'",
        "proveedores": "1234 (COD_PROV) o 'Proveedor COD_PROV=1234'",
    }.get(entity, "?")


def _to_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None
    return int(as_float) if as_float.is_integer() else None


def _compose(entity: str, values) -> str | None:
    fields = _KEY_FIELDS.get(entity)
    if fields is None or len(values) != len(fields):
        return None
    ints = [_to_int(v) for v in values]
    if any(v is None for v in ints):
        return None
    if entity == "proveedores":
        return str(ints[0])
    return json.dumps(dict(zip(fields, ints)), sort_keys=True)


def record_base_key(entity: str, external_id) -> str | None:
    """Normaliza un external_id (str de la cola o dict de Paxapos) a la clave base.

    Devuelve None si no tiene los campos de la entidad.
    """
    fields = _KEY_FIELDS.get(entity)
    if fields is None or external_id is None:
        return None
    data = external_id
    if not isinstance(data, dict):
        text = str(external_id).strip()
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            data = None
        if not isinstance(data, dict):
            # Forma plana: solo proveedores guarda el COD_PROV crudo.
            return _compose(entity, [text]) if entity == "proveedores" else None
    if not all(f in data for f in fields):
        return None
    return _compose(entity, [data[f] for f in fields])


def row_key_fn(entity: str, columns: list[str]):
    """Funcion fila (tupla) -> clave base, con los indices de columna resueltos
    una sola vez. Equivale a `record_key_from_row` sin armar un dict por fila
    (oc_items relee todos los items en cada corrida). None si la entidad o las
    columnas no alcanzan para armar la clave."""
    cols = _ROW_COLUMNS.get(entity)
    if cols is None:
        return None
    index = {str(c).upper(): i for i, c in enumerate(columns)}
    positions = [index.get(c) for c in cols]
    if any(p is None for p in positions):
        return lambda row: None
    return lambda row: _compose(entity, [row[p] for p in positions])


def record_key_from_row(entity: str, raw: dict) -> str | None:
    """Clave base desde una fila RAFAM (dict columna -> valor)."""
    cols = _ROW_COLUMNS.get(entity)
    if cols is None:
        return None
    upper = {str(k).upper(): v for k, v in raw.items()}
    return _compose(entity, [upper.get(c) for c in cols])


def parse_record_key(entity: str, text: str) -> str:
    """Interpreta lo que escribe el operador y devuelve la clave base.

    Acepta la forma corta ("2026-3-1023"), el label del mail ("OC 2026-3-1023")
    o el JSON crudo de `retry-queue`. Lanza ValueError si no se puede.
    """
    if entity not in _KEY_FIELDS:
        raise ValueError(f"La entidad {entity!r} no admite reenvio puntual")
    original = text
    value = str(text or "").strip()
    if not value:
        raise ValueError("Clave vacia")

    if value.startswith("{"):
        key = record_base_key(entity, value)
        if key is None:
            raise ValueError(
                f"JSON {original!r} no tiene los campos de {entity}: "
                f"{', '.join(_KEY_FIELDS[entity])}"
            )
        return key

    lowered = value.lower()
    for prefix in _LABEL_PREFIXES:
        if lowered.startswith(prefix):
            value = value[len(prefix):].strip()
            break

    parts = [p.strip() for p in value.replace("/", "-").split("-")]
    key = _compose(entity, parts)
    if key is None:
        raise ValueError(
            f"Clave {original!r} invalida para {entity}; formato esperado: {_key_example(entity)}"
        )
    return key
