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
import json
import logging
import os
import sys
import time

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from src.checkpoint_store import CheckpointStore
from src.config import ENTITY_CONFIGS
from src.db import create_source_engine
from src.exporter import BaseExporter, build_exporter, fetch_migrator_lookups, fetch_migrator_spec
from src.source_repository import SourceRepository
from src.sync_engine import SyncEngine

load_dotenv()

logger = logging.getLogger(__name__)


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
        logger.error("Especificá --entity=<nombre> o --all")
        sys.exit(1)

    engine = _build_engine()

    if args.all:
        for entity in ENTITY_CONFIGS:
            engine.reset_checkpoint(entity)
            logger.info("Reseteado: %s", entity)
        logger.info("Todos los checkpoints reseteados — próxima ejecución será full load.")
        return

    if args.entity not in ENTITY_CONFIGS:
        logger.error(
            "Entidad desconocida: '%s'. Válidas: %s",
            args.entity, ", ".join(sorted(ENTITY_CONFIGS)),
        )
        sys.exit(1)

    engine.reset_checkpoint(args.entity)
    logger.info("Checkpoint reseteado: %s", args.entity)


# ─── run ─────────────────────────────────────────────────────────────────────


def _sync_entity(
    source_repo: SourceRepository,
    engine: SyncEngine,
    exporter: BaseExporter,
    entity: str,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
) -> None:
    """Execute the incremental sync for a single entity."""
    cp  = engine.get_checkpoint(entity)
    cfg = ENTITY_CONFIGS[entity]
    mode = "FULL LOAD" if (cp.is_fresh or cfg.full_load) else "INCREMENTAL"
    batch_delay = float(os.getenv("MIGRATOR_BATCH_DELAY_SECONDS", "0"))

    try:
        stmt = source_repo.build_statement(entity, cp)
        total   = 0
        last_id = None
        last_ts = None

        result = source_repo.execute(stmt)
        columns = list(result.keys())
        _warn_missing_cursor_fields(cfg, columns, entity)

        batch_count = 0
        while True:
            fetch_n = batch_size if limit is None else min(batch_size, limit - total)
            if fetch_n <= 0:
                break

            raw_rows = result.fetchmany(fetch_n)
            if not raw_rows:
                break

            batch = [tuple(row) for row in raw_rows]

            bid, bts = engine.extract_cursor_values(columns, batch, entity)
            if bid is not None:
                last_id = max(last_id, bid) if last_id is not None else bid
            if bts is not None:
                last_ts = max(last_ts, bts) if last_ts is not None else bts

            if batch_delay > 0 and batch_count > 0:
                time.sleep(batch_delay)

            exporter.write_batch(entity, columns, batch)
            total += len(batch)
            batch_count += 1

            if limit is not None and total >= limit:
                break

        if dry_run:
            logger.info("[DRY RUN   ] %s — %d registros (sin avanzar checkpoint)", entity, total)
        else:
            engine.mark_success(entity, last_id, last_ts, total)
            logger.info("[%-11s] %s — %d registros", mode, entity, total)

    except Exception as exc:
        if not dry_run:
            engine.mark_error(entity, str(exc))
        logger.error("[%-11s] %s — ERROR: %s", mode, entity, exc, exc_info=True)


def _warn_missing_cursor_fields(cfg, columns: list[str], entity: str) -> None:
    """Log warnings if configured cursor fields aren't present in query results."""
    cols_upper = {c.upper() for c in columns}
    if cfg.id_field and cfg.id_field.upper() not in cols_upper:
        logger.warning(
            "id_field '%s' no encontrado en columnas reales de %s. Disponibles: %s",
            cfg.id_field, entity, ", ".join(columns),
        )
    if cfg.ts_field and cfg.ts_field.upper() not in cols_upper:
        logger.warning(
            "ts_field '%s' no encontrado en columnas reales de %s. Disponibles: %s "
            "→ Actualiza ts_field en ENTITY_CONFIGS para habilitar modo incremental.",
            cfg.ts_field, entity, ", ".join(columns),
        )


