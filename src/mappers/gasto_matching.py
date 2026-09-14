"""gasto_matching.py — pareo de un comprobante RAFAM con el gasto que Paxapos ya tiene en la OC.

Cuando el proveedor sube la factura por el portal publico, Paxapos crea un gasto
vinculado a la OC (account_gastos.pedido_id) con el PDF y lo que el OCR pudo leer
(a veces nada, a veces placeholders como 'SIN-NUMERO' / '0000'). RAFAM llega
despues con el comprobante fiscal: la decision de CUAL gasto de la OC es esa
factura la toma este modulo, y Paxapos solo recibe un edit por id.

La cascada la comparten solic_gastos y orden_pago para que ambos flujos pareen
igual:
  1. mismo nro normalizado (con pdv como desempate si ambos lo tienen)
  2. unico candidato de la OC sin comprobante real
  3. mismo importe_total (abs, +-IMPORTE_TOLERANCIA)
  4. ambiguo: sin gasto, con la lista de candidatos para marcar REVISAR.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import parse_money

# Placeholders que deja el OCR del portal cuando no pudo leer el comprobante.
NRO_PLACEHOLDERS = frozenset({"SIN-NUMERO"})

# Tolerancia para dar dos importes por iguales al desambiguar facturas de una OC.
IMPORTE_TOLERANCIA = 0.01


def norm_nro(value) -> str:
    """Normaliza pdv/nro para COMPARAR: sin espacios ni ceros a izquierda.

    Los placeholders del OCR y los valores solo-ceros quedan en '' (= sin comprobante).
    """
    if value is None:
        return ""
    text = str(value).strip()
    if text.upper() in NRO_PLACEHOLDERS:
        return ""
    return text.lstrip("0")


def comprobante_key(data: dict) -> tuple | None:
    """Identidad de comprobante normalizada (proveedor, pdv, nro, tipo) o None sin nro."""
    if not isinstance(data, dict):
        return None
    factura_nro = norm_nro(data.get("factura_nro"))
    if not factura_nro:
        return None
    proveedor_id = data.get("proveedor_id")
    tipo_factura_id = data.get("tipo_factura_id")
    return (
        int(proveedor_id) if proveedor_id not in (None, "") else None,
        norm_nro(data.get("punto_de_venta")),
        factura_nro,
        int(tipo_factura_id) if tipo_factura_id not in (None, "") else None,
    )


def importes_iguales(a, b) -> bool:
    fa = parse_money(a)
    fb = parse_money(b)
    if fa is None or fb is None:
        return False
    return round(abs(abs(fa) - abs(fb)), 2) <= IMPORTE_TOLERANCIA


@dataclass
class MatchResult:
    gasto: dict | None
    matched_by: str | None
    candidates: list[int] = field(default_factory=list)


def elegir_gasto_portal(candidates: list[dict], comprobante: dict) -> MatchResult:
    """Elige, entre los gastos de la OC, el que corresponde al comprobante RAFAM."""
    pool = [c for c in candidates if isinstance(c, dict)]
    if not pool:
        return MatchResult(None, None, [])

    nro = norm_nro(comprobante.get("factura_nro"))
    pdv = norm_nro(comprobante.get("punto_de_venta"))
    if nro:
        by_nro = [c for c in pool if norm_nro(c.get("factura_nro")) == nro]
        if len(by_nro) > 1 and pdv:
            by_pdv = [c for c in by_nro if norm_nro(c.get("punto_de_venta")) in ("", pdv)]
            if by_pdv:
                by_nro = by_pdv
        if len(by_nro) == 1:
            return MatchResult(by_nro[0], "comprobante", [])
        if by_nro:
            pool = by_nro

    if len(pool) == 1 and not norm_nro(pool[0].get("factura_nro")):
        return MatchResult(pool[0], "unico_sin_comprobante", [])

    importe = parse_money(comprobante.get("importe_total"))
    if importe:
        by_importe = [c for c in pool if importes_iguales(c.get("importe_total"), importe)]
        if len(by_importe) == 1:
            return MatchResult(by_importe[0], "importe", [])

    return MatchResult(None, None, [int(c["id"]) for c in pool if c.get("id") is not None])


def pick_resolved(candidates: list[dict], gasto_data: dict) -> dict | None:
    """Compat con solic_gastos: con 1 candidato lo devuelve; con varios, cascada."""
    if len(candidates) == 1:
        return candidates[0]
    return elegir_gasto_portal(candidates, gasto_data).gasto


def gasto_ids_pareados(link_store) -> set[int]:
    """Ids de gasto Paxapos que este script ya vinculo a un comprobante RAFAM."""
    ids: set[int] = set()
    for link in link_store.get_all_links("gasto"):
        if link.get("deleted_at"):
            continue
        try:
            ids.add(int(link.get("remote_id")))
        except (TypeError, ValueError):
            continue
    return ids
