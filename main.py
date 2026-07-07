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
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from src.batch_grouping import GROUPED_BATCH_FIELDS, ENTITY_LINK_NAMES, iter_grouped_batches
from src.checkpoint_store import CheckpointStore
from src.config import ENTITY_CONFIGS
from src.db import create_source_engine
from src.entity_link_store import EntityLinkStore
from src.error_formatting import describe_exception, format_exception_context
from src.exporter import BaseExporter, build_exporter, fetch_migrator_lookups, fetch_migrator_spec
from src.logging_config import setup_file_logging
from src.retry_store import RetryStore
from src.run_history import record_run
from src.source_repository import SourceRepository
from src.sync_engine import SyncEngine

load_dotenv()

logger = logging.getLogger(__name__)



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
        retry_store = RetryStore()
        retry_cleared = retry_store.clear_all()
        retry_store.close()
        if retry_cleared:
            logger.info("Cola de reintentos vaciada: %d items eliminados", retry_cleared)
        logger.info("Todos los checkpoints, links y reintentos reseteados — próxima ejecución será full load.")
        return

    if args.entity not in ENTITY_CONFIGS:
        logger.error(
            "Entidad desconocida: '%s'. Válidas: %s",
            args.entity, ", ".join(sorted(ENTITY_CONFIGS)),
        )
        sys.exit(1)

    engine.reset_checkpoint(args.entity)
    link_entity = ENTITY_LINK_NAMES.get(args.entity)
    if link_entity:
        count = link_store.clear_entity(link_entity)
        logger.info("Links borrados: %s (%d)", link_entity, count)
    link_store.close()
    retry_store = RetryStore()
    retry_cleared = retry_store.clear_entity(args.entity)
    retry_store.close()
    if retry_cleared:
        logger.info("Cola de reintentos vaciada para %s: %d items", args.entity, retry_cleared)
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
) -> tuple[bool, str | None, dict]:
    """Execute the incremental sync for a single entity.

    Returns (True, None, metrics) si la entidad se sincronizo OK, (False, error_msg, metrics) si hubo error.
    El caller usa este flag para devolver exit code != 0 al SO/cron y notificar.
    """
    t_start = time.monotonic()
    cp  = engine.get_checkpoint(entity)
    cfg = ENTITY_CONFIGS[entity]
    mode = "FULL LOAD" if (cp.is_fresh or cfg.full_load) else "INCREMENTAL"
    batch_delay = float(os.getenv("RAFAM_SYNC_BATCH_DELAY_SECONDS", "0"))
    # Si un batch individual falla queremos seguir con los proximos batches
    # de la misma entidad (no cortar la corrida). Acumulamos errores y al
    # final marcamos la entidad como con errores para que el caller decida.
    failed_batches = 0
    batches_ok = 0
    batch_times = []
    last_batch_error: str | None = None
    last_batch_error_detail: str | None = None
    query_duration = 0.0
    total = 0

    metrics = {
        "entity": entity,
        "mode": mode,
        "records_ok": 0,
        "batches_ok": 0,
        "batches_failed": 0,
        "query_duration_secs": 0.0,
        "duration_secs": 0.0,
        "batch_times": [],
        "success": False,
        "error_msg": None,
        # Detalle de diagnóstico para el reporte por email (soporte/dev).
        "error_type": None,        # clase de la excepción (ej: RuntimeError)
        "error_location": None,    # archivo, línea y función de origen
        "error_trace": None,       # traceback completo + contexto
        "migrator_error": None,    # mensaje crudo devuelto por el migrator
    }

    try:
        t_query_start = time.monotonic()
        stmt = source_repo.build_statement(entity, cp)
        result = source_repo.execute(stmt)
        query_duration = time.monotonic() - t_query_start
        metrics["query_duration_secs"] = query_duration

        columns = list(result.keys())
        _warn_missing_cursor_fields(cfg, columns, entity)

        batch_count = 0
        last_id = None
        last_ts = None

        def process_batch(batch: list[tuple]) -> None:
            nonlocal last_id, last_ts, total, batch_count, failed_batches, last_batch_error, last_batch_error_detail, batches_ok
            bid, bts = engine.extract_cursor_values(columns, batch, entity)
            if bid is not None:
                last_id = max(last_id, bid) if last_id is not None else bid
            if bts is not None:
                last_ts = max(last_ts, bts) if last_ts is not None else bts

            if batch_delay > 0 and batch_count > 0:
                time.sleep(batch_delay)

            t_batch_start = time.monotonic()
            try:
                exporter.write_batch(entity, columns, batch)
                batch_times.append(time.monotonic() - t_batch_start)
                batches_ok += 1
            except Exception as exc:
                batch_times.append(time.monotonic() - t_batch_start)
                failed_batches += 1
                last_batch_error = str(exc)
                # Capturar contexto detallado (clase, archivo/línea, traceback,
                # y respuesta cruda del migrator) para el reporte por email.
                last_batch_error_detail = format_exception_context(
                    exc, entity, None,
                    f"exporter.write_batch — batch #{batch_count + 1} ({len(batch)} filas)",
                )
                _info = describe_exception(exc)
                metrics["error_type"] = _info["error_type"]
                metrics["error_location"] = _info["error_location"]
                metrics["error_trace"] = last_batch_error_detail
                metrics["migrator_error"] = _info["error_message"]
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

        group_fields = GROUPED_BATCH_FIELDS.get(entity)
        if group_fields:
            for batch in iter_grouped_batches(result, columns, group_fields, batch_size):
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

        metrics["records_ok"] = total
        metrics["batches_ok"] = batches_ok
        metrics["batches_failed"] = failed_batches
        metrics["batch_times"] = batch_times

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
                metrics["success"] = False
                metrics["error_msg"] = msg
                metrics["duration_secs"] = time.monotonic() - t_start
                return False, msg, metrics
            engine.mark_success(entity, last_id, last_ts, total)
            logger.info("[%-11s] %s — %d registros", mode, entity, total)
        
        metrics["success"] = True
        metrics["duration_secs"] = time.monotonic() - t_start
        return True, None, metrics

    except Exception as exc:
        if not dry_run:
            engine.mark_error(entity, str(exc))
        logger.error("[%-11s] %s — ERROR: %s", mode, entity, exc, exc_info=True)
        _info = describe_exception(exc)
        metrics["success"] = False
        metrics["error_msg"] = str(exc)
        metrics["error_type"] = _info["error_type"]
        metrics["error_location"] = _info["error_location"]
        metrics["error_trace"] = format_exception_context(
            exc, entity, None, "sincronización de entidad (nivel superior)",
        )
        metrics["migrator_error"] = _info["error_message"]
        metrics["duration_secs"] = time.monotonic() - t_start
        return False, str(exc), metrics


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

    with _exclusive_run_lock():
        _cmd_run_locked(args)


