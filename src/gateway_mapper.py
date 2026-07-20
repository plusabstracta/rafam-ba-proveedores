import re
from typing import Any


# Mapeo RAFAM PROVEEDORES.COD_IVA -> Paxapos iva_responsabilidades.id
# Catalogo Paxapos (tabla iva_responsabilidades):
#   1 I "Resp. Inscripto"
#   2 E "Exento"
#   3 A "No Responsable"
#   4 C "Consumidor Final"
#   5 T "No Categorizado"
#   6 M "Responsable Monotributo"
_IVA_MAP = {
    "RINS":  1,  # Responsable Inscripto
    "EXEN":  2,  # Exento
    "NGAN":  3,  # No alcanzado / No responsable
    "CF":    4,  # Consumidor Final
    "RNI":   5,  # Responsable No Inscripto (figura derogada) -> No Categorizado
    "RNIS":  5,  # idem alias
    "MONOT": 6,  # Monotributista
    "M.SOC": 6,  # Monotributo Social -> mismo cubo Monotributo
    "MSOC":  6,  # alias sin punto
}

# Mapeo RAFAM JURISDICCION → Paxapos CentroCosto.id
# CentroCosto 8 ("Otro") es el fallback para jurisdicciones no mapeadas.
_JURISDICCION_CENTRO_COSTO_MAP: dict[str, int] = {
    # CentroCosto 7 — Administrativo - General
    "1110101000": 7,   # Intendencia
    "1110102000": 7,   # Secretaria de Gobierno
    "1110200000": 7,   # H.C.D.
    "1110112000": 7,   # Secretaria de Hacienda
    "1110115000": 7,   # Secretaria de Coordinación
    "1110117000": 7,   # Secretaria Legal, Técnica y Administrativa
    "1110105000": 7,   # Secretaría de Cultura y Educación
    "1110108000": 7,   # Secretaria de Producción
    "1110109000": 7,   # Secretaria de Deportes
    # CentroCosto 6 — CASER
    "1110111000": 6,   # Sec. de Obras y Serv. Públicos (CASER)
    # CentroCosto 5 — Seguridad
    "1110113000": 5,   # Sec. de Políticas de Prevención de la Seguridad
    # CentroCosto 4 — Corralón (Mantenimiento)
    "1110118000": 4,   # Secretaria de Servicios Generales y Mantenimiento
    # CentroCosto 3 — Desarrollo
    "1110106000": 3,   # Secretaría de Desarrollo Social
    # CentroCosto 2 — Obras Públicas
    "1110103000": 2,   # Secretaria de Obras y Servicios Públicos
    # CentroCosto 1 — Salud
    "1110104000": 1,   # Secretaria de Salud
}
_JURISDICCION_CENTRO_COSTO_DEFAULT = 8  # CentroCosto "Otro"

_UM: dict[str, int] = {
    "UNIDAD": 5,
    "KILOGRAMO": 3,   # Kilo
    "LITRO": 20,
    "METRO": 5,       # no hay equivalente directo, fallback a Unidad
    "PAQUETE": 11,    # Pack
    "HORAS": 5,       # no hay UM "hora", fallback a Unidad
    "DIA": 5,         # idem
}
_UM_DEFAULT = 5  # Unidad (id 5 en compras_unidad_de_medidas)

# Mapeo RAFAM CTA_COMPROB.TIPO -> Paxapos tipo_factura.id (tabla risto_tenant.tipo_facturas)
# Catalogo Paxapos:
#   1=A, 2=B, 3=X, 4=M, 5=C, 6=Vale, 7=Otros
#   8=NCB, 9=NCC, 10=NCA, 11=NDB, 12=NDC, 13=NDA, 14=NCM
RAFAM_TIPO_COMPROB_TO_PAXAPOS_ID: dict[str, int] = {
    # Facturas
    "FAA": 1,    # Factura A
    "FAS": 1,    # Factura A (alias suplente)
    "FAB": 2,    # Factura B
    "FAC": 5,    # Factura C
    "FAM": 4,    # Factura M
    "REA": 1,    # Recibo A
    "REB": 2,    # Recibo B
    "EXB": 2,    # Exento B
    # Notas de credito / debito
    "NCA": 10,
    "NCB": 8,
    "NCC": 9,
    "NCM": 14,
    "NDA": 13,
    "NDB": 11,
    "NDC": 12,
    # Otros (cae en "Otros" id=7)
    "TKT": 7,
    "LIQ": 7,
    "COM": 7,
    "VIA": 7,
    "REC": 7,
    "CEO": 7,
    "LIR": 7,
}
RAFAM_TIPO_COMPROB_DEFAULT_ID = 7  # "Otros"