def cmd_run(args) -> None:
    if args.entity and args.entity not in ENTITY_CONFIGS:
        logger.error("Entidad desconocida: '%s'", args.entity)
        sys.exit(1)

    exporter = build_exporter(args.export, force_update=args.force_update, dry_run=args.dry_run)
    engine   = _build_engine()
    targets  = [args.entity] if args.entity else list(ENTITY_CONFIGS.keys())

    try:
        source_engine = create_source_engine()
        with source_engine.connect() as conn:
            logger.info("Conexión a base origen establecida (%s)", source_engine.url.get_backend_name())
            source_repo = SourceRepository(conn)
            for entity in targets:
                _sync_entity(source_repo, engine, exporter, entity, args.batch_size, args.limit, args.dry_run)
    except (SQLAlchemyError, ValueError) as exc:
        logger.error("Error en la ejecución: %s", exc)
        sys.exit(1)
    finally:
        exporter.close()
        logger.info("Proceso finalizado.")


def cmd_spec(args) -> None:
    if args.target != "migrator":
        logger.error("Target de spec no soportado: %s", args.target)
        sys.exit(1)

    try:
        spec = fetch_migrator_spec()
    except Exception as exc:
        logger.error("No se pudo consultar spec: %s", exc)
        sys.exit(1)

    print(json.dumps(spec, ensure_ascii=False, indent=2))


def cmd_lookups(args) -> None:
    sections = []
    if args.only:
        sections = [part.strip() for part in args.only.split(",") if part.strip()]

    try:
        lookups = fetch_migrator_lookups(sections)
    except Exception as exc:
        logger.error("No se pudieron consultar lookups: %s", exc)
        sys.exit(1)

    print(json.dumps(lookups, ensure_ascii=False, indent=2))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    app_env = os.getenv("APP_ENV", "dev").strip().lower()
    default_level = "DEBUG" if app_env == "dev" else "INFO"
    log_level_name = os.getenv("LOG_LEVEL", default_level).strip().upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Motor de sincronización incremental RAFAM → Paxapos",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Muestra el checkpoint de cada entidad")

    spec_p = sub.add_parser("spec", help="Consulta contratos remotos disponibles")
    spec_p.add_argument(
        "--target",
        choices=["migrator"],
        default="migrator",
        help="Contrato remoto a consultar (default: migrator)",
    )

    lookups_p = sub.add_parser("lookups", help="Consulta catálogos remotos del migrator")
    lookups_p.add_argument(
        "--only",
        metavar="SECCIONES",
        help=(
            "Secciones separadas por coma; ej: mercaderias,unidades_de_medida,tipos_factura,tipos_de_pago,proveedores,gastos"
        ),
    )

    reset_p = sub.add_parser("reset", help="Resetea checkpoints para forzar full load")
    reset_p.add_argument("--entity", metavar="NOMBRE", help="Entidad a resetear")
    reset_p.add_argument("--all", action="store_true", help="Resetear todas las entidades")

    run_p = sub.add_parser("run", help="Ejecuta la sincronización incremental")
    run_p.add_argument("--entity", metavar="NOMBRE", help="Sincronizar solo esta entidad")
    run_p.add_argument("--limit", type=int, metavar="N", help="Máximo de filas por entidad (útil para testear)")
    run_p.add_argument("--batch-size", type=int, default=500, metavar="N", help="Filas por lote (default: 500)")
    run_p.add_argument(
        "--export",
        choices=["csv", "noop", "gateway", "migrator"],
        default="csv",
        help="Destino de salida: csv (default) | noop (solo checkpoints) | gateway | migrator",
    )
    run_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview: no avanza checkpoints; en migrator envia payload con dry_run=true",
    )
    run_p.add_argument(
        "--force-update",
        action="store_true",
        help=(
            "Solo gateway: si existe vinculacion local RAFAM->Paxapos, "
            "envia update en vez de saltear (default: create-only)"
        ),
    )

    args = parser.parse_args()
    {"status": cmd_status, "reset": cmd_reset, "run": cmd_run, "spec": cmd_spec, "lookups": cmd_lookups}[args.command](args)


if __name__ == "__main__":
    main()
