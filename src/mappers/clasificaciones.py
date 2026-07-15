"""clasificaciones.py — Mapper del clasificador por objeto del gasto (RAFAM).

RAFAM no tiene una tabla maestra limpia del clasificador: la jerarquia de 4
niveles vive desnormalizada y repetida en las tablas transaccionales.

    inciso   (nivel 1 — ej: 1 = Gastos en personal)
    par_prin (nivel 2 — ej: 1 = Personal permanente)
    par_parc (nivel 3 — ej: 6 = Contribuciones patronales)
    par_subp (nivel 4 — ej: 1 = al IPS)  [opcional]
    DENOMINACION (texto de la partida, repetido en cada transaccion)

Este mapper reconstruye ese arbol como categorias anidadas (parent_id) para la
tabla de categorias de gasto de Paxapos (nested set: parent_id + lft/rght).

Restricciones de la tabla destino (NO se toca schema):
  - `name` es varchar(50)  -> se trunca (ver NOTA_DEV mas abajo).
  - No hay columna de codigo -> el vinculo codigo RAFAM (I.PP.PC.SP) <-> id de
    categoria Paxapos se persiste FUERA de Paxapos, en EntityLinkStore
    (entidad "clasificacion").

NOTA_DEV (truncado a 50):
  Hoy truncamos `name` a 50 chars SOLO PARA PROBAR EN DESARROLLO, porque la
  columna destino es varchar(50) y varias denominaciones RAFAM la superan.
  Cuando se amplie la columna en Paxapos (issue B2), subir NAME_MAX_LEN.
"""

from __future__ import annotations

import json
import logging

from ..utils import to_int

logger = logging.getLogger(__name__)

# ── Constantes de dominio ──────────────────────────────────────────────────

# Campos de jerarquia en orden canonico (nombre RAFAM -> nivel).
LEVEL_FIELDS: tuple[str, ...] = ("INCISO", "PAR_PRIN", "PAR_PARC", "PAR_SUBP")
NAME_FIELD = "DENOMINACION"

# Limite de `name` en la tabla destino (varchar(50)). Ver NOTA_DEV.
NAME_MAX_LEN = 50

# Seccion del payload / results del migrator para esta entidad.
RESULT_SECTION = "clasificaciones"

# Colisiones conocidas: mismo codigo I.PP.PC.SP con denominaciones divergentes.
# Se elige una canonica y se descartan las demas (con log). Confirmado con el
# usuario para 3.3.6.0.
CANONICAL_OVERRIDES: dict[str, str] = {
    "3.3.6.0": "Mantenimiento y Limpieza",
}

# Mojibake conocido: bytes de denominaciones RAFAM mal decodificados
# (CP850/Latin1 leidos como otra codepage). Extensible a medida que aparezcan.
#   "desag³es" -> "desagües"  (ü corrupta)
_MOJIBAKE_MAP: dict[str, str] = {
    "³": "ü",
    "²": "ó",
    "±": "ñ",
}


# ── Normalizacion ──────────────────────────────────────────────────────────

def clean_text(value: object) -> str:
    """Limpia una denominacion RAFAM: mojibake + espacios.

    - Corrige corrupciones de encoding conocidas (_MOJIBAKE_MAP).
    - Colapsa espacios internos y recorta extremos.
    """
    text = str(value if value is not None else "")
    for bad, good in _MOJIBAKE_MAP.items():
        if bad in text:
            text = text.replace(bad, good)
    return " ".join(text.split())


def truncate_name(text: str, limit: int = NAME_MAX_LEN) -> str:
    """Trunca `name` al limite de la columna destino, cortando por palabra.

    Si el corte por palabra dejaria un nombre demasiado corto (<60% del limite),
    trunca duro en el limite para no perder informacion util.
    """
    if len(text) <= limit:
        return text
    hard = text[:limit].rstrip()
    space = hard.rfind(" ")
    if space >= int(limit * 0.6):
        return hard[:space].rstrip()
    return hard


# ── Codigos y jerarquia ────────────────────────────────────────────────────

def _lvl(value: object) -> int:
    """Nivel numerico RAFAM: entero, o 0 cuando viene vacio/None."""
    parsed = to_int(value)
    return parsed if parsed is not None else 0


