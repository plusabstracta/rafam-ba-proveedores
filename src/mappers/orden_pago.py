"""orden_pago.py â Mapper para entidad ORDEN_PAGO (egresos/pagos).

Agrupa filas por (EJERCICIO, NRO_OP), construye egresos con gastos
auto-creados y retenciones embebidas, y produce el payload ordenes_pago.
"""

from __future__ import annotations

import json
import logging

from ..utils import env_bool, format_date_only, parse_money, to_int
from ..retry_store import REASON_DEPENDENCY_MISSING
from ..validation import validate_amount
from .clasificaciones import code_str as clasif_code_str
from .clasificaciones import parent_code as clasif_parent_code
from .gasto_matching import elegir_gasto_portal, gasto_ids_pareados
from .solic_gastos import gasto_external_id
from .solic_gastos import persist_links as persist_links_gastos

logger = logging.getLogger(__name__)

# Campos del gasto del portal que se conservan en el edit (RAFAM manda el comprobante).
_PORTAL_KEEP_FIELDS = ("fecha", "importe_total", "importe_neto", "clasificacion_id")


def _partida_code_from_op_raw(raw: dict) -> str | None:
    """Codigo de partida `I.PP.PC.SP` desde las columnas OPI_ de un row de OP.

    Devuelve None si no hay INCISO (fila sin imputacion presupuestaria util).
    """
    inciso = to_int(raw.get("OPI_INCISO"))
    if inciso is None:
        return None
    par_prin = to_int(raw.get("OPI_PAR_PRIN")) or 0
    par_parc = to_int(raw.get("OPI_PAR_PARC")) or 0
    par_subp = to_int(raw.get("OPI_PAR_SUBP")) or 0
    return clasif_code_str(inciso, par_prin, par_parc, par_subp)


