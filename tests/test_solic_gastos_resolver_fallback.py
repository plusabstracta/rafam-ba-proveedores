"""Fallback por identidad de comprobante en el resolver de gastos.

El backend (`resolver_gasto`) devuelve gastos con `matched_by='comprobante'` y
`pedido_id` null cuando el gasto parcial no quedo vinculado a la OC. El mapper
los descartaba al indexar solo por `pedido_id`, dejando el fallback inerte.
"""

from __future__ import annotations

import json

from src.mappers.solic_gastos import (
    PAXAPOS_PRIORITY_GASTO_FIELDS,
    SolicGastosMapper,
    _comprobante_key,
)


class _FakeLinkStore:
    def __init__(self, gasto_refs: str, pedido_id: str = "900"):
        self._gasto_refs = gasto_refs
        self._pedido_id = pedido_id

    def get_sent_oc_gasto_refs(self):
        return {self._gasto_refs}

    def get_all_links(self, entity):
        if entity != "orden_compra":
            return []
        return [{"remote_id": self._pedido_id, "gasto_refs": self._gasto_refs}]

    def get_link(self, entity, source_key):
        return None

    def get_remote_id(self, entity, source_key):
        return "777" if entity == "proveedores" else None


class _FakeLookup:
    def resolve_tipo_factura_id(self, _value):
        return 3

    def resolve_unidad_id(self, *_args, **_kwargs):
        return 1


COLUMNS = [
    "EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC", "FECH_SOLIC", "IMPORTE_TOT",
    "ESTADO_SOLIC", "CTA_COMPROB_COUNT", "CTA_NRO_COMPROB", "CTA_TIPO_COMPROB",
    "CTA_FECH_VENCIM", "CTA_IMPORTE_COMPR", "CTA_IMPORTE_NETO", "OC_COD_PROV",
    "OBSERVACIONES",
]

ROW = tuple({
    "EJERCICIO": "2026",
    "DELEG_SOLIC": "2",
    "NRO_SOLIC": "300",
    "FECH_SOLIC": "2026-03-10 00:00:00",
    "IMPORTE_TOT": "1210.50",
    "ESTADO_SOLIC": "C",
    "CTA_COMPROB_COUNT": "1",
    "CTA_NRO_COMPROB": "0001-00012345",
    "CTA_TIPO_COMPROB": "FAB",
    "CTA_FECH_VENCIM": "2026-04-10",
    "CTA_IMPORTE_COMPR": "1210.50",
    "CTA_IMPORTE_NETO": "1000.00",
    "OC_COD_PROV": "99",
    "OBSERVACIONES": "Factura",
}.get(col, "") for col in COLUMNS)


def test_comprobante_key_normaliza_padding():
    # El backend guarda pdv/nro paddeados (5/20); RAFAM los manda pelados.
    desde_backend = _comprobante_key({
        "proveedor_id": 777,
        "punto_de_venta": "00001",
        "factura_nro": "00000000000000012345",
        "tipo_factura_id": 3,
    })
    desde_rafam = _comprobante_key({
        "proveedor_id": "777",
        "punto_de_venta": "0001",
        "factura_nro": "00012345",
        "tipo_factura_id": "3",
    })
    assert desde_backend == desde_rafam


def test_gasto_sin_pedido_id_se_enriquece_por_comprobante():
    mapper = SolicGastosMapper(
        link_store=_FakeLinkStore("SG-2026-2-300"),
        lookup_resolver=_FakeLookup(),
        resolve_gastos_fn=lambda _pedidos, _comprobantes: {
            "success": True,
            "gastos": [
                {
                    "id": 4321,
                    "pedido_id": None,          # no quedo vinculado a la OC
                    "matched_by": "comprobante",
                    "proveedor_id": 777,
                    "punto_de_venta": "00001",
                    "factura_nro": "00000000000000012345",
                    "tipo_factura_id": 3,
                    "empty_fields": ["importe_total", "importe_neto"],
                }
            ],
        },
    )

    payload, raw_by_sk = mapper.build_payload(
        COLUMNS, [ROW], dry_run=True, payload_options={}
    )

    assert payload is not None, "el gasto deberia enriquecerse por comprobante"
    gastos = payload["gastos"]
    assert len(gastos) == 1
    assert gastos[0]["Gasto"]["id"] == 4321
    assert gastos[0]["Gasto"]["merge"] == "fill_empty"
    # Solo se completan los campos vacios reportados por el backend.
    assert set(gastos[0]["Gasto"]) == {"id", "merge", "importe_total", "importe_neto"}
    assert list(raw_by_sk) == [json.dumps(gastos[0]["external_id"], sort_keys=True)]


def test_gasto_existente_solo_envia_campos_faltantes():
    mapper = SolicGastosMapper(
        link_store=_FakeLinkStore("SG-2026-2-300"),
        lookup_resolver=_FakeLookup(),
        resolve_gastos_fn=lambda _pedidos, _comprobantes: {
            "success": True,
            "gastos": [
                {
                    "id": 4321,
                    "pedido_id": 900,
                    "proveedor_id": 777,
                    "importe_total": 9999,
                    "fecha": "2025-01-01",
                    "empty_fields": ["punto_de_venta", "factura_nro"],
                }
            ],
        },
    )

    payload, _raw_by_sk = mapper.build_payload(
        COLUMNS, [ROW], dry_run=True, payload_options={}
    )

    assert payload is not None
    gasto = payload["gastos"][0]["Gasto"]
    assert gasto == {
        "id": 4321,
        "merge": "fill_empty",
        "punto_de_venta": "0001",
        "factura_nro": "00012345",
    }


def test_datos_paxapos_tienen_prioridad_para_observacion_y_adjunto():
    mapper = SolicGastosMapper(
        link_store=_FakeLinkStore("SG-2026-2-300"),
        lookup_resolver=_FakeLookup(),
        resolve_gastos_fn=lambda _pedidos, _comprobantes: {
            "success": True,
            "gastos": [
                {
                    "id": 4321,
                    "pedido_id": 900,
                    "tiene_imagen": True,
                    "tiene_observacion": True,
                    # Respuesta deliberadamente inconsistente: el mapper debe
                    # respetar igual la prioridad declarada por Paxapos.
                    "empty_fields": [
                        "observacion",
                        "media_id",
                        "file",
                        "importe_total",
                    ],
                }
            ],
        },
    )

    payload, _raw_by_sk = mapper.build_payload(
        COLUMNS, [ROW], dry_run=True, payload_options={}
    )

    assert payload is not None
    gasto = payload["gastos"][0]["Gasto"]
    assert gasto == {
        "id": 4321,
        "merge": "fill_empty",
        "importe_total": 1210.5,
    }
    assert PAXAPOS_PRIORITY_GASTO_FIELDS.isdisjoint(gasto)
