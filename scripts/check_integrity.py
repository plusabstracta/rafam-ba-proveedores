#!/usr/bin/env python
"""scripts/check_integrity.py — Verificación de integridad RAFAM → Paxapos.

Detecta dos tipos de anomalías en los registros ya migrados:

  1. ANULACIONES (todas las entidades)
     Un registro que fue enviado a Paxapos (tiene remote_id en el link store)
     ahora figura como anulado en RAFAM (ESTADO_OC/OP/SOLIC = 'A').
     Acción: marcar deleted_at en el link store para auditoría.

  2. CAMBIOS DE CONTENIDO — solo proveedores
     Un proveedor ya migrado tiene diferente hash SHA-256 respecto al guardado
     en content_hash del link store. Indica que algún campo cambió en RAFAM.
     Acción: reenviar el proveedor actualizado a Paxapos y actualizar el hash.

Modos de ejecución:
  --dry-run   Solo reporta anomalías sin escribir nada. (default)
  --apply     Aplica correcciones: marca deleted_at y reenvía proveedores.

Opciones de filtro:
  --entity ENTITY   Procesa solo una entidad (default: todas).

Uso::

    python scripts/check_integrity.py --dry-run
    python scripts/check_integrity.py --apply --entity proveedores
    python scripts/check_integrity.py --apply

"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Logging a consola — siempre activo independientemente del archivo de log
_CONSOLE_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_CONSOLE_DATE_FORMAT = "%H:%M:%S"


def setup_console_logging(level: int = logging.INFO) -> None:
    """Agrega un StreamHandler a stderr para ver los logs en tiempo real en consola."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT, datefmt=_CONSOLE_DATE_FORMAT))
    logging.getLogger().addHandler(handler)


# Asegurar que src/ esté en el path cuando se llama directamente desde scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Cambiar al directorio raíz del proyecto para que todas las rutas relativas
# (state/checkpoint.db, .env, logs/, etc.) se resuelvan correctamente
# sin importar desde qué directorio se invoque el script.
os.chdir(REPO_ROOT)

from src.config import ENTITY_CONFIGS  # noqa: E402
from src.entity_link_store import EntityLinkStore  # noqa: E402
from src.error_formatting import format_exception_context  # noqa: E402
from src.logging_config import setup_file_logging  # noqa: E402
from src.mappers.proveedores import compute_content_hash  # noqa: E402
from src.notifier import notify_integrity_result  # noqa: E402
from src.source_repository import SourceRepository  # noqa: E402

logger = logging.getLogger(__name__)

# Entidades que soportan verificación de anulaciones
ENTITIES_ANULACIONES = ["proveedores", "orden_compra", "gasto", "orden_pago", "retenciones"]

# Entidades que soportan verificación de contenido por hash
ENTITIES_CONTENT_HASH = ["proveedores"]


# ── Estructuras de resultado ──────────────────────────────────────────────────

@dataclass
class EntityResult:
    entity: str
    verificados: int = 0
    sin_cambios: int = 0
    actualizados: int = 0   # solo proveedores (hash cambió + reenvío OK)
    anulados: int = 0       # registros con ESTADO='A' en RAFAM
    fisicamente_eliminados: int = 0  # no existen en RAFAM (muy raro)
    errores: int = 0
    warnings: list[str] = field(default_factory=list)


# ── Lógica de verificación ────────────────────────────────────────────────────