class OrdenPagoMapper:
    """Mapper stateful para ORDEN_PAGO."""

    def __init__(self, *, link_store, lookup_resolver, source_repo=None, retry_store=None, resolve_gastos_fn=None):
        self._link_store = link_store
        self._lookup = lookup_resolver
        self._source_repo = source_repo
        self._retry_store = retry_store
        # Consulta resolver_gasto de Paxapos (gastos ya creados en la OC por el portal).
        self._resolve_gastos_fn = resolve_gastos_fn
        # Contadores de retenciones descartadas (shared con retenciones mapper)
        self._retencion_skipped_no_catalog: int = 0
        self._retencion_skipped_no_match: dict[str, int] = {}
        # Contadores de clasificacion de gastos por partida presupuestaria.
        self._clasif_resolved_exact: int = 0
        self._clasif_resolved_fallback: int = 0
        self._clasif_missing: int = 0

    @staticmethod
    def _partida_depth(code: str) -> int:
        """Profundidad de un code `I.PP.PC.SP`: 1..4 segun el ultimo nivel no-cero."""
        depth = 1
        for i, part in enumerate(code.split(".")):
            if part != "0":
                depth = i + 1
        return depth

    @staticmethod
    def _op_source_key(ejercicio: int, nro_op: int) -> str:
        """Clave estable de la OP (misma forma que usa el link store y la cola)."""
        return json.dumps({"ejercicio": ejercicio, "nro_op": nro_op}, sort_keys=True)

    def _enqueue_op(
        self,
        key: tuple[int, int],
        reason: str,
        dry_run: bool,
        reason_detail: str = "dependency_missing",
    ) -> None:
        """Encola una OP salteada por dependencia faltante para reintentarla.

        Sin esto la OP se pierde para siempre: el watermark del checkpoint avanza
        igual que si se hubiera migrado y la fila nunca vuelve a entrar en la query.
        """
        if self._retry_store is None or dry_run:
            return
        try:
            self._retry_store.enqueue(
                "orden_pago",
                self._op_source_key(key[0], key[1]),
                REASON_DEPENDENCY_MISSING,
                f"OP {key[0]}-{key[1]}: {reason}",
                reason_detail=reason_detail,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("No se pudo encolar OP %s-%s: %s", key[0], key[1], exc)

    def _resolve_op(self, key: tuple[int, int], dry_run: bool) -> None:
        """Saca la OP de la cola de reintentos (ya esta migrada y al dia)."""
        if self._retry_store is None or dry_run:
            return
        try:
            self._retry_store.resolve("orden_pago", self._op_source_key(key[0], key[1]))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("No se pudo resolver OP %s-%s en la cola: %s", key[0], key[1], exc)

    def _enqueue_missing_proveedores(
        self, cod_provs: list[int], op_key: tuple[int, int], dry_run: bool
    ) -> None:
        """Pide a la entidad proveedores que traiga estos COD_PROV en la proxima corrida.

        La clave es ``str(COD_PROV)`` (formato de _proveedores_retry_filter y del
        link store). dependency_missing no cuenta intentos: espera lo que haga falta.
        """
        if self._retry_store is None or dry_run:
            return
        for cod_prov in cod_provs:
            try:
                self._retry_store.enqueue(
                    "proveedores",
                    str(cod_prov),
                    REASON_DEPENDENCY_MISSING,
                    f"proveedor requerido por OP {op_key[0]}-{op_key[1]}, sin link local",
                    reason_detail="required_by_orden_pago",
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("No se pudo encolar proveedor %s: %s", cod_prov, exc)

    def _choose_partida_code(self, counts: dict[str, int]) -> str | None:
        """Elige la partida representativa de un comprobante con imputacion repartida.

        Criterio: mas profunda primero; a igual profundidad, la mas frecuente;
        desempate lexical estable.
        """
        if not counts:
            return None
        return sorted(
            counts.items(),
            key=lambda kv: (self._partida_depth(kv[0]), kv[1], kv[0]),
            reverse=True,
        )[0][0]

    def _resolve_clasificacion_id(self, code: str | None) -> tuple[int | None, bool]:
        """Resuelve clasificacion_id remoto para un code de partida.

        Devuelve (clasificacion_id, used_fallback). Si no hay match exacto, sube
        por el arbol (4->3->2->1) hasta encontrar un ancestro migrado.
        """
        if not code:
            return None, False
        remote = self._link_store.get_remote_id("clasificacion", code)
        if remote:
            return int(remote), False
        parts = [int(x) for x in code.split(".")]
        while True:
            parent = clasif_parent_code(parts[0], parts[1], parts[2], parts[3])
            if parent is None:
                return None, False
            remote = self._link_store.get_remote_id("clasificacion", parent)
            if remote:
                return int(remote), True
            parts = [int(x) for x in parent.split(".")]

    def build_payload(
        self,
        columns: list[str],
        rows: list[tuple],
        *,
        dry_run: bool,
        payload_options: dict,
    ) -> tuple[dict | None, dict[str, dict]]:
        """Construye el payload de ordenes_pago + gastos para POST al migrator."""
        grouped: dict[tuple[int, int], dict] = {}
        grouped_gasto_refs: dict[tuple[int, int], list[str]] = {}
        grouped_cc_nros: dict[tuple[int, int], list[str]] = {}
        grouped_cc_keys: dict[tuple[int, int], list[tuple[str, str, str]]] = {}
        # Partidas presupuestarias por comprobante (cc_key -> {code: veces}).
        # Un mismo comprobante puede tener imputacion repartida en varias partidas.
        grouped_cc_partidas: dict[tuple[str, str, str], dict[str, int]] = {}
        grouped_pedido_ids: dict[tuple[int, int], list[int]] = {}
        grouped_pedido_internal_ids: dict[tuple[int, int], list[str]] = {}
        grouped_oc_source_keys: dict[tuple[int, int], list[str]] = {}
        grouped_has_opi: set[tuple[int, int]] = set()
        # ORDEN_PAGO.TIPO_OP: 'P' = presupuestaria (paga comprobantes de proveedor),
        # 'N' = no presupuestaria (giro de retenciones de sueldos, embargos, cajas
        # chicas). Solo se usa para clasificar OPs sin imputacion.
        grouped_tipo_op: dict[tuple[int, int], str] = {}
        raw_by_source_key: dict[str, dict] = {}
        cc_raw_by_key: dict[tuple[str, str, str], dict] = {}
        skipped_estado: dict[str, int] = {}
        skipped_confirmado: dict[str, int] = {}
        skipped_no_fech_confirm = 0
        skipped_importe_invalido: dict[str, int] = {}
        skipped_existing_keys: set[tuple[int, int]] = set()
        skipped_excluded_prov = 0
        skipped_permanent_keys: set[tuple[int, int]] = set()
        skipped_prov_sin_link: dict[tuple[int, int], int] = {}
        grouped_prov_sin_link: dict[tuple[int, int], list[int]] = {}

        # Una OP rechazada 'permanent' sigue entrando por la ventana de reproceso
        # (pending_reprocess_days) en cada corrida; sin esta exclusion se
        # reenviaba y fallaba igual hasta salir de la ventana.
        permanent_keys: set[str] = set()
        if self._retry_store is not None:
            try:
                permanent_keys = self._retry_store.permanent_external_ids("orden_pago")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Migrator [orden_pago]: no se pudo leer permanent_external_ids: %s", exc)

        for row in rows:
            raw = dict(zip(columns, row))
            ejercicio = to_int(raw.get("EJERCICIO"))
            nro_op = to_int(raw.get("NRO_OP"))
            if ejercicio is None or nro_op is None:
                continue

            key = (ejercicio, nro_op)
            grouped_tipo_op[key] = str(raw.get("TIPO_OP") or "").strip().upper()

            if any(
                str(raw.get(field) or "").strip()
                for field in ("OPI_NRO_REG_COMP", "OPI_TIPO_COMPROB", "OPI_NRO_COMPROB", "OPI_COD_PROV")
            ):
                grouped_has_opi.add(key)

            # Recolectar ref de gasto
            sg_deleg = to_int(raw.get("SG_DELEG_SOLIC"))
            sg_nro = to_int(raw.get("SG_NRO_SOLIC"))
            if sg_deleg is not None and sg_nro is not None:
                rafam_ref = f"SG-{ejercicio}-{sg_deleg}-{sg_nro}"
                refs = grouped_gasto_refs.setdefault(key, [])
                if rafam_ref not in refs:
                    refs.append(rafam_ref)

            # Recolectar nro_comprobante (CC)
            cc_nro = str(raw.get("OPI_NRO_COMPROB") or "").strip()
            if cc_nro:
                cc_nros = grouped_cc_nros.setdefault(key, [])
                if cc_nro not in cc_nros:
                    cc_nros.append(cc_nro)
                cc_tipo = str(raw.get("OPI_TIPO_COMPROB") or "").strip()
                cc_prov = str(raw.get("OPI_COD_PROV") or "").strip()
                cc_key = (cc_tipo, cc_nro, cc_prov)
                cc_keys = grouped_cc_keys.setdefault(key, [])
                if cc_key not in cc_keys:
                    cc_keys.append(cc_key)
                # Acumular la partida imputada de esta fila OPI para el comprobante.
                partida_code = _partida_code_from_op_raw(raw)
                if partida_code is not None:
                    counts = grouped_cc_partidas.setdefault(cc_key, {})
                    counts[partida_code] = counts.get(partida_code, 0) + 1
                existing = cc_raw_by_key.get(cc_key)
                if existing is None or (
                    raw.get("CTA_IMPORTE_COMPR") is not None
                    and existing.get("CTA_IMPORTE_COMPR") is None
                ):
                    cc_raw_by_key[cc_key] = raw

            # pedido_id resolution
            pedido_id = _pedido_id_from_op_row(raw)
            if pedido_id is None:
                pedido_id = self._resolve_pedido_id_from_oc_link(raw)
            if pedido_id is not None:
                pedido_ids = grouped_pedido_ids.setdefault(key, [])
                if pedido_id not in pedido_ids:
                    pedido_ids.append(pedido_id)

            # internal_id candidato para diagnostico
            oc_ej = to_int(raw.get("SG_OC_EJERCICIO"))
            oc_nro = to_int(raw.get("SG_OC_NRO"))
            if oc_ej is not None and oc_nro is not None:
                internal_id = f"{oc_ej % 100}-{oc_nro}"
                internals = grouped_pedido_internal_ids.setdefault(key, [])
                if internal_id not in internals:
                    internals.append(internal_id)

                oc_uni = to_int(raw.get("SG_OC_UNI_COMPRA"))
                if oc_uni is not None:
                    oc_sk = json.dumps(
                        {"ejercicio": oc_ej, "nro_oc": oc_nro, "uni_compra": oc_uni},
                        sort_keys=True,
                    )
                    oc_sks = grouped_oc_source_keys.setdefault(key, [])
                    if oc_sk not in oc_sks:
                        oc_sks.append(oc_sk)

            estado = str(raw.get("ESTADO_OP", "")).strip().upper()
            if estado != "C":
                skipped_estado[estado or "(vacio)"] = skipped_estado.get(estado or "(vacio)", 0) + 1
                continue
            confirmado = str(raw.get("CONFIRMADO", "")).strip().upper()
            if confirmado != "S":
                skipped_confirmado[confirmado or "(vacio)"] = skipped_confirmado.get(confirmado or "(vacio)", 0) + 1
                continue
            fecha_confirm = format_date_only(raw.get("FECH_CONFIRM") or "")
            if not fecha_confirm:
                skipped_no_fech_confirm += 1
                continue

            sk = json.dumps({"ejercicio": ejercicio, "nro_op": nro_op}, sort_keys=True)
            if sk in permanent_keys:
                skipped_permanent_keys.add(key)
                continue
            # ABM: si la OP ya fue migrada, re-enviarla como MODIFICACION solo si
            # cambio en RAFAM (comparando el snapshot guardado en el link:
            # importe_total / estado_op / confirmado / fech_confirm). Si no cambio se
            # saltea. Al re-enviar se inyecta el id de Egreso (ver egreso["id"]) para
            # que Paxapos actualice por id (insert-or-update) sin duplicar la OP.
            op_remote_id = None
            existing_op = self._link_store.get_link("orden_pago", sk)
            if existing_op and existing_op.get("remote_id"):
                importe_snap = str(raw.get("IMPORTE_TOTAL")) if raw.get("IMPORTE_TOTAL") is not None else None
                unchanged = (
                    (existing_op.get("estado_op") or None) == (estado or None)
                    and (existing_op.get("confirmado") or None) == (confirmado or None)
                    and (existing_op.get("fech_confirm") or None) == (fecha_confirm or None)
                    and (existing_op.get("importe_total") or None) == importe_snap
                )
                if unchanged:
                    skipped_existing_keys.add(key)
                    # Ya migrada y al dia: si venia de la cola de reintentos, cerrarla.
                    self._resolve_op(key, dry_run)
                    continue
                op_remote_id = existing_op.get("remote_id")

            if key in grouped:
                continue

            raw_by_source_key[sk] = raw

            # Blocklist: OP cuyo proveedor esta excluido no se migra.
            from ..config import is_cod_prov_excluded
            prov_candidate = next(
                (
                    c
                    for c in (raw.get("COD_PROV"), raw.get("OPI_COD_PROV"), raw.get("SG_OC_COD_PROV"))
                    if c is not None and str(c).strip() != ""
                ),
                None,
            )
            if is_cod_prov_excluded(prov_candidate):
                skipped_excluded_prov += 1
                # Nunca va a migrar: si quedo encolada antes de excluirla, cerrarla.
                self._resolve_op(key, dry_run)
                logger.info(
                    "Migrator [orden_pago] OP %s-%s: omitida - proveedor excluido (COD_PROV=%s)",
                    ejercicio, nro_op, prov_candidate,
                )
                raw_by_source_key.pop(sk, None)
                continue

            # Resolver proveedor_id
            remote_prov_id: int | None = None
            cod_provs_sin_link: list[int] = []
            for cod_prov in (raw.get("COD_PROV"), raw.get("OPI_COD_PROV"), raw.get("SG_OC_COD_PROV")):
                cod_prov_norm = to_int(cod_prov)
                if cod_prov_norm is None:
                    continue
                remote_prov = self._link_store.get_remote_id("proveedores", str(cod_prov_norm))
                if remote_prov:
                    remote_prov_id = int(remote_prov)
                    break
                if cod_prov_norm not in cod_provs_sin_link:
                    cod_provs_sin_link.append(cod_prov_norm)
            if remote_prov_id is None and cod_provs_sin_link:
                grouped_prov_sin_link[key] = cod_provs_sin_link

            # Validamos el importe usando la funcion centralizada de validacion.
            # Esto previene errores de overflow DECIMAL(14,2) en base de datos
            # y asegura un redondeo simetrico y consistente.
            importe_raw = raw.get("IMPORTE_TOTAL")
            res_importe = validate_amount(
                importe_raw,
                field="IMPORTE_TOTAL",
                allow_zero=False,
                allow_negative=False,
                required=True,
            )
            if not res_importe.ok:
                reason = res_importe.reason or ""
                if "requerido y vacio" in reason:
                    skipped_importe_invalido["null"] = skipped_importe_invalido.get("null", 0) + 1
                    logger.warning(
                        "Migrator [orden_pago] OP %s-%s omitida: IMPORTE_TOTAL es NULL en RAFAM",
                        ejercicio, nro_op,
                    )
                elif "negativo" in reason or "cero" in reason:
                    skipped_importe_invalido["<=0"] = skipped_importe_invalido.get("<=0", 0) + 1
                    logger.warning(
                        "Migrator [orden_pago] OP %s-%s omitida: IMPORTE_TOTAL=%s (probable ajuste contable o anulacion)",
                        ejercicio, nro_op, importe_raw,
                    )
                else:
                    skipped_importe_invalido["no_parseable"] = skipped_importe_invalido.get("no_parseable", 0) + 1
                    logger.warning(
                        "Migrator [orden_pago] OP %s-%s omitida: IMPORTE_TOTAL %r no parseable o invalido: %s",
                        ejercicio, nro_op, importe_raw, reason,
                    )
                continue
            total = res_importe.value

            egreso: dict = {
                "identificador_pago": f"RAFAM-OP-{ejercicio}-{nro_op}",
                "total": total,
                # Default por ahora; se sobreescribe abajo con la forma de pago
                # real resuelta desde COMPROBANTES.ORIGEN_TIPO por OP.
                "tipo_de_pago_id": self._lookup.resolve_tipo_pago_id(),
                "estado": 3,
                "fecha": fecha_confirm,
            }
            # MODIFICACION por id: la OP ya existe en Paxapos y cambio en RAFAM, se
            # inyecta el id de Egreso para que el controller actualice ese registro
            # exacto (no duplica; preserva el PDF adjunto del proveedor).
            if op_remote_id:
                try:
                    egreso["id"] = int(op_remote_id)
                except (TypeError, ValueError):
                    pass

            concepto = raw.get("CONCEPTO") or raw.get("OBSERVACIONES")
            if concepto and str(concepto).strip():
                egreso["observacion"] = str(concepto).strip()[:255]

            grouped[key] = {
                "external_id": {"ejercicio": ejercicio, "nro_op": nro_op},
                "importe_total": total,
                "Egreso": egreso,
            }
            if remote_prov_id is not None:
                grouped[key]["proveedor_id"] = remote_prov_id

        # Forma de pago real por OP desde COMPROBANTES.ORIGEN_TIPO (via EGRESOS).
        # ORDEN_PAGO no tiene la forma de pago; sin esto todas las OP quedaban como
        # Transferencia bancaria. Si viene None se conserva el default del egreso.
        if grouped and self._source_repo is not None:
            forma_pago_by_op = self._source_repo.fetch_forma_pago_for_ops(list(grouped.keys()))
            if forma_pago_by_op:
                for op_key, origen_tipo in forma_pago_by_op.items():
                    op_entry = grouped.get(op_key)
                    if op_entry is not None:
                        op_entry["Egreso"]["tipo_de_pago_id"] = (
                            self._lookup.resolve_tipo_pago_id(origen_tipo)
                        )

        # Fetch deducciones por OP
        deducciones_by_op: dict[tuple[int, int], list[dict]] = {}
        if grouped and self._source_repo is not None:
            result = self._source_repo.fetch_deducciones_for_ops(list(grouped.keys()))
            if result is not None:
                deducciones_by_op = result

        ordenes_pago: list[dict] = []
        included_cc_keys: list[tuple[str, str, str]] = []
        included_cc_key_set: set[tuple[str, str, str]] = set()
        cc_key_to_pedido_id: dict[tuple[str, str, str], int] = {}
        cc_key_to_op_keys: dict[tuple[str, str, str], list[tuple[int, int]]] = {}
        skipped_no_gasto = 0
        skipped_no_opi = 0
        skipped_no_presupuestaria = 0
        skipped_no_comprobante = 0
        skipped_no_oc_canonica = 0
        skipped_no_oc_link = 0
        skipped_multiple_oc = 0
        sent_sin_oc = 0
        warned_facturas_exceed_oc = 0
        # Pagos de gasto directo (con factura real en CTA_COMPROB pero sin OC
        # en REG_COMP: servicios, etc.). Con el flag activo se envian SIN
        # pedido_id: Paxapos crea/deduplica el Gasto por proveedor+factura_nro
        # y vincula el Egreso igual. Con el flag apagado se omiten (solo pagos
        # respaldados por OC), comportamiento historico.
        migrar_sin_oc = env_bool("RAFAM_MIGRAR_OP_SIN_OC", "true")

        for key, op in grouped.items():
            cc_nros = grouped_cc_nros.get(key, [])
            if not cc_nros:
                skipped_no_gasto += 1
                if key not in grouped_has_opi:
                    if grouped_tipo_op.get(key) == "N":
                        # OP no presupuestaria sin ninguna fila en ORDEN_PAGO_IMPUT:
                        # no paga un comprobante de proveedor y nunca va a tener
                        # uno. Encolarla como dependencia la dejaba 'pending' para
                        # siempre (340 OP en sep-2026). Fuera de alcance: se cierra.
                        skipped_no_presupuestaria += 1
                        self._resolve_op(key, dry_run)
                        logger.debug(
                            "Migrator [orden_pago] OP %s-%s omitida: TIPO_OP=N sin imputacion (fuera de alcance)",
                            key[0], key[1],
                        )
                        continue
                    skipped_no_opi += 1
                    self._enqueue_op(key, "sin ORDEN_PAGO_IMPUT", dry_run, "missing_payment_imputation")
                    logger.debug(
                        "Migrator [orden_pago] OP %s-%s omitida: sin ORDEN_PAGO_IMPUT",
                        key[0], key[1],
                    )
                else:
                    skipped_no_comprobante += 1
                    self._enqueue_op(key, "sin OPI_NRO_COMPROB", dry_run, "missing_receipt_number")
                    logger.debug(
                        "Migrator [orden_pago] OP %s-%s omitida: sin OPI_NRO_COMPROB",
                        key[0], key[1],
                    )
                continue

            if len(cc_nros) == 1:
                op["gasto_nro_comprobante"] = cc_nros[0]
            else:
                op["gasto_nro_comprobante"] = cc_nros

            pedido_ids = grouped_pedido_ids.get(key, [])
            pedido_id: int | None = None
            if len(pedido_ids) == 1:
                pedido_id = pedido_ids[0]
                op["pedido_id"] = pedido_id
            elif len(pedido_ids) > 1:
                skipped_multiple_oc += 1
                self._enqueue_op(
                    key,
                    f"multiples OCs/pedido_id ({pedido_ids})",
                    dry_run,
                    "multiple_orders",
                )
                logger.warning(
                    "Migrator [orden_pago] OP %s-%s omitida: multiples OCs/pedido_id recibidos (%s)",
                    key[0], key[1], pedido_ids,
                )
                continue
            else:
                oc_source_keys = grouped_oc_source_keys.get(key, [])
                internal_ids = grouped_pedido_internal_ids.get(key, [])
                if not oc_source_keys:
                    # Gasto directo: la OP tiene factura imputada (paso el check
                    # de cc_nros arriba) pero su REG_COMP no referencia OC — la
                    # OC no va a existir nunca. Con el flag activo se envia sin
                    # pedido_id; sin flag, se omite y encola (historico).
                    if migrar_sin_oc:
                        sent_sin_oc += 1
                        logger.debug(
                            "Migrator [orden_pago] OP %s-%s: gasto directo sin OC — se envia sin pedido_id",
                            key[0], key[1],
                        )
                    else:
                        skipped_no_oc_canonica += 1
                        self._enqueue_op(
                            key,
                            "sin OC canonica en REG_COMP",
                            dry_run,
                            "missing_canonical_order",
                        )
                        logger.debug(
                            "Migrator [orden_pago] OP %s-%s omitida: sin OC canonica en "
                            "REG_COMP imputado por ORDEN_PAGO_IMPUT (pedido_internal_id candidatos=%s)",
                            key[0], key[1], internal_ids,
                        )
                        continue
                else:
                    skipped_no_oc_link += 1
                    self._enqueue_op(
                        key,
                        "OC aun no migrada en Paxapos",
                        dry_run,
                        "order_not_migrated",
                    )
                    logger.debug(
                        "Migrator [orden_pago] OP %s-%s omitida: sin OC migrada en link_store "
                        "(oc_source_keys=%s, pedido_internal_id candidatos=%s)",
                        key[0], key[1], oc_source_keys, internal_ids,
                    )
                    continue

            prov_sin_link = grouped_prov_sin_link.get(key)
            if prov_sin_link:
                # Sin proveedor_id el receptor no puede auto-crear el gasto y rechaza
                # la OP hasta agotar max_attempts. El proveedor no llego por el cursor
                # FECHA_ULT_COMP (NULL cuando nunca compro): se encola en su propia
                # cola para que _proveedores_retry_filter lo reinyecte por COD_PROV,
                # y la OP espera como dependencia.
                self._enqueue_missing_proveedores(prov_sin_link, key, dry_run)
                self._enqueue_op(
                    key,
                    f"proveedor COD_PROV={prov_sin_link[0]} aun no migrado en Paxapos",
                    dry_run,
                    reason_detail="provider_not_migrated",
                )
                skipped_prov_sin_link[key] = prov_sin_link[0]
                continue

            for cc_key in grouped_cc_keys.get(key, []):
                if cc_key not in included_cc_key_set:
                    included_cc_key_set.add(cc_key)
                    included_cc_keys.append(cc_key)
                if pedido_id is not None:
                    cc_key_to_pedido_id.setdefault(cc_key, pedido_id)
                cc_key_to_op_keys.setdefault(cc_key, []).append(key)

            # Mapear deducciones
            ret_payload: list[dict] = []
            for ded in deducciones_by_op.get(key, []):
                mapped = self._map_deduccion_dict(ded, key[0], key[1])
                if mapped is not None:
                    ret_payload.append(mapped)
            if ret_payload:
                total_egreso = op["Egreso"]["total"]
                suma_retenciones = sum(r["monto_retenido"] for r in ret_payload)
                if suma_retenciones > total_egreso:
                    logger.warning(
                        "Migrator [orden_pago] OP %s-%s: retenciones ($%.2f) superan total ($%.2f). "
                        "Descartando retenciones para evitar rechazo de Paxapos.",
                        key[0], key[1], suma_retenciones, total_egreso,
                    )
                else:
                    op["retenciones"] = ret_payload

            # No enviamos el importe_neto a nivel de OP, sino por comprobante.
            # importe_liquido = op.pop("_importe_liquido", None)
            # if importe_liquido is not None:
            #     op["importe_neto"] = importe_liquido

            # ValidaciÃ³n: suma facturas vs total OC
            oc_sks = grouped_oc_source_keys.get(key, [])
            if oc_sks and grouped_cc_keys.get(key):
                suma_facturas = 0.0
                for ck in grouped_cc_keys[key]:
                    cr = cc_raw_by_key.get(ck)
                    if cr and cr.get("CTA_IMPORTE_COMPR") is not None:
                        res_factura = validate_amount(
                            cr["CTA_IMPORTE_COMPR"],
                            field="CTA_IMPORTE_COMPR",
                            allow_zero=True,
                            allow_negative=False,
                            required=False,
                        )
                        if res_factura.ok and res_factura.value is not None:
                            suma_facturas += res_factura.value
                if suma_facturas > 0:
                    for oc_sk in oc_sks:
                        oc_link = self._link_store.get_link("orden_compra", oc_sk)
                        if oc_link and oc_link.get("importe_tot"):
                            res_oc_total = validate_amount(
                                oc_link["importe_tot"],
                                field="importe_tot",
                                allow_zero=True,
                                allow_negative=False,
                                required=False,
                            )
                            if not res_oc_total.ok or res_oc_total.value is None:
                                continue
                            oc_total = res_oc_total.value
                            if suma_facturas > oc_total:
                                warned_facturas_exceed_oc += 1
                                logger.warning(
                                    "Migrator [orden_pago] OP %s-%s: suma facturas ($%.2f) "
                                    "supera total OC ($%.2f). Comprobantes: %s. OC: %s",
                                    key[0], key[1], suma_facturas, oc_total,
                                    cc_nros, oc_sk,
                                )

            ordenes_pago.append(op)

        # Log warnings
        if skipped_no_gasto:
            logger.warning(
                "Migrator [orden_pago]: %d OPs omitidas sin gasto vinculado "
                "(sin ORDEN_PAGO_IMPUT=%d, sin OPI_NRO_COMPROB=%d, no presupuestarias TIPO_OP=N=%d)",
                skipped_no_gasto, skipped_no_opi, skipped_no_comprobante, skipped_no_presupuestaria,
            )
        if sent_sin_oc:
            logger.info(
                "Migrator [orden_pago]: %d OPs de gasto directo (sin OC) enviadas sin pedido_id "
                "(RAFAM_MIGRAR_OP_SIN_OC=true)",
                sent_sin_oc,
            )
        if skipped_no_oc_canonica:
            logger.warning(
                "Migrator [orden_pago]: %d OPs omitidas sin OC canonica en RAFAM; "
                "no se crean pagos ni gastos sueltos (RAFAM_MIGRAR_OP_SIN_OC=false)",
                skipped_no_oc_canonica,
            )
        if skipped_no_oc_link:
            logger.warning(
                "Migrator [orden_pago]: %d OPs omitidas sin OC migrada/linkeada; "
                "no se crean pagos ni gastos sueltos",
                skipped_no_oc_link,
            )
        if skipped_multiple_oc:
            logger.warning(
                "Migrator [orden_pago]: %d OPs omitidas por multiples OCs en un mismo pago; "
                "se requiere mapeo por gasto antes de enviarlas",
                skipped_multiple_oc,
            )
        if warned_facturas_exceed_oc:
            logger.warning(
                "Migrator [orden_pago]: %d OPs con suma de facturas que supera el total de la OC vinculada",
                warned_facturas_exceed_oc,
            )
        if skipped_estado:
            logger.info("Migrator [orden_pago]: OPs omitidas por estado: %s", skipped_estado)
        if skipped_confirmado:
            logger.info("Migrator [orden_pago]: OPs omitidas por CONFIRMADO: %s", skipped_confirmado)
        if skipped_no_fech_confirm:
            logger.info("Migrator [orden_pago]: %d OPs omitidas sin FECH_CONFIRM", skipped_no_fech_confirm)
        if skipped_importe_invalido:
            logger.warning(
                "Migrator [orden_pago]: OPs omitidas por IMPORTE_TOTAL invalido: %s. "
                "Esto evita crear Egresos en $0 que ensucian el panel de pagos.",
                skipped_importe_invalido,
            )
        if skipped_existing_keys:
            logger.info("Migrator [orden_pago]: %d OPs omitidas por link local existente", len(skipped_existing_keys))
        if skipped_permanent_keys:
            logger.info(
                "Migrator [orden_pago]: %d OPs 'permanent' en la cola, no se reenvian (requeue para reintentar)",
                len(skipped_permanent_keys),
            )
        if skipped_excluded_prov:
            logger.info("Migrator [orden_pago]: %d OPs omitidas por proveedor excluido", skipped_excluded_prov)
        if skipped_prov_sin_link:
            logger.warning(
                "Migrator [orden_pago]: %d OPs retenidas por proveedor sin migrar (encoladas junto con el "
                "proveedor); COD_PROV: %s",
                len(skipped_prov_sin_link),
                sorted(set(skipped_prov_sin_link.values())),
            )
        self._flush_retencion_skip_counters("orden_pago")

        if not ordenes_pago:
            logger.info("Migrator [orden_pago]: lote vacio luego del mapeo")
            return None, {}

        # Construir gastos[] con datos de CTA_COMPROB. Antes de crear, parear cada
        # comprobante con el gasto que Paxapos ya tiene en la OC (subido por el
        # proveedor via portal): si hay match se manda {id, ...} para que RAFAM lo
        # complete con un edit, no un gasto nuevo. Sin esto quedaban dos gastos por
        # factura: el del portal (PDF, sin datos) y el de RAFAM (datos, sin PDF).
        portal_by_pedido = self._fetch_gastos_portal(
            sorted({p for p in cc_key_to_pedido_id.values() if p is not None})
        )
        gastos_payload: list[dict] = []
        gasto_raw_by_sk: dict[str, dict] = {}
        seen_dedup_keys: set[tuple] = set()
        skipped_gastos_incomplete = 0
        matched_stats: dict[str, int] = {}
        ambiguous_count = 0
        # OPs con algun comprobante sin bloque gasto pero con gasto del portal libre en
        # su OC: si se enviaran, Paxapos autocrearia el gasto desde gasto_nro_comprobante.
        ops_to_hold: set[tuple[int, int]] = set()
        for cc_key in included_cc_keys:
            cc_raw = cc_raw_by_key.get(cc_key)
            if cc_raw is None:
                continue
            cc_raw_for_gasto = dict(cc_raw)
            pedido_id = cc_key_to_pedido_id.get(cc_key)
            if pedido_id is not None:
                cc_raw_for_gasto["_PAXAPOS_PEDIDO_ID"] = pedido_id
            # Clasificacion del gasto: elegir la partida representativa del
            # comprobante y resolver su clasificacion_id remoto (con fallback al
            # ancestro migrado si el code exacto no esta en el link_store).
            chosen_code = self._choose_partida_code(grouped_cc_partidas.get(cc_key, {}))
            clasif_id, used_fallback = self._resolve_clasificacion_id(chosen_code)
            if clasif_id is not None:
                cc_raw_for_gasto["_PAXAPOS_CLASIFICACION_ID"] = clasif_id
                if used_fallback:
                    self._clasif_resolved_fallback += 1
                    logger.debug(
                        "Migrator [orden_pago] CC %s: clasificacion por fallback desde code %s -> id %s",
                        cc_key, chosen_code, clasif_id,
                    )
                else:
                    self._clasif_resolved_exact += 1
            elif chosen_code is not None:
                self._clasif_missing += 1
                logger.debug(
                    "Migrator [orden_pago] CC %s: sin clasificacion para code %s (ni fallback)",
                    cc_key, chosen_code,
                )
            gasto, dedup_key = self._build_gasto_from_op_row(cc_raw_for_gasto)
            if gasto is None:
                skipped_gastos_incomplete += 1
                if pedido_id is not None and portal_by_pedido.get(pedido_id):
                    for op_key in cc_key_to_op_keys.get(cc_key, []):
                        ops_to_hold.add(op_key)
                continue
            if dedup_key in seen_dedup_keys:
                continue
            seen_dedup_keys.add(dedup_key)

            if pedido_id is not None:
                pool = portal_by_pedido.get(pedido_id, [])
                match = elegir_gasto_portal(pool, gasto["Gasto"])
                if match.gasto is not None:
                    gasto["Gasto"] = self._merge_edit_gasto_portal(match.gasto, gasto["Gasto"])
                    portal_by_pedido[pedido_id] = [g for g in pool if g is not match.gasto]
                    matched_stats[match.matched_by] = matched_stats.get(match.matched_by, 0) + 1
                elif match.candidates:
                    ambiguous_count += 1
                    nota = (
                        f"REVISAR: posible duplicado de gasto(s) #{', #'.join(str(c) for c in match.candidates)} "
                        f"en OC #{pedido_id}"
                    )
                    obs = gasto["Gasto"].get("observacion")
                    gasto["Gasto"]["observacion"] = f"{obs} | {nota}" if obs else nota
                    logger.warning(
                        "Migrator [orden_pago] CC %s en OC %s: no se pudo parear con gastos %s; se crea marcado REVISAR",
                        cc_key, pedido_id, match.candidates,
                    )

            gastos_payload.append(gasto)
            sk = json.dumps(gasto["external_id"], sort_keys=True)
            raw_for_link = dict(cc_raw_for_gasto)
            raw_for_link["_pedido_id"] = pedido_id
            raw_for_link["_nro_comprobante"] = cc_key[1]
            gasto_raw_by_sk[sk] = raw_for_link

        if ops_to_hold:
            ordenes_pago = [
                op for op in ordenes_pago
                if (op["external_id"]["ejercicio"], op["external_id"]["nro_op"]) not in ops_to_hold
            ]
            held_sks = set()
            for op_key in ops_to_hold:
                held_sks.add(self._op_source_key(op_key[0], op_key[1]))
                self._enqueue_op(op_key, "comprobante sin datos y OC con gasto del portal sin parear", dry_run)
            raw_by_source_key = {sk: r for sk, r in raw_by_source_key.items() if sk not in held_sks}
            logger.warning(
                "Migrator [orden_pago]: %d OPs retenidas (comprobante incompleto con gasto del portal en la OC)",
                len(ops_to_hold),
            )
        if skipped_gastos_incomplete:
            logger.info(
                "Migrator [orden_pago]: %d comprobantes sin datos suficientes para auto-crear gasto",
                skipped_gastos_incomplete,
            )
        if matched_stats or ambiguous_count:
            logger.info(
                "Migrator [orden_pago] pareo con gastos del portal: %s, ambiguos=%d",
                matched_stats or {}, ambiguous_count,
            )
        if self._clasif_resolved_exact or self._clasif_resolved_fallback or self._clasif_missing:
            logger.info(
                "Migrator [orden_pago] clasificacion de gastos: %d exactas, %d por fallback, %d sin clasificar",
                self._clasif_resolved_exact,
                self._clasif_resolved_fallback,
                self._clasif_missing,
            )

        if not ordenes_pago:
            logger.info("Migrator [orden_pago]: lote vacio luego de retener OPs")
            return None, {}

        payload = {
            "dry_run": dry_run,
            "options": payload_options,
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": gastos_payload,
            "ordenes_pago": ordenes_pago,
        }

        # Guardar metadata para post-send
        self._last_grouped_oc_source_keys = grouped_oc_source_keys
        self._last_skipped_no_gasto = skipped_no_gasto
        self._last_gastos_count = len(gastos_payload)
        self._last_gasto_raw_by_sk = gasto_raw_by_sk
        return payload, raw_by_source_key

    def _fetch_gastos_portal(self, pedido_ids: list[int]) -> dict[int, list[dict]]:
        """Gastos que Paxapos ya tiene en esas OCs, sin los que este script ya pareo."""
        if not pedido_ids or self._resolve_gastos_fn is None:
            return {}
        resolver = self._resolve_gastos_fn(pedido_ids, []) or {}
        gastos = resolver.get("gastos", []) if isinstance(resolver, dict) else []
        ya_pareados = gasto_ids_pareados(self._link_store)
        by_pedido: dict[int, list[dict]] = {}
        for g in gastos:
            if not isinstance(g, dict) or g.get("id") in (None, ""):
                continue
            if int(g["id"]) in ya_pareados:
                continue
            pid = to_int(g.get("pedido_id"))
            if pid is None:
                continue
            by_pedido.setdefault(pid, []).append(g)
        return by_pedido

    @staticmethod
    def _merge_edit_gasto_portal(portal: dict, rafam: dict) -> dict:
        """Edit por id del gasto del portal: comprobante de RAFAM, importes/fecha del portal.

        Paxapos guarda solo los campos enviados: el PDF (media_id) y la
        observacion no viajan y quedan intactos. fecha/importes son obligatorios
        para el receptor, asi que se reenvian los que ya tiene el gasto cuando
        existen (los cargo el proveedor o los leyo la IA del comprobante real).
        """
        merged = dict(rafam)
        merged["id"] = int(portal["id"])
        for field in _PORTAL_KEEP_FIELDS:
            value = portal.get(field)
            if value in (None, "", 0, 0.0, "0", "0.00"):
                continue
            merged[field] = value
        return merged

    
    def _build_gasto_from_op_row(self, raw: dict) -> tuple[dict | None, tuple | None]:
        """Construye un bloque Gasto desde un row de OP enriquecido con CTA_COMPROB."""
        cc_nro = str(raw.get("OPI_NRO_COMPROB") or "").strip()
        if not cc_nro:
            return None, None

        remote_prov_id: int | None = None
        for cod_prov in (raw.get("OPI_COD_PROV"), raw.get("SG_OC_COD_PROV"), raw.get("COD_PROV")):
            cod_prov_norm = to_int(cod_prov)
            if cod_prov_norm is None:
                continue
            remote_prov = self._link_store.get_remote_id("proveedores", str(cod_prov_norm))
            if remote_prov:
                remote_prov_id = int(remote_prov)
                break
        if remote_prov_id is None:
            return None, None

        importe_raw = raw.get("CTA_IMPORTE_COMPR")
        res_total = validate_amount(
            importe_raw,
            field="CTA_IMPORTE_COMPR",
            allow_zero=True,
            allow_negative=False,
            required=True,
        )
        if not res_total.ok:
            return None, None
        importe_total = res_total.value

        importe_neto = parse_money(raw.get("CTA_IMPORTE_NETO"))
        if importe_neto is None:
            importe_neto = parse_money(raw.get("CTA_IMPORTE_SIN_IVA"))
        if importe_neto is None:
            importe_neto = importe_total

        fecha = format_date_only(raw.get("CTA_FECH_COMPROB"))
        if not fecha:
            return None, None

        gasto_data: dict = {
            "fecha": fecha,
            "importe_total": importe_total,
            "importe_neto": importe_neto,
            "proveedor_id": remote_prov_id,
        }
        pedido_id = to_int(raw.get("_PAXAPOS_PEDIDO_ID") or raw.get("pedido_id"))
        if pedido_id is not None:
            gasto_data["pedido_id"] = pedido_id

        clasif_id = to_int(raw.get("_PAXAPOS_CLASIFICACION_ID"))
        if clasif_id is not None:
            gasto_data["clasificacion_id"] = clasif_id

        tipo_factura_id = self._lookup.resolve_tipo_factura_id(raw.get("OPI_TIPO_COMPROB"))
        if tipo_factura_id is not None:
            gasto_data["tipo_factura_id"] = tipo_factura_id

        dash_pos = cc_nro.find("-")
        if dash_pos > 0:
            punto_de_venta = cc_nro[:dash_pos]
            factura_nro = cc_nro[dash_pos + 1:]
        else:
            punto_de_venta = ""
            factura_nro = cc_nro
        gasto_data["punto_de_venta"] = punto_de_venta
        gasto_data["factura_nro"] = factura_nro

        fech_venc = format_date_only(raw.get("CTA_FECH_VENCIM"))
        if fech_venc:
            gasto_data["fecha_vencimiento"] = fech_venc

        sg_ej = to_int(raw.get("EJERCICIO"))
        sg_deleg = to_int(raw.get("SG_DELEG_SOLIC"))
        sg_nro = to_int(raw.get("SG_NRO_SOLIC"))
        if sg_ej is not None and sg_deleg is not None and sg_nro is not None:
            external_id = gasto_external_id(sg_ej, sg_deleg, sg_nro)
        else:
            external_id = {
                "rafam_ref": (
                    f"CC-{raw.get('EJERCICIO')}-{raw.get('OPI_TIPO_COMPROB') or ''}-"
                    f"{cc_nro}-{raw.get('OPI_COD_PROV') or ''}"
                )
            }

        dedup_key = (remote_prov_id, punto_de_venta, factura_nro, tipo_factura_id)
        return {"external_id": external_id, "Gasto": gasto_data}, dedup_key

    def _map_deduccion_dict(self, ded: dict, ejercicio: int, nro_op: int) -> dict | None:
        """Mapea una deducciÃ³n de ORDEN_PAGO_DEDUC al formato Paxapos."""
        codigo_deduc = ded.get("codigo_deduc")
        importe_reten = ded.get("importe_reten")
        if codigo_deduc is None or importe_reten is None:
            return None

        cod_text = str(codigo_deduc).strip()
        if not cod_text:
            return None

        res_monto = validate_amount(
            importe_reten,
            field="importe_reten",
            allow_zero=False,
            allow_negative=False,
            required=True,
        )
        if not res_monto.ok:
            return None
        monto_retenido = res_monto.value

        descripcion = str(ded.get("descripcion") or "").strip()

        tipo_retencion_id = self._lookup.resolve_tipo_retencion_id(cod_text, descripcion)
        if tipo_retencion_id is None:
            alias = self._lookup.retencion_alias(descripcion or cod_text)
            if alias:
                tipo_retencion_id = self._lookup.resolve_tipo_retencion_id_by_alias(alias)

        if tipo_retencion_id is None:
            if not self._lookup.tipos_retencion:
                self._retencion_skipped_no_catalog += 1
            else:
                key = descripcion or f"CODIGO_DEDUC={cod_text}"
                self._retencion_skipped_no_match[key] = self._retencion_skipped_no_match.get(key, 0) + 1
            return None

        retencion: dict = {
            "external_id": {
                "ejercicio": ejercicio,
                "nro_op": nro_op,
                "codigo_deduc": cod_text,
            },
            "monto_retenido": monto_retenido,
            "numero_certificado": f"RAFAM-RET-{ejercicio}-{nro_op}-{cod_text}",
            "tipo_impuesto_id": tipo_retencion_id,
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

        comprob_deduc = ded.get("comprob_deduc")
        if comprob_deduc is not None and str(comprob_deduc).strip():
            retencion["numero_certificado"] = str(comprob_deduc).strip()

        if descripcion:
            retencion["observacion"] = f"Deduccion RAFAM {descripcion} OP {ejercicio}/{nro_op}"

        return retencion

    def _resolve_pedido_id_from_oc_link(self, raw: dict) -> int | None:
        """Resuelve pedido_id desde link_store con OC RAFAM del REG_COMP."""
        ej = to_int(raw.get("SG_OC_EJERCICIO"))
        uni = to_int(raw.get("SG_OC_UNI_COMPRA"))
        nro = to_int(raw.get("SG_OC_NRO"))
        if ej is None or uni is None or nro is None:
            return None
        source_key = json.dumps(
            {"ejercicio": ej, "nro_oc": nro, "uni_compra": uni},
            sort_keys=True,
        )
        link = self._link_store.get_link("orden_compra", source_key)
        if not link:
            return None
        remote_id = link.get("remote_id")
        try:
            return int(remote_id) if remote_id is not None else None
        except (TypeError, ValueError):
            return None

    def _flush_retencion_skip_counters(self, entity_label: str) -> None:
        """Reporta y resetea contadores de retenciones descartadas."""
        if self._retencion_skipped_no_catalog:
            logger.warning(
                "Migrator [%s]: %d retenciones omitidas porque tipos_retencion lookup esta vacio. "
                "Cargar account_tipo_impuestos en el tenant Paxapos.",
                entity_label,
                self._retencion_skipped_no_catalog,
            )
            self._retencion_skipped_no_catalog = 0
        if self._retencion_skipped_no_match:
            logger.warning(
                "Migrator [%s]: retenciones omitidas sin match en lookup: %s",
                entity_label,
                self._retencion_skipped_no_match,
            )
            self._retencion_skipped_no_match = {}

   
    def process_response(self, parsed: dict, raw_by_source_key: dict[str, dict], *, link_store, dry_run: bool) -> None:
        """Persist links y marcar OCs has_op despuÃ©s del POST."""
        persist_links_orden_pago(parsed, raw_by_source_key, link_store, dry_run)
        if not dry_run:
            # Los gastos editados/creados quedan vinculados por comprobante RAFAM; en la
            # proxima corrida _fetch_gastos_portal los excluye del pool de candidatos.
            persist_links_gastos(parsed, getattr(self, "_last_gasto_raw_by_sk", {}), link_store)
        self._mark_oc_has_op(parsed, link_store)

    def _mark_oc_has_op(self, parsed: dict, link_store) -> None:
        """Marca OCs asociadas con has_op para protegerlas de anulaciÃ³n."""
        op_results = (parsed.get("results", {}) or {}).get("ordenes_pago", [])
        if not isinstance(op_results, list):
            return
        grouped_oc_source_keys = getattr(self, "_last_grouped_oc_source_keys", {})
        marked_oc_sks: set[str] = set()
        for result in op_results:
            if not isinstance(result, dict) or not result.get("success"):
                continue
            ext = result.get("external_id") or {}
            ej = ext.get("ejercicio")
            nro = ext.get("nro_op")
            if ej is None or nro is None:
                continue
            op_key = (int(ej), int(nro))
            for oc_sk in grouped_oc_source_keys.get(op_key, []):
                if oc_sk not in marked_oc_sks:
                    link_store.mark_oc_has_op(oc_sk)
                    marked_oc_sks.add(oc_sk)
        if marked_oc_sks:
            logger.info(
                "Migrator [orden_pago]: %d OCs marcadas con has_op",
                len(marked_oc_sks),
            )

    def log_stats(self, parsed: dict, dry_run: bool) -> None:
        """Loguea estadÃ­sticas post-send."""
        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get("ordenes_pago", {}) if isinstance(stats, dict) else {}
        ordenes_pago_count = section_stats.get("ok", 0) + section_stats.get("error", 0)
        skipped = getattr(self, "_last_skipped_no_gasto", 0)
        logger.info(
            "Migrator OK [orden_pago]: %d ok, %d error, ops=%d, omitidas=%d, dry_run=%s",
            section_stats.get("ok", 0),
            section_stats.get("error", 0),
            ordenes_pago_count,
            skipped,
            dry_run,
        )



def persist_links_orden_pago(parsed: dict, raw_by_source_key: dict[str, dict], link_store, dry_run: bool) -> None:
    """Persiste entity links de ordenes_pago desde la respuesta del API."""
    if dry_run or not isinstance(parsed, dict):
        return
    results = parsed.get("results", {})
    if not isinstance(results, dict):
        return

    section = results.get("ordenes_pago", [])
    if not isinstance(section, list):
        return

    pk_fields = ["ejercicio", "nro_op"]
    for result in section:
        if not isinstance(result, dict) or not result.get("success"):
            continue
        if result.get("mode") == "skipped_not_found":
            # El id de Egreso ya no existe en Paxapos (baja manual). No se recrea ni
            # se pisa el link: se conserva y se loguea para el reporte/mail del run.
            logger.warning(
                "Migrator [orden_pago]: id Paxapos %s inexistente (baja manual); "
                "se omite la modificacion. external_id=%s",
                result.get("id"), result.get("external_id"),
            )
            continue
        external_id = result.get("external_id") or {}
        if not isinstance(external_id, dict):
            continue
        remote_id = result.get("id")
        if remote_id is None:
            continue

        key_dict = {k: external_id[k] for k in pk_fields if k in external_id}
        if len(key_dict) != len(pk_fields):
            logger.warning("Migrator [orden_pago]: external_id incompleto: %s", external_id)
            continue
        source_key = json.dumps(key_dict, sort_keys=True)

        raw = raw_by_source_key.get(source_key, {})
        estado_op = str(raw.get("ESTADO_OP", "")).strip().upper() or None
        confirmado = str(raw.get("CONFIRMADO", "")).strip().upper() or None
        fech_confirm = format_date_only(raw.get("FECH_CONFIRM", "")) or None
        importe_total = str(raw.get("IMPORTE_TOTAL")) if raw.get("IMPORTE_TOTAL") is not None else None

        link_store.save_link(
            entity="orden_pago",
            source_key=source_key,
            remote_id=str(remote_id),
            estado_op=estado_op,
            confirmado=confirmado,
            fech_confirm=fech_confirm,
            importe_total=importe_total,
        )



def _pedido_id_from_op_row(raw: dict) -> int | None:
    """Devuelve pedido_id si la fila ya lo trae."""
    for field in ("pedido_id", "PEDIDO_ID", "PAXAPOS_PEDIDO_ID"):
        pedido_id = to_int(raw.get(field))
        if pedido_id is not None:
            return pedido_id
    return None


RESULT_SECTION = "ordenes_pago"
