"""solic_gastos.py â Mapper para entidad SOLIC_GASTOS (facturas/gastos).

Transforma filas crudas de RAFAM SOLIC_GASTOS + CTA_COMPROB al formato
del migrator Paxapos y persiste entity links a partir de la respuesta.
"""

from __future__ import annotations

import json
import logging

from ..utils import format_date_only, parse_money, to_int

logger = logging.getLogger(__name__)


class SolicGastosMapper:
    """Mapper para gastos de solicitud (SOLIC_GASTOS + CTA_COMPROB)."""

    def __init__(self, *, link_store, lookup_resolver):
        self._link_store = link_store
        self._lookup = lookup_resolver

    def build_payload(
        self,
        columns: list[str],
        rows: list[tuple],
        *,
        dry_run: bool,
        payload_options: dict,
    ) -> tuple[dict | None, dict[str, dict]]:
        """Construye el payload de gastos para POST al migrator.

        Filtra: solo gastos vinculados a OCs ya enviadas a Paxapos.
        """
        allowed_refs = self._link_store.get_sent_oc_gasto_refs()

        gastos: list[dict] = []
        raw_by_source_key: dict[str, dict] = {}
        skipped_no_oc = 0

        for row in rows:
            raw = dict(zip(columns, row))
            gasto = self._map_solic_gasto(raw)
            if gasto is None:
                continue

            # Filtrar: solo gastos cuya ref estÃ© vinculada a una OC enviada
            ext = gasto.get("external_id", {})
            rafam_ref = _gasto_ref_from_external_id(ext) if ext else ""
            if rafam_ref not in allowed_refs:
                skipped_no_oc += 1
                continue

            gastos.append(gasto)
            if ext:
                sk = json.dumps(ext, sort_keys=True)
                raw_by_source_key[sk] = raw

        if skipped_no_oc:
            logger.info(
                "Migrator [solic_gastos]: %d gastos omitidos (sin OC enviada vinculada)",
                skipped_no_oc,
            )

        if not gastos:
            logger.info("Migrator [solic_gastos]: lote vacÃ­o luego del mapeo")
            return None, {}

        payload = {
            "dry_run": dry_run,
            "options": payload_options,
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": gastos,
            "ordenes_pago": [],
        }
        return payload, raw_by_source_key

    def _map_solic_gasto(self, raw: dict) -> dict | None:
        """Mapea una fila de SOLIC_GASTOS + CTA_COMPROB al formato Paxapos."""
        ejercicio = to_int(raw.get("EJERCICIO"))
        deleg_solic = to_int(raw.get("DELEG_SOLIC"))
        nro_solic = to_int(raw.get("NRO_SOLIC"))
        if ejercicio is None or deleg_solic is None or nro_solic is None:
            return None

        fecha_raw = raw.get("FECH_SOLIC")
        fecha = format_date_only(fecha_raw)
        if not fecha:
            return None

        # Excluir anuladas
        if str(raw.get("ESTADO_SOLIC", "")).strip().upper() == "A":
            return None

        cta_count = to_int(raw.get("CTA_COMPROB_COUNT"))
        if cta_count != 1:
            logger.debug(
                "Migrator [solic_gastos] SG %s-%s-%s omitida: CTA_COMPROB_COUNT=%s",
                ejercicio, deleg_solic, nro_solic, raw.get("CTA_COMPROB_COUNT"),
            )
            return None

        importe_total = parse_money(raw.get("CTA_IMPORTE_COMPR"))
        if importe_total is None:
            importe_total = parse_money(raw.get("IMPORTE_TOT"))
        if importe_total is None:
            return None

        importe_neto = parse_money(raw.get("CTA_IMPORTE_NETO"))
        if importe_neto is None:
            importe_neto = parse_money(raw.get("CTA_IMPORTE_SIN_IVA"))
        if importe_neto is None:
            importe_neto = importe_total

        gasto_data: dict = {
            "fecha": fecha,
            "importe_total": importe_total,
            "importe_neto": importe_neto,
        }

        nro_comprob = str(raw.get("CTA_NRO_COMPROB") or "").strip()
        if not nro_comprob:
            logger.debug(
                "Migrator [solic_gastos] SG %s-%s-%s omitida: sin CTA_COMPROB.NRO_COMPROB",
                ejercicio, deleg_solic, nro_solic,
            )
            return None

        tipo_factura_id = self._lookup.resolve_tipo_factura_id(
            raw.get("CTA_TIPO_COMPROB") or raw.get("TIPO_DOC")
        )
        if tipo_factura_id is not None:
            gasto_data["tipo_factura_id"] = tipo_factura_id

        # Parsear NRO_COMPROB: si tiene guion, separar en punto_de_venta + factura_nro
        dash_pos = nro_comprob.find("-")
        if dash_pos > 0:
            gasto_data["punto_de_venta"] = nro_comprob[:dash_pos]
            gasto_data["factura_nro"] = nro_comprob[dash_pos + 1:]
        else:
            gasto_data["factura_nro"] = nro_comprob

        # fecha_vencimiento: FECH_NECESIDAD con fallback a FECH_ENTREGA
        fech_venc = (
            format_date_only(raw.get("CTA_FECH_VENCIM"))
            or format_date_only(raw.get("FECH_NECESIDAD"))
            or format_date_only(raw.get("FECH_ENTREGA"))
        )
        if fech_venc:
            gasto_data["fecha_vencimiento"] = fech_venc

        # proveedor_id via EntityLinkStore
        cod_prov = to_int(raw.get("OC_COD_PROV"))
        if cod_prov is not None:
            remote_prov = self._link_store.get_remote_id("proveedores", str(cod_prov))
            if remote_prov:
                gasto_data["proveedor_id"] = int(remote_prov)
            else:
                logger.debug(
                    "Migrator [solic_gastos] SG %s-%s-%s: proveedor COD_PROV=%s sin link remoto",
                    ejercicio, deleg_solic, nro_solic, cod_prov,
                )

        obs = raw.get("OBSERVACIONES")
        if obs and str(obs).strip():
            gasto_data["observacion"] = str(obs).strip()[:255]

        return {
            "external_id": gasto_external_id(ejercicio, deleg_solic, nro_solic),
            "Gasto": gasto_data,
        }


