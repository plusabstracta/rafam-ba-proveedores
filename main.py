#!/usr/bin/env python3
"""
main.py — CLI entry point for the RAFAM → Paxapos incremental sync.

Usage:
    python main.py status
    python main.py reset --entity=proveedores
    python main.py reset --all
    python main.py run [--entity=proveedores]
    python main.py resend --entity=orden_pago --key "OP 2026-1023"
"""

import argparse
import fcntl
import json
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from src.batch_grouping import GROUPED_BATCH_FIELDS, ENTITY_LINK_NAMES, iter_grouped_batches
from src.batch_isolation import BatchIsolator, group_rows_by_key
from src.checkpoint_store import CheckpointStore
from src.config import ENTITY_CONFIGS, is_cod_prov_excluded
from src.db import create_source_engine
from src.entity_link_store import EntityLinkStore
from src.error_formatting import describe_exception, format_exception_context
from src.exporter import BaseExporter, build_exporter, fetch_migrator_lookups, fetch_migrator_spec
from src.incident_alerts import RUN_ENTITY, update_incidents
from src.gateway_mapper import map_proveedor_migrator_row
from src.logging_config import setup_file_logging
from src.models import Checkpoint
from src.record_alerts import flush_record_alerts
from src.record_events import RecordEventSink
from src.record_ledger import LEDGER_ENTITIES, RunLedger, close_entity
from src.operator_report import build_operator_report
from src.retry_labels import (
    RESENDABLE_ENTITIES,
    describe_retry_key,
    parse_record_key,
    record_base_key,
)
from src.retry_store import STATUS_PENDING, STATUS_PERMANENT, RetryStore
from src.run_history import record_run
from src.source_repository import SourceRepository
from src.sync_engine import SyncEngine
from src.utils import utc_sql_to_local

load_dotenv()

logger = logging.getLogger(__name__)

OFFICIAL_ENTITIES = (
    "clasificaciones",
    "proveedores",
    "oc_items",
    "solic_gastos",
    "orden_pago",
    "retenciones",
)


def _infra_abort_after() -> int:
    """Batches consecutivos con fallo de infraestructura del backend antes de cortar la entidad.

    Con `account_gasto_itemes doesn't exist` (sep-2026) cada corrida siguio
    mandando los 4-8 batches de la entidad a un backend que no podia procesar
    ninguno. El watermark ya queda congelado en el primer fallo, asi que cortar
    no pierde filas: la proxima corrida las vuelve a leer.
    """
    raw = os.getenv("RAFAM_INFRA_ABORT_AFTER", "2")
    try:
        return max(1, int(raw))
    except ValueError:
        return 2


def _mail_retry_detail_limit() -> int:
    """Tope de registros por entidad en la lista PARA REVISAR EN RAFAM del mail.

    El cuerpo del mail se corta a los N mas viejos (los mas urgentes) de cada
    entidad, con un puntero a `retry-queue --entity X` para el resto (0 = sin tope).
    """
    raw = os.getenv("RAFAM_MAIL_RETRY_DETAIL_LIMIT", "50")
    try:
        return max(0, int(raw))
    except ValueError:
        return 50


def _effective_batch_size(entity: str, requested_batch_size: int) -> int:
    if entity != "oc_items":
        return requested_batch_size

    raw_limit = os.getenv("RAFAM_OC_MAX_BATCH_ROWS", "100")
    try:
        oc_limit = int(raw_limit)
    except ValueError:
        logger.warning(
            "RAFAM_OC_MAX_BATCH_ROWS=%r no es valido; se usara 100",
            raw_limit,
        )
        oc_limit = 100

    if oc_limit <= 0:
        logger.warning(
            "RAFAM_OC_MAX_BATCH_ROWS debe ser mayor a 0; se usara 100"
        )
        oc_limit = 100

    return min(requested_batch_size, oc_limit)



def _build_engine() -> SyncEngine:
    return SyncEngine(CheckpointStore())


_LOCK_PATH = Path(__file__).resolve().parent / "state" / "migrator.lock"


_LOCK_POLL_SECONDS = 2.0