def code_str(inciso: int, par_prin: int, par_parc: int, par_subp: int) -> str:
    """Codigo compuesto estable `I.PP.PC.SP` (clave de negocio del nodo)."""
    return f"{inciso}.{par_prin}.{par_parc}.{par_subp}"


def parent_code(inciso: int, par_prin: int, par_parc: int, par_subp: int) -> str | None:
    """Codigo del nodo padre, ceroando el nivel no-cero mas profundo.

    Un inciso (PP=PC=SP=0) es raiz -> None.
    """
    if par_subp != 0:
        return code_str(inciso, par_prin, par_parc, 0)
    if par_parc != 0:
        return code_str(inciso, par_prin, 0, 0)
    if par_prin != 0:
        return code_str(inciso, 0, 0, 0)
    return None


def nivel(inciso: int, par_prin: int, par_parc: int, par_subp: int) -> int:
    """Profundidad del nodo en el arbol (1=inciso .. 4=subparcial)."""
    if par_subp != 0:
        return 4
    if par_parc != 0:
        return 3
    if par_prin != 0:
        return 2
    return 1


# ── Construccion de nodos ──────────────────────────────────────────────────

def build_nodes(
    columns: list[str],
    rows: list[tuple],
    *,
    name_max_len: int = NAME_MAX_LEN,
) -> tuple[list[dict], list[dict]]:
    """Reconstruye el arbol de nodos desde filas distinct de 4 niveles.

    Args:
        columns: nombres de columna del batch (deben incluir LEVEL_FIELDS + NAME_FIELD).
        rows: filas crudas (tuplas alineadas con `columns`).
        name_max_len: limite de truncado de `name` (dev: 50).

    Returns:
        (nodes, discarded)
        - nodes: lista ordenada (padres antes que hijos) de dicts:
            {code, parent_code, nivel, name, denominacion}
          Deduplicada por `code`: se conserva la primera aparicion.
        - discarded: filas descartadas por colision de codigo, para log/QA:
            {code, name, kept}
    """
    by_code: dict[str, dict] = {}
    first_denom_by_code: dict[str, str] = {}
    discarded: list[dict] = []

    for row in rows:
        raw = dict(zip(columns, row))
        inciso = to_int(raw.get("INCISO"))
        if inciso is None:
            # Fila basura sin inciso: se ignora (defensa como en la query fuente).
            continue
        par_prin = _lvl(raw.get("PAR_PRIN"))
        par_parc = _lvl(raw.get("PAR_PARC"))
        par_subp = _lvl(raw.get("PAR_SUBP"))

        code = code_str(inciso, par_prin, par_parc, par_subp)
        original_clean = clean_text(raw.get(NAME_FIELD))

        # Override canonico para colisiones conocidas (ej: 3.3.6.0). El nombre
        # a mostrar puede diferir de la denominacion original de la fila.
        override = CANONICAL_OVERRIDES.get(code)
        display_name = override if override is not None else original_clean

        if code in by_code:
            # Colision: mismo codigo. La deteccion se hace sobre la denominacion
            # ORIGINAL (no el override) para no perder visibilidad en el log.
            if original_clean != first_denom_by_code.get(code):
                discarded.append(
                    {"code": code, "name": original_clean, "kept": by_code[code]["name"]}
                )
            continue

        first_denom_by_code[code] = original_clean
        by_code[code] = {
            "code": code,
            "parent_code": parent_code(inciso, par_prin, par_parc, par_subp),
            "nivel": nivel(inciso, par_prin, par_parc, par_subp),
            "name": truncate_name(display_name, name_max_len),
            "denominacion": display_name,
            "_order": (inciso, par_prin, par_parc, par_subp),
        }

    # Orden: padres antes que hijos (necesario para resolver parent_id en el
    # receptor y para reconstruir lft/rght del nested set).
    nodes = sorted(by_code.values(), key=lambda n: n.pop("_order"))
    return nodes, discarded


# ── Mapper (interfaz EntityWriter) ─────────────────────────────────────────

