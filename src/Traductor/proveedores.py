from datetime import date, datetime
import re
from typing import Any

from .base import BaseTranslator


class ProveedoresTranslator(BaseTranslator):
    """Translate RAFAM PROVEEDORES rows into Paxapos supplier payloads.

    Field mapping reference (schema confirmed 2026-03-17):
        RAFAM            → Paxapos
        CUIT             → cuit
        RAZON_SOCIAL     → name
        EMAIL            → mail
        COD_POSTAL       → codigo_postal
        FECHA_ALTA       → created
        CALLE_POSTAL +   → domicilio
          NRO_POSTAL
        NRO_TELE_TE1 +   → telefono   (fallback: TE_CELULAR)
          NRO_PAIS_TE1 +
          NRO_INTE_TE1
        derived          → name_cuit  (RAZON_SOCIAL + " - " + CUIT)
        hardcoded        → tipo_documento_id = 1 (RAFAM solo maneja CUIT)

    Not available in RAFAM: iva_condicion_id, localidad, provincia, cbu,
    cbu_alias, modified, created_by, deleted_date.
    """

    endpoint_path = "account/proveedores/add"

    # RAFAM stores only CUIT as document identifier → Paxapos dropdown ID = 1
    _TIPO_DOCUMENTO_CUIT = 1

    def translate(self, columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
        raw = {k.upper(): v for k, v in self._row_to_raw(columns, row).items()}

        payload: dict[str, Any] = {}

        # CUIT — NOT NULL in RAFAM, VARCHAR2(13).
        # Paxapos expects digits only (no hyphens or separators).
        cuit = raw.get("CUIT")
        if cuit not in (None, ""):
            cuit_normalizado = self._normalize_cuit(str(cuit))
            if cuit_normalizado:
                payload["cuit"] = cuit_normalizado

        # name — NOT NULL in RAFAM, VARCHAR2(70)
        razon_social = raw.get("RAZON_SOCIAL")
        if razon_social is not None:
            name = str(razon_social).strip()
            if name:
                payload["name"] = name

        # tipo_documento_id — always 1 because RAFAM only uses CUIT
        payload["tipo_documento_id"] = self._TIPO_DOCUMENTO_CUIT

        # name_cuit — derived: shown in Paxapos lists as "<name> - <cuit>"
        if "name" in payload and "cuit" in payload:
            payload["name_cuit"] = f"{payload['name']} - {payload['cuit']}"

        # mail — nullable in RAFAM, VARCHAR2(50)
        email = raw.get("EMAIL")
        if email not in (None, ""):
            payload["mail"] = str(email).strip()

        # telefono — assembled from fragmented TE1 fields, fallback to mobile
        telefono = self._build_telefono(raw)
        if telefono:
            payload["telefono"] = telefono

        # domicilio — CALLE_POSTAL + NRO_POSTAL
        domicilio = self._build_domicilio(raw)
        if domicilio:
            payload["domicilio"] = domicilio

        # codigo_postal — NOT NULL in RAFAM, VARCHAR2(8)
        cod_postal = raw.get("COD_POSTAL")
        if cod_postal not in (None, ""):
            payload["codigo_postal"] = str(cod_postal).strip()

        # created — FECHA_ALTA NOT NULL DATE in RAFAM
        fecha_alta = raw.get("FECHA_ALTA")
        if fecha_alta is not None:
            payload["created"] = self._format_date(fecha_alta)

        # Fields Paxapos expects but RAFAM PROVEEDORES does not store → explicit null
        payload.setdefault("iva_condicion_id", None)  # COD_IVA is a code, not a Paxapos ID
        payload.setdefault("localidad", None)          # LOCA_POSTAL is a FK code, not the name
        payload.setdefault("provincia", None)          # PROV_POSTAL is a FK code, not the name
        payload.setdefault("cbu", None)
        payload.setdefault("cbu_alias", None)
        payload.setdefault("modified", None)           # no FECHA_MODIFICACION in RAFAM
        payload.setdefault("created_by", None)
        payload.setdefault("deleted_date", None)

        return payload

    # ─── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _build_telefono(raw: dict[str, Any]) -> str | None:
        """Assemble phone from RAFAM TE1 fragment fields; fallback to TE_CELULAR."""
        nro_tele = raw.get("NRO_TELE_TE1")
        if nro_tele not in (None, ""):
            parts = []
            pais = raw.get("NRO_PAIS_TE1")
            inte = raw.get("NRO_INTE_TE1")
            if pais not in (None, ""):
                parts.append(f"+{str(pais).strip()}")
            if inte not in (None, ""):
                parts.append(str(inte).strip())
            parts.append(str(nro_tele).strip())
            return " ".join(parts)

        celular = raw.get("TE_CELULAR")
        if celular not in (None, ""):
            return str(celular).strip()

        return None

    @staticmethod
    def _build_domicilio(raw: dict[str, Any]) -> str | None:
        """Assemble street address from CALLE_POSTAL and NRO_POSTAL."""
        calle = raw.get("CALLE_POSTAL")
        if calle in (None, ""):
            return None
        parts = [str(calle).strip()]
        nro = raw.get("NRO_POSTAL")
        if nro not in (None, ""):
            parts.append(str(nro).strip())
        return " ".join(parts)

    @staticmethod
    def _format_date(value: Any) -> str | None:
        """Convert Oracle DATE / Python datetime to ISO 8601 date string."""
        if isinstance(value, (datetime, date)):
            return value.strftime("%Y-%m-%d")
        return str(value) if value is not None else None

    @staticmethod
    def _normalize_cuit(value: str) -> str:
        """Keep only CUIT digits, stripping hyphens/spaces/other separators."""
        return re.sub(r"\D", "", value or "")