@contextmanager
def _exclusive_run_lock(wait_seconds: float = 0):
    """Lock exclusivo via fcntl.flock para que dos cron concurrentes no se pisen.

    Si otro proceso esta corriendo `main.py run`, este sale con codigo 75
    (EX_TEMPFAIL) en vez de avanzar checkpoints en paralelo. El lock se libera
    automaticamente al cerrar el FD (fin de proceso o context exit).

    Con ``wait_seconds > 0`` (comandos manuales como `resend`) espera hasta
    ese tiempo a que termine la corrida en curso antes de rendirse.
    """
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    # "a" y NO "w": abrir con "w" trunca el archivo ANTES de intentar el flock,
    # asi que un contendiente que pierde el lock borraba el PID del dueno.
    fd = open(_LOCK_PATH, "a")
    try:
        deadline = time.monotonic() + max(0.0, wait_seconds)
        warned = False
        while True:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    logger.error(
                        "Otro proceso ya esta ejecutando el sync (lock: %s). Saliendo sin avanzar checkpoints.",
                        _LOCK_PATH,
                    )
                    sys.exit(75)
                if not warned:
                    logger.info(
                        "Hay una corrida del sync en curso; esperando hasta %.0f s a que termine...",
                        wait_seconds,
                    )
                    warned = True
                time.sleep(_LOCK_POLL_SECONDS)
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
    retry_store=None,
    *,
    sink: RecordEventSink | None = None,
    link_store=None,
) -> tuple[bool, str | None, dict]:
    """Execute the incremental sync for a single entity.

    Returns (True, None, metrics) si la entidad se sincronizo OK, (False, error_msg, metrics) si hubo error.
    El caller usa este flag para devolver exit code != 0 al SO/cron y notificar.

    Con ``sink`` (motivos de omision de los mappers) y ``link_store`` se cierra
    las cuentas de la entidad al final (src/record_ledger.py): ningun registro
    leido queda sin ID de Paxapos y sin motivo.
    """
    t_start = time.monotonic()
    cp  = engine.get_checkpoint(entity)
    cfg = ENTITY_CONFIGS[entity]
    effective_batch_size = _effective_batch_size(entity, batch_size)
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
    retry_lookup_failed_detail: str | None = None
    infra_streak = 0
    infra_abort_after = _infra_abort_after()
    abort_entity = False
    # Batches que quedaron caidos por el backend/red (vs. por un registro que
    # no se pudo aislar): decide el tipo de incidente que se avisa por mail.
    infra_failed_batches = 0
    unresolved_keys: list[str] = []
    query_duration = 0.0
    total = 0
    migrator_sent = 0
    migrator_saved = 0
    migrator_errors = 0
    migrator_deferred = 0
    migrator_outcomes = {
        "created": 0,
        "updated": 0,
        "replaced": 0,
        "deleted": 0,
        "skipped": 0,
        "unclassified": 0,
        "unchanged": 0,
        "excluded": 0,
        "invalid": 0,
    }

    metrics = {
        "entity": entity,
        "mode": mode,
        "records_ok": 0,
        "migrator_sent": 0,
        "migrator_saved": 0,
        "migrator_errors": 0,
        # Filas que Paxapos difirio por dependencia pendiente (egreso_not_found,
        # etc.); quedan en la cola y no cuentan como rechazo.
        "migrator_deferred": 0,
        "migrator_created": 0,
        "migrator_updated": 0,
        "migrator_replaced": 0,
        "migrator_deleted": 0,
        "migrator_skipped": 0,
        "migrator_unclassified": 0,
        "source_unchanged": 0,
        "source_excluded": 0,
        "source_invalid": 0,
        "batches_ok": 0,
        "batches_failed": 0,
        # Batches que fallaron enteros y se recuperaron aislando el/los
        # registros que los rompian (src/batch_isolation.py).
        "batches_recovered": 0,
        "records_isolated": 0,
        "bisect_requests": 0,
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
        # "backend_infra" cuando el fallo es del server Paxapos (SQL/PHP), no de los datos.
        "error_kind": None,
        # Incidente de la entidad para src/incident_alerts.py (None = sin incidente):
        # "backend" (Paxapos/red caidos), "batch" (batch caido sin aislar) o
        # "error" (la entidad no pudo correr).
        "incident_kind": None,
        "incident_detail": None,
        "incident_keys": [],
        # 'permanent' que se reintentaron solos en esta corrida.
        "permanent_retried": 0,
        # Cierre de cuentas (src/record_ledger.py); None = no se evaluo.
        "ledger": None,
    }

    ledger = (
        RunLedger(entity)
        if (
            retry_store is not None and sink is not None and link_store is not None
            and not dry_run and entity in LEDGER_ENTITIES
        )
        else None
    )
    retry_as_of: str | None = None

    try:
        t_query_start = time.monotonic()
        # Reinyectar lo pendiente en la cola de reintentos: sin esto una fila
        # salteada por dependencia faltante queda fuera del cursor para siempre
        # (el watermark avanza igual que si se hubiera migrado). Incluye los
        # 'permanent' cuyo reintento automatico ya vencio.
        retry_keys = None
        if retry_store is not None:
            try:
                retry_as_of = retry_store.now()
                due_permanent = retry_store.due_permanent_external_ids(entity)
                if due_permanent:
                    metrics["permanent_retried"] = len(due_permanent)
                    logger.info(
                        "[%s] Reintento automatico de %d registro(s) 'permanent' (vencio su espera de %g h).",
                        entity, len(due_permanent), retry_store.permanent_retry_hours,
                    )
                retry_keys = retry_store.pending_external_ids(entity)
            except Exception as retry_exc:  # pragma: no cover - defensive
                retry_lookup_failed_detail = str(retry_exc)
                logger.warning(
                    "[%s] No se pudo leer la cola de reintentos: %s — esta corrida "
                    "NO reinyecta pendientes de %s (se reintenta en la proxima).",
                    entity, retry_exc, entity,
                )
        result = source_repo.fetch_entity(entity, cp, retry_keys)
        query_duration = time.monotonic() - t_query_start
        metrics["query_duration_secs"] = query_duration

        columns = list(result.keys())
        _warn_missing_cursor_fields(cfg, columns, entity)

        batch_count = 0
        last_id = None
        last_ts = None

        def record_migrator_metrics() -> None:
            nonlocal migrator_sent, migrator_saved, migrator_errors, migrator_deferred
            metrics_fn = getattr(exporter, "get_last_batch_migrator_metrics", None)
            if not callable(metrics_fn):
                return
            batch_metrics = metrics_fn() or {}
            try:
                migrator_sent += int(batch_metrics.get("sent", 0) or 0)
            except (TypeError, ValueError):
                pass
            try:
                migrator_saved += int(batch_metrics.get("saved", 0) or 0)
            except (TypeError, ValueError):
                pass
            try:
                migrator_errors += int(batch_metrics.get("errors", 0) or 0)
            except (TypeError, ValueError):
                pass
            try:
                migrator_deferred += int(batch_metrics.get("deferred", 0) or 0)
            except (TypeError, ValueError):
                pass
            for key in migrator_outcomes:
                try:
                    migrator_outcomes[key] += int(batch_metrics.get(key, 0) or 0)
                except (TypeError, ValueError):
                    pass

        def after_write(_exc) -> None:
            record_migrator_metrics()
            if ledger is None:
                return
            outcomes_fn = getattr(exporter, "get_last_batch_outcomes", None)
            if callable(outcomes_fn):
                ledger.add_outcomes(outcomes_fn())
            sent_fn = getattr(exporter, "get_last_batch_sent_keys", None)
            if callable(sent_fn):
                ledger.add_sent(sent_fn())

        isolator = BatchIsolator(
            exporter,
            entity,
            retry_store=retry_store,
            dry_run=dry_run,
            delay=batch_delay,
            after_write=after_write,
        )

        def process_batch(batch: list[tuple]) -> None:
            nonlocal last_id, last_ts, total, batch_count, failed_batches, last_batch_error, last_batch_error_detail, batches_ok
            nonlocal infra_streak, abort_entity, infra_failed_batches
            batch_keys = ledger.see_rows(columns, batch) if ledger is not None else []
            bid, bts = engine.extract_cursor_values(columns, batch, entity)
            if bid is not None:
                last_id = max(last_id, bid) if last_id is not None else bid
            if bts is not None:
                last_ts = max(last_ts, bts) if last_ts is not None else bts

            # El sleep entre requests (RAFAM_SYNC_BATCH_DELAY_SECONDS) lo hace
            # el isolator, y solo si el request anterior llego a hacer un POST.
            t_batch_start = time.monotonic()
            outcome = isolator.write(columns, batch)
            batch_times.append(time.monotonic() - t_batch_start)
            if outcome.recovered:
                logger.warning(
                    "[%-11s] %s — batch #%d (%d filas): %d registro(s) fallan solos y quedaron en la cola "
                    "como batch_failed; el resto se envio (%d request(s) extra). Error: %s",
                    mode, entity, batch_count + 1, len(batch), len(outcome.isolated),
                    outcome.requests, outcome.first_error,
                )
            if outcome.ok:
                batches_ok += 1
                infra_streak = 0
            else:
                exc = outcome.error
                failed_batches += 1
                last_batch_error = str(exc)
                if ledger is not None:
                    # Se releen en la proxima corrida (watermark congelado).
                    ledger.mark_failed(batch_keys)
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
                if outcome.infra:
                    metrics["error_kind"] = "backend_infra"
                    infra_failed_batches += 1
                    infra_streak += 1
                    if infra_streak >= infra_abort_after:
                        abort_entity = True
                else:
                    infra_streak = 0
                    unresolved_keys.extend(k for k in outcome.unresolved if k is not None)
                logger.error(
                    "[%-11s] %s — batch #%d (%d filas) FALLO: %s. %s",
                    mode, entity, batch_count + 1, len(batch), exc,
                    "Backend caido: se corta la entidad por esta corrida." if abort_entity
                    else "Continuando con el siguiente batch.",
                    exc_info=None if outcome.infra else exc,
                )
                batch_count += 1
                return

            total += len(batch)
            batch_count += 1

            # Watermark incremental: persistir progreso por batch para que un
            # crash a mitad de corrida no rebobine al inicio. Solo cuando la
            # entidad tiene cursor real (no full_load) y no estamos en dry-run.
            # Si YA fallo un batch en esta corrida, el watermark se congela:
            # avanzarlo con batches posteriores dejaria el cursor por encima de
            # las filas del batch fallido y no volverian a entrar nunca (el
            # reintento del receptor solo cubre filas que llegaron a responder).
            if (
                not dry_run
                and not cfg.full_load
                and failed_batches == 0
                and (bid is not None or bts is not None)
            ):
                try:
                    engine.advance_partial(entity, bid, bts, len(batch))
                except Exception as cp_exc:  # pragma: no cover - defensive
                    logger.warning(
                        "[%s] No se pudo persistir watermark parcial: %s",
                        entity, cp_exc,
                    )

        group_fields = GROUPED_BATCH_FIELDS.get(entity)
        if group_fields:
            for batch in iter_grouped_batches(
                result, columns, group_fields, effective_batch_size
            ):
                if abort_entity or (limit is not None and total >= limit):
                    break
                process_batch(batch)
                if limit is not None and total >= limit:
                    break
        else:
            while not abort_entity:
                fetch_n = batch_size if limit is None else min(batch_size, limit - total)
                if fetch_n <= 0:
                    break

                raw_rows = result.fetchmany(fetch_n)
                if not raw_rows:
                    break

                process_batch([tuple(row) for row in raw_rows])

        metrics["records_ok"] = total
        metrics["migrator_sent"] = migrator_sent
        metrics["migrator_saved"] = migrator_saved
        metrics["migrator_errors"] = migrator_errors
        metrics["migrator_deferred"] = migrator_deferred
        metrics["migrator_created"] = migrator_outcomes["created"]
        metrics["migrator_updated"] = migrator_outcomes["updated"]
        metrics["migrator_replaced"] = migrator_outcomes["replaced"]
        metrics["migrator_deleted"] = migrator_outcomes["deleted"]
        metrics["migrator_skipped"] = migrator_outcomes["skipped"]
        metrics["migrator_unclassified"] = migrator_outcomes["unclassified"]
        metrics["source_unchanged"] = migrator_outcomes["unchanged"]
        metrics["source_excluded"] = migrator_outcomes["excluded"]
        metrics["source_invalid"] = migrator_outcomes["invalid"]
        metrics["batches_ok"] = batches_ok
        metrics["batches_failed"] = failed_batches
        metrics["batch_times"] = batch_times
        metrics["batches_recovered"] = isolator.batches_recovered
        metrics["records_isolated"] = isolator.records_isolated
        metrics["bisect_requests"] = isolator.extra_requests
        records_isolated = isolator.records_isolated

        if failed_batches > 0 and not dry_run:
            metrics["incident_kind"] = "backend" if infra_failed_batches else "batch"
            metrics["incident_detail"] = last_batch_error
            metrics["incident_keys"] = [
                describe_retry_key(entity, key) for key in dict.fromkeys(unresolved_keys)
            ][:10]

        if not dry_run and retry_store is not None:
            _close_entity_books(
                entity, ledger, metrics, sink=sink, retry_store=retry_store, link_store=link_store,
                # Solo si se leyo todo: un 'permanent' vencido que no se llego a
                # leer (batch caido, corte por backend, --limit) sigue vencido.
                retry_as_of=retry_as_of if (failed_batches == 0 and not abort_entity and limit is None) else None,
            )

        if dry_run:
            logger.info("[DRY RUN   ] %s — %d registros (sin avanzar checkpoint)", entity, total)
        else:
            if (
                failed_batches > 0
                or migrator_errors > 0
                or migrator_outcomes["invalid"] > 0
                or records_isolated > 0
                or retry_lookup_failed_detail is not None
            ):
                # Hubo batches que fallaron pero la corrida siguió. Marcamos la
                # entidad como con errores para que el caller devuelva exit!=0
                # y el cron/operador se entere, pero no perdimos las filas OK.
                if failed_batches > 0:
                    if metrics.get("error_kind") == "backend_infra":
                        msg = (
                            f"BACKEND PAXAPOS CON FALLA DE INFRAESTRUCTURA (no son datos): {failed_batches} "
                            f"batch(es) fallaron{' y se corto la entidad por esta corrida' if abort_entity else ''}; "
                            f"ultimo error: {last_batch_error}"
                        )
                    else:
                        msg = f"{failed_batches} batch(es) fallaron; ultimo error: {last_batch_error}"
                elif migrator_outcomes["invalid"] > 0:
                    msg = (
                        f"{migrator_outcomes['invalid']} fila(s) de origen no pudieron mapearse; "
                        "revisar errores del mapper"
                    )
                elif records_isolated > 0:
                    msg = (
                        f"{records_isolated} registro(s) hacian fallar su batch entero; se aislaron en "
                        "la cola de reintentos (batch_failed) y el resto del batch se envio"
                    )
                elif migrator_errors > 0:
                    msg = f"Paxapos rechazo {migrator_errors} item(s); quedaron registrados en la cola de reintentos"
                else:
                    msg = (
                        f"No se pudo leer la cola de reintentos: {retry_lookup_failed_detail}. "
                        "Esta corrida NO reinyecto los pendientes de esta entidad "
                        "(se reintenta automaticamente en la proxima corrida)."
                    )
                engine.mark_error(entity, msg)
                if failed_batches > 0:
                    logger.error(
                        "[%-11s] %s — %d filas leidas, %d batch(es) con error. Ultimo: %s",
                        mode, entity, total, failed_batches, last_batch_error,
                    )
                elif migrator_errors > 0 or migrator_outcomes["invalid"] > 0 or records_isolated > 0:
                    logger.error(
                        "[%-11s] %s — %d filas leidas, %d rechazo(s) de Paxapos, "
                        "%d fila(s) invalidas, %d registro(s) aislados de batches caidos; "
                        "revisar log y cola de reintentos.",
                        mode, entity, total, migrator_errors, migrator_outcomes["invalid"], records_isolated,
                    )
                else:
                    logger.error("[%-11s] %s — %s", mode, entity, msg)
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
            metrics["incident_kind"] = "error"
            metrics["incident_detail"] = str(exc)
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


