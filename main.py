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
import fcntl
import json
import logging
import logging.handlers
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from src.checkpoint_store import CheckpointStore
from src.config import ENTITY_CONFIGS
from src.db import create_source_engine
from src.entity_link_store import EntityLinkStore
from src.exporter import BaseExporter, _env_bool, build_exporter, fetch_migrator_lookups, fetch_migrator_spec
from src.retry_store import RetryStore
from src.source_repository import SourceRepository
from src.sync_engine import SyncEngine

load_dotenv()

logger = logging.getLogger(__name__)


_GROUPED_BATCH_FIELDS = {
    "oc_items": ["EJERCICIO", "UNI_COMPRA", "NRO_OC"],
    "orden_compra": ["EJERCICIO", "UNI_COMPRA", "NRO_OC"],
    "orden_pago": ["EJERCICIO", "NRO_OP"],
    "retenciones": ["EJERCICIO", "NRO_OP"],
}

# Maps entity config names to the link store entity they write to.
_ENTITY_LINK_NAMES: dict[str, str] = {
    "proveedores": "proveedores",
    "orden_compra": "orden_compra",
    "oc_items": "orden_compra",
    "solic_gastos": "gasto",
    "orden_pago": "orden_pago",
}


def _build_engine() -> SyncEngine:
    return SyncEngine(CheckpointStore())


_LOCK_PATH = Path(__file__).resolve().parent / "state" / "migrator.lock"


