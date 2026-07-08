"""lookups.py â ResoluciÃ³n de catÃ¡logos remotos Paxapos para mapping.

Centraliza la lÃ³gica que antes estaba dispersa en MigratorExporter para
resolver IDs de Paxapos a partir de cÃ³digos RAFAM: tipos de factura,
tipos de pago, tipos de retenciÃ³n, unidades de medida y centros de costo.
"""

from __future__ import annotations

import logging
import os

from ..gateway_mapper import (
    RAFAM_TIPO_CANCE_DEFAULT_PAGO_ID,
    RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_ID,
    RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_NAME,
    RAFAM_TIPO_COMPROB_DEFAULT_ID,
    RAFAM_TIPO_COMPROB_TO_PAXAPOS_ID,
    _UM_DEFAULT,
    resolve_centro_costo_id,
)
from ..utils import build_single_index, lookup_list, normalize_text, to_int

logger = logging.getLogger(__name__)


class LookupResolver:
    """Resuelve IDs de catÃ¡logos Paxapos a partir de cÃ³digos RAFAM.

    Se construye una vez con el payload de lookups del migrator y se
    reutiliza en todos los mappers de la corrida.
    """

    def __init__(self, lookup_payload: dict):
        # Tipos de factura
        self._tipos_factura = lookup_list(lookup_payload, "tipos_factura")
        self._tipos_factura_by_codename = build_single_index(self._tipos_factura, "codename")
        self._tipos_factura_by_name = build_single_index(self._tipos_factura, "name")
        self._default_tipo_factura_id = to_int(os.getenv("PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID"))

        # Tipos de pago
        self._tipos_de_pago = lookup_list(lookup_payload, "tipos_de_pago")
        self._tipos_de_pago_by_name = build_single_index(self._tipos_de_pago, "name")
        self._default_tipo_pago_id = to_int(os.getenv("PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID")) or 1

        # Tipos de retenciÃ³n
        self._tipos_retencion = lookup_list(lookup_payload, "tipos_retencion")
        self._tipos_retencion_by_codigo = build_single_index(self._tipos_retencion, "codigo")
        self._tipos_retencion_by_codename = build_single_index(self._tipos_retencion, "codename")
        self._tipos_retencion_by_name = build_single_index(self._tipos_retencion, "name")

    # ââ Tipo Factura ââââââââââââââââââââââââââââââââââââââââââââââââââââââ

    def resolve_tipo_factura_id(self, tipo_doc) -> int | None:
        """Mapea un cÃ³digo RAFAM CTA_COMPROB.TIPO al tipo_factura.id de Paxapos.

        Estrategia:
        1) Mapping directo a ID via RAFAM_TIPO_COMPROB_TO_PAXAPOS_ID (fuente de verdad).
        2) Fallback a lookup por codename/name del tenant.
        3) Default fijo o env override.
        """
        if tipo_doc:
            code = str(tipo_doc).strip().upper()
            mapped_id = RAFAM_TIPO_COMPROB_TO_PAXAPOS_ID.get(code)
            if mapped_id is not None:
                return mapped_id
            # Fallback: lookup en catalogo del tenant por codename / name
            text = normalize_text(tipo_doc)
            by_codename = self._tipos_factura_by_codename.get(text)
            if by_codename and to_int(by_codename.get("id")) is not None:
                return int(by_codename.get("id"))
            by_name = self._tipos_factura_by_name.get(text)
            if by_name and to_int(by_name.get("id")) is not None:
                return int(by_name.get("id"))
            # Default mapper si nada matchea
            if self._default_tipo_factura_id is not None:
                return self._default_tipo_factura_id
            return RAFAM_TIPO_COMPROB_DEFAULT_ID
        return self._default_tipo_factura_id

    # ââ Tipo Pago âââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

    def resolve_tipo_pago_id(self, raw: dict | None = None) -> int:
        """Mapea ORDEN_PAGO.TIPO_CANCE al tipo_de_pago.id de Paxapos."""
        if raw:
            raw_tipo_cance = ""
            for key, value in raw.items():
                key_name = str(key).rsplit(".", 1)[-1].upper()
                if key_name == "TIPO_CANCE":
                    raw_tipo_cance = value
                    break
            tipo_cance = str(raw_tipo_cance).strip().upper()
            mapped_name = RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_NAME.get(tipo_cance)
            by_name = self._tipos_de_pago_by_name.get(normalize_text(mapped_name))
            if by_name and to_int(by_name.get("id")) is not None:
                return int(by_name.get("id"))
            mapped_id = RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_ID.get(tipo_cance)
            if mapped_id is not None:
                return mapped_id
            return RAFAM_TIPO_CANCE_DEFAULT_PAGO_ID
        return self._default_tipo_pago_id

    # ââ Tipo RetenciÃ³n ââââââââââââââââââââââââââââââââââââââââââââââââââââ

    @property
    def tipos_retencion(self) -> list[dict]:
        """Catalogo de tipos de retenciÃ³n para contadores de skip."""
        return self._tipos_retencion

    def resolve_tipo_retencion_id(self, cod_ret, descripcion) -> int | None:
        """Resuelve tipo_impuesto_id por codigo y/o descripcion."""
        cod_text = str(cod_ret).strip() if cod_ret is not None else ""
        for value, index in (
            (cod_text, self._tipos_retencion_by_codigo),
            (cod_text, self._tipos_retencion_by_codename),
            (descripcion, self._tipos_retencion_by_name),
        ):
            text = normalize_text(value)
            if not text:
                continue
            row = index.get(text)
            if row and to_int(row.get("id")) is not None:
                return int(row.get("id"))
        return None

    def resolve_tipo_retencion_id_by_alias(self, alias: str) -> int | None:
        """Busca tipo_impuesto en lookups por alias normalizado."""
        if not alias or not self._tipos_retencion:
            return None
        target_tokens = {
            "ganancias": ("ganancia",),
            "iibb": ("iibb", "ingresos brutos", "ingreso bruto"),
            "suss": ("suss", "seguridad social"),
            "iva": ("iva",),
        }.get(alias, (alias,))

        for tr in self._tipos_retencion:
            name_norm = normalize_text(tr.get("name") or "")
            if not name_norm:
                continue
            for tok in target_tokens:
                if normalize_text(tok) in name_norm:
                    tid = to_int(tr.get("id"))
                    if tid is not None:
                        return tid
        return None

    # ââ Centro de Costo âââââââââââââââââââââââââââââââââââââââââââââââââââ

    @staticmethod
    def resolve_centro_costo_id(jurisdiccion) -> int | None:
        """Mapea JURISDICCION RAFAM a CentroCosto.id Paxapos."""
        if jurisdiccion is None:
            return None
        text = str(jurisdiccion).strip()
        if not text:
            return None
        return resolve_centro_costo_id(text)

    # ââ Unidad de Medida ââââââââââââââââââââââââââââââââââââââââââââââââââ

    @staticmethod
    def resolve_unidad_medida_id(raw: dict) -> int:
        """RAFAM no expone catÃ¡logo de unidades mapeable 1:1 con Paxapos."""
        return _UM_DEFAULT

    # ââ RetenciÃ³n alias âââââââââââââââââââââââââââââââââââââââââââââââââââ

    @staticmethod
    def retencion_alias(value) -> str | None:
        """Clasifica una descripciÃ³n de retenciÃ³n en un alias canÃ³nico."""
        text = normalize_text(value)
        if not text:
            return None
        if "ganancia" in text:
            return "ganancias"
        if "iibb" in text or ("ingreso" in text and "bruto" in text):
            return "iibb"
        if "suss" in text or "seguridad social" in text or "jubil" in text:
            return "suss"
        if "iva" in text:
            return "iva"
        return None
