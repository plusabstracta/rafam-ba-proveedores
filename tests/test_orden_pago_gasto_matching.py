"""Pareo de comprobantes de OP con los gastos que el portal ya creo en la OC.

Antes el bloque gastos[] de orden_pago se mandaba sin id y Paxapos, al no
encontrarlo por identidad exacta (el OCR dejo otro tipo, pdv placeholder o
'SIN-NUMERO'), creaba un segundo gasto en la misma OC. Ahora el mapper
consulta resolver_gasto, elige el gasto del portal con la cascada compartida
(gasto_matching) y manda {id, ...} para que RAFAM lo complete con un edit.
"""

from __future__ import annotations

import json

from src.mappers.gasto_matching import elegir_gasto_portal, gasto_ids_pareados, norm_nro
from src.mappers.orden_pago import OrdenPagoMapper


# ── fakes ───────────────────────────────────────────────────────────────────

class FakeLinkStore:
    def __init__(self, gasto_links=None):
        self._gasto_links = gasto_links or []
        self.saved = []
        self.enqueued = []

    def get_remote_id(self, entity, key):
        return "999" if entity == "proveedores" else None

    def get_link(self, entity, key):
        return None

    def get_all_links(self, entity):
        return list(self._gasto_links) if entity == "gasto" else []

    def save_link(self, **kwargs):
        self.saved.append(kwargs)

    def mark_oc_has_op(self, sk):
        pass


class FakeRetryStore:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, entity, sk, reason, detail, reason_detail=None):
        self.enqueued.append((entity, sk, reason_detail))

    def resolve(self, entity, sk):
        pass


class FakeLookup:
    def resolve_tipo_factura_id(self, tipo):
        return 1

    def resolve_tipo_pago_id(self, origen_tipo=None):
        return 4


COLUMNS = [
    "EJERCICIO", "NRO_OP", "ESTADO_OP", "CONFIRMADO", "FECH_CONFIRM", "IMPORTE_TOTAL",
    "CONCEPTO", "COD_PROV", "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
    "OPI_NRO_COMPROB", "OPI_TIPO_COMPROB", "OPI_COD_PROV",
    "CTA_IMPORTE_COMPR", "CTA_IMPORTE_NETO", "CTA_FECH_COMPROB", "pedido_id",
]


def _row(nro_op, cc_nro, importe="1210.00", pedido_id="500", fech_comprob="2026-03-09", sg_nro="77"):
    vals = {
        "EJERCICIO": "2026", "NRO_OP": str(nro_op), "ESTADO_OP": "C", "CONFIRMADO": "S",
        "FECH_CONFIRM": "2026-03-20 00:00:00", "IMPORTE_TOTAL": importe, "CONCEPTO": "Pago",
        "COD_PROV": "123", "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": sg_nro,
        "OPI_NRO_COMPROB": cc_nro, "OPI_TIPO_COMPROB": "FAA", "OPI_COD_PROV": "123",
        "CTA_IMPORTE_COMPR": importe, "CTA_IMPORTE_NETO": "1000.00",
        "CTA_FECH_COMPROB": fech_comprob, "pedido_id": pedido_id,
    }
    return tuple(vals.get(c, "") for c in COLUMNS)


def _portal(gasto_id, **extra):
    base = {
        "id": gasto_id, "pedido_id": 500, "proveedor_id": 999,
        "punto_de_venta": "00000", "factura_nro": "SIN-NUMERO", "tipo_factura_id": 2,
        "importe_total": 1210.0, "importe_neto": 1000.0, "fecha": "2026-03-10",
        "clasificacion_id": None, "tiene_imagen": True, "empty_fields": [],
    }
    base.update(extra)
    return base


def _mapper(portal_gastos, gasto_links=None, retry_store=None):
    calls = []

    def resolver(pedido_ids, comprobantes):
        calls.append(pedido_ids)
        return {"success": True, "gastos": portal_gastos}

    store = FakeLinkStore(gasto_links=gasto_links)
    m = OrdenPagoMapper(
        link_store=store, lookup_resolver=FakeLookup(),
        retry_store=retry_store, resolve_gastos_fn=resolver,
    )
    return m, store, calls


def _build(m, rows):
    return m.build_payload(COLUMNS, rows, dry_run=False, payload_options={})


# ── cascada compartida ──────────────────────────────────────────────────────

def test_norm_nro_placeholders():
    assert norm_nro("SIN-NUMERO") == ""
    assert norm_nro("0000") == ""
    assert norm_nro("00000000000000000456") == "456"


def test_elegir_por_nro_aunque_tipo_y_pdv_difieran():
    pool = [_portal(1, factura_nro="00000000000000000456", punto_de_venta="00000", tipo_factura_id=2)]
    r = elegir_gasto_portal(pool, {"punto_de_venta": "0001", "factura_nro": "456", "tipo_factura_id": 1})
    assert r.gasto["id"] == 1 and r.matched_by == "comprobante"


def test_elegir_unico_sin_comprobante():
    r = elegir_gasto_portal([_portal(7, importe_total=50.0)], {"factura_nro": "999", "importe_total": 1210})
    assert r.gasto["id"] == 7 and r.matched_by == "unico_sin_comprobante"


def test_elegir_por_importe_en_multifactura():
    pool = [_portal(1, importe_total=1000.0), _portal(2, importe_total=2500.0)]
    r = elegir_gasto_portal(pool, {"factura_nro": "456", "importe_total": "2500.01"})
    assert r.gasto["id"] == 2 and r.matched_by == "importe"