def _cmd_run_locked(args) -> None:
    from src.config import _EJERCICIO_MIN, _EJERCICIO_MIN_ENTITIES
    import socket
    from datetime import datetime

    run_t0 = time.monotonic()
    run_start_dt = datetime.now()
    start_time_str = run_start_dt.strftime("%Y-%m-%d %H:%M:%S")
    retry_counts_start = {}
    entity_metrics = []

    if _EJERCICIO_MIN:
        if args.entity:
            # Run de una sola entidad: el log habla solo de esa entidad.
            aplica = "aplica" if args.entity in _EJERCICIO_MIN_ENTITIES else "no aplica"
            logger.info(
                "RAFAM_EJERCICIO_MIN=%d — %s a %s",
                _EJERCICIO_MIN,
                aplica,
                args.entity,
            )
        else:
            entidades = ", ".join(sorted(_EJERCICIO_MIN_ENTITIES))
            logger.info(
                "RAFAM_EJERCICIO_MIN=%d — aplica solo a: %s",
                _EJERCICIO_MIN,
                entidades,
            )
    else:
        logger.info("RAFAM_EJERCICIO_MIN no configurado — se procesarán TODOS los ejercicios")

    exporter = None
    retry_store = None
    targets = []
    failed_entities: list[str] = []
    entity_errors: dict[str, str] = {}

    try:
        exporter = build_exporter(dry_run=args.dry_run)
        engine   = _build_engine()

        # Determinar las entidades a procesar ANTES de loguear la cola de reintentos,
        # para filtrar el snapshot por lo que realmente corre esta vez (un run
        # `--entity retenciones` no debe loguear pendientes de orden_pago/oc_items).
        # Sin --entity explicito, ejecutar las 5 entidades oficiales en orden de FKs.
        # Las demas no se migran:
        #   - orden_compra (header) → reemplazado por oc_items (incluye items embebidos)
        #   - pedidos / ped_items   → deshabilitados, los pedidos llegan como OCs via oc_items
        # retenciones corre al final: depende de que la OP (Egreso) ya exista para
        # resolver el destino; si no, se encola y se reintenta en la proxima corrida.
        if args.entity:
            targets = [args.entity]
        else:
            official = ["proveedores", "oc_items", "solic_gastos", "orden_pago", "retenciones"]
            targets = [e for e in official if e in ENTITY_CONFIGS]
            logger.info("Ejecutando entidades oficiales en orden FK → %s", targets)

        # Cola de reintentos (F1): captura filas rechazadas por el receptor para
        # reintentarlas en la proxima corrida. Manejo fila-a-fila — el batch no se
        # cancela por una fila mala; el watermark avanza con seguridad porque lo
        # pendiente queda registrado aca.
        retry_store = RetryStore()
        if hasattr(exporter, "attach_retry_store"):
            exporter.attach_retry_store(retry_store)
            pending = retry_store.counts_by_entity(entities=targets)
            if pending:
                logger.info("Cola de reintentos al inicio: %s", json.dumps(pending, ensure_ascii=False))
                retry_counts_start = dict(pending)

        source_engine = create_source_engine()
        with source_engine.connect() as conn:
            logger.info("Conexión a base origen establecida (%s)", source_engine.url.get_backend_name())
            source_repo = SourceRepository(conn)
            # Inyectar source_repo al exporter para fetch secundarios
            # (ej: retenciones por OP, evita cartesian en query principal).
            if hasattr(exporter, "attach_source"):
                exporter.attach_source(source_repo)
            for entity in targets:
                ok, err_msg, metrics = _sync_entity(source_repo, engine, exporter, entity, args.batch_size, args.limit, args.dry_run)
                entity_metrics.append(metrics)
                if not ok:
                    failed_entities.append(entity)
                    entity_errors[entity] = err_msg or "Error desconocido"

        # Calcular duración total
        run_duration_secs = time.monotonic() - run_t0
        hours, rem = divmod(int(run_duration_secs), 3600)
        minutes, seconds = divmod(rem, 60)
        duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        if failed_entities:
            logger.error(
                "Sincronización con errores en %d/%d entidades: %s",
                len(failed_entities), len(targets), ", ".join(failed_entities),
            )
            # Sin mail por corrida: se registra para el resumen diario
            # (main.py daily-report). El detalle por entidad y la respuesta del
            # migrator viajan dentro de entity_metrics. Los errores de negocio
            # por batch NO cortan la corrida (exit 0) para que cron/make no
            # falle y las demas entidades sigan; solo el `except Exception` de
            # abajo (crash de sistema, caida de DB) es fatal.
            summary_data = {
                "hostname": socket.gethostname(),
                "start_time": start_time_str,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration_formatted": duration_formatted,
                "success": False,
                "error_msg": f"Las siguientes entidades fallaron: {', '.join(failed_entities)}",
            }
            record_run(summary_data, entity_metrics)
        else:
            summary_data = {
                "hostname": socket.gethostname(),
                "start_time": start_time_str,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration_formatted": duration_formatted,
                "success": True,
                "error_msg": None,
            }
            record_run(summary_data, entity_metrics)

    except Exception as exc:
        logger.error("Error en la ejecución de la sincronización: %s", exc, exc_info=True)

        # Calcular duración total
        run_duration_secs = time.monotonic() - run_t0
        hours, rem = divmod(int(run_duration_secs), 3600)
        minutes, seconds = divmod(rem, 60)
        duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        summary_data = {
            "hostname": socket.gethostname(),
            "start_time": start_time_str,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_formatted": duration_formatted,
            "success": False,
            "error_msg": f"Excepción general de ejecución: {exc}",
        }
        try:
            record_run(summary_data, entity_metrics)
        except Exception:
            logger.warning("No se pudo registrar la corrida para el resumen diario", exc_info=True)
        sys.exit(1)
    finally:
        if exporter:
            exporter.close()
        try:
            if retry_store and targets:
                final_pending = retry_store.counts_by_entity(entities=targets)
                if final_pending:
                    logger.info("Cola de reintentos al finalizar: %s", json.dumps(final_pending, ensure_ascii=False))
        except Exception:
            pass
        finally:
            if retry_store:
                retry_store.close()
        logger.info("Proceso finalizado.")