def _close_entity_books(
    entity: str,
    ledger: RunLedger | None,
    metrics: dict,
    *,
    sink: RecordEventSink | None,
    retry_store,
    link_store,
    retry_as_of: str | None,
) -> None:
    """Cierre de cuentas + reintento de 'permanent'; nunca corta la corrida.

    ``retry_as_of`` es None cuando la entidad no termino de leer todo (batch
    caido, corte por backend o ``--limit``): los 'permanent' vencidos que no se
    llegaron a mandar siguen vencidos y se reintentan en la proxima corrida.
    """
    if ledger is not None:
        try:
            metrics["ledger"] = close_entity(
                ledger, sink=sink, retry_store=retry_store, link_store=link_store,
            )
        except Exception:  # noqa: BLE001 - el cierre no puede romper la corrida
            logger.warning("[%s] No se pudo cerrar las cuentas de la entidad", entity, exc_info=True)
    if retry_as_of is not None:
        try:
            deferred = retry_store.defer_due_permanents(entity, retry_as_of)
            if deferred:
                logger.info(
                    "[%s] %d 'permanent' vencido(s) no se enviaron (el script ya no los manda); "
                    "se vuelven a intentar en %g h.",
                    entity, deferred, retry_store.permanent_retry_hours,
                )
        except Exception:  # noqa: BLE001
            logger.warning("[%s] No se pudo reprogramar el reintento de los 'permanent'", entity, exc_info=True)


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
    retry_counts_end = {}
    retry_summary_start = []
    retry_summary_end = []
    record_alerts_sent = 0
    incident_alerts_sent = 0
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
        # Sin --entity explicito, ejecutar las entidades oficiales en orden de FKs.
        # Las demas no se migran:
        #   - orden_compra (header) → reemplazado por oc_items (incluye items embebidos)
        #   - pedidos / ped_items   → deshabilitados, los pedidos llegan como OCs via oc_items
        # retenciones corre al final: depende de que la OP (Egreso) ya exista para
        # resolver el destino; si no, se encola y se reintenta en la proxima corrida.
        if args.entity:
            targets = [args.entity]
        else:
            targets = [entity for entity in OFFICIAL_ENTITIES if entity in ENTITY_CONFIGS]
            logger.info("Ejecutando entidades oficiales en orden FK → %s", targets)

        # Cola de reintentos (F1): captura filas rechazadas por el receptor para
        # reintentarlas en la proxima corrida. Manejo fila-a-fila — el batch no se
        # cancela por una fila mala; el watermark avanza con seguridad porque lo
        # pendiente queda registrado aca.
        retry_store = RetryStore()
        # Motivos por los que los mappers omiten registros: el cierre de
        # cuentas de cada entidad los usa para que nada quede sin ID y sin motivo.
        skip_sink = RecordEventSink()
        if hasattr(exporter, "attach_event_sink"):
            exporter.attach_event_sink(skip_sink)
        link_store = getattr(exporter, "_link_store", None)
        if hasattr(exporter, "attach_retry_store"):
            exporter.attach_retry_store(retry_store)
            pending = retry_store.counts_by_entity(entities=targets)
            if pending:
                logger.info("Cola de reintentos al inicio: %s", json.dumps(pending, ensure_ascii=False))
                retry_counts_start = dict(pending)
            retry_summary_start = retry_store.summary_by_reason(targets)

        source_engine = create_source_engine()
        with source_engine.connect() as conn:
            logger.info("Conexión a base origen establecida (%s)", source_engine.url.get_backend_name())
            source_repo = SourceRepository(conn)
            # Inyectar source_repo al exporter para fetch secundarios
            # (ej: retenciones por OP, evita cartesian en query principal).
            if hasattr(exporter, "attach_source"):
                exporter.attach_source(source_repo)
            for entity in targets:
                ok, err_msg, metrics = _sync_entity(
                    source_repo, engine, exporter, entity, args.batch_size, args.limit, args.dry_run, retry_store,
                    sink=skip_sink, link_store=link_store,
                )
                entity_metrics.append(metrics)
                if not ok:
                    failed_entities.append(entity)
                    entity_errors[entity] = err_msg or "Error desconocido"

        # Snapshot final de la cola de reintentos (para el resumen diario).
        try:
            if retry_store:
                retry_counts_end = dict(retry_store.counts_by_entity(entities=targets))
                retry_summary_end = retry_store.summary_by_reason(targets)
        except Exception:  # pragma: no cover - defensive
            pass

        # Un mail por cada registro que en esta corrida quedo rechazado u
        # omitido por datos invalidos (el resumen diario sigue igual).
        if retry_store and not args.dry_run:
            record_alerts_sent = _flush_record_alerts(retry_store, link_store)
        # Un mail por incidente si una entidad entera no se pudo sincronizar
        # (Paxapos caido, batch que no se pudo aislar) y otro al normalizarse.
        if not args.dry_run:
            incident_alerts_sent = _update_incidents(entity_metrics)

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
                "retry_counts_start": retry_counts_start,
                "retry_counts_end": retry_counts_end,
                "retry_summary_start": retry_summary_start,
                "retry_summary_end": retry_summary_end,
                "record_alerts_sent": record_alerts_sent,
                "incident_alerts_sent": incident_alerts_sent,
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
                "retry_counts_start": retry_counts_start,
                "retry_counts_end": retry_counts_end,
                "retry_summary_start": retry_summary_start,
                "retry_summary_end": retry_summary_end,
                "record_alerts_sent": record_alerts_sent,
                "incident_alerts_sent": incident_alerts_sent,
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
        if not args.dry_run:
            summary_data["incident_alerts_sent"] = _update_incidents(
                entity_metrics, run_error=f"{type(exc).__name__}: {exc}",
            )
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
    exporter = build_exporter(dry_run=args.dry_run)

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


