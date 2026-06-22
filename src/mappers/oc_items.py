"""oc_items.py â Mapper para entidad OC_ITEMS (Ã³rdenes de compra + Ã­tems).

Agrupa filas por OC (cabecera + Ã­tems), clasifica por estado vs link
previo, y construye el payload de ordenes_compra para el migrator Paxapos.
"""

from __future__ import annotations

import json
import logging

from ..utils import format_date_only, normalize_text, to_int

logger = logging.getLogger(__name__)


class OcItemsMapper:
    """Mapper stateful para OC_ITEMS: acumula contadores cross-batch."""

    def __init__(self, *, link_store, lookup_resolver):
        self._link_store = link_store
        self._lookup = lookup_resolver
        # Acumula items sin match de mercaderÃ­a entre batches para report final
        self._missing_mercaderia_matches: dict[str, int] = {}

    def build_payload(
        self,
        columns: list[str],
        rows: list[tuple],
        *,
        dry_run: bool,
        payload_options: dict,
    ) -> tuple[dict | None, dict[str, dict]]:
        """Construye el payload de ordenes_compra para POST al migrator."""

        # ââ 1. Agrupar filas por OC (cabecera + items) ââââââââââââââââââââ
        grouped: dict[tuple[int, int, int], dict] = {}
        grouped_raw: dict[tuple[int, int, int], dict] = {}
        grouped_gasto_refs: dict[tuple[int, int, int], list[str]] = {}
        seen_items_per_oc: dict[tuple[int, int, int], set[int]] = {}
        skipped_no_prov: set[tuple[int, int, int]] = set()
        unresolved_items = 0

        for row in rows:
            raw = dict(zip(columns, row))

            ejercicio = to_int(raw.get("EJERCICIO"))
            uni_compra = to_int(raw.get("UNI_COMPRA"))
            nro_oc = to_int(raw.get("NRO_OC"))
            if ejercicio is None or uni_compra is None or nro_oc is None:
                continue

            key = (ejercicio, uni_compra, nro_oc)
            if key in skipped_no_prov:
                continue
            if key not in grouped:
                # Resolver proveedor_id via link_store (RAFAM COD_PROV â Paxapos id)
                cod_prov = raw.get("COD_PROV")
                remote_prov_id: int | None = None
                if cod_prov is not None:
                    remote_prov = self._link_store.get_remote_id("proveedores", str(cod_prov))
                    if remote_prov:
                        remote_prov_id = int(remote_prov)

                if remote_prov_id is None:
                    logger.warning(
                        "Migrator [oc_items] OC %s-%s-%s: omitida â sin proveedor (COD_PROV=%s)",
                        ejercicio, uni_compra, nro_oc, cod_prov,
                    )
                    skipped_no_prov.add(key)
                    continue

                pedido: dict = {
                    "internal_id": f"{ejercicio % 100}-{nro_oc}",
                    "tipo": "orden_compra",
                    "estado_aprobacion": 2,
                    "proveedor_id": remote_prov_id,
                }

                obs = _compose_oc_observacion(raw)
                if obs:
                    pedido["observacion"] = obs

                fech_oc = format_date_only(raw.get("OC_FECH_OC"))
                if fech_oc:
                    pedido["created"] = f"{fech_oc} 00:00:00"

                oc_data: dict = {
                    "external_id": {
                        "ejercicio": ejercicio,
                        "uni_compra": uni_compra,
                        "nro_oc": nro_oc,
                    },
                    "Pedido": pedido,
                    "items": [],
                }

                sg_jurisdiccion = raw.get("SG_JURISDICCION")
                centro_costo_id = self._lookup.resolve_centro_costo_id(sg_jurisdiccion)
                if centro_costo_id is not None:
                    oc_data["centro_costo_id"] = centro_costo_id

                grouped[key] = oc_data
                grouped_raw[key] = raw

            # Recolectar ref de gasto desde DELEG_SOLIC + NRO_SOLIC del Ã­tem
            deleg_solic = to_int(raw.get("DELEG_SOLIC"))
            nro_solic = to_int(raw.get("NRO_SOLIC"))
            if deleg_solic is not None and nro_solic is not None:
                rafam_ref = f"SG-{ejercicio}-{deleg_solic}-{nro_solic}"
                refs = grouped_gasto_refs.setdefault(key, [])
                if rafam_ref not in refs:
                    refs.append(rafam_ref)

            # Dedup por ITEM_OC
            item_oc = to_int(raw.get("ITEM_OC"))
            seen_items = seen_items_per_oc.setdefault(key, set())
            if item_oc is not None and item_oc in seen_items:
                continue

            item = self._map_oc_item(raw)
            if item is None:
                unresolved_items += 1
                self._track_unresolved_item(raw.get("DESCRIPCION"), raw.get("COD_PROV"))
                continue
            if item_oc is not None:
                seen_items.add(item_oc)
            grouped[key]["items"].append(item)

        # ââ 2. Clasificar OCs por acciÃ³n segÃºn estado y link previo âââââââ
        ocs_to_create: list[dict] = []
        ocs_to_anular: list[dict] = []
        ocs_to_skip_register: list[tuple[int, int, int]] = []
        ocs_to_skip_has_op: list[tuple[int, int, int]] = []
        ocs_same_state: list[tuple[int, int, int]] = []
        skipped_same_state = 0

        for key, oc_data in grouped.items():
            if not oc_data["items"]:
                continue

            raw = grouped_raw[key]
            estado_actual = str(raw.get("OC_ESTADO_OC", "")).strip().upper()
            source_key = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            link_previo = self._link_store.get_link("orden_compra", source_key)
            estado_previo = link_previo.get("estado_oc", "").strip().upper() if link_previo else None

            if estado_actual == "R":
                if link_previo is None or estado_previo != "R":
                    ocs_to_create.append(oc_data)
                else:
                    ocs_same_state.append(key)
                    skipped_same_state += 1
            elif estado_actual == "A":
                if link_previo and estado_previo == "R" and link_previo.get("remote_id"):
                    if link_previo.get("has_op"):
                        logger.info(
                            "Migrator [oc_items] OC %s-%s-%s anulada en RAFAM pero tiene OP,"
                            " no se elimina de Paxapos",
                            key[0], key[1], key[2],
                        )
                        ocs_to_skip_has_op.append(key)
                    else:
                        oc_data["Pedido"]["deleted"] = 1
                        ocs_to_anular.append(oc_data)
                else:
                    ocs_to_skip_register.append(key)
            else:
                has_cc = bool(str(raw.get("OC_CC_NRO") or "").strip())
                has_op = bool(link_previo and link_previo.get("has_op"))
                if has_cc or has_op:
                    logger.info(
                        "Migrator [oc_items] OC %s-%s-%s estado %s pero tiene %s,"
                        " enviando a Paxapos como fallback",
                        key[0], key[1], key[2], estado_actual,
                        "comprobante+OP" if (has_cc and has_op)
                        else ("comprobante" if has_cc else "OP"),
                    )
                    ocs_to_create.append(oc_data)
                else:
                    ocs_to_skip_register.append(key)

        # ââ 3. Registrar en link TODAS las OCs (con o sin envÃ­o) ââââââââââ
        for key in ocs_to_skip_register + ocs_same_state + ocs_to_skip_has_op:
            raw = grouped_raw[key]
            source_key = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            estado_oc = str(raw.get("OC_ESTADO_OC", "")).strip().upper() or None
            fech_confirm = format_date_only(raw.get("OC_FECH_CONFIRM", "")) or None
            cod_prov = str(raw.get("COD_PROV")) if raw.get("COD_PROV") is not None else None
            importe_tot = str(raw.get("OC_IMPORTE_TOT")) if raw.get("OC_IMPORTE_TOT") is not None else None
            gasto_refs_list = grouped_gasto_refs.get(key, [])
            gasto_refs = ",".join(gasto_refs_list) if gasto_refs_list else ""

            existing = self._link_store.get_link("orden_compra", source_key)
            remote_id = existing.get("remote_id", "") if existing else ""
            gasto_linked_refs = existing.get("gasto_linked_refs", "") if existing else ""

            self._link_store.save_link(
                entity="orden_compra",
                source_key=source_key,
                remote_id=remote_id,
                estado_oc=estado_oc,
                fech_confirm=fech_confirm,
                cod_prov=cod_prov,
                importe_tot=importe_tot,
                gasto_refs=gasto_refs,
                gasto_linked_refs=gasto_linked_refs,
            )

        # ââ 4. Enviar OCs a crear + OCs a anular en un solo payload âââââââ
        ordenes_compra = ocs_to_create + ocs_to_anular
        raw_by_source_key: dict[str, dict] = {}
        for key in grouped_raw:
            sk = json.dumps(
                {"ejercicio": key[0], "nro_oc": key[2], "uni_compra": key[1]},
                sort_keys=True,
            )
            raw_by_source_key[sk] = grouped_raw[key]
            gasto_refs_list = grouped_gasto_refs.get(key, [])
            raw_by_source_key[sk]["_GASTO_REFS"] = ",".join(gasto_refs_list) if gasto_refs_list else ""
            raw_by_source_key[sk]["_GASTO_LINKED_REFS"] = ""

        if not ordenes_compra:
            logger.info(
                "Migrator [oc_items]: nada que enviar (skip_estado=%d, mismo_estado=%d, skip_has_op=%d, sin_items=%d)",
                len(ocs_to_skip_register),
                skipped_same_state,
                len(ocs_to_skip_has_op),
                unresolved_items,
            )
            return None, {}

        payload = {
            "dry_run": dry_run,
            "options": payload_options,
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": ordenes_compra,
            "gastos": [],
            "ordenes_pago": [],
        }

        # Store stats metadata for logging after POST
        self._last_stats = {
            "crear": len(ocs_to_create),
            "anular": len(ocs_to_anular),
            "skip_estado": len(ocs_to_skip_register),
            "mismo_estado": skipped_same_state,
            "skip_has_op": len(ocs_to_skip_has_op),
            "unresolved_items": unresolved_items,
        }
        return payload, raw_by_source_key

    def _map_oc_item(self, raw: dict) -> dict | None:
        """Mapea un Ã­tem de OC RAFAM al formato Paxapos."""
        mercaderia_external_ref = _mercaderia_external_ref_oc_item(raw)
        if mercaderia_external_ref is None:
            return None

        cantidad = raw.get("CANTIDAD")
        if cantidad is None:
            return None

        item = {
            "cantidad": float(cantidad),
            "unidad_de_medida_id": self._lookup.resolve_unidad_medida_id(raw),
        }

        if raw.get("IMP_UNITARIO") is not None:
            item["precio_unitario"] = round(float(raw.get("IMP_UNITARIO")), 2)

        if raw.get("CANT_RECIB") is not None:
            item["recibida_cantidad"] = float(raw.get("CANT_RECIB"))

        descripcion = raw.get("DESCRIPCION")
        if descripcion:
            item["name"] = str(descripcion).strip()[:255]

        centro_costo_id = self._lookup.resolve_centro_costo_id(raw.get("SG_JURISDICCION"))
        if centro_costo_id is not None:
            item["centro_costo_id"] = centro_costo_id

        return item

    def _track_unresolved_item(self, description, proveedor) -> None:
        desc_key = normalize_text(description)
        if not desc_key:
            desc_key = "(sin descripcion)"
        prov_key = str(to_int(proveedor)) if to_int(proveedor) is not None else "(sin proveedor)"
        key = f"{prov_key}::{desc_key}"
        self._missing_mercaderia_matches[key] = self._missing_mercaderia_matches.get(key, 0) + 1

    def log_unresolved_summary(self) -> None:
        """Loguea resumen de items sin match de mercaderÃ­a (top 10)."""
        if not self._missing_mercaderia_matches:
            return
        top = sorted(self._missing_mercaderia_matches.items(), key=lambda kv: kv[1], reverse=True)[:10]
        summary = ", ".join(f"{k} x{v}" for k, v in top)
        logger.warning("Migrator [oc_items] sin match de mercaderia (top 10): %s", summary)

    def log_stats(self, parsed: dict, dry_run: bool) -> None:
        """Loguea estadÃ­sticas post-send."""
        stats_dict = getattr(self, "_last_stats", {})
        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("ordenes_compra", {}) if isinstance(stats, dict) else {}
        logger.info(
            "Migrator OK [oc_items->ordenes_compra]: %d ok, %d error, crear=%d, anular=%d, "
            "skip_estado=%d, mismo_estado=%d, skip_has_op=%d, dry_run=%s",
            section_stats.get("ok", 0),
            section_stats.get("error", 0),
            stats_dict.get("crear", 0),
            stats_dict.get("anular", 0),
            stats_dict.get("skip_estado", 0),
            stats_dict.get("mismo_estado", 0),
            stats_dict.get("skip_has_op", 0),
            dry_run,
        )
        self.log_unresolved_summary()