def cmd_sync_changes(args) -> None:
    if args.entity and args.entity not in ["proveedores", "oc_items"]:
        logger.error("Entidad para sync-changes debe ser 'proveedores' o 'oc_items'.")
        sys.exit(1)

    with _exclusive_run_lock():
        _cmd_sync_changes_locked(args)


def _cmd_sync_changes_locked(args) -> None:
    from src.change_sync import ChangeSyncService

    entities = [args.entity] if args.entity else ["proveedores", "oc_items"]
    link_store = EntityLinkStore()
    exporter = build_exporter(args.export, dry_run=args.dry_run)

    failed = False
    try:
        source_engine = create_source_engine()
        with source_engine.connect() as conn:
            source_repo = SourceRepository(conn)
            if hasattr(exporter, "attach_source"):
                exporter.attach_source(source_repo)

            service = ChangeSyncService(source_repo, exporter, link_store)
            for entity in entities:
                if not service.sync_entity(entity, backfill_only=args.backfill_only, dry_run=args.dry_run):
                    failed = True
    except Exception as exc:
        logger.error("Error en sync-changes: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        exporter.close()
        link_store.close()

    if failed:
        sys.exit(1)


def _sync_entity_changes(
    source_repo: SourceRepository,
    exporter: BaseExporter,
    link_store: EntityLinkStore,
    entity: str,
    backfill_only: bool = False,
    dry_run: bool = False,
) -> bool:
    from src.change_sync import ChangeSyncService

    service = ChangeSyncService(source_repo, exporter, link_store)
    return service.sync_entity(entity, backfill_only=backfill_only, dry_run=dry_run)


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


# ─── backfill-gastos ──────────────────────────────────────────────────────────


def cmd_backfill_gastos(args) -> None:
    """Backfill unico: recupera links locales faltantes de gastos ya migrados.

    La ventana incremental solo re-escanea los ultimos 30 dias. Los gastos ya
    presentes en Paxapos pero SIN link local siguen reenviandose en cada corrida
    y el receptor los rechaza como duplicados, engordando la cola de reintentos.

    Este comando fuerza un escaneo COMPLETO de solic_gastos (ignora la ventana
    de 30 dias y NO toca el checkpoint incremental persistido) y reenvia solo los
    gastos aun sin link — la Solucion B del mapper omite los ya vinculados. Cada
    respuesta con exito + id persiste el link via upsert, con lo que el gasto deja
    de reenviarse en las proximas corridas.

    Los gastos que el receptor no logra reconocer por upsert (divergencia entre la
    busqueda del upsert y la validacion de duplicado) quedan sin link: esos
    dependen de la Solucion A (idempotencia garantizada en el receptor) y quedan
    encolados para reintento.
    """
    with _exclusive_run_lock():
        _cmd_backfill_gastos_locked(args)


def _cmd_backfill_gastos_locked(args) -> None:
    from src.models import Checkpoint

    entity = "solic_gastos"
    dry_run = bool(getattr(args, "dry_run", False))
    batch_size = getattr(args, "batch_size", 500) or 500
    limit = getattr(args, "limit", None)

    if dry_run:
        logger.warning(
            "Backfill en dry-run: el receptor NO persiste, por lo que NO se "
            "recuperan links. Sirve solo para ver cuantos gastos se reenviarian."
        )

    link_store = EntityLinkStore()
    links_before = link_store.count("gasto")
    link_store.close()

    exporter = None
    retry_store = None
    total_scanned = 0
    try:
        exporter = build_exporter(dry_run=dry_run)
        retry_store = RetryStore()
        if hasattr(exporter, "attach_retry_store"):
            exporter.attach_retry_store(retry_store)

        source_engine = create_source_engine()
        with source_engine.connect() as conn:
            logger.info(
                "Backfill gastos: conexion origen (%s), escaneo COMPLETO de %s",
                source_engine.url.get_backend_name(), entity,
            )
            source_repo = SourceRepository(conn)
            if hasattr(exporter, "attach_source"):
                exporter.attach_source(source_repo)

            # Checkpoint sintetico "fresco" (todo None) -> fuerza full scan sin
            # tocar el checkpoint incremental persistido en state/checkpoint.db.
            fresh_cp = Checkpoint(entity=entity)
            stmt = source_repo.build_statement(entity, fresh_cp)
            result = source_repo.execute(stmt)
            columns = list(result.keys())

            def process_batch(batch: list[tuple]) -> None:
                nonlocal total_scanned
                try:
                    exporter.write_batch(entity, columns, batch)
                except Exception as exc:  # noqa: BLE001 - seguir con el proximo batch
                    logger.error(
                        "Backfill: batch de %d filas FALLO: %s. Continuando.",
                        len(batch), exc, exc_info=True,
                    )
                    return
                total_scanned += len(batch)

            group_fields = GROUPED_BATCH_FIELDS.get(entity)
            if group_fields:
                for batch in iter_grouped_batches(result, columns, group_fields, batch_size):
                    if limit is not None and total_scanned >= limit:
                        break
                    process_batch(batch)
            else:
                while True:
                    remaining = None if limit is None else limit - total_scanned
                    if remaining is not None and remaining <= 0:
                        break
                    fetch_n = batch_size if remaining is None else min(batch_size, remaining)
                    raw_rows = result.fetchmany(fetch_n)
                    if not raw_rows:
                        break
                    process_batch([tuple(row) for row in raw_rows])

        link_store = EntityLinkStore()
        links_after = link_store.count("gasto")
        link_store.close()
        recovered = links_after - links_before

        logger.info(
            "Backfill gastos finalizado: filas escaneadas=%d, links antes=%d, "
            "links despues=%d, recuperados=%d.",
            total_scanned, links_before, links_after, recovered,
        )
        if not dry_run and total_scanned > 0 and recovered <= 0:
            logger.warning(
                "No se recuperaron links nuevos: los gastos que siguen sin "
                "vinculo dependen de la Solucion A (idempotencia en el receptor)."
            )
    except Exception as exc:
        logger.error("Backfill gastos: error general: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        if exporter:
            exporter.close()
        if retry_store:
            retry_store.close()
        logger.info("Backfill gastos: proceso finalizado.")


# ─── daily-report ─────────────────────────────────────────────────────────────


def cmd_daily_report(args) -> None:
    """Envia UN unico mail resumen del dia y purga el historial reportado."""
    from datetime import date

    from src.notifier import notify_run_report
    from src.run_history import aggregate_runs, load_runs, prune_reported

    target_date = getattr(args, "date", None) or date.today().isoformat()
    runs = load_runs(target_date)
    if not runs:
        logger.info("Resumen diario: sin corridas registradas para %s.", target_date)
        return

    summary_data, entity_metrics = aggregate_runs(runs, target_date)
    sent = notify_run_report(summary_data, entity_metrics, dry_run=False)
    if sent:
        remaining = prune_reported(target_date)
        logger.info(
            "Resumen diario enviado para %s (%d corridas). Historial restante: %d.",
            target_date, len(runs), remaining,
        )
    else:
        logger.info(
            "Resumen diario NO enviado para %s (notificaciones deshabilitadas o sin SMTP).",
            target_date,
        )


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
        "--dry-run",
        action="store_true",
        help="Preview: no avanza checkpoints; envia el payload con dry_run=true (el receptor no persiste)",
    )

    backfill_p = sub.add_parser(
        "backfill-gastos",
        help="Backfill unico: recupera links faltantes de gastos ya migrados (escaneo completo, no toca el checkpoint)",
    )
    backfill_p.add_argument("--limit", type=int, metavar="N", help="Máximo de filas a escanear (útil para testear)")
    backfill_p.add_argument("--batch-size", type=int, default=500, metavar="N", help="Filas por lote (default: 500)")
    backfill_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview: envia con dry_run=true; el receptor NO persiste, no recupera links",
    )

    sync_p = sub.add_parser("sync-changes", help="Detecta y re-envía registros modificados en RAFAM")
    sync_p.add_argument("--entity", choices=["proveedores", "oc_items"], help="Filtrar por entidad")
    sync_p.add_argument(
        "--export",
        choices=["csv", "noop", "gateway", "migrator"],
        default="migrator",
        help="Destino de salida (default: migrator)",
    )
    sync_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview sin re-enviar ni actualizar hashes locales",
    )
    sync_p.add_argument(
        "--backfill-only",
        action="store_true",
        help="Calcula y guarda los hashes de registros ya vinculados sin enviarlos a Paxapos",
    )

    daily_p = sub.add_parser(
        "daily-report",
        help="Envia UN mail resumen del dia (total y errores) y purga el historial reportado",
    )
    daily_p.add_argument("--date", metavar="YYYY-MM-DD", help="Fecha a reportar (default: hoy)")

    args = parser.parse_args()
    setup_file_logging(args)
    {
        "status": cmd_status,
        "reset": cmd_reset,
        "run": cmd_run,
        "spec": cmd_spec,
        "lookups": cmd_lookups,
        "reconcile": cmd_reconcile,
        "backfill-gastos": cmd_backfill_gastos,
        "sync-changes": cmd_sync_changes,
        "daily-report": cmd_daily_report,
    }[args.command](args)


if __name__ == "__main__":
    main()