# ─── retry-queue ─────────────────────────────────────────────────────────────


def cmd_retry_queue(args) -> None:
    """Inspecciona la cola de reintentos, reencola 'permanent' y/o fuerza el reenvio YA.

    Una fila que agota max_attempts pasa a 'permanent' y deja de reinyectarse
    (``pending_external_ids`` solo mira 'pending'). Cuando el rechazo se
    arregla del lado del receptor (core#406), hay que devolverla a 'pending'
    a mano: sin eso, el fix del backend no desbloquea lo ya trabado.

    ``--send-now`` fuerza el reenvio EN ESTE MISMO PROCESO en vez de esperar
    al proximo cron: sin el, `--requeue` solo deja la fila en 'pending' y hay
    que esperar (o correr `main.py run --entity X` a mano) para que se
    reintente de verdad.
    """
    send_now = bool(getattr(args, "send_now", False))
    if send_now and not args.entity:
        logger.error(
            "--send-now requiere --entity (para forzar TODA la cola de todas las "
            "entidades usa `main.py run`, que ya reinyecta todo lo 'pending')"
        )
        raise SystemExit(2)

    if send_now:
        with _exclusive_run_lock():
            _cmd_retry_queue_locked(args)
    else:
        _cmd_retry_queue_locked(args)


def _cmd_retry_queue_locked(args) -> None:
    send_now = bool(getattr(args, "send_now", False))
    retry_store = RetryStore()
    try:
        if args.dismiss and args.requeue:
            logger.error("--dismiss y --requeue son operaciones excluyentes")
            raise SystemExit(2)
        if args.dismiss and send_now:
            logger.error("--dismiss y --send-now son operaciones excluyentes")
            raise SystemExit(2)
        if args.dismiss:
            if not args.entity or not args.external_id or not args.note:
                logger.error("--dismiss requiere --entity, --external-id y --note")
                raise SystemExit(2)
            dismissed = retry_store.dismiss(args.entity, args.external_id, args.note)
            if not dismissed:
                logger.error(
                    "No existe retry para entity=%s external_id=%s",
                    args.entity,
                    args.external_id,
                )
                raise SystemExit(1)
            return

        if args.requeue:
            reencoladas = retry_store.requeue(entity=args.entity, external_id=args.external_id)
            logger.info("Filas reencoladas (permanent -> pending): %d", reencoladas)
            if not reencoladas:
                logger.info("No habia filas 'permanent' con ese filtro.")
            if not send_now:
                return

        if send_now:
            _force_send_pending(retry_store, args.entity)
            return

        items = retry_store.list_items(
            entity=args.entity,
            status=args.status,
            external_id=args.external_id,
        )
        if not items:
            print("\nCola de reintentos vacia (con los filtros dados).\n")
            return

        col = "{:<14} {:<40} {:<28} {:<22} {:<24} {:<8} {}"
        print()
        print(col.format(
            "Entidad", "External ID", "Registro (OC/OP/etc)", "Motivo", "Detalle", "Intentos", "Estado",
        ))
        print("─" * 165)
        for it in items:
            print(col.format(
                it.entity,
                it.external_id[:40],
                describe_retry_key(it.entity, it.external_id)[:28],
                it.reason_code,
                it.reason_detail or "legacy_unspecified",
                it.attempts,
                it.status,
            ))
        print()
        for it in items:
            print(
                f"  {describe_retry_key(it.entity, it.external_id)} "
                f"(entity={it.entity} external_id={it.external_id}): "
                f"first_seen={utc_sql_to_local(it.first_seen)}, "
                f"last_attempt={utc_sql_to_local(it.last_attempt)} (hora local)"
            )
            if it.status == STATUS_PERMANENT:
                if not it.auto_retry:
                    print("    reintento automatico: NO (rechazo terminal; solo a mano con --requeue o resend)")
                elif it.next_retry_after:
                    print(f"    proximo reintento automatico: {utc_sql_to_local(it.next_retry_after)} (hora local)")
            if it.error_message:
                print(f"    ultimo error: {it.error_message}")
        print()
    finally:
        retry_store.close()