# ââ Persist Links ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def persist_links(parsed: dict, raw_by_source_key: dict[str, dict], link_store) -> None:
    """Persiste entity links de ordenes_compra desde la respuesta del API."""
    if not isinstance(parsed, dict):
        return
    results = parsed.get("results", {})
    if not isinstance(results, dict):
        return

    section = results.get("ordenes_compra", [])
    if not isinstance(section, list):
        return

    pk_fields = ["ejercicio", "uni_compra", "nro_oc"]
    for result in section:
        if not isinstance(result, dict) or not result.get("success"):
            continue
        external_id = result.get("external_id") or {}
        if not isinstance(external_id, dict):
            continue
        remote_id = result.get("id")
        if remote_id is None:
            continue

        key_dict = {k: external_id[k] for k in pk_fields if k in external_id}
        if len(key_dict) != len(pk_fields):
            logger.warning("Migrator [orden_compra]: external_id incompleto: %s", external_id)
            continue
        source_key = json.dumps(key_dict, sort_keys=True)

        raw = raw_by_source_key.get(source_key, {})
        estado_oc = str(raw.get("OC_ESTADO_OC", "")).strip().upper() or None
        fech_confirm = format_date_only(raw.get("OC_FECH_CONFIRM", "")) or None
        cod_prov = str(raw.get("COD_PROV")) if raw.get("COD_PROV") is not None else None
        importe_tot = str(raw.get("OC_IMPORTE_TOT")) if raw.get("OC_IMPORTE_TOT") is not None else None

        gasto_refs = raw.get("_GASTO_REFS", "")
        gasto_linked_refs = raw.get("_GASTO_LINKED_REFS", "")

        paxapos_gasto_ids_list = result.get("gasto_ids") or []
        paxapos_gasto_ids = ",".join(str(g) for g in paxapos_gasto_ids_list) if paxapos_gasto_ids_list else ""

        link_store.save_link(
            entity="orden_compra",
            source_key=source_key,
            remote_id=str(remote_id),
            estado_oc=estado_oc,
            fech_confirm=fech_confirm,
            cod_prov=cod_prov,
            importe_tot=importe_tot,
            gasto_refs=gasto_refs,
            gasto_linked_refs=gasto_linked_refs,
            paxapos_gasto_ids=paxapos_gasto_ids,
        )


