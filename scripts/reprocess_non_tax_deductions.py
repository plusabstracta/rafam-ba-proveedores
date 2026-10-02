#!/usr/bin/env python
"""scripts/reprocess_non_tax_deductions.py - reproceso de deducciones no impositivas.

paxapos/paxapos#738 (espejo: plusabstracta/rafam-ba-proveedores#18).

Garantia (cod 4) y Caja de Medicos (cod 8) se omitian al migrar: Paxapos no las
podia representar y ``Egreso.neto_transferido`` de esas OP quedo sobreestimado.
Desde que el backend (v3.16.0) las modela como deduccion NO impositiva y este
migrador las manda (``RAFAM_NON_TAX_DEDUCTION_MAP``), hay que reenviar las OP YA
migradas para que el receptor las reemplace con el conjunto completo y recalcule
el neto.

Una OP ya enviada no se vuelve a escanear sola (la ventana incremental mira solo
los ultimos 30 dias): se reinyecta por la cola de reintentos. Este script:

  1. busca en RAFAM (solo lectura) las OP >= ``--ejercicio-min`` con una
     deduccion mapeada (y no 'I'), que ya esten migradas a Paxapos (link local);
  2. informa cuales ya estan en la cola (``non_tax_deduction`` de antes: van solas),
     cuales hay que encolar y el importe que va a bajar de ``neto_transferido``;
  3. con ``--apply`` ENCOLA las que faltan (escribe SOLO la cola local SQLite:
     nunca RAFAM ni Paxapos).

Modo por defecto = ``--dry-run`` (solo informa). Despues del ``--apply``::

    .venv/bin/python main.py run --entity retenciones --dry-run   # preview: el receptor no persiste
    .venv/bin/python main.py run --entity retenciones             # real, recien con el backend v3.16.0

Uso::

    .venv/bin/python scripts/reprocess_non_tax_deductions.py --dry-run
    .venv/bin/python scripts/reprocess_non_tax_deductions.py --apply
    make reprocess-non-tax-dry        # = --dry-run
    make reprocess-non-tax            # = --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from src.config import ENTITY_CONFIGS, non_tax_deduction_concept, non_tax_deduction_map  # noqa: E402
from src.retry_store import REASON_DEPENDENCY_MISSING  # noqa: E402

REASON_DETAIL_REPROCESS = "non_tax_deduction_reprocess"

# Estados del plan por OP.
ST_ALREADY_PENDING = "ya_en_cola"          # entra sola en la proxima corrida
ST_TO_ENQUEUE = "encolar"                  # migrada, hay que reinyectarla
ST_PERMANENT = "permanente_en_cola"        # rechazo terminal (ej. Egreso borrado): no tocar
ST_NOT_MIGRATED = "sin_migrar"             # el flujo normal ya la manda completa cuando migre

_IN_CHUNK = 900  # limite practico del IN de Oracle (1000)


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:  # noqa: BLE001
        return Decimal(0)


def _fmt(value: Decimal) -> str:
    return f"${value:,.2f}"


def _op_source_key(ejercicio: int, nro_op: int) -> str:
    return json.dumps({"ejercicio": int(ejercicio), "nro_op": int(nro_op)}, sort_keys=True)


def _numeric_codes(codes: list[str]) -> list[int]:
    out: list[int] = []
    for code in codes:
        if code.isdigit():
            out.append(int(code))
        else:
            print(f"AVISO: el codigo {code!r} del mapa no es numerico (CODIGO_DEDUC es NUMBER); se ignora.")
    return out


def find_candidates(repo, conn, ejercicio_min: int) -> dict[tuple[int, int], list[dict]]:
    """OP (>= ejercicio_min) con al menos una deduccion no impositiva mapeada.

    Devuelve ``{(ejercicio, nro_op): [deduccion, ...]}`` con SOLO las deducciones
    mapeadas (``fetch_deducciones_for_ops`` trae el TIPO_DEDUC y la descripcion).
    Solo lectura sobre RAFAM.
    """
    codes = _numeric_codes(sorted(non_tax_deduction_map()))
    if not codes:
        return {}

    deduc_t = repo._reflect_optional_table("ORDEN_PAGO_DEDUC")  # noqa: SLF001 - script interno
    if deduc_t is None:
        raise SystemExit("No se pudo reflejar ORDEN_PAGO_DEDUC (revisar privilegios de lectura)")
    cols = {}
    for name in ("EJERCICIO", "NRO_OP", "CODIGO_DEDUC", "IMPORTE_RETEN"):
        col = repo._safe_column(deduc_t, name)  # noqa: SLF001
        if col is None:
            raise SystemExit(f"ORDEN_PAGO_DEDUC no expone la columna {name}")
        cols[name] = col

    stmt = select(cols["EJERCICIO"], cols["NRO_OP"]).where(
        cols["EJERCICIO"] >= ejercicio_min,
        cols["CODIGO_DEDUC"].in_(codes),
        cols["IMPORTE_RETEN"] > 0,
    ).distinct()
    op_keys = [(int(r[0]), int(r[1])) for r in conn.execute(stmt)]
    if not op_keys:
        return {}

    detail: dict[tuple[int, int], list[dict]] = {}
    for start in range(0, len(op_keys), _IN_CHUNK):
        chunk = op_keys[start:start + _IN_CHUNK]
        batch = repo.fetch_deducciones_for_ops(chunk)
        if batch is None:
            raise SystemExit("fetch_deducciones_for_ops fallo (ORDEN_PAGO_DEDUC no disponible)")
        detail.update(batch)

    out: dict[tuple[int, int], list[dict]] = {}
    for key, deds in detail.items():
        mapped = [
            d for d in deds
            if d.get("codigo_deduc") is not None
            and non_tax_deduction_concept(d.get("codigo_deduc"), d.get("tipo_deduc")) is not None
            and _money(d.get("importe_reten")) > 0
        ]
        if mapped:
            out[key] = mapped
    return out


def build_plan(
    candidates: dict[tuple[int, int], list[dict]],
    *,
    op_links: dict[str, dict],
    pending_ids: set[str],
    permanent_ids: set[str],
) -> list[dict]:
    """Clasifica cada OP candidata. Funcion pura (sin I/O).

    ``op_links``: ``source_key -> link`` de la entidad ``orden_pago`` (lo migrado).
    """
    plan: list[dict] = []
    for (ejercicio, nro_op), deds in sorted(candidates.items()):
        sk = _op_source_key(ejercicio, nro_op)
        link = op_links.get(sk)
        if not link or not link.get("remote_id") or link.get("deleted_at"):
            state = ST_NOT_MIGRATED
        elif sk in permanent_ids:
            state = ST_PERMANENT
        elif sk in pending_ids:
            state = ST_ALREADY_PENDING
        else:
            state = ST_TO_ENQUEUE
        plan.append({
            "ejercicio": ejercicio,
            "nro_op": nro_op,
            "source_key": sk,
            "state": state,
            "egreso_id": link.get("remote_id") if link else None,
            "deducciones": [
                {
                    "codigo": str(d["codigo_deduc"]).strip(),
                    "concepto": non_tax_deduction_concept(d.get("codigo_deduc"), d.get("tipo_deduc")),
                    "importe": _money(d.get("importe_reten")),
                }
                for d in deds
            ],
        })
    return plan


def format_report(plan: list[dict], *, apply: bool, ejercicio_min: int) -> str:
    lines = [
        "=" * 78,
        f"REPROCESO DE DEDUCCIONES NO IMPOSITIVAS  ejercicio>={ejercicio_min}  "
        f"({'APPLY: encola' if apply else 'DRY-RUN: no escribe nada'})",
        "=" * 78,
        "Mapa vigente (RAFAM_NON_TAX_DEDUCTION_MAP): "
        + (", ".join(f"{c}={n}" for c, n in sorted(non_tax_deduction_map().items())) or "(vacio: desactivado)"),
        "",
    ]
    by_state: dict[str, list[dict]] = defaultdict(list)
    for item in plan:
        by_state[item["state"]].append(item)

    def _totals(items: list[dict]) -> str:
        per_concept: dict[str, list] = defaultdict(lambda: [0, Decimal(0)])
        for it in items:
            for d in it["deducciones"]:
                per_concept[f"{d['codigo']} {d['concepto']}"][0] += 1
                per_concept[f"{d['codigo']} {d['concepto']}"][1] += d["importe"]
        return "; ".join(f"{k}: {n} deduc. {_fmt(imp)}" for k, (n, imp) in sorted(per_concept.items())) or "-"

    labels = {
        ST_TO_ENQUEUE: "A ENCOLAR (migradas; hay que reinyectarlas)",
        ST_ALREADY_PENDING: "YA EN COLA (non_tax_deduction de antes: entran solas en la proxima corrida)",
        ST_PERMANENT: "PERMANENTES EN COLA (rechazo terminal, ej. Egreso borrado: no se tocan)",
        ST_NOT_MIGRATED: "SIN MIGRAR (el flujo normal las manda completas cuando migren)",
    }
    for state in (ST_TO_ENQUEUE, ST_ALREADY_PENDING, ST_PERMANENT, ST_NOT_MIGRATED):
        items = by_state.get(state, [])
        lines.append(f"{labels[state]}: {len(items)} OP")
        if items:
            lines.append(f"    {_totals(items)}")
            for it in items[:50]:
                detalle = ", ".join(f"{d['concepto']} {_fmt(d['importe'])}" for d in it["deducciones"])
                lines.append(f"    OP {it['ejercicio']}/{it['nro_op']}  egreso={it['egreso_id'] or '-'}  {detalle}")
            if len(items) > 50:
                lines.append(f"    ... y {len(items) - 50} mas")
        lines.append("")

    reprocesables = by_state.get(ST_TO_ENQUEUE, []) + by_state.get(ST_ALREADY_PENDING, [])
    lines.append(
        f"Total a reenviar: {len(reprocesables)} OP; "
        f"importe que baja de Egreso.neto_transferido: {_fmt(sum((d['importe'] for it in reprocesables for d in it['deducciones']), Decimal(0)))}"
    )
    lines.append("")
    if apply:
        lines.append("Siguiente paso: main.py run --entity retenciones --dry-run  (preview)  y despues sin --dry-run.")
    else:
        lines.append("DRY-RUN: no se encolo nada. Para encolar: --apply (escribe solo la cola local SQLite).")
    return "\n".join(lines)


def apply_plan(plan: list[dict], retry_store) -> int:
    """Encola (cola local SQLite) las OP en estado 'encolar'. Devuelve cuantas."""
    enqueued = 0
    for item in plan:
        if item["state"] != ST_TO_ENQUEUE:
            continue
        resumen = ", ".join(f"{d['concepto']} {_fmt(d['importe'])}" for d in item["deducciones"])
        retry_store.enqueue(
            "retenciones",
            item["source_key"],
            REASON_DEPENDENCY_MISSING,
            f"OP {item['ejercicio']}-{item['nro_op']}: reproceso paxapos#738 ({resumen})",
            reason_detail=REASON_DETAIL_REPROCESS,
        )
        enqueued += 1
    return enqueued


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ejercicio-min", type=int, default=ENTITY_CONFIGS["orden_pago"].ejercicio_min)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Solo informa (default). No escribe nada.")
    mode.add_argument("--apply", action="store_true", help="Encola en la cola LOCAL las OP migradas a reenviar.")
    args = parser.parse_args(argv)

    os.chdir(REPO_ROOT)
    from dotenv import load_dotenv

    load_dotenv()

    from src.db import create_source_engine
    from src.entity_link_store import EntityLinkStore
    from src.retry_store import RetryStore
    from src.source_repository import SourceRepository

    engine = create_source_engine()
    links = EntityLinkStore()
    retry = RetryStore()
    try:
        with engine.connect() as conn:
            repo = SourceRepository(conn)
            candidates = find_candidates(repo, conn, args.ejercicio_min)
        op_links = {link["source_key"]: link for link in links.get_all_links("orden_pago")}
        plan = build_plan(
            candidates,
            op_links=op_links,
            pending_ids=retry.pending_external_ids("retenciones"),
            permanent_ids=retry.permanent_external_ids("retenciones"),
        )
        print(format_report(plan, apply=args.apply, ejercicio_min=args.ejercicio_min))
        if args.apply:
            print(f"\nEncoladas: {apply_plan(plan, retry)} OP.")
    finally:
        retry.close()
        links.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