def _flush_record_alerts(retry_store: RetryStore, link_store=None) -> int:
    """Mails individuales pendientes; un fallo del mail nunca corta el comando."""
    try:
        return flush_record_alerts(retry_store, link_store=link_store)
    except Exception:  # noqa: BLE001 - las alertas no pueden romper la corrida
        logger.warning("No se pudieron enviar las alertas por registro", exc_info=True)
        return 0


def _update_incidents(entity_metrics: list[dict], run_error: str | None = None) -> int:
    """Abre/cierra incidentes por entidad; un fallo del mail nunca corta la corrida."""
    observations = [
        {
            "entity": m.get("entity"),
            "kind": m.get("incident_kind"),
            "detail": m.get("incident_detail"),
            "keys": m.get("incident_keys") or [],
        }
        for m in entity_metrics
        if m.get("entity")
    ]
    observations.append({
        "entity": RUN_ENTITY,
        "kind": "error" if run_error else None,
        "detail": run_error,
    })
    try:
        return update_incidents(observations)
    except Exception:  # noqa: BLE001 - las alertas no pueden romper la corrida
        logger.warning("No se pudieron actualizar los incidentes", exc_info=True)
        return 0


def _force_send_pending(retry_store: RetryStore, entity: str, batch_size: int | None = None) -> None:
    """Reenvia YA lo 'pending' de `entity` en la cola, sin esperar al proximo cron.

    Manda SOLO las claves de la cola (via `_resend_records`, el mismo camino
    que `main.py resend --from-queue`): no corre la entidad entera ni toca el
    checkpoint -- eso lo sigue haciendo el cron. Si habia filas 'permanent',
    usar `--requeue --send-now` juntos para que primero vuelvan a 'pending'.
    """
    keys = _queue_keys(retry_store, entity, STATUS_PENDING)
    if not keys:
        logger.info("retry-queue --send-now [%s]: no hay registros 'pending' en la cola.", entity)
        return
    report = _resend_records(retry_store, entity, keys=keys, batch_size=batch_size)
    _print_resend_report(report)
    _flush_record_alerts(retry_store)
    # Un registro que sigue esperando una dependencia (OMITIDO) es normal en la
    # cola; solo un rechazo o un envio caido hacen fallar el comando.
    if report.exit_code(strict=False):
        raise SystemExit(1)


# ─── resend ───────────────────────────────────────────────────────────────────

# Resultados posibles por registro en `main.py resend`.
RESEND_OK = "OK"
RESEND_REJECTED = "RECHAZADO"
RESEND_NOT_APPLIED = "NO APLICADO"
RESEND_SKIPPED = "OMITIDO"
RESEND_UNCHANGED = "SIN CAMBIOS"
RESEND_NOT_FOUND = "NO EXISTE EN RAFAM"
RESEND_FAILED = "FALLO EL ENVIO"
RESEND_NOT_SENT = "NO ENVIADO"

# Espera maxima del lock para comandos manuales (una corrida de cron puede
# tardar varios minutos).
_RESEND_LOCK_WAIT_SECONDS = 600
# Requests extra por batch para aislar (biseccion) el registro que hace
# fallar un batch entero.
_RESEND_ISOLATION_MAX_REQUESTS = 50
_RESEND_KEYS_BATCH_SIZE = 50
_RESEND_WINDOW_BATCH_SIZE = 500