def check_anulaciones(
    entity: str,
    link_store: EntityLinkStore,
    repo: SourceRepository,
    *,
    apply: bool,
) -> EntityResult:
    """Verifica anulaciones para una entidad. Devuelve el resultado."""
    result = EntityResult(entity=entity)

    try:
        links = link_store.iter_all_links(entity, include_deleted=False)
        # Solo verificar links que ya tienen remote_id (fueron enviados a Paxapos)
        links = [lk for lk in links if lk.get("remote_id")]
    except Exception as exc:
        msg = format_exception_context(
            exc, entity, None, "Obteniendo enlaces locales (links) de la base de datos de checkpoints"
        )
        logger.error("\n" + msg)
        result.errores += 1
        result.warnings.append(msg)
        return result

    for link in links:
        source_key = link["source_key"]
        remote_id = link.get("remote_id")
        result.verificados += 1

        try:
            info = repo.fetch_estado_by_key(entity, source_key)
        except Exception as exc:
            msg = format_exception_context(
                exc, entity, source_key, "Consultando estado de anulación en RAFAM"
            )
            logger.error("\n" + msg)
            result.errores += 1
            result.warnings.append(msg)
            continue

        if info is None:
            # Registro eliminado físicamente de RAFAM (muy raro)
            msg = (
                f"Entidad '{entity}' clave '{source_key}' (remote_id: {remote_id}): "
                f"ELIMINADO FÍSICAMENTE de RAFAM (no existe en la tabla de origen)"
            )
            logger.warning(msg)
            result.fisicamente_eliminados += 1
            result.warnings.append(f"FÍSICO: {msg}")
            if apply:
                try:
                    link_store.mark_deleted(entity, source_key)
                except Exception as exc2:
                    msg_err = format_exception_context(
                        exc2, entity, source_key, "Marcando registro como eliminado físicamente en base de datos local"
                    )
                    logger.error("\n" + msg_err)
                    result.errores += 1
                    result.warnings.append(msg_err)
            continue

        if info["anulado"]:
            msg = (
                f"Entidad '{entity}' clave '{source_key}' (remote_id: {remote_id}): "
                f"ANULADO en RAFAM (estado: {info['estado']!r}"
                + (f", fecha_anulación: {info['fech_anul']!r}" if info.get("fech_anul") else "")
                + ")"
            )
            logger.warning(msg)
            result.anulados += 1
            result.warnings.append(f"ANULADO: {msg}")
            if apply:
                try:
                    link_store.mark_deleted(entity, source_key)
                    logger.info("Registro marcado como anulado localmente: %s key=%s", entity, source_key)
                except Exception as exc2:
                    msg_err = format_exception_context(
                        exc2, entity, source_key, "Marcando registro como anulado en base de datos local"
                    )
                    logger.error("\n" + msg_err)
                    result.errores += 1
                    result.warnings.append(msg_err)
        else:
            result.sin_cambios += 1

    return result


def check_content_hash_proveedores(
    link_store: EntityLinkStore,
    repo: SourceRepository,
    *,
    apply: bool,
    exporter,
) -> EntityResult:
    """Verifica y reenvía proveedores cuyo hash cambió en RAFAM."""
    from src.exporter import MigratorExporter  # importar aquí para evitar ciclos

    result = EntityResult(entity="proveedores")

    try:
        links = link_store.iter_all_links("proveedores", include_deleted=False)
        links = [lk for lk in links if lk.get("remote_id")]
    except Exception as exc:
        msg = format_exception_context(
            exc, "proveedores", None, "Obteniendo enlaces locales de proveedores de la base de datos de checkpoints"
        )
        logger.error("\n" + msg)
        result.errores += 1
        result.warnings.append(msg)
        return result

    for link in links:
        source_key = link["source_key"]
        saved_hash = link.get("content_hash")
        result.verificados += 1

        try:
            cod_prov = int(source_key)
        except (ValueError, TypeError) as exc:
            msg = format_exception_context(
                exc, "proveedores", source_key, "Conversión de clave de proveedor (source_key) a entero"
            )
            logger.error("\n" + msg)
            result.errores += 1
            result.warnings.append(msg)
            continue

        try:
            raw = repo.fetch_proveedor_row(cod_prov)
        except Exception as exc:
            msg = format_exception_context(
                exc, "proveedores", source_key, "Consultando fila completa del proveedor en RAFAM para control de hash"
            )
            logger.error("\n" + msg)
            result.errores += 1
            result.warnings.append(msg)
            continue

        if raw is None:
            # El proveedor ya no existe; la verificación de anulaciones lo maneja
            result.sin_cambios += 1
            continue

        current_hash = compute_content_hash(raw)

        if saved_hash is not None and saved_hash == current_hash:
            result.sin_cambios += 1
            continue

        # Hash cambió (o nunca fue guardado)
        changed_fields = _diff_fields(link, raw) if saved_hash is not None else ["(baseline no guardado)"]
        msg = (
            f"proveedores COD_PROV={source_key}: CONTENIDO MODIFICADO "
            f"campos={changed_fields}"
        )
        logger.warning(msg)
        result.warnings.append(f"ACTUALIZADO: {msg}")

        if apply:
            try:
                _reenviar_proveedor(
                    raw=raw,
                    source_key=source_key,
                    link_store=link_store,
                    exporter=exporter,
                    content_hash=current_hash,
                )
                result.actualizados += 1
                logger.info("Proveedor COD_PROV=%s reenviado y hash actualizado", source_key)
            except Exception as exc:
                msg2 = format_exception_context(
                    exc, "proveedores", source_key, f"Reenviando proveedor modificado a Paxapos (cuit={raw.get('CUIT')}, fantasia={raw.get('FANTASIA')})"
                )
                logger.error("\n" + msg2)
                result.errores += 1
                result.warnings.append(msg2)
        else:
            # dry-run: contar como "actualizados pendientes"
            result.actualizados += 1

    return result


