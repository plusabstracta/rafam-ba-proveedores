#!/usr/bin/env python3
"""
main.py — CLI entry point for the RAFAM → Paxapos incremental sync.

Usage:
    python main.py status
    python main.py reset --entity=proveedores
    python main.py reset --all
    python main.py run [--entity=proveedores]
"""

import argparse
import os
import sys

import oracledb
from dotenv import load_dotenv

from src.checkpoint_store import CheckpointStore
from src.exporter import build_exporter
from src.sync_engine import ENTITY_CONFIGS, SyncEngine

load_dotenv()

DB_HOST     = os.getenv("DB_HOST", "10.10.91.241")
DB_PORT     = int(os.getenv("DB_PORT", 1521))
DB_SERVICE  = os.getenv("DB_SERVICE", "BDRAFAM")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


def _build_engine() -> SyncEngine:
    return SyncEngine(CheckpointStore())


# ─── status ──────────────────────────────────────────────────────────────────

def cmd_status(_args) -> None:
    engine = _build_engine()
    checkpoints = {cp.entity: cp for cp in engine._store.all_checkpoints()}
    known = sorted(ENTITY_CONFIGS.keys())

    col = "{:<20} {:<14} {:<12} {:<22} {:<22} {}"
    print()
    print(col.format("Entidad", "Estado", "Último ID", "Último TS", "Último run", "Enviados"))
    print("─" * 100)

    for entity in known:
        cp = checkpoints.get(entity)
        if cp is None:
            print(col.format(entity, "⏳ pendiente", "—", "—", "—", 0))
            continue

        icon = "✅" if cp.status == "ok" else "❌"
        last_id  = str(cp.last_id)  if cp.last_id  is not None else "—"
        last_ts  = cp.last_ts.strftime("%Y-%m-%d %H:%M:%S")  if cp.last_ts  else "—"
        last_run = cp.last_run.strftime("%Y-%m-%d %H:%M:%S") if cp.last_run else "—"
        status_label = f"{icon} {cp.status[:10]}"
        print(col.format(entity, status_label, last_id, last_ts, last_run, cp.records_sent))

    print()


# ─── reset ───────────────────────────────────────────────────────────────────

def cmd_reset(args) -> None:
    if not args.entity and not args.all:
        print("❌  Especificá --entity=<nombre> o --all")
        sys.exit(1)

    engine = _build_engine()

    if args.all:
        for entity in ENTITY_CONFIGS:
            engine.reset_checkpoint(entity)
            print(f"  🔄 Reseteado: {entity}")
        print("✅  Todos los checkpoints reseteados — próxima ejecución será full load.")
        return

    if args.entity not in ENTITY_CONFIGS:
        print(f"❌  Entidad desconocida: '{args.entity}'")
        print(f"    Entidades válidas: {', '.join(sorted(ENTITY_CONFIGS))}")
        sys.exit(1)

    engine.reset_checkpoint(args.entity)
    print(f"✅  Checkpoint reseteado: {args.entity}")


# ─── run ─────────────────────────────────────────────────────────────────────

def cmd_run(args) -> None:
    if args.entity and args.entity not in ENTITY_CONFIGS:
        print(f"❌  Entidad desconocida: '{args.entity}'")
        sys.exit(1)

    try:
        oracledb.init_oracle_client(lib_dir=r"C:\oracle\instantclient")
        dsn  = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE)
        conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=dsn)
        print(f"✅  Conectado a [{DB_SERVICE}] en {DB_HOST}:{DB_PORT}\n")
    except oracledb.Error as exc:
        print(f"❌  Error al conectar: {exc}")
        sys.exit(1)

    exporter = build_exporter(args.export)
    engine   = _build_engine()
    targets  = [args.entity] if args.entity else list(ENTITY_CONFIGS.keys())

    try:
        for entity in targets:
            cfg = ENTITY_CONFIGS[entity]
            cp  = engine.get_checkpoint(entity)
            mode = "FULL LOAD" if (cp.is_fresh or cfg.full_load) else "INCREMENTAL"
            print(f"🔍  [{mode:<11}] {entity} ...", end=" ", flush=True)

            try:
                sql, params = engine.build_incremental_query(entity, cfg.base_query)
                batch_size = args.batch_size
                limit      = args.limit

                total     = 0
                last_id   = None
                last_ts   = None
                columns   = None

                with conn.cursor() as cursor:
                    cursor.execute(sql, params)
                    columns = [col[0] for col in cursor.description]

                    # Validate cursor fields exist in the actual result columns
                    cols_upper = {c.upper() for c in columns}
                    if cfg.id_field and cfg.id_field.upper() not in cols_upper:
                        print(f"\n  ⚠️  id_field '{cfg.id_field}' no encontrado en columnas reales de {entity}.")
                        print(f"     Columnas disponibles: {', '.join(columns)}")
                    if cfg.ts_field and cfg.ts_field.upper() not in cols_upper:
                        print(f"\n  ⚠️  ts_field '{cfg.ts_field}' no encontrado en columnas reales de {entity}.")
                        print(f"     Columnas disponibles: {', '.join(columns)}")
                        print(f"     → Actualizá ts_field en ENTITY_CONFIGS para habilitar modo incremental.")

                    while True:
                        fetch_n = batch_size if limit is None else min(batch_size, limit - total)
                        batch   = cursor.fetchmany(fetch_n)
                        if not batch:
                            break

                        bid, bts = engine.extract_cursor_values(columns, batch, entity)
                        if bid is not None:
                            last_id = max(last_id, bid) if last_id is not None else bid
                        if bts is not None:
                            last_ts = max(last_ts, bts) if last_ts is not None else bts

                        exporter.write_batch(entity, columns, batch)

                        # ── Opción B (futuro): gateway Paxapos ────────────────
                        # from src.gateway_client import GatewayClient
                        # GatewayClient().upsert_batch(entity, columns, batch)
                        # ─────────────────────────────────────────────────────

                        total += len(batch)
                        print(f"\r🔍  [{mode:<11}] {entity} ... {total} filas", end="", flush=True)

                        if limit is not None and total >= limit:
                            break

                engine.mark_success(entity, last_id, last_ts, total)
                print(f"\r🔍  [{mode:<11}] {entity} ... {total:>6} registros  ")

            except Exception as exc:
                engine.mark_error(entity, str(exc))
                print(f"ERROR — {exc}")

    finally:
        exporter.close()
        conn.close()
        print("\n🔒  Conexión cerrada.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Motor de sincronización incremental RAFAM → Paxapos",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Muestra el checkpoint de cada entidad")

    reset_p = sub.add_parser("reset", help="Resetea checkpoints para forzar full load")
    reset_p.add_argument("--entity", metavar="NOMBRE", help="Entidad a resetear")
    reset_p.add_argument("--all", action="store_true", help="Resetear todas las entidades")

    run_p = sub.add_parser("run", help="Ejecuta la sincronización incremental")
    run_p.add_argument("--entity", metavar="NOMBRE", help="Sincronizar solo esta entidad")
    run_p.add_argument("--limit", type=int, metavar="N", help="Máximo de filas por entidad (útil para testear)")
    run_p.add_argument("--batch-size", type=int, default=500, metavar="N", help="Filas por lote (default: 500)")
    run_p.add_argument("--export", choices=["csv", "noop"], default="csv", help="Destino de salida: csv (default) | noop (solo checkpoints)")

    args = parser.parse_args()
    {"status": cmd_status, "reset": cmd_reset, "run": cmd_run}[args.command](args)


if __name__ == "__main__":
    main()