# IDs canonicos de tipo_de_pagos para ORIGEN_TIPO.
RAFAM_ORIGEN_TIPO_TO_PAXAPOS_PAGO_ID: dict[str, int] = {
    "CA": 9,   # Cheque al dia
    "CM": 9,   # Cheque manual / diferido
    "NO": 1,   # Transferencia bancaria
}
# Default para ORIGEN_TIPO no mapeado (IN, EB, OB, EFP, INT, BSF, etc.) o ausente.
RAFAM_ORIGEN_TIPO_DEFAULT_PAGO_ID = 10  # "Otros"


def resolve_centro_costo_id(jurisdiccion: Any) -> int:
    """Devuelve el CentroCosto.id de Paxapos para una jurisdicción RAFAM."""
    if jurisdiccion is None:
        return _JURISDICCION_CENTRO_COSTO_DEFAULT
    key = str(jurisdiccion).strip()
    return _JURISDICCION_CENTRO_COSTO_MAP.get(key, _JURISDICCION_CENTRO_COSTO_DEFAULT)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _clean(value)
        if text:
            return text
    return None


def _normalize_cuit(cuit: Any) -> str | None:
    text = _clean(cuit)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) != 11:
        return None
    return digits


def _join_address(street: Any, number: Any) -> str | None:
    s = _clean(street)
    n = _clean(number)
    if s and n:
        return f"{s} {n}"
    return s or n


def _build_phone(pais: Any, inte: Any, tele: Any) -> str | None:
    """Concatena los tres campos de teléfono RAFAM en un único string."""
    parts = [_clean(pais), _clean(inte), _clean(tele)]
    non_empty = [p for p in parts if p]
    if not non_empty:
        return None
    return " ".join(non_empty)


def map_proveedor_row(raw: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """Map a RAFAM proveedor row to CakePHP Proveedor payload.

    Output format is ready for Account/ProveedoresController::add:
        {"Proveedor": {...}}
    """
    name = _first_non_empty(raw.get("FANTASIA"), raw.get("RAZON_SOCIAL"))
    if not name:
        return None

    cuit = _normalize_cuit(raw.get("CUIT"))
    iva_code = (_clean(raw.get("COD_IVA")) or "").upper()

    domicilio = _join_address(raw.get("CALLE_LEGAL"), raw.get("NRO_LEGAL"))
    if not domicilio:
        domicilio = _join_address(raw.get("CALLE_POSTAL"), raw.get("NRO_POSTAL"))

    telefono = _first_non_empty(
        _build_phone(raw.get("NRO_PAIS_TE1"), raw.get("NRO_INTE_TE1"), raw.get("NRO_TELE_TE1")),
        _build_phone(raw.get("NRO_PAIS_TE2"), raw.get("NRO_INTE_TE2"), raw.get("NRO_TELE_TE2")),
        _build_phone(raw.get("NRO_PAIS_TE3"), raw.get("NRO_INTE_TE3"), raw.get("NRO_TELE_TE3")),
        raw.get("TE_CELULAR"),
    )

    razon_social = _clean(raw.get("RAZON_SOCIAL"))

    data: dict[str, Any] = {
        "name": name[:100],
        "razon_social": razon_social[:200] if razon_social else None,
        "mail": (_clean(raw.get("EMAIL")) or "")[:100] or None,
        "telefono": (telefono or "")[:100] or None,
        "domicilio": (domicilio or "")[:100] or None,
        "localidad": (_first_non_empty(raw.get("LOCA_LEGAL"), raw.get("LOCA_POSTAL")) or "")[:100] or None,
        "provincia": (_first_non_empty(raw.get("PROV_LEGAL"), raw.get("PROV_POSTAL")) or "")[:100] or None,
        "codigo_postal": (_first_non_empty(raw.get("COD_LEGAL"), raw.get("COD_POSTAL")) or "")[:10] or None,
        "cuit": cuit,
        "tipo_documento_id": 1 if cuit else None,  # TIPO_DOCUMENTO_CUIT
        "iva_condicion_id": _IVA_MAP.get(iva_code),
    }

    compact = {k: v for k, v in data.items() if v not in (None, "")}
    return {"Proveedor": compact}


def map_proveedor_migrator_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    proveedor_payload = map_proveedor_row(raw)
    if not proveedor_payload:
        return None

    cod_prov = raw.get("COD_PROV")
    if cod_prov is None:
        return None

    # Blocklist: proveedores tecnicos/servicios/caja chica que NO deben migrar.
    from .config import is_cod_prov_excluded
    if is_cod_prov_excluded(cod_prov):
        return None

    return {
        "external_id": {"cod_prov": int(cod_prov)},
        "Proveedor": proveedor_payload["Proveedor"],
    }