def _diff_fields(link: dict, raw: dict) -> list[str]:
    """Detecta qué campos del hash difieren (solo para logging descriptivo)."""
    from src.mappers.proveedores import _HASH_FIELDS
    changed = []
    for f in _HASH_FIELDS:
        old_val = None  # no tenemos los valores anteriores, solo el hash
        new_val = str(raw.get(f) or "")
        _ = old_val  # suprimir warning
        changed.append(f)  # reportamos todos los campos relevantes como contexto
    # En realidad no podemos saber cuál cambió (solo tenemos el hash viejo, no los valores)
    # así que indicamos que hay una diferencia de hash sin detallar campos individuales.
    return ["(diferencia de hash detectada — ver logs de RAFAM para detalle)"]


def _reenviar_proveedor(
    raw: dict,
    source_key: str,
    link_store: EntityLinkStore,
    exporter: Any,
    content_hash: str,
) -> None:
    """Reenvía un proveedor actualizado a Paxapos usando la lógica del exporter.

    Esto garantiza que el mapeo, el POST a Paxapos y la actualización del
    content_hash en el link store se realicen bajo la misma lógica del pipeline.
    """
    # Convertir dict raw a formato columns/rows esperado por el exporter
    columns = list(raw.keys())
    rows = [tuple(raw[col] for col in columns)]

    # El exporter internamente mapea (inyectando el remote_id si existe), envía y actualiza el link (con el nuevo hash)
    exporter.write_batch(entity="proveedores", columns=columns, rows=rows)
    link = link_store.get_link("proveedores", source_key) or {}
    remote_id = link.get("remote_id")
    if remote_id:
        link_store.save_link(
            entity="proveedores",
            source_key=source_key,
            remote_id=str(remote_id),
            content_hash=content_hash,
        )



# ── Resumen tabular ───────────────────────────────────────────────────────────

def print_summary(results: list[EntityResult], *, dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"\n{'─' * 80}")
    print(f"  RESUMEN DE INTEGRIDAD RAFAM → Paxapos  [{mode}]")
    print(f"{'─' * 80}")
    print(
        f"  {'Entidad':<16} {'Verif':>7} {'OK':>7} {'Actualiz':>9} "
        f"{'Anulados':>9} {'Físicos':>8} {'Errores':>8}"
    )
    print(f"  {'─'*16} {'─'*7} {'─'*7} {'─'*9} {'─'*9} {'─'*8} {'─'*8}")
    total = EntityResult(entity="TOTAL")
    for r in results:
        actualizados_str = str(r.actualizados) if r.entity in ENTITIES_CONTENT_HASH else "—"
        print(
            f"  {r.entity:<16} {r.verificados:>7} {r.sin_cambios:>7} "
            f"{actualizados_str:>9} {r.anulados:>9} {r.fisicamente_eliminados:>8} {r.errores:>8}"
        )
        total.verificados += r.verificados
        total.sin_cambios += r.sin_cambios
        total.actualizados += r.actualizados
        total.anulados += r.anulados
        total.fisicamente_eliminados += r.fisicamente_eliminados
        total.errores += r.errores
    print(f"  {'─'*16} {'─'*7} {'─'*7} {'─'*9} {'─'*9} {'─'*8} {'─'*8}")
    print(
        f"  {'TOTAL':<16} {total.verificados:>7} {total.sin_cambios:>7} "
        f"{total.actualizados:>9} {total.anulados:>9} {total.fisicamente_eliminados:>8} {total.errores:>8}"
    )
    print(f"{'─' * 80}\n")

    if dry_run and (total.anulados > 0 or total.actualizados > 0 or total.fisicamente_eliminados > 0):
        print("  ⚠  Modo DRY-RUN: no se aplicaron cambios.")
        print("  ✓  Ejecutar con --apply para persistir las correcciones.\n")
    elif not dry_run and total.errores > 0:
        print(f"  ⚠  {total.errores} errores durante la corrección. Revisar logs.\n")
    elif not dry_run:
        print("  ✓  Correcciones aplicadas exitosamente.\n")


