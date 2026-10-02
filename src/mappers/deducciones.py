"""deducciones.py - Deducciones NO impositivas de ORDEN_PAGO_DEDUC (paxapos/paxapos#738).

RAFAM aplica al pagar deducciones que no son retencion fiscal
(``DEDUCCIONES.TIPO_DEDUC = 'O'``): en Madariaga, Garantia (cod 4) y Caja de
Medicos (cod 8). Paxapos las guarda en ``account_retenciones`` con la marca
``no_impositiva``: restan de ``neto_transferido``, se muestran con su nombre y no
llevan certificado ni entran al libro de retenciones.

Este helper lo comparten ``OrdenPagoMapper`` (retenciones embebidas en
``ordenes_pago``) y ``RetencionesMapper`` (pasada F3 standalone), para que las dos
rutas manden exactamente la misma forma.
"""

from __future__ import annotations

from ..config import non_tax_deduction_concept
from ..validation import validate_amount


def map_non_tax_deduction(
    ded: dict,
    *,
    cod_text: str,
    monto_retenido: float,
    descripcion: str,
    ejercicio: int,
    nro_op: int,
) -> dict | None:
    """Arma la retencion no impositiva, o None si esta deduccion no esta mapeada.

    Solo se manda lo que el operador mapeo (``RAFAM_NON_TAX_DEDUCTION_MAP``, por
    default cod 4 y 8) y que RAFAM no marca como impositiva ('I'). Cualquier otra
    ('O' sin mapeo: IPS, IOMA, sindicatos, embargos...) devuelve None y sigue el
    camino de siempre (omitida y encolada como ``non_tax_deduction``).
    """
    concepto = non_tax_deduction_concept(cod_text, ded.get("tipo_deduc"))
    if concepto is None:
        return None

    retencion: dict = {
        "external_id": {
            "ejercicio": ejercicio,
            "nro_op": nro_op,
            "codigo_deduc": cod_text,
        },
        # Sin tipo_impuesto_id ni numero_certificado: no es una retencion fiscal.
        "no_impositiva": True,
        "codigo_externo": cod_text,
        "concepto": concepto,
        "monto_retenido": monto_retenido,
    }

    alicuota = ded.get("alicuota")
    if alicuota is not None:
        res_alicuota = validate_amount(
            alicuota,
            field="alicuota",
            allow_zero=False,
            allow_negative=False,
            required=False,
        )
        if res_alicuota.ok and res_alicuota.value is not None:
            retencion["alicuota"] = res_alicuota.value

    if descripcion:
        retencion["observacion"] = f"Deduccion RAFAM {descripcion} OP {ejercicio}/{nro_op}"

    return retencion