@dataclass
class ResendResult:
    key: str
    status: str
    detail: str = ""


@dataclass
class ResendReport:
    entity: str
    dry_run: bool
    by_keys: bool
    results: list[ResendResult] = field(default_factory=list)
    # Filas de OTRAS entidades que vinieron en la misma respuesta (gastos
    # embebidos en el payload de orden_pago).
    related: list[tuple[str, str, str]] = field(default_factory=list)
    requeued: int = 0
    aborted_reason: str | None = None

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for res in self.results:
            out[res.status] = out.get(res.status, 0) + 1
        return out

    def exit_code(self, strict: bool | None = None) -> int:
        """1 si algun registro no quedo OK.

        ``strict`` (default: modo por claves): un OMITIDO tambien cuenta como
        fallo -- el operador pidio ese registro puntual y no se envio. En modo
        ventana o desde la cola, OMITIDO/SIN CAMBIOS son esperables.
        """
        if strict is None:
            strict = self.by_keys
        failing = {RESEND_REJECTED, RESEND_NOT_APPLIED, RESEND_FAILED, RESEND_NOT_SENT}
        if strict:
            failing |= {RESEND_SKIPPED, RESEND_NOT_FOUND}
        return 1 if any(r.status in failing for r in self.results) else 0


def _queue_keys(retry_store: RetryStore, entity: str, status: str | None) -> list[str]:
    """Claves base de la cola de `entity` (dedup, en orden de la cola)."""
    keys: list[str] = []
    for item in retry_store.list_items(entity=entity, status=status):
        base = record_base_key(entity, item.external_id)
        if base is not None and base not in keys:
            keys.append(base)
    return keys


def _queue_reason(retry_store: RetryStore, entity: str, base_key: str) -> str | None:
    for item in retry_store.list_items(entity=entity):
        if record_base_key(entity, item.external_id) == base_key:
            motivo = item.reason_detail or item.reason_code
            return f"en cola ({item.status}, {motivo}): {item.error_message or 'sin detalle'}"
    return None


class _ResendRun:
    """Estado acumulado de un reenvio (claves vistas, resultados, fallos)."""

    def __init__(self, entity: str):
        self.entity = entity
        self.seen: list[str] = []
        self._seen_set: set[str] = set()
        self.outcomes: dict[str, list] = {}
        self.related: list = []
        self.failed: dict[str, str] = {}
        self.not_sent: dict[str, str] = {}
        # Solo proveedores: su mapper es funcional (sin sink), asi que el motivo
        # de omision se deduce de la fila cruda.
        self.raw_by_key: dict[str, dict] = {}
        self.aborted_reason: str | None = None

    def see(self, key: str | None) -> None:
        if key is not None and key not in self._seen_set:
            self._seen_set.add(key)
            self.seen.append(key)

    def add_outcomes(self, outcomes) -> None:
        for outcome in outcomes:
            if outcome.entity != self.entity:
                self.related.append(outcome)
                continue
            base = outcome.base_key
            if base is not None:
                self.outcomes.setdefault(base, []).append(outcome)


def _resend_batch(isolator: BatchIsolator, run: _ResendRun, columns: list[str], batch: list[tuple]) -> None:
    """Manda un batch del reenvio; si cae entero, el isolator aisla el registro
    que lo rompe (y lo deja en la cola como batch_failed, salvo en dry-run)."""
    groups = group_rows_by_key(run.entity, columns, batch)
    keys = [k for k in groups if k is not None]
    for key in keys:
        run.see(key)
        if run.entity == "proveedores":
            run.raw_by_key[key] = dict(zip(columns, groups[key][0]))

    if run.aborted_reason is not None:
        for key in keys:
            run.not_sent[key] = run.aborted_reason
        return

    result = isolator.write(columns, batch)
    for key, message in result.isolated.items():
        run.failed[key] = message
    if result.ok:
        return
    pending = [k for k in result.unresolved if k is not None and k not in run.outcomes]
    if result.infra:
        run.aborted_reason = f"backend/red caido, se corto el reenvio: {result.error}"
        logger.error("resend [%s]: %s", run.entity, run.aborted_reason)
        for key in pending:
            run.not_sent[key] = run.aborted_reason
    else:
        for key in pending:
            run.failed[key] = str(result.error)


def _iter_resend_batches(result, columns: list[str], entity: str, batch_size: int):
    group_fields = GROUPED_BATCH_FIELDS.get(entity)
    if group_fields:
        yield from iter_grouped_batches(result, columns, group_fields, batch_size)
        return
    while True:
        rows = result.fetchmany(batch_size)
        if not rows:
            return
        yield [tuple(row) for row in rows]


def _classify_resend_key(
    run: _ResendRun,
    key: str,
    *,
    by_keys: bool,
    dry_run: bool,
    sink: RecordEventSink,
    retry_store: RetryStore,
) -> ResendResult:
    outcomes = run.outcomes.get(key)
    if outcomes:
        errors = [o for o in outcomes if not o.ok]
        if errors:
            detail = " ; ".join(dict.fromkeys(o.message or "rechazado sin mensaje" for o in errors))
            return ResendResult(key, RESEND_REJECTED, detail)
    # Su request fallo (aunque Paxapos haya llegado a responder algo de la fila).
    if key in run.failed:
        return ResendResult(key, RESEND_FAILED, run.failed[key])
    if outcomes:
        not_found = [o for o in outcomes if o.mode == "skipped_not_found"]
        if not_found:
            return ResendResult(
                key, RESEND_NOT_APPLIED,
                f"el id Paxapos {not_found[0].remote_id} ya no existe (baja manual en destino); no se modifico nada",
            )
        last = outcomes[-1]
        detail = f"modo={last.mode or '?'}"
        if last.remote_id is not None:
            detail += f", id Paxapos={last.remote_id}"
        if dry_run:
            detail += " (dry-run: Paxapos no persiste)"
        return ResendResult(key, RESEND_OK, detail)
    if key in run.not_sent:
        return ResendResult(key, RESEND_NOT_SENT, run.not_sent[key])
    if key not in run._seen_set:
        return ResendResult(key, RESEND_NOT_FOUND, "no hay filas en RAFAM con esa clave")

    reason = sink.reason_for(run.entity, key)
    if reason is None and run.entity == "proveedores":
        if is_cod_prov_excluded(key):
            reason = "proveedor excluido por configuracion"
        elif map_proveedor_migrator_row(run.raw_by_key.get(key, {})) is None:
            reason = "fila invalida en RAFAM: no se pudo mapear (falta FANTASIA/RAZON_SOCIAL)"
    if reason is None:
        reason = _queue_reason(retry_store, run.entity, key)
    if reason is None:
        if not by_keys:
            return ResendResult(key, RESEND_UNCHANGED, "ya migrado y sin cambios en RAFAM")
        reason = "omitido por el script sin motivo registrado (ver log)"
    return ResendResult(key, RESEND_SKIPPED, reason)