class ClasificacionesMapper:
    """Mapper del clasificador de gasto -> categorias anidadas Paxapos."""

    def __init__(self, *, link_store, lookup_resolver=None):
        self._link_store = link_store
        self._lookup = lookup_resolver  # no usado hoy; simetria con otros mappers

    def build_payload(
        self,
        columns: list[str],
        rows: list[tuple],
        *,
        dry_run: bool,
        payload_options: dict,
    ) -> tuple[dict | None, dict[str, dict]]:
        """Construye el payload `clasificaciones` para POST al migrator.

        Returns:
            (payload, raw_by_source_key) o (None, {}) si el lote queda vacio.
        """
        nodes, discarded = build_nodes(columns, rows)

        if discarded:
            for d in discarded:
                logger.info(
                    "Migrator [clasificaciones] colision codigo %s: se descarta "
                    "'%s' (se conserva '%s')",
                    d["code"], d["name"], d["kept"],
                )
            logger.warning(
                "Migrator [clasificaciones]: %d denominaciones descartadas por "
                "colision de codigo (ver detalle arriba)",
                len(discarded),
            )

        if not nodes:
            logger.info("Migrator [clasificaciones]: lote vacio luego del mapeo")
            return None, {}

        clasificaciones: list[dict] = []
        raw_by_source_key: dict[str, dict] = {}

        for node in nodes:
            code = node["code"]
            payload_row: dict = {
                "external_id": {"codigo": code},
                "Clasificacion": {
                    "name": node["name"],
                    "nivel": node["nivel"],
                },
            }

            parent = node["parent_code"]
            if parent is not None:
                payload_row["parent_external_id"] = {"codigo": parent}
                # Si el padre ya fue migrado en una corrida previa, inyectar su
                # id remoto para que el receptor lo linkee sin depender del orden.
                remote_parent = self._link_store.get_remote_id("clasificacion", parent)
                if remote_parent:
                    payload_row["parent_id"] = int(remote_parent)

            # Upsert: si el nodo ya existe, inyectar su id remoto.
            remote_id = self._link_store.get_remote_id("clasificacion", code)
            if remote_id:
                payload_row["Clasificacion"]["id"] = int(remote_id)

            clasificaciones.append(payload_row)
            raw_by_source_key[code] = {
                "codigo": code,
                "denominacion": node["denominacion"],
                "nivel": node["nivel"],
                "parent_codigo": parent or "",
            }

        payload = {
            "dry_run": dry_run,
            "options": payload_options,
            "proveedores": [],
            "pedidos": [],
            "ordenes_compra": [],
            "gastos": [],
            "ordenes_pago": [],
            "clasificaciones": clasificaciones,
        }
        return payload, raw_by_source_key

    def log_stats(self, parsed: dict, dry_run: bool) -> None:
        stats = parsed.get("stats", {}) if isinstance(parsed, dict) else {}
        section_stats = stats.get(RESULT_SECTION, {}) if isinstance(stats, dict) else {}
        logger.info(
            "Migrator OK [clasificaciones]: %d ok, %d error, dry_run=%s",
            section_stats.get("ok", 0),
            section_stats.get("error", 0),
            dry_run,
        )


# ── Persist links ──────────────────────────────────────────────────────────

def persist_links(parsed: dict, raw_by_source_key: dict[str, dict], link_store) -> None:
    """Persiste los links codigo RAFAM <-> id categoria Paxapos desde la respuesta."""
    if not isinstance(parsed, dict):
        return
    results = parsed.get("results", {})
    if not isinstance(results, dict):
        return

    section = results.get(RESULT_SECTION, [])
    if not isinstance(section, list):
        return

    for result in section:
        if not isinstance(result, dict) or not result.get("success"):
            continue
        if result.get("mode") == "skipped_not_found":
            # El id de Paxapos ya no existe (baja manual desde la UI). No se recrea
            # (respeta spec.no_borra) ni se pisa el link: se conserva y se loguea
            # para que quede en el reporte/mail del run.
            logger.warning(
                "Migrator [clasificaciones]: id Paxapos %s inexistente (baja manual); "
                "se omite la modificacion. external_id=%s",
                result.get("id"), result.get("external_id"),
            )
            continue
        external_id = result.get("external_id") or {}
        if not isinstance(external_id, dict):
            continue
        code = external_id.get("codigo")
        remote_id = result.get("id")
        if code is None or remote_id is None:
            continue

        raw = raw_by_source_key.get(str(code), {})
        link_store.save_link(
            entity="clasificacion",
            source_key=str(code),
            remote_id=str(remote_id),
            denominacion=raw.get("denominacion"),
            nivel=str(raw.get("nivel")) if raw.get("nivel") is not None else None,
            parent_codigo=raw.get("parent_codigo") or None,
        )
