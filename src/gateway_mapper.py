import re
from typing import Any


_IVA_MAP = {
    "RINS": 1,   # Responsable Inscripto
    "MONOT": 2,  # Monotributista
    "EXEN": 3,   # Exento
    "CF": 4,     # Consumidor final
    "NGAN": 5,   # No responsable
    "RNI": 6,    # Responsable no inscripto
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

    data: dict[str, Any] = {
        "name": name[:100],
        "razon_social": _clean(raw.get("RAZON_SOCIAL")),
        "mail": _clean(raw.get("EMAIL")),
        "telefono": telefono,
        "domicilio": domicilio,
        "localidad": _first_non_empty(raw.get("LOCA_LEGAL"), raw.get("LOCA_POSTAL")),
        "provincia": _first_non_empty(raw.get("PROV_LEGAL"), raw.get("PROV_POSTAL")),
        "codigo_postal": _first_non_empty(raw.get("COD_LEGAL"), raw.get("COD_POSTAL")),
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

    return {
        "external_id": {"cod_prov": int(cod_prov)},
        "Proveedor": proveedor_payload["Proveedor"],
    }
