"""Entity configurations for the RAFAM incremental sync engine.

The query layer builds SQLAlchemy expressions from this metadata, avoiding
hand-written SQL in application code.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from .models import EntityConfig

# load_dotenv() MUST run before reading env vars, because this module is
# imported before main.py calls load_dotenv().  It's idempotent so safe
# to call multiple times.
# Use explicit path because find_dotenv() from src/ may not locate the
# project root .env depending on python-dotenv version.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

SCHEMA = "OWNER_RAFAM"

# Ejercicio minimo a migrar. Por defecto 2026 (hardcodeado) pero se puede
# sobrescribir por entorno (RAFAM_EJERCICIO_MIN) si hiciera falta.
# La regla de corte (ver source_repository._ejercicio_boundary_filter) admite
# ademas una excepcion de cruce fiscal: entidades del ejercicio anterior
# (min-1) confirmadas ya en el ejercicio nuevo (FECH_CONFIRM >= min-01-01)
# tambien se migran.
_EJERCICIO_MIN = int(os.getenv("RAFAM_EJERCICIO_MIN", "2026")) or None

ENTITY_CONFIGS: dict[str, EntityConfig] = {
    "proveedores": EntityConfig(
        name="proveedores",
        table_name="PROVEEDORES",
        ts_field="FECHA_ULT_COMP",
    ),
    "pedidos": EntityConfig(
        name="pedidos",
        table_name="PEDIDOS",
        ts_field="FECH_EMI",
        ejercicio_min=_EJERCICIO_MIN,
    ),
    "ped_items": EntityConfig(
        name="ped_items",
        table_name="PED_ITEMS",
        full_load=True,  # no reliable cursor column yet — confirm with explore_schema.py
        ejercicio_min=_EJERCICIO_MIN,
    ),
    "orden_compra": EntityConfig(
        name="orden_compra",
        table_name="ORDEN_COMPRA",
        ts_field="FECH_OC",
        # Re-process OCs with estado N from recent days to detect N→A transitions.
        pending_state_field="ESTADO_OC",
        pending_state_value="N",
        pending_reprocess_days=30,
        ejercicio_min=_EJERCICIO_MIN,
    ),
    "oc_items": EntityConfig(
        name="oc_items",
        table_name="OC_ITEMS",
        full_load=True,  # no date/timestamp column in table
        ejercicio_min=_EJERCICIO_MIN,
    ),
    "solic_gastos": EntityConfig(
        name="solic_gastos",
        table_name="SOLIC_GASTOS",
        ts_field="FECH_SOLIC",
        # Re-process confirmed gastos from recent days to catch those
        # whose linked OC was sent after the gasto was first processed.
        pending_state_field="ESTADO_SOLIC",
        pending_state_value="C",
        pending_reprocess_days=30,
        ejercicio_min=_EJERCICIO_MIN,
    ),
    "orden_pago": EntityConfig(
        name="orden_pago",
        table_name="ORDEN_PAGO",
        ts_field="FECH_CONFIRM",
        # Re-process confirmed payments from recent days in case their linked OC
        # o gastos recien se migraron despues del primer intento.
        # OJO: el valor DEBE ser "C". _build_orden_pago_statement ANDea un filtro
        # base ESTADO_OP='C'; con "N" la clausula pending era siempre falsa y la
        # ventana de reproceso nunca se aplicaba (las OP salteadas se perdian al
        # avanzar el watermark).
        pending_state_field="ESTADO_OP",
        pending_state_value="C",
        pending_reprocess_days=30,
        ejercicio_min=_EJERCICIO_MIN,
    ),
    # Retenciones: escanea las MISMAS OP que orden_pago (build_statement
    # delega en _build_orden_pago_statement) y trae las deducciones por OP via
    # fetch_deducciones_for_ops. Tiene su propio checkpoint (keyed por nombre)
    # para no pisar el de orden_pago. Corre al final del pipeline porque
    # depende de que la OP (Egreso) ya exista en Paxapos.
    "retenciones": EntityConfig(
        name="retenciones",
        table_name="ORDEN_PAGO",
        ts_field="FECH_CONFIRM",
        # Mismo criterio que orden_pago: "C" (el filtro base exige ESTADO_OP='C').
        pending_state_field="ESTADO_OP",
        pending_state_value="C",
        pending_reprocess_days=30,
        ejercicio_min=_EJERCICIO_MIN,
    ),
    # Clasificador por objeto del gasto: la jerarquia de 4 niveles vive
    # desnormalizada en GASTOS (no hay tabla maestra). Se escanea DISTINCT de
    # (INCISO, PAR_PRIN, PAR_PARC, PAR_SUBP, DENOMINACION) — ver
    # SourceRepository._build_clasificaciones_statement. Sin filtro de
    # ejercicio: es un catalogo atemporal. NO corre en el run por defecto
    # (main.py: solo proveedores + oc_items); se invoca con --entity clasificaciones.
    "clasificaciones": EntityConfig(
        name="clasificaciones",
        table_name="GASTOS",
        full_load=True,
    ),
}

# Entidades sujetas al filtro RAFAM_EJERCICIO_MIN (todas menos proveedores, que
# no tiene columna de ejercicio). Se mantiene en sync con los EntityConfig de
# arriba que reciben ejercicio_min=_EJERCICIO_MIN.
_EJERCICIO_MIN_ENTITIES = frozenset(
    {
        "pedidos",
        "ped_items",
        "orden_compra",
        "oc_items",
        "solic_gastos",
        "orden_pago",
        "retenciones",
    }
)

# ─── Proveedores excluidos de la migracion ──────────────────────────────────
# COD_PROV de RAFAM que NO deben exportarse ni migrarse a Paxapos. Son cuentas
# tecnicas / de servicios publicos / caja chica / organismos que no representan
# proveedores reales en el sistema Paxapos (telefonia, gas, luz, cajas chicas,
# organismos, indigentes, costas judiciales, etc.).
#
# El filtro se aplica en 3 puntos para garantizar exclusion total:
#   1. gateway_mapper.map_proveedor_migrator_row  -> el Proveedor no se crea/actualiza
#   2. mappers/oc_items                            -> sus OC no se migran
#   3. mappers/orden_pago                          -> sus OP (Egresos) no se migran
#
# Se puede EXTENDER (nunca reemplazar) via env RAFAM_EXCLUDED_COD_PROV con una
# lista separada por comas (ej: "50001,50002,51234").
_EXCLUDED_COD_PROV_DEFAULT: frozenset[int] = frozenset(
    {
        50001,  # Telefonica Argentina
        50002,  # Telefonica Moviles Argentina S.A.
        50003,  # Viatico
        50012,  # Caja Chica Compras
        50014,  # Caja Chica Contaduria
        50015,  # Caja Chica Accion Social
        50020,  # Caja Chica Cultura
        50023,  # Camuzzi Gas Pampeana
        50031,  # Indigentes
        50036,  # Telecom
        50072,  # Costas Judiciales
        50087,  # Banco Provincia
        50154,  # Asistencia Social al Personal
        50209,  # Grupo Teatral "Producciones Independientes"
        50219,  # Asociacion Civil Comedor Escolar Gral. Madariaga
        50256,  # Uni-Co
        50280,  # Caja Chica Direccion Administrativa Hospital
        50283,  # Caja Chica Delegacion
        50363,  # Caja Chica Escuela Bellas Artes
        50410,  # Registro de la Propiedad Inmueble
        50431,  # Provida Madariaga
        50448,  # Caja Chica Deportes
        50449,  # Caja Chica Seguridad
        50925,  # Edea
        50929,  # Dattatec.com SRL
        51021,  # Gustavo Montarce
        51044,  # Ministerio de las Mujeres, Politicas de Genero y Diversidad Sexual
        51096,  # Camara de Grabadores de Aut. de Vehiculos Automotores
    }
)


def _parse_excluded_cod_prov_env() -> frozenset[int]:
    """Lee COD_PROV extra a excluir desde RAFAM_EXCLUDED_COD_PROV (CSV)."""
    raw = os.getenv("RAFAM_EXCLUDED_COD_PROV", "")
    extra: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            extra.add(int(token))
        except ValueError:
            continue
    return frozenset(extra)


EXCLUDED_COD_PROV: frozenset[int] = _EXCLUDED_COD_PROV_DEFAULT | _parse_excluded_cod_prov_env()


def is_cod_prov_excluded(cod_prov: object) -> bool:
    """True si el COD_PROV esta en la blocklist de proveedores no migrables.

    Acepta int, str o None (tolerante a valores crudos de RAFAM). Cualquier
    valor no convertible a int se considera NO excluido.
    """
    if cod_prov is None:
        return False
    try:
        return int(str(cod_prov).strip()) in EXCLUDED_COD_PROV
    except (ValueError, TypeError):
        return False