# ââ Helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _compose_oc_observacion(raw: dict) -> str | None:
    """Return real RAFAM observation or None. Never fabricate a traza string."""
    obs = raw.get("OC_OBSERVACIONES")
    if obs and str(obs).strip():
        return str(obs).strip()[:255]
    return None


def _mercaderia_external_ref_oc_item(raw: dict) -> dict | None:
    """Construye la referencia externa de mercaderÃ­a para un Ã­tem de OC."""
    ejercicio = to_int(raw.get("EJERCICIO"))
    uni_compra = to_int(raw.get("UNI_COMPRA"))
    nro_oc = to_int(raw.get("NRO_OC"))
    item_oc = to_int(raw.get("ITEM_OC"))

    if ejercicio is None or uni_compra is None or nro_oc is None or item_oc is None:
        return None

    ref = {
        "source": "rafam",
        "entity": "oc_items",
        "ejercicio": ejercicio,
        "uni_compra": uni_compra,
        "nro_oc": nro_oc,
        "item_oc": item_oc,
    }

    deleg_solic = to_int(raw.get("DELEG_SOLIC"))
    nro_solic = to_int(raw.get("NRO_SOLIC"))
    item_real = to_int(raw.get("ITEM_REAL"))
    if deleg_solic is not None:
        ref["deleg_solic"] = deleg_solic
    if nro_solic is not None:
        ref["nro_solic"] = nro_solic
    if item_real is not None:
        ref["item_real"] = item_real
    return ref


# SecciÃ³n de resultado en la respuesta del API
RESULT_SECTION = "ordenes_compra"
