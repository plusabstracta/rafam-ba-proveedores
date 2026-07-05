"""oc_items.py â Mapper para entidad OC_ITEMS (Ã³rdenes de compra + Ã­tems).

Agrupa filas por OC (cabecera + Ã­tems), clasifica por estado vs link
previo, y construye el payload de ordenes_compra para el migrator Paxapos.
"""

from __future__ import annotations

import json
import logging

from ..utils import format_date_only, normalize_text, to_int
from ..change_detection import compute_payload_hash

logger = logging.getLogger(__name__)


class OcItemsMapper:
    """Mapper stateful para OC_ITEMS: acumula contadores cross-batch."""

    def __init__(self, *, link_store, lookup_resolver, resolver_url=None):
        self._link_store = link_store
        self._lookup = lookup_resolver
        self._resolver_url = resolver_url
        # Acumula items sin match de mercaderÃ­a entre batches para report final
        self._missing_mercaderia_matches: dict[str, int] = {}
        # Indices de mercaderias del tenant para resolucion offline por nombre.
        mercaderias = getattr(lookup_resolver, "mercaderias", None) or []
        self._mercaderias_by_nombre_compra = self._build_clean_mercaderia_index(mercaderias, "nombre_compra")
        self._mercaderias_by_name = self._build_clean_mercaderia_index(mercaderias, "name")
        # Cache in-memory de resoluciones (source_key -> remote_id) de la corrida.
        self._mercaderia_resolved: dict[str, int] = {}

    def group_rows(
        self,
        columns: list[str],
        rows: list[tuple],
        *,
        post_fn=None,
        allow_api: bool = False,
    ) -> tuple[dict, dict, dict, int]:
        """Agrupa filas RAFAM OC_ITEMS por OC (cabecera + items).

        Fuente única del agrupamiento: la usan tanto ``build_payload`` (envío)
        como el flujo de detección de cambios (sync-changes) para hashear el
        mismo ``oc_data`` que se enviaría. Es pura respecto al link store salvo
        la resolución de proveedor_id (lectura).

        Returns:
            (grouped, grouped_raw, grouped_gasto_refs, unresolved_items)
        """
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
                # Resolver proveedor_id via link_store (RAFAM COD_PROV -> Paxapos id)
                cod_prov = raw.get("COD_PROV")
                remote_prov_id: int | None = None
                if cod_prov is not None:
                    remote_prov = self._link_store.get_remote_id("proveedores", str(cod_prov))
                    if remote_prov:
                        remote_prov_id = int(remote_prov)

                if remote_prov_id is None:
                    logger.warning(
                        "Migrator [oc_items] OC %s-%s-%s: omitida - sin proveedor (COD_PROV=%s)",
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

            # Recolectar ref de gasto desde DELEG_SOLIC + NRO_SOLIC del item
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

            item = self._map_oc_item(raw, post_fn=post_fn, allow_api=allow_api)
            if item is None:
                unresolved_items += 1
                self._track_unresolved_item(raw.get("DESCRIPCION"), raw.get("COD_PROV"))
                continue
            if item_oc is not None:
                seen_items.add(item_oc)
            grouped[key]["items"].append(item)

        return grouped, grouped_raw, grouped_gasto_refs, unresolved_items

    def build_payload(
        self,
        columns: list[str],
        rows: list[tuple],
        *,
        dry_run: bool,
        payload_options: dict,
        post_fn=None,
    ) -> tuple[dict | None, dict[str, dict]]:
        """Construye el payload de ordenes_compra para POST al migrator."""

        # En dry-run no se contacta al resolver remoto: la mercaderia se resuelve
        # solo offline (cache/link/indice). En envio real se permite crear via API.
        grouped, grouped_raw, grouped_gasto_refs, unresolved_items = self.group_rows(
            columns, rows, post_fn=post_fn, allow_api=not dry_run
        )

        # Fingerprint de contenido por OC (para detección de cambios / sync-changes).
        # Se calcula ANTES de clasificar para no incluir mutaciones de envío
        # (ej. Pedido.deleted en anulaciones).
        payload_hashes: dict[str, str] = {}
        for _key, _oc_data in grouped.items():
            _sk = json.dumps(
                {"ejercicio": _key[0], "nro_oc": _key[2], "uni_compra": _key[1]},
                sort_keys=True,
            )
            payload_hashes[_sk] = compute_payload_hash(_oc_data)

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
                payload_hash=payload_hashes.get(source_key),
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
            raw_by_source_key[sk]["_PAYLOAD_HASH"] = payload_hashes.get(sk)

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

    def _map_oc_item(self, raw: dict, *, post_fn=None, allow_api: bool = False) -> dict | None:
        """Mapea un Ã­tem de OC RAFAM al formato Paxapos.

        Resuelve ``mercaderia_id`` (cache -> link -> indice local -> resolver
        API) en vez de enviar una referencia externa: el contrato exige que los
        Ã­tems lleguen con la mercaderia real de Paxapos, no con nombres
        autogenerados ``[RAFAM-...]``.
        """
        descripcion = raw.get("DESCRIPCION")
        cantidad = raw.get("CANTIDAD")
        if cantidad is None:
            return None
        if not str(descripcion or "").strip():
            return None

        unidad_de_medida_id = self._lookup.resolve_unidad_medida_id(raw)
        proveedor_id = self._resolve_proveedor_id(raw)
        mercaderia_id = self._resolve_mercaderia_id(
            raw,
            unidad_de_medida_id=unidad_de_medida_id,
            proveedor_id=proveedor_id,
            post_fn=post_fn,
            allow_api=allow_api,
        )
        if mercaderia_id is None:
            return None

        item = {
            "cantidad": float(cantidad),
            "unidad_de_medida_id": unidad_de_medida_id,
            "mercaderia_id": mercaderia_id,
        }

        if raw.get("IMP_UNITARIO") is not None:
            item["precio_unitario"] = round(float(raw.get("IMP_UNITARIO")), 2)

        if raw.get("CANT_RECIB") is not None:
            item["recibida_cantidad"] = float(raw.get("CANT_RECIB"))

        # Conservar el nombre descriptivo SOLO cuando la descripcion coincide
        # con una mercaderia limpia del catalogo local (label heuristico). Es
        # deterministico respecto de los datos (no de la via de resolucion), asi
        # el hash de deteccion de cambios es estable entre corridas: no importa
        # si la mercaderia se resuelve por indice (1a vez) o por link (2a vez).
        if self._description_matches_catalog(descripcion):
            name = str(descripcion).strip()[:255]
            if name:
                item["name"] = name

        centro_costo_id = self._lookup.resolve_centro_costo_id(raw.get("SG_JURISDICCION"))
        if centro_costo_id is not None:
            item["centro_costo_id"] = centro_costo_id

        return item

    # ââ Resolucion de mercaderia âââââââââââââââââââââââââââââââââââââââââââ

    def _resolve_proveedor_id(self, raw: dict) -> int | None:
        cod_prov = raw.get("COD_PROV")
        if cod_prov is None:
            return None
        remote = self._link_store.get_remote_id("proveedores", str(cod_prov))
        return to_int(remote)

    @staticmethod
    def _mercaderia_description_source_key(normalized_description: str) -> str:
        return f"name:{normalized_description}"

    def _description_matches_catalog(self, description) -> bool:
        """True si la descripcion coincide con una mercaderia limpia del catalogo.

        Deterministico respecto de los datos (indices construidos al init), no
        de la via de resolucion ni de side-effects de link. Esto mantiene el
        hash de deteccion de cambios estable entre corridas.
        """
        normalized = normalize_text(description)
        if not normalized:
            return False
        return (
            normalized in self._mercaderias_by_nombre_compra
            or normalized in self._mercaderias_by_name
        )

    @staticmethod
    def _is_generated_rafam_mercaderia(row: dict) -> bool:
        """True si la mercaderia es un nombre autogenerado por RAFAM.

        Estos nombres (``[RAFAM-...]``, ``RAFAM:``, "mercaderia desarrollo") no
        deben reutilizarse: son placeholders feos que el resolver debe reemplazar
        por una mercaderia real.
        """
        for field in ("nombre_compra", "name", "descripcion", "producto_nombre"):
            value = row.get(field)
            text = str(value or "").strip().lower()
            normalized = normalize_text(value)
            if text and ("[rafam-" in text or "rafam:" in text or "mercaderia desarrollo" in normalized):
                return True
        return False

    @classmethod
    def _build_clean_mercaderia_index(cls, rows, field: str) -> dict[str, dict]:
        idx: dict[str, dict] = {}
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            if cls._is_generated_rafam_mercaderia(row):
                continue
            key = normalize_text(row.get(field))
            if not key:
                continue
            idx[key] = row
        return idx

    def _save_mercaderia_link(self, source_key: str, remote_id: int, *, barcode=None, nombre_compra=None) -> None:
        self._link_store.save_link(
            entity="mercaderia",
            source_key=source_key,
            remote_id=str(remote_id),
            barcode=str(barcode) if barcode else None,
            nombre_compra=str(nombre_compra)[:255] if nombre_compra else None,
        )
        self._mercaderia_resolved[source_key] = remote_id

    def _resolve_mercaderia_id(
        self,
        raw: dict,
        *,
        unidad_de_medida_id: int | None,
        proveedor_id: int | None,
        post_fn=None,
        allow_api: bool = False,
    ) -> int | None:
        """Resuelve el mercaderia_id de Paxapos.

        Estrategia (offline primero): cache -> link_store -> indice local del
        tenant -> resolver remoto (solo si ``allow_api`` y hay ``post_fn``).
        """
        description = raw.get("DESCRIPCION")
        normalized = normalize_text(description)
        if not normalized:
            return None

        source_key = self._mercaderia_description_source_key(normalized)

        cached = self._mercaderia_resolved.get(source_key)
        if cached is not None:
            return cached

        remote_id = to_int(self._link_store.get_remote_id("mercaderia", source_key))
        if remote_id is not None:
            self._mercaderia_resolved[source_key] = remote_id
            return remote_id

        for index in (self._mercaderias_by_nombre_compra, self._mercaderias_by_name):
            row = index.get(normalized)
            idx_id = to_int(row.get("id")) if row else None
            if idx_id is not None:
                self._save_mercaderia_link(
                    source_key,
                    idx_id,
                    barcode=row.get("barcode"),
                    nombre_compra=row.get("nombre_compra") or row.get("name"),
                )
                return idx_id

        if not allow_api or post_fn is None:
            return None

        resolved = self._resolve_mercaderia_via_api(
            post_fn,
            description=str(description).strip(),
            unidad_de_medida_id=unidad_de_medida_id,
            proveedor_id=proveedor_id,
        )
        api_id = to_int(resolved.get("mercaderia_id"))
        if api_id is None:
            raise RuntimeError(f"resolver_mercaderia no devolvio mercaderia_id para {description!r}")

        self._save_mercaderia_link(
            source_key,
            api_id,
            barcode=resolved.get("barcode"),
            nombre_compra=resolved.get("nombre_compra"),
        )
        return api_id

    def _resolve_mercaderia_via_api(
        self,
        post_fn,
        *,
        description: str,
        unidad_de_medida_id: int | None,
        proveedor_id: int | None,
    ) -> dict:
        name = str(description or "").strip()[:255]
        item: dict = {
            "name": name,
            "descripcion": name,
            "nombre_compra": name,
            "producto_nombre": name,
            "unidad_de_medida_id": unidad_de_medida_id or self._lookup.resolve_unidad_medida_id({}),
        }
        if proveedor_id is not None:
            item["proveedor_id"] = proveedor_id

        payload = {
            "item": item,
            "pedido": {"proveedor_id": proveedor_id} if proveedor_id is not None else {},
            "options": {"create_if_missing": True},
        }
        parsed = post_fn(self._resolver_url, payload)
        resolver = parsed.get("resolver") if isinstance(parsed, dict) else None
        if not isinstance(resolver, dict):
            raise RuntimeError(f"Respuesta invalida de resolver_mercaderia para {description!r}")
        if not resolver.get("success"):
            message = resolver.get("message") or "No se pudo resolver mercaderia"
            raise RuntimeError(str(message))
        if self._is_generated_rafam_mercaderia(resolver):
            visible_name = resolver.get("nombre_compra") or resolver.get("name") or resolver.get("descripcion")
            raise RuntimeError(
                f"resolver_mercaderia devolvio nombre generado para {description!r}: {visible_name!r}"
            )
        if not resolver.get("nombre_compra"):
            resolver["nombre_compra"] = resolver.get("name") or name
        return resolver


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
        payload_hash = raw.get("_PAYLOAD_HASH")

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
            payload_hash=payload_hash,
        )


# ââ Helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _compose_oc_observacion(raw: dict) -> str | None:
    """Return real RAFAM observation or None. Never fabricate a traza string."""
    obs = raw.get("OC_OBSERVACIONES")
    if obs and str(obs).strip():
        return str(obs).strip()[:255]
    return None


def _mercaderia_external_ref_oc_item(raw: dict) -> dict | None:
    """DEPRECATED: se reemplazó por resolución de ``mercaderia_id`` en el mapper.

    Se mantiene por compatibilidad con cualquier import externo, pero el path de
    envío ya no envía referencias externas de mercadería.
    """
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