def _resend_records(
    retry_store: RetryStore,
    entity: str,
    *,
    keys: list[str] | None = None,
    date_range: tuple[date, date] | None = None,
    dry_run: bool = False,
    batch_size: int | None = None,
) -> ResendReport:
    """Envia a Paxapos SOLO los registros pedidos, sin tocar checkpoints.

    ``keys`` (claves base) fuerza el reenvio aunque el registro este "sin
    cambios" o 'permanent'; ``date_range`` reevalua una ventana con las reglas
    normales del pipeline (ver `SourceRepository.build_statement`).
    """
    if (keys is None) == (date_range is None):
        raise ValueError("_resend_records requiere keys o date_range (uno solo)")
    by_keys = keys is not None
    keys = list(dict.fromkeys(keys)) if keys is not None else None
    if batch_size is None:
        batch_size = _RESEND_KEYS_BATCH_SIZE if by_keys else _RESEND_WINDOW_BATCH_SIZE
    batch_size = _effective_batch_size(entity, batch_size)

    report = ResendReport(entity=entity, dry_run=dry_run, by_keys=by_keys)
    run = _ResendRun(entity)
    sink = RecordEventSink()
    exporter = build_exporter(dry_run=dry_run)
    try:
        # Un 'permanent' reenviado a mano arranca de cero: si vuelve a fallar se
        # reencola con attempts=1 en vez de quedar trabado en 'permanent'.
        if by_keys and not dry_run:
            wanted = set(keys)
            for item in retry_store.list_items(entity=entity, status=STATUS_PERMANENT):
                if record_base_key(entity, item.external_id) in wanted:
                    report.requeued += retry_store.requeue(entity=entity, external_id=item.external_id)

        exporter.attach_retry_store(retry_store)
        exporter.attach_event_sink(sink)
        if by_keys:
            exporter.set_force_keys(entity, keys)

        source_engine = create_source_engine()
        with source_engine.connect() as conn:
            source_repo = SourceRepository(conn)
            exporter.attach_source(source_repo)
            # Checkpoint sintetico: nunca se lee ni se escribe state/checkpoint.db.
            stmt = source_repo.build_statement(
                entity,
                Checkpoint(entity=entity),
                only_keys=set(keys) if by_keys else None,
                date_range=date_range,
            )
            result = source_repo.execute(stmt)
            columns = list(result.keys())
            isolator = BatchIsolator(
                exporter,
                entity,
                retry_store=retry_store,
                dry_run=dry_run,
                max_requests=_RESEND_ISOLATION_MAX_REQUESTS,
                after_write=lambda _exc: run.add_outcomes(exporter.get_last_batch_outcomes()),
            )
            for batch in _iter_resend_batches(result, columns, entity, batch_size):
                _resend_batch(isolator, run, columns, batch)
    finally:
        exporter.close()

    report.aborted_reason = run.aborted_reason
    for key in (keys if by_keys else run.seen):
        report.results.append(_classify_resend_key(
            run, key, by_keys=by_keys, dry_run=dry_run, sink=sink, retry_store=retry_store,
        ))
    for outcome in run.related:
        status = RESEND_OK if outcome.ok else RESEND_REJECTED
        detail = (
            f"modo={outcome.mode or '?'}, id Paxapos={outcome.remote_id}"
            if outcome.ok
            else (outcome.message or "rechazado sin mensaje")
        )
        report.related.append((describe_retry_key(outcome.entity, outcome.key), status, detail))
    return report


def _print_resend_report(report: ResendReport) -> None:
    title = f"Reenvio de {report.entity}"
    if report.dry_run:
        title += " [DRY-RUN: Paxapos no persiste nada]"
    print()
    print(title)
    print("─" * 100)
    if report.requeued:
        print(f"  {report.requeued} registro(s) estaban 'permanent' en la cola: se reencolaron (pending, 0 intentos).")
    if report.by_keys:
        shown = report.results
    else:
        # Ventana: puede traer miles de registros. Se detalla lo que fallo y los
        # omitidos se agrupan por motivo.
        shown = [
            r for r in report.results
            if r.status not in (RESEND_OK, RESEND_UNCHANGED, RESEND_SKIPPED)
        ]
    col = "  {:<32} {:<20} {}"
    if shown:
        print(col.format("Registro", "Resultado", "Detalle"))
        for res in shown:
            print(col.format(describe_retry_key(report.entity, res.key)[:32], res.status, res.detail))
    if not report.by_keys:
        by_reason: dict[str, list[str]] = {}
        for res in report.results:
            if res.status == RESEND_SKIPPED:
                by_reason.setdefault(_reason_category(res.detail), []).append(
                    describe_retry_key(report.entity, res.key)
                )
        if by_reason:
            print()
            print("  Omitidos por motivo (detalle de cada uno: resend --key <registro>):")
            for reason, labels in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
                ejemplos = ", ".join(labels[:3]) + (" ..." if len(labels) > 3 else "")
                print(f"    {len(labels):>5} x {reason}  [{ejemplos}]")
    if report.related:
        print()
        print("  Registros relacionados en la misma respuesta:")
        for label, status, detail in report.related:
            print(col.format(label[:32], status, detail))
    print()
    counts = report.counts()
    resumen = ", ".join(f"{status}: {n}" for status, n in sorted(counts.items())) or "sin registros"
    print(f"  Total {len(report.results)} registro(s) — {resumen}")
    if report.aborted_reason:
        print(f"  ATENCION: {report.aborted_reason}")
    print()


def _reason_category(detail: str) -> str:
    """Motivo sin numeros ni comando sugerido, para agrupar omitidos de una ventana."""
    reason = detail.split("; primero:", 1)[0]
    return re.sub(r"\d[\d.-]*", "#", reason)


def _read_keys_file(path: str) -> list[str]:
    lines: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if line:
                lines.append(line)
    return lines


