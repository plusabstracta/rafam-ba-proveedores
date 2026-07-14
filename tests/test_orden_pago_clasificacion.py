"""Tests de la clasificacion de gastos por partida presupuestaria en ORDEN_PAGO.

Cubre el wiring OP -> partida (ORDEN_PAGO_IMPUT) -> clasificacion_id remoto:
  - Computo del codigo de partida desde columnas OPI_.
  - Eleccion de partida representativa cuando un comprobante tiene imputacion
    repartida (mas profunda, luego mas frecuente).
  - Resolucion del clasificacion_id con fallback jerarquico (4 -> 3 -> inciso).
  - Estampado del clasificacion_id en el bloque Gasto auto-creado.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.mappers.orden_pago import OrdenPagoMapper, _partida_code_from_op_raw


class FakeLinkStore:
    def __init__(self, clasif=None, proveedores=None):
        self._clasif = clasif or {}
        self._prov = proveedores or {}

    def get_remote_id(self, entity, key):
        if entity == "clasificacion":
            return self._clasif.get(key)
        if entity == "proveedores":
            return self._prov.get(str(key))
        return None

    def get_link(self, entity, key):
        return None


class FakeLookup:
    def resolve_tipo_factura_id(self, tipo):
        return 7

    def resolve_tipo_pago_id(self, raw):
        return 1


def _mapper(clasif=None, proveedores=None):
    return OrdenPagoMapper(
        link_store=FakeLinkStore(clasif=clasif, proveedores=proveedores),
        lookup_resolver=FakeLookup(),
    )


# ── code desde OPI_ ─────────────────────────────────────────────────────────

def test_partida_code_desde_opi():
    raw = {"OPI_INCISO": 3, "OPI_PAR_PRIN": 3, "OPI_PAR_PARC": 6, "OPI_PAR_SUBP": 0}
    assert _partida_code_from_op_raw(raw) == "3.3.6.0"


def test_partida_code_con_subparcial():
    raw = {"OPI_INCISO": 1, "OPI_PAR_PRIN": 1, "OPI_PAR_PARC": 6, "OPI_PAR_SUBP": 1}
    assert _partida_code_from_op_raw(raw) == "1.1.6.1"


def test_partida_code_sin_inciso_es_none():
    assert _partida_code_from_op_raw({"OPI_INCISO": None}) is None
    assert _partida_code_from_op_raw({}) is None


# ── profundidad y eleccion de partida ───────────────────────────────────────

def test_partida_depth():
    m = _mapper()
    assert m._partida_depth("2.0.0.0") == 1
    assert m._partida_depth("3.3.6.0") == 3
    assert m._partida_depth("1.1.6.1") == 4


def test_choose_partida_prefiere_mas_profunda():
    m = _mapper()
    assert m._choose_partida_code({"2.5.0.0": 9, "2.5.6.0": 1}) == "2.5.6.0"


def test_choose_partida_desempata_por_frecuencia():
    m = _mapper()
    assert m._choose_partida_code({"2.5.6.0": 1, "2.5.7.0": 5}) == "2.5.7.0"


def test_choose_partida_vacia_es_none():
    assert _mapper()._choose_partida_code({}) is None


# ── resolucion con fallback ─────────────────────────────────────────────────

def test_resolve_exacto():
    m = _mapper(clasif={"2.5.6.0": "500"})
    assert m._resolve_clasificacion_id("2.5.6.0") == (500, False)


def test_resolve_fallback_a_parcial():
    m = _mapper(clasif={"2.5.0.0": "400"})
    assert m._resolve_clasificacion_id("2.5.6.0") == (400, True)


def test_resolve_fallback_a_inciso():
    m = _mapper(clasif={"2.0.0.0": "200"})
    assert m._resolve_clasificacion_id("2.5.6.0") == (200, True)


def test_resolve_sin_match_es_none():
    m = _mapper(clasif={})
    assert m._resolve_clasificacion_id("2.5.6.0") == (None, False)


def test_resolve_code_none():
    assert _mapper()._resolve_clasificacion_id(None) == (None, False)


# ── estampado en el gasto ───────────────────────────────────────────────────

def test_build_gasto_estampa_clasificacion_id():
    m = _mapper(proveedores={"123": "999"})
    raw = {
        "OPI_NRO_COMPROB": "0001-00000011",
        "OPI_COD_PROV": "123",
        "OPI_TIPO_COMPROB": "FA",
        "CTA_IMPORTE_COMPR": "1000.00",
        "CTA_FECH_COMPROB": "2026-01-15",
        "EJERCICIO": 2026,
        "_PAXAPOS_CLASIFICACION_ID": 500,
    }
    gasto, _dedup = m._build_gasto_from_op_row(raw)
    assert gasto is not None
    assert gasto["Gasto"]["clasificacion_id"] == 500
    assert gasto["Gasto"]["proveedor_id"] == 999


def test_build_gasto_sin_clasificacion_no_estampa():
    m = _mapper(proveedores={"123": "999"})
    raw = {
        "OPI_NRO_COMPROB": "0001-00000011",
        "OPI_COD_PROV": "123",
        "OPI_TIPO_COMPROB": "FA",
        "CTA_IMPORTE_COMPR": "1000.00",
        "CTA_FECH_COMPROB": "2026-01-15",
        "EJERCICIO": 2026,
    }
    gasto, _dedup = m._build_gasto_from_op_row(raw)
    assert gasto is not None
    assert "clasificacion_id" not in gasto["Gasto"]
