#!/usr/bin/env python
"""scripts/audit_op_scope.py — Auditoría de alcance de órdenes de pago (solo lectura).

Responde, contra la fuente RAFAM configurada (Oracle en producción, SQLite en
dev) y el estado local del migrador, las preguntas que aparecieron al analizar
la cola de reintentos de sep-2026:

  1. ¿Qué son las OP encoladas como ``missing_payment_imputation``?
     Hipótesis: todas ``TIPO_OP='N'`` (no presupuestarias: giro de retenciones
     de sueldos, embargos, cajas chicas) sin ningún comprobante imputado.
  2. ¿Qué OP de proveedor están respaldadas SOLO por comprobantes tipo ``LIQ``
     (liquidaciones) y a qué COD_PROV pertenecen? ¿Ya se migraron a Paxapos?
  3. ¿Qué deducciones son impositivas (``TIPO_DEDUC='I'``) y cuáles no (``'O'``)?
     ¿Las OP encoladas como ``retention_type_unresolved`` tienen alguna ``I``?

No escribe nada: ni en RAFAM ni en el estado local. Uso::

    .venv/bin/python scripts/audit_op_scope.py
    .venv/bin/python scripts/audit_op_scope.py --ejercicio-min 2025 --top 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import and_, select  # noqa: E402

load_dotenv()

from src.config import ENTITY_CONFIGS, EXCLUDED_COD_PROV  # noqa: E402
from src.db import create_source_engine  # noqa: E402
from src.entity_link_store import EntityLinkStore  # noqa: E402
from src.retry_store import RetryStore  # noqa: E402
from src.source_repository import SourceRepository  # noqa: E402

SEP = "=" * 78
SUB = "-" * 78
_IN_CHUNK = 900  # limite practico del IN de Oracle (1000)


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:  # noqa: BLE001
        return Decimal(0)


def _fmt(value: Decimal) -> str:
    return f"${value:,.2f}"


def _s(value) -> str:
    return str(value or "").strip()


def _col(repo: SourceRepository, table, name: str):
    col = repo._safe_column(table, name)  # noqa: SLF001 - script interno
    if col is None:
        raise SystemExit(f"La tabla {table.name} no expone la columna {name}")
    return col


def _fetch(conn, stmt) -> list[dict]:
    return [dict(row._mapping) for row in conn.execute(stmt)]


def _op_key(ej, nro) -> str:
    return json.dumps({"ejercicio": int(ej), "nro_op": int(nro)}, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ejercicio-min", type=int, default=ENTITY_CONFIGS["orden_pago"].ejercicio_min)
    parser.add_argument("--top", type=int, default=15, help="Filas a mostrar en cada ranking")
    args = parser.parse_args()
    ej_min = args.ejercicio_min

    engine = create_source_engine()
    with engine.connect() as conn:
        repo = SourceRepository(conn)
        orden_pago = repo._reflect_table("ORDEN_PAGO")  # noqa: SLF001
        opi_t = repo._reflect_optional_table("ORDEN_PAGO_IMPUT")  # noqa: SLF001
        deduc_t = repo._reflect_optional_table("ORDEN_PAGO_DEDUC")  # noqa: SLF001
        ded_cat_t = repo._reflect_optional_table("DEDUCCIONES")  # noqa: SLF001
        prov_t = repo._reflect_optional_table("PROVEEDORES")  # noqa: SLF001
        if opi_t is None or deduc_t is None:
            raise SystemExit("Se requieren ORDEN_PAGO_IMPUT y ORDEN_PAGO_DEDUC para la auditoría")

        print(SEP)
        print(f"AUDITORÍA DE ALCANCE DE OP — fuente={conn.dialect.name} schema={repo._schema or '-'} ejercicio>={ej_min}")  # noqa: SLF001
        print(SEP)

        # ── ORDEN_PAGO ──────────────────────────────────────────────────
        op_cols = {name: _col(repo, orden_pago, name) for name in (
            "EJERCICIO", "NRO_OP", "TIPO_OP", "ESTADO_OP", "CONFIRMADO", "COD_PROV", "IMPORTE_TOTAL",
        )}
        concepto_col = repo._safe_column(orden_pago, "CONCEPTO")  # noqa: SLF001
        sel = list(op_cols.values()) + ([concepto_col] if concepto_col is not None else [])
        ops = _fetch(conn, select(*sel).where(op_cols["EJERCICIO"] >= ej_min))
        confirmed = [o for o in ops if _s(o["ESTADO_OP"]).upper() == "C" and _s(o["CONFIRMADO"]).upper() == "S"]
        by_key = {(int(o["EJERCICIO"]), int(o["NRO_OP"])): o for o in confirmed}

        print("\n[1] Distribución de TIPO_OP en ORDEN_PAGO")
        print(SUB)
        dist = Counter((_s(o["TIPO_OP"]) or "(vacío)", _s(o["ESTADO_OP"]), _s(o["CONFIRMADO"])) for o in ops)
        for (tipo, estado, conf), n in sorted(dist.items()):
            print(f"  TIPO_OP={tipo:<7} ESTADO_OP={estado:<2} CONFIRMADO={conf:<2} -> {n:>6}")

        # ── ORDEN_PAGO_IMPUT ────────────────────────────────────────────
        opi_ej, opi_op = _col(repo, opi_t, "EJERCICIO"), _col(repo, opi_t, "NRO_OP")
        opi_tipo = _col(repo, opi_t, "TIPO_COMPROB")
        opi_rows = _fetch(conn, select(opi_ej, opi_op, opi_tipo).where(opi_ej >= ej_min))
        tipos_by_op: dict[tuple[int, int], set[str]] = defaultdict(set)
        for r in opi_rows:
            tipos_by_op[(int(r["EJERCICIO"]), int(r["NRO_OP"]))].add(_s(r["TIPO_COMPROB"]).upper() or "(vacío)")

        print("\n[2] OP confirmadas SIN ninguna fila en ORDEN_PAGO_IMPUT (= no pueden migrarse), por TIPO_OP")
        print(SUB)
        sin_opi = [o for k, o in by_key.items() if k not in tipos_by_op]
        con_opi = [o for k, o in by_key.items() if k in tipos_by_op]
        agg: dict[str, list] = defaultdict(lambda: [0, Decimal(0), Counter()])
        for o in sin_opi:
            tipo = _s(o["TIPO_OP"]) or "(vacío)"
            agg[tipo][0] += 1
            agg[tipo][1] += _money(o["IMPORTE_TOTAL"])
            if concepto_col is not None:
                agg[tipo][2][_s(o.get("CONCEPTO"))[:40].lower() or "(sin concepto)"] += 1
        for tipo, (n, imp, conceptos) in sorted(agg.items()):
            print(f"  TIPO_OP={tipo:<7} {n:>6} OP  {_fmt(imp)}")
            for concepto, c in conceptos.most_common(8):
                print(f"      · {c:>4}× {concepto}")
        print(f"  (con imputación: {Counter(_s(o['TIPO_OP']) or '(vacío)' for o in con_opi)})")
        if not sin_opi:
            print("  ninguna")

        # ── Estado local: cola y links ──────────────────────────────────
        retry = RetryStore()
        links = EntityLinkStore()
        op_links = {l["source_key"]: l for l in links.get_all_links("orden_pago")}
        try:
            print("\n[3] Cola de reintentos orden_pago (missing_payment_imputation) cruzada con TIPO_OP real")
            print(SUB)
            queued = [i for i in retry.list_items("orden_pago") if (i.reason_detail or "") == "missing_payment_imputation"]
            cross = Counter()
            missing = 0
            for item in queued:
                try:
                    ext = json.loads(item.external_id)
                    key = (int(ext["ejercicio"]), int(ext["nro_op"]))
                except Exception:  # noqa: BLE001
                    cross["(clave ilegible)"] += 1
                    continue
                op = by_key.get(key)
                if op is None:
                    missing += 1
                    continue
                cross[f"TIPO_OP={_s(op['TIPO_OP']) or '(vacío)'} imput={'sí' if key in tipos_by_op else 'no'}"] += 1
            print(f"  encoladas: {len(queued)}  (no encontradas como C/S en la fuente: {missing})")
            for label, n in cross.most_common():
                print(f"  {n:>6}  {label}")

            # ── Composición de comprobantes de las OP de proveedor ─────
            print("\n[4] OP confirmadas CON imputación, por composición de TIPO_COMPROB")
            print(SUB)
            comp = Counter()
            comp_imp: dict[str, Decimal] = defaultdict(Decimal)
            for key, o in by_key.items():
                tipos = tipos_by_op.get(key)
                if not tipos:
                    continue
                label = ",".join(sorted(tipos))
                comp[label] += 1
                comp_imp[label] += _money(o["IMPORTE_TOTAL"])
            for label, n in comp.most_common(args.top):
                print(f"  {n:>6}  {_fmt(comp_imp[label]):>22}  {label}")

            print("\n[5] OP respaldadas ÚNICAMENTE por liquidaciones (LIQ/LIR), por COD_PROV")
            print(SUB)
            liq_keys = [k for k, tipos in tipos_by_op.items() if k in by_key and tipos and tipos <= {"LIQ", "LIR"}]
            liq_by_prov: dict[str, list] = defaultdict(lambda: [0, Decimal(0), 0])
            for k in liq_keys:
                o = by_key[k]
                prov = _s(o["COD_PROV"])
                liq_by_prov[prov][0] += 1
                liq_by_prov[prov][1] += _money(o["IMPORTE_TOTAL"])
                link = op_links.get(_op_key(*k))
                if link and link.get("remote_id"):
                    liq_by_prov[prov][2] += 1
            prov_info = _fetch_proveedores(conn, repo, prov_t, list(liq_by_prov))
            for prov, (n, imp, linked) in sorted(liq_by_prov.items(), key=lambda kv: -kv[1][0]):
                info = prov_info.get(prov)
                razon = info["RAZON_SOCIAL"] if info else "(NO está en PROVEEDORES)"
                tipo_prov = f" TIPO_PROV={info['TIPO_PROV']}" if info else ""
                excl = " [YA EXCLUIDO]" if _to_int(prov) in EXCLUDED_COD_PROV else ""
                print(f"  COD_PROV={prov:<7} {n:>5} OP  {_fmt(imp):>22}  migradas={linked:<5} {razon}{tipo_prov}{excl}")
            if not liq_keys:
                print("  ninguna")

            # ── Deducciones ─────────────────────────────────────────────
            print("\n[6] Deducciones de OP confirmadas por TIPO_DEDUC (I=impositiva, O=otra)")
            print(SUB)
            ded_cat: dict[tuple[str, int | None], dict] = {}
            if ded_cat_t is not None:
                cat_cols = [_col(repo, ded_cat_t, "CODIGO"), _col(repo, ded_cat_t, "DESCRIPCION")]
                cat_tipo = repo._safe_column(ded_cat_t, "TIPO_DEDUC")  # noqa: SLF001
                cat_ej = repo._safe_column(ded_cat_t, "EJERCICIO")  # noqa: SLF001
                cat_cols += [c for c in (cat_tipo, cat_ej) if c is not None]
                for r in _fetch(conn, select(*cat_cols)):
                    ej = _to_int(r.get("EJERCICIO"))
                    ded_cat[(_s(r["CODIGO"]), ej)] = r
                    ded_cat.setdefault((_s(r["CODIGO"]), None), r)
            d_ej, d_op = _col(repo, deduc_t, "EJERCICIO"), _col(repo, deduc_t, "NRO_OP")
            d_cod, d_imp = _col(repo, deduc_t, "CODIGO_DEDUC"), _col(repo, deduc_t, "IMPORTE_RETEN")
            ded_rows = _fetch(conn, select(d_ej, d_op, d_cod, d_imp).where(d_ej >= ej_min))
            ded_by_op: dict[tuple[int, int], list[tuple[str, str, Decimal]]] = defaultdict(list)
            per_code: dict[tuple[str, str, str], list] = defaultdict(lambda: [set(), Decimal(0)])
            for r in ded_rows:
                key = (int(r["EJERCICIO"]), int(r["NRO_OP"]))
                if key not in by_key:
                    continue
                imp = _money(r["IMPORTE_RETEN"])
                if imp <= 0:
                    continue
                cod = _s(r["CODIGO_DEDUC"])
                cat = ded_cat.get((cod, key[0])) or ded_cat.get((cod, None)) or {}
                tipo = _s(cat.get("TIPO_DEDUC")) or "?"
                descr = " ".join(_s(cat.get("DESCRIPCION")).split()) or "(sin catálogo)"
                ded_by_op[key].append((cod, tipo, imp))
                per_code[(tipo, cod, descr)][0].add(key)
                per_code[(tipo, cod, descr)][1] += imp
            for (tipo, cod, descr), (keys, imp) in sorted(per_code.items(), key=lambda kv: (kv[0][0], -len(kv[1][0]))):
                excluded_only = all(_to_int(by_key[k]["COD_PROV"]) in EXCLUDED_COD_PROV or k in liq_keys for k in keys)
                flag = "  (solo en OP LIQ/excluidas)" if excluded_only else ""
                print(f"  {tipo}  cod={cod:<5} {len(keys):>5} OP  {_fmt(imp):>22}  {descr}{flag}")

            print("\n[7] Cola retenciones (retention_type_unresolved) cruzada con la composición real de deducciones")
            print(SUB)
            queued_ret = [i for i in retry.list_items("retenciones") if (i.reason_detail or "") == "retention_type_unresolved"]
            cls = Counter()
            unresolved_o_codes = Counter()
            for item in queued_ret:
                try:
                    ext = json.loads(item.external_id)
                    key = (int(ext["ejercicio"]), int(ext["nro_op"]))
                except Exception:  # noqa: BLE001
                    cls["(clave ilegible)"] += 1
                    continue
                deds = ded_by_op.get(key, [])
                tipos = {t for _, t, _ in deds}
                prov = _s(by_key[key]["COD_PROV"]) if key in by_key else "?"
                liq = " LIQ" if key in set(liq_keys) else ""
                if not deds:
                    cls[f"sin deducciones >0{liq}"] += 1
                elif "I" in tipos:
                    cls[f"tiene alguna impositiva (I){liq}"] += 1
                else:
                    cls[f"solo no impositivas (O){liq} COD_PROV={prov}"] += 1
                    for cod, t, _ in deds:
                        unresolved_o_codes[cod] += 1
            print(f"  encoladas: {len(queued_ret)}")
            for label, n in cls.most_common():
                print(f"  {n:>6}  {label}")
            if unresolved_o_codes:
                print(f"  códigos O involucrados: {dict(unresolved_o_codes.most_common())}")

            print("\n[8] Deducciones NO impositivas en OP de proveedores REALES (no LIQ, no excluidos): impacto en neto")
            print(SUB)
            real_o: dict[tuple[str, str], list] = defaultdict(lambda: [set(), Decimal(0)])
            for key, deds in ded_by_op.items():
                if key in set(liq_keys) or _to_int(by_key[key]["COD_PROV"]) in EXCLUDED_COD_PROV:
                    continue
                for cod, tipo, imp in deds:
                    if tipo == "I":
                        continue
                    cat = ded_cat.get((cod, key[0])) or ded_cat.get((cod, None)) or {}
                    descr = " ".join(_s(cat.get("DESCRIPCION")).split()) or "(sin catálogo)"
                    real_o[(cod, descr)][0].add(key)
                    real_o[(cod, descr)][1] += imp
            for (cod, descr), (keys, imp) in sorted(real_o.items(), key=lambda kv: -len(kv[1][0])):
                print(f"  cod={cod:<5} {len(keys):>5} OP  {_fmt(imp):>22}  {descr}")
            if not real_o:
                print("  ninguna")
        finally:
            retry.close()
            links.close()

    print("\n" + SEP)
    print("Fin. No se modificó ningún dato.")
    return 0


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _fetch_proveedores(conn, repo, prov_t, cod_provs: list[str]) -> dict[str, dict]:
    if prov_t is None or not cod_provs:
        return {}
    p_cod = _col(repo, prov_t, "COD_PROV")
    p_razon = _col(repo, prov_t, "RAZON_SOCIAL")
    p_tipo = repo._safe_column(prov_t, "TIPO_PROV")  # noqa: SLF001
    cols = [p_cod, p_razon] + ([p_tipo] if p_tipo is not None else [])
    out: dict[str, dict] = {}
    ints = [v for v in (_to_int(c) for c in cod_provs) if v is not None]
    for i in range(0, len(ints), _IN_CHUNK):
        chunk = ints[i:i + _IN_CHUNK]
        for r in _fetch(conn, select(*cols).where(and_(p_cod.in_(chunk)))):
            out[_s(r["COD_PROV"])] = {
                "RAZON_SOCIAL": _s(r["RAZON_SOCIAL"]),
                "TIPO_PROV": _s(r.get("TIPO_PROV")),
            }
    return out


if __name__ == "__main__":
    sys.exit(main())