def _parse_iso_date(value: str, flag: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        logger.error("%s debe tener formato YYYY-MM-DD (recibido: %r)", flag, value)
        raise SystemExit(2)


def cmd_resend(args) -> None:
    """Reenvia registros puntuales (o una ventana de fechas) sin tocar checkpoints."""
    entity = args.entity
    keys: list[str] | None = None
    date_range: tuple[date, date] | None = None

    if args.status and not args.from_queue:
        logger.error("--status solo aplica junto con --from-queue")
        raise SystemExit(2)
    if args.hasta and not args.desde:
        logger.error("--hasta requiere --desde")
        raise SystemExit(2)

    if args.key or args.keys_file:
        raw_keys = list(args.key or [])
        if args.keys_file:
            try:
                raw_keys.extend(_read_keys_file(args.keys_file))
            except OSError as exc:
                logger.error("No se pudo leer --keys-file %s: %s", args.keys_file, exc)
                raise SystemExit(2)
        keys, errors = [], []
        for raw in raw_keys:
            try:
                keys.append(parse_record_key(entity, raw))
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            for err in errors:
                logger.error(err)
            raise SystemExit(2)
        if not keys:
            logger.error("No se indico ninguna clave")
            raise SystemExit(2)
    elif args.desde:
        desde = _parse_iso_date(args.desde, "--desde")
        hasta = _parse_iso_date(args.hasta, "--hasta") if args.hasta else date.today()
        if desde > hasta:
            logger.error("--desde (%s) es posterior a --hasta (%s)", desde, hasta)
            raise SystemExit(2)
        date_range = (desde, hasta)

    with _exclusive_run_lock(wait_seconds=_RESEND_LOCK_WAIT_SECONDS):
        retry_store = RetryStore()
        try:
            if args.from_queue:
                status = None if args.status == "all" else (args.status or STATUS_PENDING)
                keys = _queue_keys(retry_store, entity, status)
                if not keys:
                    print(f"\nLa cola de reintentos de {entity} no tiene registros (status={args.status or STATUS_PENDING}).\n")
                    return
            report = _resend_records(
                retry_store,
                entity,
                keys=keys,
                date_range=date_range,
                dry_run=bool(args.dry_run),
                batch_size=args.batch_size,
            )
            if not args.dry_run:
                _flush_record_alerts(retry_store)
        finally:
            retry_store.close()

    _print_resend_report(report)
    code = report.exit_code(strict=not args.from_queue and keys is not None)
    if code:
        raise SystemExit(code)


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

    # Lista para el operador de RAFAM (en vivo desde la cola): que registros no
    # llegaron a Paxapos y que se destrabo hoy.
    try:
        retry_store = RetryStore()
        try:
            link_store = EntityLinkStore()
            try:
                summary_data["operator"] = build_operator_report(
                    retry_store,
                    day=date.fromisoformat(target_date),
                    body_limit=_mail_retry_detail_limit(),
                    link_store=link_store,
                )
            finally:
                link_store.close()
            retry_store.prune_resolved(keep_days=30)
        finally:
            retry_store.close()
    except Exception:
        logger.warning(
            "No se pudo armar la lista de registros a revisar para el mail",
            exc_info=True,
        )

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
        "--dry-run",
        action="store_true",
        help="Preview sin re-enviar ni actualizar hashes locales",
    )
    sync_p.add_argument(
        "--backfill-only",
        action="store_true",
        help="Calcula y guarda los hashes de registros ya vinculados sin enviarlos a Paxapos",
    )

    retry_p = sub.add_parser(
        "retry-queue",
        help="Lista la cola de reintentos y permite reencolar filas 'permanent'",
    )
    retry_p.add_argument("--entity", metavar="NOMBRE", help="Filtrar por entidad")
    retry_p.add_argument("--status", choices=["pending", "permanent"], help="Filtrar por estado")
    retry_p.add_argument("--external-id", metavar="ID", help="Filtrar por external_id exacto")
    retry_p.add_argument(
        "--requeue",
        action="store_true",
        help="Devuelve las filas 'permanent' (con los filtros dados) a 'pending' con intentos en 0",
    )
    retry_p.add_argument(
        "--dismiss",
        action="store_true",
        help="Descarta exactamente un retry; requiere --entity, --external-id y --note",
    )
    retry_p.add_argument("--note", help="Motivo de auditoria requerido por --dismiss")
    retry_p.add_argument(
        "--send-now",
        action="store_true",
        help=(
            "Reenvia YA (sin esperar al proximo cron) SOLO las claves 'pending' de "
            "--entity en la cola, y muestra el resultado de cada una (mismo camino "
            "que `resend --from-queue`; no toca el checkpoint). Combinable con "
            "--requeue (primero permanent -> pending, despues se reenvia). "
            "Requiere --entity."
        ),
    )

    resend_p = sub.add_parser(
        "resend",
        help="Reenvia registros puntuales (o una ventana de fechas) sin tocar checkpoints",
        description=(
            "Reenvia a Paxapos SOLO los registros indicados y muestra el resultado de cada uno. "
            "Con claves (--key/--keys-file/--from-queue) se fuerza el reenvio aunque el registro "
            "este 'sin cambios' o 'permanent' (las reglas de negocio se respetan). Con --desde/--hasta "
            "se reevalua la ventana con las reglas normales (solo se manda lo que cambio). "
            "Exit 0 si todo quedo OK, 1 si algun registro no."
        ),
    )
    resend_p.add_argument("--entity", required=True, choices=RESENDABLE_ENTITIES)
    resend_mode = resend_p.add_mutually_exclusive_group(required=True)
    resend_mode.add_argument(
        "--key",
        action="append",
        metavar="CLAVE",
        help=(
            "Clave a reenviar (repetible). Formas: OC 2026-3-1023, OP 2026-1023, gasto 2026-1-58, "
            "proveedor 1234; tambien el label del mail ('OP 2026-1023') o el JSON de retry-queue"
        ),
    )
    resend_mode.add_argument("--keys-file", metavar="ARCHIVO", help="Archivo con una clave por linea ('#' = comentario)")
    resend_mode.add_argument(
        "--from-queue", action="store_true", help="Reenvia las claves de la cola de reintentos de --entity",
    )
    resend_mode.add_argument("--desde", metavar="YYYY-MM-DD", help="Inicio de la ventana de fechas (inclusive)")
    resend_p.add_argument("--hasta", metavar="YYYY-MM-DD", help="Fin de la ventana (inclusive; default: hoy)")
    resend_p.add_argument(
        "--status",
        choices=["pending", "permanent", "all"],
        help="Con --from-queue: que filas de la cola reenviar (default: pending)",
    )
    resend_p.add_argument(
        "--batch-size",
        type=int,
        metavar="N",
        help=f"Filas por request (default: {_RESEND_KEYS_BATCH_SIZE} con claves, {_RESEND_WINDOW_BATCH_SIZE} con ventana)",
    )
    resend_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Envia con dry_run=true (Paxapos valida pero no persiste); no toca la cola",
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
        "retry-queue": cmd_retry_queue,
        "resend": cmd_resend,
        "daily-report": cmd_daily_report,
    }[args.command](args)


if __name__ == "__main__":
    main()