# ── Entrypoint ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifica integridad de registros RAFAM → Paxapos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Solo reporta anomalías sin aplicar cambios (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Aplica correcciones: marca deleted_at y reenvía proveedores.",
    )
    parser.add_argument(
        "--entity",
        choices=ENTITIES_ANULACIONES,
        default=None,
        help="Procesa solo la entidad indicada (default: todas).",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        default=False,
        help="Suprime el envío de notificaciones por email para esta ejecución.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    apply = args.apply
    dry_run = not apply

    # Configurar logging: consola primero, luego archivo
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.root.setLevel(log_level)   # nivel raíz sin agregar handlers
    setup_console_logging(log_level)

    args.command = "check_integrity"
    setup_file_logging(args)
    logger.info(
        "check_integrity iniciado — modo=%s entity=%s",
        "apply" if apply else "dry-run",
        args.entity or "todas",
    )

    # Determinar entidades a verificar
    entities = [args.entity] if args.entity else ENTITIES_ANULACIONES

    # Abrir conexiones
    from src.db import create_source_engine  # importación local para flexibilidad

    engine = create_source_engine()
    conn = engine.connect()
    repo = SourceRepository(conn)

    # Variable canonica LOCAL_STATE_DB_PATH (misma DB que checkpoints/links del
    # resto del sistema). El alias LINK_STORE_PATH apuntaba a otra DB y dejaba
    # la verificacion corriendo contra un store distinto al real.
    link_store_path = os.environ.get("LOCAL_STATE_DB_PATH", "state/checkpoint.db")
    link_store = EntityLinkStore(db_path=link_store_path)

    # Exporter solo se necesita en modo apply para proveedores
    exporter = None
    if apply and "proveedores" in entities:
        from src.exporter import MigratorExporter
        exporter = MigratorExporter()

    results: list[EntityResult] = []

    # ── Paso 1: Anulaciones (todas las entidades) ─────────────────────────
    for entity in entities:
        r = check_anulaciones(entity, link_store, repo, apply=apply)
        results.append(r)

        # Log ultra-corto y conciso si no hay anomalías ni errores
        if r.anulados == 0 and r.fisicamente_eliminados == 0 and r.errores == 0:
            logger.info("Verificando anulaciones para %s... OK", entity)
        else:
            # Si hay anomalías o errores, dar un resumen explícito de anomalías
            logger.info(
                "Verificando anulaciones para %s... ANOMALÍAS/ERRORES DETECTADOS (Verificados: %d, Anulados: %d, Físicos: %d, Errores: %d)",
                entity, r.verificados, r.anulados, r.fisicamente_eliminados, r.errores
            )

    # ── Paso 2: Content hash — solo proveedores ───────────────────────────
    if "proveedores" in entities:
        r_hash = check_content_hash_proveedores(
            link_store, repo, apply=apply, exporter=exporter
        )
        # Fusionar con el resultado de anulaciones de proveedores
        for r in results:
            if r.entity == "proveedores":
                r.actualizados = r_hash.actualizados
                r.errores += r_hash.errores
                r.warnings.extend(r_hash.warnings)
                # Ajustar sin_cambios: no contar doble los que ya tienen
                # deleted_at del paso 1 (se verifican los activos en ambos pasos)
                break

        # Log ultra-corto y conciso si no hay cambios ni errores
        if r_hash.actualizados == 0 and r_hash.errores == 0:
            logger.info("Verificando cambios de contenido para proveedores... OK")
        else:
            logger.info(
                "Verificando cambios de contenido para proveedores... MODIFICACIONES/ERRORES DETECTADOS (Verificados: %d, Actualizados: %d, Errores: %d)",
                r_hash.verificados, r_hash.actualizados, r_hash.errores
            )

    conn.close()
    engine.dispose()

    print_summary(results, dry_run=dry_run)

    # ── Notificación por email ────────────────────────────────────────────
    total_actualizados = sum(r.actualizados for r in results)
    total_anulados = sum(r.anulados for r in results)
    total_errores = sum(r.errores for r in results)

    # Solo notificar por mail si hay errores reales (total_errores > 0)
    if total_errores > 0 and not getattr(args, "no_notify", False):
        # Construir resumen tabular como texto para el cuerpo del email
        summary_lines: list[str] = []
        header = f"  {'Entidad':<16} {'Verif':>7} {'OK':>7} {'Actualiz':>9} {'Anulados':>9} {'Físicos':>8} {'Errores':>8}"
        summary_lines.append(header)
        summary_lines.append("  " + "─" * (len(header) - 2))
        for r in results:
            act_str = str(r.actualizados) if r.entity in ENTITIES_CONTENT_HASH else "—"
            summary_lines.append(
                f"  {r.entity:<16} {r.verificados:>7} {r.sin_cambios:>7} "
                f"{act_str:>9} {r.anulados:>9} {r.fisicamente_eliminados:>8} {r.errores:>8}"
            )

        all_warnings: list[str] = []
        for r in results:
            all_warnings.extend(r.warnings)

        sent = notify_integrity_result(
            summary_lines=summary_lines,
            warnings=all_warnings,
            dry_run=dry_run,
            entity=args.entity,
            total_actualizados=total_actualizados,
            total_anulados=total_anulados,
            total_errores=total_errores,
        )
        if sent:
            logger.info("Notificación por email enviada exitosamente")
    elif total_errores == 0:
        logger.debug("Notificaciones omitidas: no se registraron errores (total_errores=0)")
    else:
        logger.debug("Notificaciones suprimidas por --no-notify")

    # Código de salida: 0 si todo OK o solo warnings, 1 si hay errores
    return 1 if total_errores > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
