"""solic_gastos.py â Mapper para entidad SOLIC_GASTOS (facturas/gastos).

Transforma filas crudas de RAFAM SOLIC_GASTOS + CTA_COMPROB al formato
del migrator Paxapos y persiste entity links a partir de la respuesta.
"""

from __future__ import annotations

import hashlib
import json
import logging

from ..utils import format_date_only, parse_money, to_int

logger = logging.getLogger(__name__)

PAXAPOS_ATTACHMENT_GASTO_FIELDS = frozenset({"media_id", "file"})
PAXAPOS_PRIORITY_GASTO_FIELDS = PAXAPOS_ATTACHMENT_GASTO_FIELDS | {"observacion"}

ENRICHABLE_GASTO_FIELDS = frozenset({
    "proveedor_id",
    "punto_de_venta",
    "factura_nro",
    "tipo_factura_id",
    "clasificacion_id",
    "importe_total",
    "importe_neto",
    "fecha",
    "fecha_vencimiento",
    "observacion",
    "media_id",
    "file",
})


class SolicGastosMapper:
    """Mapper para gastos de solicitud (SOLIC_GASTOS + CTA_COMPROB)."""

    def __init__(self, *, link_store, lookup_resolver, resolve_gastos_fn=None, source_repo=None):
        self._link_store = link_store
        self._lookup = lookup_resolver
        self._resolve_gastos_fn = resolve_gastos_fn
        # Inyectado por exporter.attach_source: se usa para expandir SGs con
        # multiples comprobantes (fetch_cta_comprob_for_sgs).
        self._source_repo = source_repo

    def build_payload(
        self,
        columns: list[str],
        rows: list[tuple],
        *,
        dry_run: bool,
        payload_options: dict,
    ) -> tuple[dict | None, dict[str, dict]]:
        """Construye el payload de ENRIQUECIMIENTO de gastos (UPDATE-ONLY).

        No crea gastos. Solo completa campos vacios de gastos que Paxapos ya
        creo (al subir el proveedor la factura de una OC; account_gastos.pedido_id).
        El pareo usa el gasto_id que devuelve resolver_gasto, matcheado por el
        pedido_id de la OC (remote_id del link orden_compra). Gastos sin OC
        enviada, sin gasto parcial en Paxapos, o ya completos, se omiten.
        """
        allowed_refs = self._link_store.get_sent_oc_gasto_refs()

        # Indice inverso rafam_ref -> pedido_id (remote_id de la OC en Paxapos).
        oc_ref_to_pedido: dict[str, int] = {}
        for link in self._link_store.get_all_links("orden_compra"):
            remote_id = link.get("remote_id")
            gasto_refs = link.get("gasto_refs") or ""
            if not remote_id or not gasto_refs:
                continue
            try:
                pedido_id = int(remote_id)
            except (TypeError, ValueError):
                continue
            for ref in str(gasto_refs).split(","):
                ref = ref.strip()
                if ref:
                    oc_ref_to_pedido.setdefault(ref, pedido_id)

        # Mapear cada fila. Las SGs con 2+ comprobantes no caben en la fila
        # agregada (MIN() trae uno solo): se juntan y se expanden despues en un
        # candidato por comprobante via fetch_cta_comprob_for_sgs.
        candidates: list[tuple[dict, dict]] = []
        multi_pending: list[dict] = []
        for row in rows:
            raw = dict(zip(columns, row))
            cta_count = to_int(raw.get("CTA_COMPROB_COUNT"))
            if cta_count is not None and cta_count > 1:
                multi_pending.append(raw)
                continue
            gasto = self._map_solic_gasto(raw)
            if gasto is not None:
                candidates.append((gasto, raw))

        candidates.extend(self._expand_multi_comprobante(multi_pending))

        mapped: list[dict] = []
        skipped_no_oc = 0
        for gasto, raw in candidates:
            ext = gasto.get("external_id", {})
            rafam_ref = _gasto_ref_from_external_id(ext) if ext else ""
            if rafam_ref not in allowed_refs:
                skipped_no_oc += 1
                continue
            sk = json.dumps(ext, sort_keys=True) if ext else None
            mapped.append({
                "external_id": ext,
                "gasto_data": gasto.get("Gasto", {}),
                "rafam_ref": rafam_ref,
                "sk": sk,
                "pedido_id": oc_ref_to_pedido.get(rafam_ref),
                "raw": raw,
            })

        if skipped_no_oc:
            logger.info(
                "Migrator [solic_gastos]: %d gastos omitidos (sin OC enviada vinculada)",
                skipped_no_oc,
            )

        if not mapped:
            logger.info("Migrator [solic_gastos]: lote vacio luego del mapeo")
            return None, {}

        # Consultar resolver_gasto: gastos parciales ya creados por Paxapos.
        pedido_ids = sorted({m["pedido_id"] for m in mapped if m["pedido_id"] is not None})
        comprobantes: list[dict] = []
        for m in mapped:
            gd = m["gasto_data"]
            if not gd.get("factura_nro"):
                continue
            comprobantes.append({
                "proveedor_id": gd.get("proveedor_id"),
                "punto_de_venta": gd.get("punto_de_venta"),
                "factura_nro": gd.get("factura_nro"),
                "tipo_factura_id": gd.get("tipo_factura_id"),
            })

        resolver = {}
        if self._resolve_gastos_fn is not None:
            resolver = self._resolve_gastos_fn(pedido_ids, comprobantes) or {}

        resolved_gastos = resolver.get("gastos", []) if isinstance(resolver, dict) else []
        by_pedido: dict[int, list[dict]] = {}
        # Indice secundario por identidad de comprobante: cubre los gastos que el
        # resolver devuelve con matched_by='comprobante' y pedido_id null (no
        # quedaron vinculados a la OC). Sin esto el fallback del backend era
        # inalcanzable y esos gastos nunca se enriquecian.
        by_comprobante: dict[tuple, dict] = {}
        for g in resolved_gastos:
            if not isinstance(g, dict):
                continue
            comp_key = _comprobante_key(g)
            if comp_key is not None:
                by_comprobante.setdefault(comp_key, g)
            try:
                gp_int = int(g.get("pedido_id"))
            except (TypeError, ValueError):
                continue
            by_pedido.setdefault(gp_int, []).append(g)

        gastos: list[dict] = []
        raw_by_source_key: dict[str, dict] = {}
        skipped_no_match = 0
        skipped_complete = 0
        skipped_same_hash = 0
        skipped_ambiguous = 0

        for m in mapped:
            pedido_id = m["pedido_id"]
            gd = m["gasto_data"]
            candidates = by_pedido.get(pedido_id) if pedido_id is not None else None
            if candidates:
                resolved = _pick_resolved(candidates, gd)
            else:
                # Fallback: identidad de comprobante (proveedor + pdv + nro + tipo).
                resolved = by_comprobante.get(_comprobante_key(gd))
            if resolved is None:
                if candidates:
                    skipped_ambiguous += 1
                else:
                    skipped_no_match += 1
                continue

            empty_fields = resolved.get("empty_fields") or []
            enrich = {
                field: gd[field]
                for field in empty_fields
                if field in ENRICHABLE_GASTO_FIELDS
                and not (
                    field in PAXAPOS_ATTACHMENT_GASTO_FIELDS
                    and resolved.get("tiene_imagen")
                )
                and not (
                    field == "observacion"
                    and resolved.get("tiene_observacion")
                )
                and field in gd
                and gd[field] not in (None, "")
            }
            if not enrich:
                skipped_complete += 1
                continue

            gasto_id = resolved.get("id")
            if gasto_id is None:
                skipped_no_match += 1
                continue

            payload_hash = _stable_payload_hash({"id": gasto_id, "enrich": enrich})
            sk = m["sk"]
            if sk is not None:
                existing_link = self._link_store.get_link("gasto", sk)
                if existing_link and existing_link.get("payload_hash") == payload_hash:
                    skipped_same_hash += 1
                    continue

            entry_gasto = {"id": gasto_id, "merge": "fill_empty"}
            entry_gasto.update(enrich)
            gastos.append({"external_id": m["external_id"], "Gasto": entry_gasto})

            if sk is not None:
                raw = dict(m["raw"])
                raw["_pedido_id"] = pedido_id
                raw["_nro_comprobante"] = _nro_comprobante_from_gasto(gd)
                raw["_payload_hash"] = payload_hash
                raw_by_source_key[sk] = raw

        for cnt, label in (
            (skipped_no_match, "sin gasto parcial en Paxapos (proveedor aun no subio factura)"),
            (skipped_ambiguous, "ambiguos (varias facturas en la OC sin desambiguar)"),
            (skipped_complete, "ya completos"),
            (skipped_same_hash, "sin cambios (mismo hash)"),
        ):
            if cnt:
                logger.info("Migrator [solic_gastos]: %d gastos omitidos (%s)", cnt, label)

        if not gastos:
            logger.info("Migrator [solic_gastos]: nada para enriquecer este lote")
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

    # Campos de comprobante que se sobreescriben al expandir una SG multi.
    _CTA_FIELDS = (
        "CTA_NRO_COMPROB", "CTA_TIPO_COMPROB", "CTA_FECH_COMPROB",
        "CTA_FECH_VENCIM", "CTA_IMPORTE_COMPR", "CTA_IMPORTE_NETO",
        "CTA_IMPORTE_SIN_IVA",
    )

    def _expand_multi_comprobante(self, pending: list[dict]) -> list[tuple[dict, dict]]:
        """Expande SGs con 2+ comprobantes en un candidato por comprobante.

        Antes estas SGs se OMITIAN por completo (CTA_COMPROB_COUNT != 1) y sus
        gastos nunca se enriquecian. Cada candidato lleva el external_id
        extendido con ``nro_comprob`` para que los links locales no colisionen
        entre comprobantes de la misma SG; el resolver los matchea por
        identidad de comprobante (proveedor + pdv + nro + tipo).
        """
        if not pending:
            return []
        if self._source_repo is None:
            logger.info(
                "Migrator [solic_gastos]: %d SGs con multiples comprobantes omitidas "
                "(sin source_repo para expandirlas)",
                len(pending),
            )
            return []

        raw_by_key: dict[tuple[int, int, int], dict] = {}
        for raw in pending:
            ej = to_int(raw.get("EJERCICIO"))
            deleg = to_int(raw.get("DELEG_SOLIC"))
            nro = to_int(raw.get("NRO_SOLIC"))
            if ej is None or deleg is None or nro is None:
                continue
            raw_by_key.setdefault((ej, deleg, nro), raw)

        if not raw_by_key:
            return []

        try:
            comps = self._source_repo.fetch_cta_comprob_for_sgs(list(raw_by_key.keys()))
        except Exception as exc:
            logger.warning(
                "Migrator [solic_gastos]: fallo el fetch de comprobantes multiples (%s); "
                "%d SGs quedan sin enriquecer este lote",
                exc, len(raw_by_key),
            )
            return []
        if comps is None:
            logger.warning(
                "Migrator [solic_gastos]: REG_COMP/CTA_COMPROB no disponibles; "
                "%d SGs multi-comprobante sin enriquecer",
                len(raw_by_key),
            )
            return []

        out: list[tuple[dict, dict]] = []
        for key, comp_rows in comps.items():
            base = raw_by_key.get(key)
            if base is None:
                continue
            for comp in comp_rows:
                candidate = dict(base)
                for field in self._CTA_FIELDS:
                    candidate[field] = comp.get(field)
                candidate["CTA_COMPROB_COUNT"] = 1
                gasto = self._map_solic_gasto(candidate)
                if gasto is None:
                    continue
                nro_comprob = str(comp.get("CTA_NRO_COMPROB") or "").strip()
                gasto["external_id"] = {**gasto["external_id"], "nro_comprob": nro_comprob}
                out.append((gasto, candidate))

        if out:
            logger.info(
                "Migrator [solic_gastos]: %d SGs con multiples comprobantes expandidas "
                "en %d candidatos de enriquecimiento",
                len(raw_by_key), len(out),
            )
        return out

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