@contextmanager
def _exclusive_run_lock():
    """Lock exclusivo via fcntl.flock para que dos cron concurrentes no se pisen.

    Si otro proceso esta corriendo `main.py run`, este sale con codigo 75
    (EX_TEMPFAIL) en vez de avanzar checkpoints en paralelo. El lock se libera
    automaticamente al cerrar el FD (fin de proceso o context exit).
    """
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = open(_LOCK_PATH, "w")
    try:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.error(
                "Otro proceso ya esta ejecutando el sync (lock: %s). Saliendo sin avanzar checkpoints.",
                _LOCK_PATH,
            )
            sys.exit(75)
        # Marca PID del owner para diagnostico.
        try:
            fd.seek(0)
            fd.truncate()
            fd.write(f"{os.getpid()}\n")
            fd.flush()
        except OSError:
            pass
        yield
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fd.close()


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
    link_store = EntityLinkStore()

    if args.all:
        for entity in ENTITY_CONFIGS:
            engine.reset_checkpoint(entity)
            logger.info("Reseteado: %s", entity)
        cleared = link_store.clear_all()
        for link_entity, count in cleared.items():
            if count:
                logger.info("Links borrados: %s (%d)", link_entity, count)
        link_store.close()
        logger.info("Todos los checkpoints y links reseteados — próxima ejecución será full load.")
        return

    if args.entity not in ENTITY_CONFIGS:
        logger.error(
            "Entidad desconocida: '%s'. Válidas: %s",
            args.entity, ", ".join(sorted(ENTITY_CONFIGS)),
        )
        sys.exit(1)

    engine.reset_checkpoint(args.entity)
    link_entity = _ENTITY_LINK_NAMES.get(args.entity)
    if link_entity:
        count = link_store.clear_entity(link_entity)
        logger.info("Links borrados: %s (%d)", link_entity, count)
    link_store.close()
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
) -> bool:
    """Execute the incremental sync for a single entity.

    Returns True si la entidad se sincronizo OK, False si hubo error. El caller
    usa este flag para devolver exit code != 0 al SO/cron.
    """
    cp  = engine.get_checkpoint(entity)
    cfg = ENTITY_CONFIGS[entity]
    mode = "FULL LOAD" if (cp.is_fresh or cfg.full_load) else "INCREMENTAL"
    batch_delay = float(os.getenv("RAFAM_SYNC_BATCH_DELAY_SECONDS", "0"))
    # Si un batch individual falla queremos seguir con los proximos batches
    # de la misma entidad (no cortar la corrida). Acumulamos errores y al
    # final marcamos la entidad como con errores para que el caller decida.
    failed_batches = 0
    last_batch_error: str | None = None

    try:
        stmt = source_repo.build_statement(entity, cp)
        total   = 0
        last_id = None
        last_ts = None

        result = source_repo.execute(stmt)
        columns = list(result.keys())
        _warn_missing_cursor_fields(cfg, columns, entity)

        batch_count = 0

        def process_batch(batch: list[tuple]) -> None:
            nonlocal last_id, last_ts, total, batch_count, failed_batches, last_batch_error
            bid, bts = engine.extract_cursor_values(columns, batch, entity)
            if bid is not None:
                last_id = max(last_id, bid) if last_id is not None else bid
            if bts is not None:
                last_ts = max(last_ts, bts) if last_ts is not None else bts

            if batch_delay > 0 and batch_count > 0:
                time.sleep(batch_delay)

            try:
                exporter.write_batch(entity, columns, batch)
            except Exception as exc:
                # Aislamiento por batch: si el POST falla (HTTP 5xx, validacion
                # del backend, JSON parse, etc.) NO cortamos la entidad. Logueamos
                # el error con stack trace y seguimos con el proximo batch. El
                # watermark NO se avanza para este batch (esta logica ya esta abajo:
                # solo se avanza despues del write exitoso).
                failed_batches += 1
                last_batch_error = str(exc)
                logger.error(
                    "[%-11s] %s — batch #%d (%d filas) FALLO: %s. Continuando con el siguiente batch.",
                    mode, entity, batch_count + 1, len(batch), exc,
                    exc_info=True,
                )
                batch_count += 1
                return

            total += len(batch)
            batch_count += 1

            # Watermark incremental: persistir progreso por batch para que un
            # crash a mitad de corrida no rebobine al inicio. Solo cuando la
            # entidad tiene cursor real (no full_load) y no estamos en dry-run.
            if not dry_run and not cfg.full_load and (bid is not None or bts is not None):
                try:
                    engine.advance_partial(entity, bid, bts, len(batch))
                except Exception as cp_exc:  # pragma: no cover - defensive
                    logger.warning(
                        "[%s] No se pudo persistir watermark parcial: %s",
                        entity, cp_exc,
                    )

        group_fields = _GROUPED_BATCH_FIELDS.get(entity)
        if group_fields:
            for batch in _iter_grouped_batches(result, columns, group_fields, batch_size):
                if limit is not None and total >= limit:
                    break
                process_batch(batch)
                if limit is not None and total >= limit:
                    break
        else:
            while True:
                fetch_n = batch_size if limit is None else min(batch_size, limit - total)
                if fetch_n <= 0:
                    break

                raw_rows = result.fetchmany(fetch_n)
                if not raw_rows:
                    break

                process_batch([tuple(row) for row in raw_rows])


        if dry_run:
            logger.info("[DRY RUN   ] %s — %d registros (sin avanzar checkpoint)", entity, total)
        else:
            if failed_batches > 0:
                # Hubo batches que fallaron pero la corrida siguió. Marcamos la
                # entidad como con errores para que el caller devuelva exit!=0
                # y el cron/operador se entere, pero no perdimos las filas OK.
                msg = f"{failed_batches} batch(es) fallaron; ultimo error: {last_batch_error}"
                engine.mark_error(entity, msg)
                logger.error(
                    "[%-11s] %s — %d registros OK, %d batch(es) con error. Ultimo: %s",
                    mode, entity, total, failed_batches, last_batch_error,
                )
                return False
            engine.mark_success(entity, last_id, last_ts, total)
            logger.info("[%-11s] %s — %d registros", mode, entity, total)
        return True

    except Exception as exc:
        if not dry_run:
            engine.mark_error(entity, str(exc))
        logger.error("[%-11s] %s — ERROR: %s", mode, entity, exc, exc_info=True)
        return False


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