def test_elegir_ambiguo_lista_candidatos():
    pool = [_portal(1, importe_total=1000.0), _portal(2, importe_total=1000.0)]
    r = elegir_gasto_portal(pool, {"factura_nro": "456", "importe_total": 1000})
    assert r.gasto is None and r.candidates == [1, 2]


def test_gasto_ids_pareados_ignora_borrados():
    store = FakeLinkStore(gasto_links=[
        {"remote_id": "10"}, {"remote_id": "11", "deleted_at": "2026-01-01"}, {"remote_id": "x"},
    ])
    assert gasto_ids_pareados(store) == {10}


# ── build_payload ───────────────────────────────────────────────────────────

def test_comprobante_pareado_se_manda_como_edit_por_id():
    m, store, calls = _mapper([_portal(900)])
    payload, _ = _build(m, [_row(1001, "0001-00000456")])

    assert calls == [[500]]
    gastos = payload["gastos"]
    assert len(gastos) == 1
    g = gastos[0]["Gasto"]
    assert g["id"] == 900
    assert "merge" not in g
    # Comprobante de RAFAM
    assert g["punto_de_venta"] == "0001" and g["factura_nro"] == "00000456" and g["tipo_factura_id"] == 1
    # Importes/fecha del portal se conservan; PDF y observacion no viajan
    assert g["importe_total"] == 1210.0 and g["fecha"] == "2026-03-10"
    assert "media_id" not in g and "observacion" not in g
    # La OP sigue viajando con su nro de comprobante (Paxapos ya lo encuentra)
    assert payload["ordenes_pago"][0]["gasto_nro_comprobante"] == "0001-00000456"


def test_sin_gasto_portal_se_crea_como_siempre():
    m, _, _ = _mapper([])
    payload, _ = _build(m, [_row(1001, "0001-00000456")])
    g = payload["gastos"][0]["Gasto"]
    assert "id" not in g
    assert g["importe_total"] == 1210.0


def test_ambiguo_crea_marcado_revisar():
    m, _, _ = _mapper([_portal(900, importe_total=1210.0), _portal(901, importe_total=1210.0)])
    payload, _ = _build(m, [_row(1001, "0001-00000456")])
    g = payload["gastos"][0]["Gasto"]
    assert "id" not in g
    assert "REVISAR: posible duplicado de gasto(s) #900, #901 en OC #500" in g["observacion"]


def test_gasto_ya_pareado_queda_fuera_del_pool():
    m, _, _ = _mapper([_portal(900)], gasto_links=[{"remote_id": "900"}])
    payload, _ = _build(m, [_row(1001, "0001-00000456")])
    assert "id" not in payload["gastos"][0]["Gasto"]


def test_dos_comprobantes_misma_oc_no_reusan_el_mismo_gasto():
    portal = [_portal(900, importe_total=1210.0), _portal(901, importe_total=800.0)]
    m, _, _ = _mapper(portal)
    payload, _ = _build(m, [
        _row(1001, "0001-00000456", importe="1210.00", sg_nro="77"),
        _row(1002, "0001-00000457", importe="800.00", sg_nro="78"),
    ])
    ids = sorted(g["Gasto"]["id"] for g in payload["gastos"])
    assert ids == [900, 901]


def test_op_con_comprobante_incompleto_y_gasto_portal_se_retiene():
    retry = FakeRetryStore()
    m, _, _ = _mapper([_portal(900)], retry_store=retry)
    payload, raw = _build(m, [_row(1001, "0001-00000456", fech_comprob="")])
    # Sin CTA_FECH_COMPROB no hay bloque gasto: si la OP viajara, Paxapos autocrearia
    # el gasto desde gasto_nro_comprobante ignorando el del portal.
    assert payload is None
    assert raw == {}
    assert retry.enqueued and retry.enqueued[0][0] == "orden_pago"


def test_op_con_comprobante_incompleto_sin_gasto_portal_viaja():
    m, _, _ = _mapper([])
    payload, _ = _build(m, [_row(1001, "0001-00000456", fech_comprob="")])
    assert payload is not None
    assert payload["gastos"] == []
    assert len(payload["ordenes_pago"]) == 1


def test_process_response_persiste_link_de_gasto():
    m, store, _ = _mapper([_portal(900)])
    payload, raw_by_sk = _build(m, [_row(1001, "0001-00000456")])
    parsed = {
        "results": {
            "gastos": [{"success": True, "id": 900, "external_id": payload["gastos"][0]["external_id"], "mode": "update"}],
            "ordenes_pago": [{"success": True, "id": 55, "external_id": {"ejercicio": 2026, "nro_op": 1001}}],
        }
    }
    m.process_response(parsed, raw_by_sk, link_store=store, dry_run=False)
    gasto_links = [s for s in store.saved if s["entity"] == "gasto"]
    assert gasto_links and gasto_links[0]["remote_id"] == "900"
    assert gasto_links[0]["pedido_id"] == "500"
    assert gasto_links[0]["nro_comprobante"] == "0001-00000456"


def test_resolver_que_falla_aborta_el_lote():
    def resolver(pedido_ids, comprobantes):
        raise RuntimeError("resolver_gasto fallo")

    m = OrdenPagoMapper(link_store=FakeLinkStore(), lookup_resolver=FakeLookup(), resolve_gastos_fn=resolver)
    try:
        _build(m, [_row(1001, "0001-00000456")])
    except RuntimeError as exc:
        assert "resolver_gasto" in str(exc)
    else:
        raise AssertionError("debia propagar el error del resolver para no crear duplicados")
