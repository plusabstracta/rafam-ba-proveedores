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