def _iter_grouped_batches(result, columns: list[str], group_fields: list[str], batch_size: int):
    """Yield batches without splitting rows that share the same business key."""
    col_idx = {name.upper(): i for i, name in enumerate(columns)}
    group_indexes = [col_idx.get(field.upper()) for field in group_fields]
    if any(index is None for index in group_indexes):
        while True:
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            yield [tuple(row) for row in rows]
        return

    pending: list[tuple] = []
    current_group: list[tuple] = []
    current_key = None

    while True:
        rows = result.fetchmany(batch_size)
        if not rows:
            break

        for raw_row in rows:
            row = tuple(raw_row)
            key = tuple(row[index] for index in group_indexes if index is not None)
            if current_group and key != current_key:
                if pending and len(pending) + len(current_group) > batch_size:
                    yield pending
                    pending = []
                pending.extend(current_group)
                current_group = []

            current_key = key
            current_group.append(row)

    if current_group:
        if pending and len(pending) + len(current_group) > batch_size:
            yield pending
            pending = []
        pending.extend(current_group)

    if pending:
        yield pending


def cmd_run(args) -> None:
    if args.entity and args.entity not in ENTITY_CONFIGS:
        logger.error("Entidad desconocida: '%s'", args.entity)
        sys.exit(1)

    with _exclusive_run_lock():
        _cmd_run_locked(args)


def _cmd_run_locked(args) -> None:
    from src.config import _EJERCICIO_MIN, _EJERCICIO_MIN_ENTITIES
    if _EJERCICIO_MIN:
        entidades = ", ".join(sorted(_EJERCICIO_MIN_ENTITIES))
        logger.info(
            "RAFAM_EJERCICIO_MIN=%d — aplica solo a: %s",
            _EJERCICIO_MIN,
            entidades,
        )
    else:
        logger.info("RAFAM_EJERCICIO_MIN no configurado — se procesarán TODOS los ejercicios")

    exporter = build_exporter(args.export, force_update=args.force_update, dry_run=args.dry_run)
    engine   = _build_engine()
    # Cola de reintentos (F1): captura filas rechazadas por el receptor para
    # reintentarlas en la proxima corrida. Manejo fila-a-fila — el batch no se
    # cancela por una fila mala; el watermark avanza con seguridad porque lo
    # pendiente queda registrado aca.
    retry_store = RetryStore()
    if hasattr(exporter, "attach_retry_store"):
        exporter.attach_retry_store(retry_store)
        pending = retry_store.counts_by_entity()
        if pending:
            logger.info("Cola de reintentos al inicio: %s", json.dumps(pending, ensure_ascii=False))
    targets  = [args.entity] if args.entity else list(ENTITY_CONFIGS.keys())

    # En modo migrator, sin --entity explicito, restringir a las 3 entidades oficiales
    # (proveedores, oc_items, orden_pago, retenciones) en orden de FKs. Las demas no se migran:
    #   - orden_compra (header) → reemplazado por oc_items (incluye items embebidos)
    #   - solic_gastos          → los gastos los crean humanos en Paxapos; RAFAM solo manda el pago
    #   - pedidos / ped_items   → deshabilitados, los pedidos llegan como OCs via oc_items
    # retenciones corre al final: depende de que la OP (Egreso) ya exista para
    # resolver el destino; si no, se encola y se reintenta en la proxima corrida.
    if not args.entity and args.export == "migrator":
        official = ["proveedores", "oc_items", "orden_pago", "retenciones"]
        targets = [e for e in official if e in ENTITY_CONFIGS]
        logger.info("Modo migrator: ejecutando entidades oficiales en orden FK → %s", targets)

    failed_entities: list[str] = []
    try:
        source_engine = create_source_engine()
        with source_engine.connect() as conn:
            logger.info("Conexión a base origen establecida (%s)", source_engine.url.get_backend_name())
            source_repo = SourceRepository(conn)
            # Inyectar source_repo al exporter para fetch secundarios
            # (ej: retenciones por OP, evita cartesian en query principal).
            if hasattr(exporter, "attach_source"):
                exporter.attach_source(source_repo)
            for entity in targets:
                ok = _sync_entity(source_repo, engine, exporter, entity, args.batch_size, args.limit, args.dry_run)
                if not ok:
                    failed_entities.append(entity)
    except (SQLAlchemyError, ValueError) as exc:
        logger.error("Error en la ejecución: %s", exc)
        sys.exit(1)
    finally:
        exporter.close()
        try:
            final_pending = retry_store.counts_by_entity()
            if final_pending:
                logger.info("Cola de reintentos al finalizar: %s", json.dumps(final_pending, ensure_ascii=False))
        finally:
            retry_store.close()
        logger.info("Proceso finalizado.")

    if failed_entities:
        logger.error(
            "Sincronización con errores en %d/%d entidades: %s",
            len(failed_entities), len(targets), ", ".join(failed_entities),
        )
        sys.exit(1)


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