def _norm_factura(value) -> str:
    """Normaliza un numero de factura para comparar (sin ceros a izquierda)."""
    if value is None:
        return ""
    return str(value).strip().lstrip("0")


def _comprobante_key(data: dict) -> tuple | None:
    """Identidad de comprobante normalizada (proveedor, pdv, nro, tipo).

    Sirve para cruzar el gasto mapeado desde RAFAM con el que devuelve
    resolver_gasto, que ya viene con pdv/nro paddeados a 5/20 por el backend.
    """
    if not isinstance(data, dict):
        return None
    factura_nro = _norm_factura(data.get("factura_nro"))
    if not factura_nro:
        return None
    proveedor_id = data.get("proveedor_id")
    tipo_factura_id = data.get("tipo_factura_id")
    return (
        int(proveedor_id) if proveedor_id not in (None, "") else None,
        _norm_factura(data.get("punto_de_venta")),
        factura_nro,
        int(tipo_factura_id) if tipo_factura_id not in (None, "") else None,
    )


def _pick_resolved(candidates: list[dict], gasto_data: dict) -> dict | None:
    """Elige el gasto resolver correcto cuando una OC tiene varias facturas.

    Con un solo candidato lo devuelve. Con varios, desambigua por factura_nro;
    si no se puede, devuelve None (se omite para no enriquecer el gasto errado).
    """
    if len(candidates) == 1:
        return candidates[0]
    want = _norm_factura(gasto_data.get("factura_nro"))
    if not want:
        return None
    for candidate in candidates:
        if _norm_factura(candidate.get("factura_nro")) == want:
            return candidate
    return None


def _stable_payload_hash(obj) -> str:
    """Hash estable del contenido de enriquecimiento (para anti-reenvio)."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _nro_comprobante_from_gasto(gasto_data: dict) -> str | None:
    """Reconstruye el nro de comprobante (pdv-nro) desde el gasto mapeado."""
    factura_nro = gasto_data.get("factura_nro")
    if not factura_nro:
        return None
    pdv = gasto_data.get("punto_de_venta")
    if pdv:
        return f"{pdv}-{factura_nro}"
    return str(factura_nro)


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
        pedido_id = str(raw["_pedido_id"]) if raw.get("_pedido_id") is not None else None
        nro_comprobante = raw.get("_nro_comprobante")
        payload_hash = raw.get("_payload_hash")

        link_store.save_link(
            entity="gasto",
            source_key=source_key,
            remote_id=str(remote_id),
            estado_solic=estado_solic,
            importe_tot=importe_tot,
            cod_prov=cod_prov,
            pedido_id=pedido_id,
            nro_comprobante=nro_comprobante,
            payload_hash=payload_hash,
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
                pedido_id=pedido_id,
                nro_comprobante=nro_comprobante,
                payload_hash=payload_hash,
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