# ââ Persist Links ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def persist_links(parsed: dict, raw_by_source_key: dict[str, dict], link_store) -> None:
    """Persiste entity links de gastos desde la respuesta del API."""
    if not isinstance(parsed, dict):
        return
    results = parsed.get("results", {})
    if not isinstance(results, dict):
        return

    section = results.get("gastos", [])
    if not isinstance(section, list):
        return

    for result in section:
        if not isinstance(result, dict) or not result.get("success"):
            continue
        external_id = result.get("external_id") or {}
        if not isinstance(external_id, dict):
            continue
        remote_id = result.get("id")
        if remote_id is None:
            continue

        source_key = json.dumps(external_id, sort_keys=True)

        raw = raw_by_source_key.get(source_key, {})
        estado_solic = str(raw.get("ESTADO_SOLIC", "")).strip().upper() or None
        importe_tot = str(raw.get("IMPORTE_TOT")) if raw.get("IMPORTE_TOT") is not None else None
        cod_prov = str(raw.get("OC_COD_PROV")) if raw.get("OC_COD_PROV") is not None else None

        link_store.save_link(
            entity="gasto",
            source_key=source_key,
            remote_id=str(remote_id),
            estado_solic=estado_solic,
            importe_tot=importe_tot,
            cod_prov=cod_prov,
        )

        rafam_ref = _gasto_ref_from_external_id(external_id)
        alias_keys = _gasto_source_keys_from_ref(rafam_ref) if rafam_ref else []
        for alias_key in alias_keys:
            if alias_key == source_key:
                continue
            link_store.save_link(
                entity="gasto",
                source_key=alias_key,
                remote_id=str(remote_id),
                estado_solic=estado_solic,
                importe_tot=importe_tot,
                cod_prov=cod_prov,
            )


def log_stats(parsed: dict, gastos_count: int, dry_run: bool) -> None:
    """Loguea estadÃ­sticas de la pasada."""
    stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
    section_stats = stats.get("gastos", {}) if isinstance(stats, dict) else {}
    logger.info(
        "Migrator OK [solic_gastos->gastos]: %d ok, %d error, gastos=%d, dry_run=%s",
        section_stats.get("ok", 0),
        section_stats.get("error", 0),
        gastos_count,
        dry_run,
    )


# ââ Funciones de external_id compartidas âââââââââââââââââââââââââââââââââ
# Usadas por solic_gastos y orden_pago para construir/parsear refs de gastos.

def gasto_external_id(ejercicio: int, deleg_solic: int, nro_solic: int) -> dict:
    return {
        "ejercicio": ejercicio,
        "deleg_solic": deleg_solic,
        "nro_solic": nro_solic,
    }


def gasto_legacy_ref(ejercicio: int, deleg_solic: int, nro_solic: int) -> str:
    return f"SG-{ejercicio}-{deleg_solic}-{nro_solic}"


def _gasto_ref_from_external_id(external_id: dict) -> str:
    """Construye rafam_ref desde un external_id de gasto."""
    if not isinstance(external_id, dict):
        return ""
    rafam_ref = external_id.get("rafam_ref")
    if rafam_ref:
        return str(rafam_ref)
    ejercicio = to_int(external_id.get("ejercicio"))
    deleg_solic = to_int(external_id.get("deleg_solic"))
    nro_solic = to_int(external_id.get("nro_solic"))
    if ejercicio is None or deleg_solic is None or nro_solic is None:
        return ""
    return gasto_legacy_ref(ejercicio, deleg_solic, nro_solic)


def _gasto_external_id_from_ref(rafam_ref: str) -> dict | None:
    parts = str(rafam_ref).split("-")
    if len(parts) != 4 or parts[0] != "SG":
        return None
    ejercicio = to_int(parts[1])
    deleg_solic = to_int(parts[2])
    nro_solic = to_int(parts[3])
    if ejercicio is None or deleg_solic is None or nro_solic is None:
        return None
    return gasto_external_id(ejercicio, deleg_solic, nro_solic)


def _gasto_source_keys_from_ref(rafam_ref: str) -> list[str]:
    keys: list[str] = []
    external_id = _gasto_external_id_from_ref(rafam_ref)
    if external_id is not None:
        keys.append(json.dumps(external_id, sort_keys=True))
    keys.append(json.dumps({"rafam_ref": rafam_ref}, sort_keys=True))
    return keys


# SecciÃ³n de resultado en la respuesta del API
RESULT_SECTION = "gastos"