def cmd_reconcile(args) -> None:
    """Reconciliacion read-only RAFAM vs estado migrado local (F4).

    Compara conteos de origen contra links migrados y la cola de reintentos.
    NO escribe nada. Sale con codigo 2 si detecta drift (para alertas de cron).
    """
    from src.config import _EJERCICIO_MIN
    from src.reconcile import format_report, has_drift, reconcile

    link_store = EntityLinkStore()
    retry_store = RetryStore()
    try:
        source_engine = create_source_engine()
        with source_engine.connect() as conn:
            source_repo = SourceRepository(conn)
            rows = reconcile(
                source_repo,
                link_store,
                retry_store,
                ejercicio_min=_EJERCICIO_MIN,
            )
    except (SQLAlchemyError, ValueError) as exc:
        logger.error("Error en reconciliacion: %s", exc)
        sys.exit(1)
    finally:
        link_store.close()
        retry_store.close()

    print()
    print(format_report(rows))
    print()

    if has_drift(rows):
        drifted = [r.label for r in rows if r.drift != 0]
        logger.warning("Drift detectado en: %s", ", ".join(drifted))
        sys.exit(2)
    logger.info("Reconciliacion OK: sin drift.")


# ─── Main ─────────────────────────────────────────────────────────────────────


def _setup_file_logging(args) -> None:
    """
    Adjunta un FileHandler con rotacion mensual al logger raiz.

    - Directorio: $RAFAM_LOG_DIR (default: ./logs).
    - Un archivo por script/entidad: rafam-{entity}-YYYY-MM.log.
      Para cmd_run usa el --entity (proveedores | oc_items | orden_pago).
      Para los otros comandos (status/reset/spec/lookups) usa el nombre del comando.
      Si --entity esta vacio en run (corrida full) usa 'all'.
    - Rotacion mensual: cada vez que se ejecuta se abre el archivo del mes en
      curso (rafam-proveedores-2026-05.log). Al cambiar de mes se crea el del
      mes siguiente automaticamente. Codificar el nombre del archivo en YYYY-MM
      da rotacion real, predecible y sin riesgo de perdida (no dependemos del
      TimedRotatingFileHandler que solo rota dentro de un proceso vivo).
    - Override completo via $RAFAM_LOG_FILE (un solo archivo, sin rotacion).
    - Si $RAFAM_LOG_DIR='' o $RAFAM_LOG_DISABLE=true: no escribe a archivo.
    """
    if _env_bool("RAFAM_LOG_DISABLE", "false"):
        return

    log_dir = os.getenv("RAFAM_LOG_DIR", "logs").strip()
    log_file_override = os.getenv("RAFAM_LOG_FILE", "").strip()

    if log_file_override:
        log_path = Path(log_file_override)
    else:
        if not log_dir:
            return
        cmd = getattr(args, "command", "app") or "app"
        if cmd == "run":
            entity = (getattr(args, "entity", None) or "all").strip() or "all"
            base_name = f"rafam-{entity}"
        else:
            base_name = f"rafam-{cmd}"
        month_suffix = datetime.now().strftime("%Y-%m")
        log_path = Path(log_dir) / f"{base_name}-{month_suffix}.log"

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        # Heredar el nivel del root logger (configurado por LOG_LEVEL)
        handler.setLevel(logging.getLogger().level)
        logging.getLogger().addHandler(handler)
        logger.info("Logging a archivo: %s", log_path)
    except OSError as exc:
        logger.warning("No se pudo abrir archivo de log %s: %s", log_path, exc)


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

    sub.add_parser(
        "reconcile",
        help="Reconciliacion read-only RAFAM vs migrado (drift). Exit 2 si hay drift.",
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
    _setup_file_logging(args)
    {"status": cmd_status, "reset": cmd_reset, "run": cmd_run, "spec": cmd_spec, "lookups": cmd_lookups, "reconcile": cmd_reconcile}[args.command](args)


if __name__ == "__main__":
    main()
