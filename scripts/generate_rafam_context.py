#!/usr/bin/env python3
"""Generate a RAFAM source-of-truth Markdown report from the real source DB."""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.config import ENTITY_CONFIGS  # noqa: E402

DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "rafam_context"
DEFAULT_SCHEMA = "OWNER_RAFAM"
DECIMAL_10_2_MAX = 99_999_999.99

# Tablas estrictamente relevantes para el circuito RAFAM -> Paxapos.
# Se incluyen REG_COMP, RG_COMP y CTA_COMPROB porque la corrida real debe
# resolver con evidencia cual es registro/puente y cual contiene comprobantes.
CORE_TABLES = [
    "JURISDICCIONES",
    "PROVEEDORES",
    "PEDIDOS",
    "PED_ITEMS",
    "SOLIC_GASTOS",
    "ORDEN_COMPRA",
    "OC_ITEMS",
    "ORDEN_PAGO",
    "REG_COMP",
    "RG_COMP",
    "CTA_COMPROB",
    "CTA_HOJA_DE_RUTA",
    "RETENCIONES",
    "DEDUCCIONES",
]

REG_COMP_FOCUS_TABLES = ["REG_COMP", "RG_COMP", "CTA_COMPROB"]

DATE_COLUMNS = {
    "PROVEEDORES": ["FECHA_ULT_COMP", "FECHA_ALTA"],
    "PEDIDOS": ["FECH_EMI", "FECH_MODI_ULT"],
    "SOLIC_GASTOS": ["FECH_SOLIC", "FECH_CONFIRM", "FECH_ANUL"],
    "ORDEN_COMPRA": ["FECH_OC", "FECH_CONFIRM", "FECH_ANUL"],
    "ORDEN_PAGO": ["FECH_OP", "FECH_CONFIRM", "FECH_ANUL"],
    "REG_COMP": ["FECH_REG_COMP", "FECH_CONFIRM", "FECH_ANUL"],
    "CTA_COMPROB": ["FECH_COMPROB", "FECH_MOVIM", "FECH_VENCIM"],
    "CTA_HOJA_DE_RUTA": ["OP_FECH", "SG_FECH", "PE_FECH"],
    "RETENCIONES": ["FECH_RETEN"],
    "DEDUCCIONES": ["FECH_DEDUC"],
    "RG_COMP": ["FECH_COMP", "FECH_REG_COMP"],
}

DOMAIN_FIELDS = [
    ("ORDEN_COMPRA", "ESTADO_OC"),
    ("SOLIC_GASTOS", "ESTADO_SOLIC"),
    ("ORDEN_PAGO", "ESTADO_OP"),
    ("PROVEEDORES", "TIPO_DOC"),
    ("PROVEEDORES", "COD_IVA"),
    ("PROVEEDORES", "COD_ESTADO"),
    ("ORDEN_COMPRA", "CONFIRMADO"),
    ("SOLIC_GASTOS", "CONFIRMADO"),
    ("ORDEN_PAGO", "CONFIRMADO"),
    ("PED_ITEMS", "UNI_MED"),
    ("OC_ITEMS", "UNI_MED"),
    ("REG_COMP", "TIPO_REGIS"),
    ("REG_COMP", "ESTADO_REG_COMP"),
    ("CTA_COMPROB", "TIPO"),
    ("RETENCIONES", "COD_RET"),
    ("JURISDICCIONES", "JURISDICCION"),
]

CRITICAL_FIELDS = {
    "PROVEEDORES": ["COD_PROV", "RAZON_SOCIAL", "CUIT", "COD_ESTADO", "FECHA_ULT_COMP"],
    "PEDIDOS": ["EJERCICIO", "NUM_PED", "FECH_EMI", "JURISDICCION", "COSTO_TOT"],
    "PED_ITEMS": ["EJERCICIO", "NUM_PED", "ORDEN", "CANTIDAD", "UNI_MED", "DESCRIP_BIE", "COSTO_UNI"],
    "SOLIC_GASTOS": [
        "EJERCICIO",
        "DELEG_SOLIC",
        "NRO_SOLIC",
        "NRO_PED",
        "JURISDICCION",
        "FECH_SOLIC",
        "IMPORTE_TOT",
        "ESTADO_SOLIC",
    ],
    "ORDEN_COMPRA": ["EJERCICIO", "UNI_COMPRA", "NRO_OC", "FECH_OC", "COD_PROV", "ESTADO_OC", "IMPORTE_TOT"],
    "OC_ITEMS": [
        "EJERCICIO",
        "UNI_COMPRA",
        "NRO_OC",
        "ITEM_OC",
        "DELEG_SOLIC",
        "NRO_SOLIC",
        "CANTIDAD",
        "IMP_UNITARIO",
    ],
    "ORDEN_PAGO": [
        "EJERCICIO",
        "NRO_OP",
        "FECH_OP",
        "NRO_CANCE",
        "RECO_DEU_COMPRA",
        "RECO_DEU_COMPRA_EJER",
        "COD_PROV",
        "ESTADO_OP",
        "IMPORTE_TOTAL",
    ],
    "REG_COMP": [
        "EJERCICIO",
        "NRO_REG_COMP",
        "FECH_REG_COMP",
        "UNI_COMPRA",
        "NRO_OC",
        "DELEG_SOLIC",
        "NRO_SOLIC",
        "TIPO_DOC",
        "NRO_DOC",
        "COD_PROV",
        "IMPORTE_TOT",
        "ESTADO_REG_COMP",
    ],
    "CTA_COMPROB": [
        "EJERCICIO",
        "TIPO",
        "NRO_COMPROB",
        "COD_PROV",
        "COD_PROV_REAL",
        "NRO_REG_COMP",
        "FECH_COMPROB",
        "FECH_VENCIM",
        "IMPORTE_COMPR",
        "IMPORTE_PAGADO",
    ],
}

NUMERIC_FIELDS = [
    ("SOLIC_GASTOS", "IMPORTE_TOT"),
    ("ORDEN_COMPRA", "IMPORTE_TOT"),
    ("ORDEN_PAGO", "IMPORTE_TOTAL"),
    ("ORDEN_PAGO", "IMPORTE_LIQUIDO"),
    ("PEDIDOS", "COSTO_TOT"),
    ("PED_ITEMS", "COSTO_UNI"),
    ("OC_ITEMS", "IMP_UNITARIO"),
    ("REG_COMP", "IMPORTE_TOT"),
    ("CTA_COMPROB", "IMPORTE_COMPR"),
    ("CTA_COMPROB", "IMPORTE_PAGADO"),
]

@dataclass(frozen=True)
class RelationSpec:
    name: str
    description: str
    left_table: str
    right_table: str
    left_key_expr: str
    right_key_expr: str
    join_condition: str
    right_present_expr: str
    expected: str
    required_columns: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class OpResolutionSpec:
    name: str
    description: str
    from_clause: str
    right_key_expr: str
    right_present_expr: str
    required_columns: tuple[tuple[str, str], ...]


REG_COMP_RELATIONS = [
    RelationSpec(
        name="reg_comp_to_cta_comprob",
        description="Candidato de join REG_COMP -> CTA_COMPROB por EJERCICIO + NRO_REG_COMP.",
        left_table="REG_COMP",
        right_table="CTA_COMPROB",
        left_key_expr="l.EJERCICIO || '-' || l.NRO_REG_COMP",
        right_key_expr="r.EJERCICIO || '-' || r.TIPO || '-' || r.NRO_COMPROB || '-' || r.COD_PROV",
        join_condition="l.EJERCICIO = r.EJERCICIO AND l.NRO_REG_COMP = r.NRO_REG_COMP",
        right_present_expr="r.NRO_REG_COMP",
        expected="1:N",
        required_columns=(
            ("REG_COMP", "EJERCICIO"),
            ("REG_COMP", "NRO_REG_COMP"),
            ("CTA_COMPROB", "EJERCICIO"),
            ("CTA_COMPROB", "NRO_REG_COMP"),
            ("CTA_COMPROB", "TIPO"),
            ("CTA_COMPROB", "NRO_COMPROB"),
            ("CTA_COMPROB", "COD_PROV"),
        ),
    ),
    RelationSpec(
        name="reg_comp_to_orden_compra",
        description="Candidato de join REG_COMP -> ORDEN_COMPRA por EJERCICIO + UNI_COMPRA + NRO_OC.",
        left_table="REG_COMP",
        right_table="ORDEN_COMPRA",
        left_key_expr="l.EJERCICIO || '-' || l.NRO_REG_COMP",
        right_key_expr="r.EJERCICIO || '-' || r.UNI_COMPRA || '-' || r.NRO_OC",
        join_condition="l.EJERCICIO = r.EJERCICIO AND l.UNI_COMPRA = r.UNI_COMPRA AND l.NRO_OC = r.NRO_OC",
        right_present_expr="r.EJERCICIO",
        expected="N:1",
        required_columns=(
            ("REG_COMP", "EJERCICIO"),
            ("REG_COMP", "NRO_REG_COMP"),
            ("REG_COMP", "UNI_COMPRA"),
            ("REG_COMP", "NRO_OC"),
            ("ORDEN_COMPRA", "EJERCICIO"),
            ("ORDEN_COMPRA", "UNI_COMPRA"),
            ("ORDEN_COMPRA", "NRO_OC"),
        ),
    ),
    RelationSpec(
        name="rg_comp_to_cta_comprob",
        description="Candidato de join RG_COMP -> CTA_COMPROB por EJERCICIO + NRO_REG_COMP.",
        left_table="RG_COMP",
        right_table="CTA_COMPROB",
        left_key_expr="l.EJERCICIO || '-' || l.NRO_REG_COMP",
        right_key_expr="r.EJERCICIO || '-' || r.TIPO || '-' || r.NRO_COMPROB || '-' || r.COD_PROV",
        join_condition="l.EJERCICIO = r.EJERCICIO AND l.NRO_REG_COMP = r.NRO_REG_COMP",
        right_present_expr="r.NRO_REG_COMP",
        expected="1:N candidato",
        required_columns=(
            ("RG_COMP", "EJERCICIO"),
            ("RG_COMP", "NRO_REG_COMP"),
            ("CTA_COMPROB", "EJERCICIO"),
            ("CTA_COMPROB", "NRO_REG_COMP"),
            ("CTA_COMPROB", "TIPO"),
            ("CTA_COMPROB", "NRO_COMPROB"),
            ("CTA_COMPROB", "COD_PROV"),
        ),
    ),
    RelationSpec(
        name="rg_comp_to_orden_compra_by_nro_oc",
        description="Candidato RG_COMP -> ORDEN_COMPRA sin UNI_COMPRA; mide si NRO_OC solo es ambiguo.",
        left_table="RG_COMP",
        right_table="ORDEN_COMPRA",
        left_key_expr="l.EJERCICIO || '-' || l.NRO_REG_COMP",
        right_key_expr="r.EJERCICIO || '-' || r.UNI_COMPRA || '-' || r.NRO_OC",
        join_condition="l.EJERCICIO = r.EJERCICIO AND l.NRO_OC = r.NRO_OC",
        right_present_expr="r.EJERCICIO",
        expected="candidato ambiguo",
        required_columns=(
            ("RG_COMP", "EJERCICIO"),
            ("RG_COMP", "NRO_REG_COMP"),
            ("RG_COMP", "NRO_OC"),
            ("ORDEN_COMPRA", "EJERCICIO"),
            ("ORDEN_COMPRA", "UNI_COMPRA"),
            ("ORDEN_COMPRA", "NRO_OC"),
        ),
    ),
]


RELATIONS = [
    RelationSpec(
        name="pedidos_to_ped_items",
        description="Pedido interno RAFAM con sus items.",
        left_table="PEDIDOS",
        right_table="PED_ITEMS",
        left_key_expr="l.EJERCICIO || '-' || l.NUM_PED",
        right_key_expr="r.EJERCICIO || '-' || r.NUM_PED || '-' || r.ORDEN",
        join_condition="l.EJERCICIO = r.EJERCICIO AND l.NUM_PED = r.NUM_PED",
        right_present_expr="r.EJERCICIO",
        expected="1:N",
        required_columns=(
            ("PEDIDOS", "EJERCICIO"),
            ("PEDIDOS", "NUM_PED"),
            ("PED_ITEMS", "EJERCICIO"),
            ("PED_ITEMS", "NUM_PED"),
            ("PED_ITEMS", "ORDEN"),
        ),
    ),
    RelationSpec(
        name="pedidos_to_solic_gastos",
        description="Solicitud de gasto originada por pedido interno.",
        left_table="PEDIDOS",
        right_table="SOLIC_GASTOS",
        left_key_expr="l.EJERCICIO || '-' || l.NUM_PED",
        right_key_expr="r.EJERCICIO || '-' || r.DELEG_SOLIC || '-' || r.NRO_SOLIC",
        join_condition="l.EJERCICIO = r.EJERCICIO AND l.NUM_PED = r.NRO_PED",
        right_present_expr="r.EJERCICIO",
        expected="1:N",
        required_columns=(
            ("PEDIDOS", "EJERCICIO"),
            ("PEDIDOS", "NUM_PED"),
            ("SOLIC_GASTOS", "EJERCICIO"),
            ("SOLIC_GASTOS", "NRO_PED"),
            ("SOLIC_GASTOS", "DELEG_SOLIC"),
            ("SOLIC_GASTOS", "NRO_SOLIC"),
        ),
    ),
    RelationSpec(
        name="solic_gastos_to_oc_items",
        description="Solicitud de gasto vinculada a items de orden de compra.",
        left_table="SOLIC_GASTOS",
        right_table="OC_ITEMS",
        left_key_expr="l.EJERCICIO || '-' || l.DELEG_SOLIC || '-' || l.NRO_SOLIC",
        right_key_expr="r.EJERCICIO || '-' || r.UNI_COMPRA || '-' || r.NRO_OC || '-' || r.ITEM_OC",
        join_condition=(
            "l.EJERCICIO = r.EJERCICIO AND l.DELEG_SOLIC = r.DELEG_SOLIC "
            "AND l.NRO_SOLIC = r.NRO_SOLIC"
        ),
        right_present_expr="r.EJERCICIO",
        expected="1:N",
        required_columns=(
            ("SOLIC_GASTOS", "EJERCICIO"),
            ("SOLIC_GASTOS", "DELEG_SOLIC"),
            ("SOLIC_GASTOS", "NRO_SOLIC"),
            ("OC_ITEMS", "EJERCICIO"),
            ("OC_ITEMS", "DELEG_SOLIC"),
            ("OC_ITEMS", "NRO_SOLIC"),
            ("OC_ITEMS", "UNI_COMPRA"),
            ("OC_ITEMS", "NRO_OC"),
            ("OC_ITEMS", "ITEM_OC"),
        ),
    ),
    RelationSpec(
        name="oc_items_to_orden_compra",
        description="Item de OC con su cabecera de orden de compra.",
        left_table="OC_ITEMS",
        right_table="ORDEN_COMPRA",
        left_key_expr="l.EJERCICIO || '-' || l.UNI_COMPRA || '-' || l.NRO_OC || '-' || l.ITEM_OC",
        right_key_expr="r.EJERCICIO || '-' || r.UNI_COMPRA || '-' || r.NRO_OC",
        join_condition=(
            "l.EJERCICIO = r.EJERCICIO AND l.UNI_COMPRA = r.UNI_COMPRA "
            "AND l.NRO_OC = r.NRO_OC"
        ),
        right_present_expr="r.EJERCICIO",
        expected="N:1",
        required_columns=(
            ("OC_ITEMS", "EJERCICIO"),
            ("OC_ITEMS", "UNI_COMPRA"),
            ("OC_ITEMS", "NRO_OC"),
            ("OC_ITEMS", "ITEM_OC"),
            ("ORDEN_COMPRA", "EJERCICIO"),
            ("ORDEN_COMPRA", "UNI_COMPRA"),
            ("ORDEN_COMPRA", "NRO_OC"),
        ),
    ),
]

OP_RESOLUTION_SPECS = [
    OpResolutionSpec(
        name="nro_cance_to_solic_gastos",
        description="ORDEN_PAGO.NRO_CANCE contra SOLIC_GASTOS.NRO_SOLIC en el mismo ejercicio.",
        from_clause=(
            "{op} op LEFT JOIN {sg} sg ON op.EJERCICIO = sg.EJERCICIO "
            "AND op.NRO_CANCE = sg.NRO_SOLIC"
        ),
        right_key_expr="sg.EJERCICIO || '-' || sg.DELEG_SOLIC || '-' || sg.NRO_SOLIC",
        right_present_expr="sg.EJERCICIO",
        required_columns=(
            ("ORDEN_PAGO", "EJERCICIO"),
            ("ORDEN_PAGO", "NRO_OP"),
            ("ORDEN_PAGO", "NRO_CANCE"),
            ("SOLIC_GASTOS", "EJERCICIO"),
            ("SOLIC_GASTOS", "NRO_SOLIC"),
            ("SOLIC_GASTOS", "DELEG_SOLIC"),
        ),
    ),
    OpResolutionSpec(
        name="reco_deu_compra_to_orden_compra",
        description="ORDEN_PAGO.RECO_DEU_COMPRA contra ORDEN_COMPRA.NRO_OC, midiendo ambiguedad de UNI_COMPRA.",
        from_clause=(
            "{op} op LEFT JOIN {oc} oc ON COALESCE(op.RECO_DEU_COMPRA_EJER, op.EJERCICIO) = oc.EJERCICIO "
            "AND op.RECO_DEU_COMPRA = oc.NRO_OC"
        ),
        right_key_expr="oc.EJERCICIO || '-' || oc.UNI_COMPRA || '-' || oc.NRO_OC",
        right_present_expr="oc.EJERCICIO",
        required_columns=(
            ("ORDEN_PAGO", "EJERCICIO"),
            ("ORDEN_PAGO", "NRO_OP"),
            ("ORDEN_PAGO", "RECO_DEU_COMPRA"),
            ("ORDEN_PAGO", "RECO_DEU_COMPRA_EJER"),
            ("ORDEN_COMPRA", "EJERCICIO"),
            ("ORDEN_COMPRA", "UNI_COMPRA"),
            ("ORDEN_COMPRA", "NRO_OC"),
        ),
    ),
    OpResolutionSpec(
        name="reco_deu_compra_to_solic_gastos",
        description="RECO_DEU_COMPRA -> ORDEN_COMPRA -> OC_ITEMS -> SOLIC_GASTOS.",
        from_clause=(
            "{op} op LEFT JOIN {oc} oc ON COALESCE(op.RECO_DEU_COMPRA_EJER, op.EJERCICIO) = oc.EJERCICIO "
            "AND op.RECO_DEU_COMPRA = oc.NRO_OC "
            "LEFT JOIN {oi} oi ON oc.EJERCICIO = oi.EJERCICIO AND oc.UNI_COMPRA = oi.UNI_COMPRA "
            "AND oc.NRO_OC = oi.NRO_OC "
            "LEFT JOIN {sg} sg ON oi.EJERCICIO = sg.EJERCICIO AND oi.DELEG_SOLIC = sg.DELEG_SOLIC "
            "AND oi.NRO_SOLIC = sg.NRO_SOLIC"
        ),
        right_key_expr="sg.EJERCICIO || '-' || sg.DELEG_SOLIC || '-' || sg.NRO_SOLIC",
        right_present_expr="sg.EJERCICIO",
        required_columns=(
            ("ORDEN_PAGO", "EJERCICIO"),
            ("ORDEN_PAGO", "NRO_OP"),
            ("ORDEN_PAGO", "RECO_DEU_COMPRA"),
            ("ORDEN_PAGO", "RECO_DEU_COMPRA_EJER"),
            ("ORDEN_COMPRA", "EJERCICIO"),
            ("ORDEN_COMPRA", "UNI_COMPRA"),
            ("ORDEN_COMPRA", "NRO_OC"),
            ("OC_ITEMS", "EJERCICIO"),
            ("OC_ITEMS", "UNI_COMPRA"),
            ("OC_ITEMS", "NRO_OC"),
            ("OC_ITEMS", "DELEG_SOLIC"),
            ("OC_ITEMS", "NRO_SOLIC"),
            ("SOLIC_GASTOS", "EJERCICIO"),
            ("SOLIC_GASTOS", "DELEG_SOLIC"),
            ("SOLIC_GASTOS", "NRO_SOLIC"),
        ),
    ),
    OpResolutionSpec(
        name="cta_hoja_ruta_by_nro_cance",
        description="ORDEN_PAGO.NRO_CANCE contra CTA_HOJA_DE_RUTA.SG_NRO.",
        from_clause=(
            "{op} op LEFT JOIN {hdr} hdr ON op.EJERCICIO = hdr.SG_EJERCICIO "
            "AND op.NRO_CANCE = hdr.SG_NRO"
        ),
        right_key_expr="hdr.SG_EJERCICIO || '-' || hdr.SG_DELEG_SOLIC || '-' || hdr.SG_NRO",
        right_present_expr="hdr.SG_NRO",
        required_columns=(
            ("ORDEN_PAGO", "EJERCICIO"),
            ("ORDEN_PAGO", "NRO_OP"),
            ("ORDEN_PAGO", "NRO_CANCE"),
            ("CTA_HOJA_DE_RUTA", "SG_EJERCICIO"),
            ("CTA_HOJA_DE_RUTA", "SG_NRO"),
            ("CTA_HOJA_DE_RUTA", "SG_DELEG_SOLIC"),
        ),
    ),
    OpResolutionSpec(
        name="cta_hoja_ruta_by_op_nro",
        description="ORDEN_PAGO.EJERCICIO + NRO_OP contra CTA_HOJA_DE_RUTA.OP_EJERCICIO + OP_NRO.",
        from_clause="{op} op LEFT JOIN {hdr} hdr ON op.EJERCICIO = hdr.OP_EJERCICIO AND op.NRO_OP = hdr.OP_NRO",
        right_key_expr="hdr.SG_EJERCICIO || '-' || hdr.SG_DELEG_SOLIC || '-' || hdr.SG_NRO",
        right_present_expr="hdr.OP_NRO",
        required_columns=(
            ("ORDEN_PAGO", "EJERCICIO"),
            ("ORDEN_PAGO", "NRO_OP"),
            ("CTA_HOJA_DE_RUTA", "OP_EJERCICIO"),
            ("CTA_HOJA_DE_RUTA", "OP_NRO"),
            ("CTA_HOJA_DE_RUTA", "SG_EJERCICIO"),
            ("CTA_HOJA_DE_RUTA", "SG_NRO"),
            ("CTA_HOJA_DE_RUTA", "SG_DELEG_SOLIC"),
        ),
    ),
]


class RafamContextCollector:
    def __init__(
        self,
        conn,
        backend: str,
        schema: str,
        years: int | None,
        sample_limit: int,
        progress: bool = False,
        skip_completeness: bool = False,
    ):
        self.conn = conn
        self.backend = backend
        self.schema = schema
        self.years = years
        self.sample_limit = sample_limit
        self.progress = progress
        self.skip_completeness = skip_completeness
        self.period_start_year = datetime.now().year - years + 1 if years else None
        self.columns_by_table: dict[str, list[dict[str, Any]]] = {}
        self.constraints_by_table: dict[str, dict[str, Any]] = {}

    def collect(self) -> dict[str, Any]:
        self.log_progress("leyendo columnas core")
        self.columns_by_table = self.collect_columns()
        self.log_progress("leyendo constraints")
        self.constraints_by_table = self.collect_constraints()
        self.log_progress("perfilando tablas")
        table_profiles = self.collect_table_profiles()
        self.log_progress("resumiendo modelo")
        schema_summary = self.collect_schema_summary()
        self.log_progress("midiendo relaciones RAFAM")
        relations = self.collect_relations()
        self.log_progress("comparando estrategias OP-SG-OC")
        op_resolution = self.collect_op_resolution()
        self.log_progress("analizando REG_COMP/RG_COMP/CTA_COMPROB")
        reg_comp_analysis = self.collect_reg_comp_analysis()
        self.log_progress("leyendo dominios")
        domains = self.collect_domains()
        if self.skip_completeness:
            self.log_progress("saltando completitud por --skip-completeness")
            completeness = []
        else:
            self.log_progress("midiendo completitud por tabla")
            completeness = self.collect_completeness()
        self.log_progress("midiendo calidad numerica")
        numeric_quality = self.collect_numeric_quality()
        self.log_progress("tomando muestras de borde")
        edge_samples = self.collect_edge_samples()
        return {
            "metadata": self.collect_metadata(),
            "entity_contracts": self.collect_entity_contracts(),
            "table_profiles": table_profiles,
            "schema": schema_summary,
            "relations": relations,
            "op_resolution": op_resolution,
            "reg_comp_analysis": reg_comp_analysis,
            "domains": domains,
            "completeness": completeness,
            "numeric_quality": numeric_quality,
            "edge_samples": edge_samples,
        }

    def log_progress(self, message: str) -> None:
        if self.progress:
            print(f"[rafam-context] {message}", file=sys.stderr, flush=True)

    def collect_metadata(self) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "backend": self.backend,
            "schema": self.schema if self.backend == "oracle" else "sqlite",
            "period": "all_years" if self.period_start_year is None else f"ejercicio >= {self.period_start_year}",
            "sample_limit": self.sample_limit,
            "script_commit": git_commit(),
        }

    def collect_entity_contracts(self) -> list[dict[str, Any]]:
        rows = []
        for entity, cfg in ENTITY_CONFIGS.items():
            rows.append(
                {
                    "entity": entity,
                    "table": cfg.table_name,
                    "id_field": cfg.id_field or "",
                    "ts_field": cfg.ts_field or "",
                    "full_load": cfg.full_load,
                    "pending_state_field": cfg.pending_state_field or "",
                    "pending_state_value": cfg.pending_state_value or "",
                    "pending_reprocess_days": cfg.pending_reprocess_days or "",
                }
            )
        return rows

    def collect_columns(self) -> dict[str, list[dict[str, Any]]]:
        if self.backend == "oracle":
            return {table: self._oracle_columns(table) for table in CORE_TABLES}
        return {table: self._sqlite_columns(table) for table in CORE_TABLES}

    def collect_constraints(self) -> dict[str, dict[str, Any]]:
        if self.backend == "oracle":
            return {table: self._oracle_constraints(table) for table in CORE_TABLES if self.has_table(table)}
        return {table: {"pk": self._sqlite_pk(table), "fk": []} for table in CORE_TABLES if self.has_table(table)}

    def collect_table_profiles(self) -> list[dict[str, Any]]:
        rows = []
        for table in CORE_TABLES:
            if not self.has_table(table):
                rows.append({"table": table, "exists": False})
                continue
            total_rows = self.scalar(f"SELECT COUNT(*) FROM {self.table_ref(table)}")
            period_rows = ""
            if self.period_start_year and self.has_column(table, "EJERCICIO"):
                period_rows = self.scalar(
                    f"SELECT COUNT(*) FROM {self.table_ref(table)} WHERE EJERCICIO >= :year",
                    {"year": self.period_start_year},
                )
            rows.append(
                {
                    "table": table,
                    "exists": True,
                    "columns": len(self.columns_by_table.get(table, [])),
                    "total_rows": int_or_blank(total_rows),
                    "period_rows": int_or_blank(period_rows),
                    "date_ranges": self.date_ranges(table),
                }
            )
        return rows

    def collect_schema_summary(self) -> dict[str, Any]:
        tables = []
        for table in CORE_TABLES:
            if not self.has_table(table):
                continue
            constraints = self.constraints_by_table.get(table, {"pk": [], "fk": []})
            tables.append(
                {
                    "table": table,
                    "pk": ", ".join(constraints.get("pk", [])),
                    "fk_count": len(constraints.get("fk", [])),
                    "fks": constraints.get("fk", []),
                    "columns": self.columns_by_table.get(table, []),
                }
            )
        return {"tables": tables}

    def collect_relations(self) -> list[dict[str, Any]]:
        metrics = []
        for spec in RELATIONS:
            if not self.require_columns(spec.required_columns):
                metrics.append(self.skipped_metric(spec.name, spec.description, "faltan columnas o tablas"))
                continue
            metrics.append(self.measure_relation(spec))
        return metrics

    def collect_op_resolution(self) -> list[dict[str, Any]]:
        metrics = []
        for spec in OP_RESOLUTION_SPECS:
            if not self.require_columns(spec.required_columns):
                metrics.append(self.skipped_metric(spec.name, spec.description, "faltan columnas o tablas"))
                continue
            metrics.append(self.measure_op_resolution(spec))
        return metrics

    def collect_reg_comp_analysis(self) -> dict[str, Any]:
        table_signals = [self.reg_comp_table_signal(table) for table in REG_COMP_FOCUS_TABLES]
        relation_metrics = []
        for spec in REG_COMP_RELATIONS:
            if not self.require_columns(spec.required_columns):
                relation_metrics.append(self.skipped_metric(spec.name, spec.description, "faltan columnas o tablas"))
                continue
            relation_metrics.append(self.measure_relation(spec))
        return {
            "summary": self.reg_comp_summary(table_signals, relation_metrics),
            "table_signals": table_signals,
            "relation_metrics": relation_metrics,
            "samples": self.collect_reg_comp_samples(),
        }

    def reg_comp_table_signal(self, table: str) -> dict[str, Any]:
        columns = {row.get("name") for row in self.columns_by_table.get(table, [])}
        constraints = self.constraints_by_table.get(table, {"pk": [], "fk": []})
        signal = {
            "table": table,
            "exists": self.has_table(table),
            "pk": ", ".join(constraints.get("pk", [])),
            "has_nro_reg_comp": "NRO_REG_COMP" in columns,
            "has_nro_comprob": "NRO_COMPROB" in columns,
            "has_oc_link": "NRO_OC" in columns,
            "has_uni_compra": "UNI_COMPRA" in columns,
            "has_sg_link": {"DELEG_SOLIC", "NRO_SOLIC"}.issubset(columns),
            "doc_columns": ", ".join(col for col in ["TIPO", "NRO_COMPROB", "TIPO_DOC", "NRO_DOC"] if col in columns),
            "date_columns": ", ".join(col for col in ["FECH_COMPROB", "FECH_REG_COMP", "FECH_MOVIM", "FECH_VENCIM"] if col in columns),
            "amount_columns": ", ".join(col for col in ["IMPORTE_COMPR", "IMPORTE_TOT", "IMPORTE_PAGADO"] if col in columns),
        }
        signal["inferred_role"] = self.infer_reg_comp_role(signal)
        return signal

    @staticmethod
    def infer_reg_comp_role(signal: dict[str, Any]) -> str:
        if not signal["exists"]:
            return "ausente"
        if signal["has_nro_comprob"]:
            return "comprobante_fiscal_por_columnas"
        if signal["has_nro_reg_comp"] and (signal["has_oc_link"] or signal["has_sg_link"]):
            return "registro_o_puente_por_columnas"
        if signal["has_nro_reg_comp"]:
            return "registro_por_columnas"
        return "pendiente_validacion"

    @staticmethod
    def reg_comp_summary(table_signals: list[dict[str, Any]], relation_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        signals_by_table = {row["table"]: row for row in table_signals}
        metrics_by_name = {row["name"]: row for row in relation_metrics if row.get("status") == "measured"}
        cta_signal = signals_by_table.get("CTA_COMPROB", {})
        reg_signal = signals_by_table.get("REG_COMP", {})
        rg_signal = signals_by_table.get("RG_COMP", {})
        return [
            {
                "question": "Donde esta el numero fiscal del comprobante?",
                "evidence": "CTA_COMPROB tiene NRO_COMPROB" if cta_signal.get("has_nro_comprob") else "No se detecto NRO_COMPROB en CTA_COMPROB",
                "status": "confirmado_por_schema" if cta_signal.get("has_nro_comprob") else "pendiente_validacion",
            },
            {
                "question": "REG_COMP parece comprobante o registro?",
                "evidence": f"rol={reg_signal.get('inferred_role', 'ausente')}; doc_columns={reg_signal.get('doc_columns', '')}",
                "status": "inferido_por_schema",
            },
            {
                "question": "RG_COMP parece comprobante o registro?",
                "evidence": f"rol={rg_signal.get('inferred_role', 'ausente')}; doc_columns={rg_signal.get('doc_columns', '')}",
                "status": "inferido_por_schema",
            },
            {
                "question": "REG_COMP conecta con CTA_COMPROB?",
                "evidence": metrics_by_name.get("reg_comp_to_cta_comprob", {}).get("resolved_pct", "sin medicion"),
                "status": "medido" if "reg_comp_to_cta_comprob" in metrics_by_name else "pendiente_validacion",
            },
            {
                "question": "REG_COMP conecta con ORDEN_COMPRA?",
                "evidence": metrics_by_name.get("reg_comp_to_orden_compra", {}).get("resolved_pct", "sin medicion"),
                "status": "medido" if "reg_comp_to_orden_compra" in metrics_by_name else "pendiente_validacion",
            },
        ]

    def collect_reg_comp_samples(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "reg_comp_cta_comprob": self.sample_two_table_join(
                left_table="REG_COMP",
                left_alias="rc",
                right_table="CTA_COMPROB",
                right_alias="cc",
                join_condition="rc.EJERCICIO = cc.EJERCICIO AND rc.NRO_REG_COMP = cc.NRO_REG_COMP",
                left_columns=["EJERCICIO", "NRO_REG_COMP", "UNI_COMPRA", "NRO_OC", "DELEG_SOLIC", "NRO_SOLIC", "TIPO_DOC", "NRO_DOC", "COD_PROV", "IMPORTE_TOT"],
                right_columns=["TIPO", "NRO_COMPROB", "COD_PROV", "COD_PROV_REAL", "FECH_COMPROB", "IMPORTE_COMPR"],
            ),
            "reg_comp_orden_compra": self.sample_two_table_join(
                left_table="REG_COMP",
                left_alias="rc",
                right_table="ORDEN_COMPRA",
                right_alias="oc",
                join_condition="rc.EJERCICIO = oc.EJERCICIO AND rc.UNI_COMPRA = oc.UNI_COMPRA AND rc.NRO_OC = oc.NRO_OC",
                left_columns=["EJERCICIO", "NRO_REG_COMP", "UNI_COMPRA", "NRO_OC", "COD_PROV", "IMPORTE_TOT"],
                right_columns=["UNI_COMPRA", "NRO_OC", "COD_PROV", "FECH_OC", "IMPORTE_TOT"],
            ),
            "rg_comp_cta_comprob": self.sample_two_table_join(
                left_table="RG_COMP",
                left_alias="rg",
                right_table="CTA_COMPROB",
                right_alias="cc",
                join_condition="rg.EJERCICIO = cc.EJERCICIO AND rg.NRO_REG_COMP = cc.NRO_REG_COMP",
                left_columns=["EJERCICIO", "NRO_REG_COMP", "NRO_OC", "COD_PROV", "JURISDICCION", "FECH_REG_COMP"],
                right_columns=["TIPO", "NRO_COMPROB", "COD_PROV", "COD_PROV_REAL", "FECH_COMPROB", "IMPORTE_COMPR"],
            ),
        }

    def sample_two_table_join(
        self,
        left_table: str,
        left_alias: str,
        right_table: str,
        right_alias: str,
        join_condition: str,
        left_columns: list[str],
        right_columns: list[str],
    ) -> list[dict[str, Any]]:
        if not self.has_table(left_table) or not self.has_table(right_table):
            return []
        select_cols = []
        for column in left_columns:
            if self.has_column(left_table, column):
                select_cols.append(f"{left_alias}.{column} AS {left_alias}_{column}")
        for column in right_columns:
            if self.has_column(right_table, column):
                select_cols.append(f"{right_alias}.{column} AS {right_alias}_{column}")
        if not select_cols:
            return []
        sql = f"""
            SELECT {", ".join(select_cols)}
            FROM {self.table_ref(left_table)} {left_alias}
            JOIN {self.table_ref(right_table)} {right_alias}
              ON {join_condition}
            {self.period_where(left_alias, left_table)}
        """
        try:
            return self.fetch_dicts(self.limit_sql(sql))
        except Exception as exc:
            return [{"error": str(exc)}]

    def collect_domains(self) -> list[dict[str, Any]]:
        rows = []
        for table, column in DOMAIN_FIELDS:
            if not self.has_column(table, column):
                continue
            sql = f"""
                SELECT {column} AS value, COUNT(*) AS total
                FROM {self.table_ref(table)} t
                {self.period_where('t', table)}
                GROUP BY {column}
                ORDER BY total DESC
            """
            values = self.fetch_dicts(sql)[: self.sample_limit]
            rows.append(
                {
                    "table": table,
                    "column": column,
                    "distinct_sampled": len(values),
                    "top_values": values,
                }
            )
        return rows

    def collect_completeness(self) -> list[dict[str, Any]]:
        rows = []
        for table, columns in CRITICAL_FIELDS.items():
            if not self.has_table(table):
                continue
            available_columns = [column for column in columns if self.has_column(table, column)]
            if not available_columns:
                continue

            missing_exprs = [
                f"SUM(CASE WHEN {self.blank_expression('t', table, column)} THEN 1 ELSE 0 END) AS missing_{index}"
                for index, column in enumerate(available_columns)
            ]
            sql = f"""
                SELECT
                    COUNT(*) AS total,
                    {", ".join(missing_exprs)}
                FROM {self.table_ref(table)} t
                {self.period_where('t', table)}
            """
            data = self.fetch_one(sql)
            total = to_int(data.get("total"))
            for index, column in enumerate(available_columns):
                missing = to_int(data.get(f"missing_{index}"))
                rows.append(
                    {
                        "table": table,
                        "column": column,
                        "total": total,
                        "missing": missing,
                        "missing_pct": pct(missing, total),
                    }
                )
        return rows

    def collect_numeric_quality(self) -> list[dict[str, Any]]:
        rows = []
        for table, column in NUMERIC_FIELDS:
            if not self.has_column(table, column):
                continue
            sql = f"""
                SELECT
                    COUNT(*) AS total,
                    MIN({column}) AS min_value,
                    MAX({column}) AS max_value,
                    SUM(CASE WHEN {column} < 0 THEN 1 ELSE 0 END) AS negative_count,
                    SUM(CASE WHEN {column} = 0 THEN 1 ELSE 0 END) AS zero_count,
                    SUM(CASE WHEN {column} > :max_decimal THEN 1 ELSE 0 END) AS decimal_overflow_count
                FROM {self.table_ref(table)} t
                {self.period_where('t', table)}
            """
            data = self.fetch_one(sql, {"max_decimal": DECIMAL_10_2_MAX})
            rows.append({"table": table, "column": column, **data})
        return rows

    def collect_edge_samples(self) -> dict[str, list[dict[str, Any]]]:
        samples: dict[str, list[dict[str, Any]]] = {}
        sample_builders = [
            ("orden_pago_without_nro_cance_sg", self.sample_op_without_nro_cance_sg),
            ("reco_deu_compra_ambiguous_uni_compra", self.sample_reco_ambiguous),
            ("sg_with_multiple_oc_providers", self.sample_sg_multi_provider),
            ("op_oc_provider_mismatch", self.sample_op_oc_provider_mismatch),
            ("importe_over_decimal_10_2", self.sample_decimal_overflow),
        ]
        for name, builder in sample_builders:
            try:
                rows = builder()
            except Exception as exc:
                rows = [{"error": str(exc)}]
            samples[name] = rows
        return samples

    def measure_relation(self, spec: RelationSpec) -> dict[str, Any]:
        inner = f"""
            SELECT {spec.left_key_expr} AS source_key,
                   COUNT(DISTINCT CASE WHEN {spec.right_present_expr} IS NOT NULL THEN {spec.right_key_expr} END) AS match_count
            FROM {self.table_ref(spec.left_table)} l
            LEFT JOIN {self.table_ref(spec.right_table)} r ON {spec.join_condition}
            {self.period_where('l', spec.left_table)}
            GROUP BY {spec.left_key_expr}
        """
        return self.metric_from_inner_query(
            name=spec.name,
            description=spec.description,
            expected=spec.expected,
            inner=inner,
        )

    def measure_op_resolution(self, spec: OpResolutionSpec) -> dict[str, Any]:
        from_clause = spec.from_clause.format(
            op=self.table_ref("ORDEN_PAGO"),
            sg=self.table_ref("SOLIC_GASTOS"),
            oc=self.table_ref("ORDEN_COMPRA"),
            oi=self.table_ref("OC_ITEMS"),
            hdr=self.table_ref("CTA_HOJA_DE_RUTA"),
        )
        inner = f"""
            SELECT op.EJERCICIO || '-' || op.NRO_OP AS source_key,
                   COUNT(DISTINCT CASE WHEN {spec.right_present_expr} IS NOT NULL THEN {spec.right_key_expr} END) AS match_count
            FROM {from_clause}
            {self.period_where('op', 'ORDEN_PAGO')}
            GROUP BY op.EJERCICIO || '-' || op.NRO_OP
        """
        return self.metric_from_inner_query(
            name=spec.name,
            description=spec.description,
            expected="OP path",
            inner=inner,
        )

    def metric_from_inner_query(self, name: str, description: str, expected: str, inner: str) -> dict[str, Any]:
        sql = f"""
            SELECT
                COUNT(*) AS total_sources,
                SUM(CASE WHEN match_count > 0 THEN 1 ELSE 0 END) AS resolved_sources,
                SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END) AS unresolved_sources,
                SUM(CASE WHEN match_count > 1 THEN 1 ELSE 0 END) AS multi_match_sources,
                MAX(match_count) AS max_matches
            FROM ({inner}) m
        """
        data = self.fetch_one(sql)
        total = to_int(data.get("total_sources"))
        resolved = to_int(data.get("resolved_sources"))
        unresolved = to_int(data.get("unresolved_sources"))
        multi = to_int(data.get("multi_match_sources"))
        return {
            "name": name,
            "description": description,
            "expected": expected,
            "status": "measured",
            "total_sources": total,
            "resolved_sources": resolved,
            "unresolved_sources": unresolved,
            "multi_match_sources": multi,
            "max_matches": int_or_blank(data.get("max_matches")),
            "resolved_pct": pct(resolved, total),
            "unresolved_pct": pct(unresolved, total),
            "multi_match_pct": pct(multi, total),
            "sample_unresolved": self.sample_from_inner(inner, "match_count = 0"),
            "sample_multi_match": self.sample_from_inner(inner, "match_count > 1"),
        }

    def skipped_metric(self, name: str, description: str, reason: str) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "expected": "",
            "status": "skipped",
            "reason": reason,
        }

    def sample_from_inner(self, inner: str, where_clause: str) -> list[dict[str, Any]]:
        sql = f"SELECT source_key, match_count FROM ({inner}) s WHERE {where_clause}"
        return self.fetch_dicts(self.limit_sql(sql))

    def date_ranges(self, table: str) -> str:
        ranges = []
        for column in DATE_COLUMNS.get(table, []):
            if not self.has_column(table, column):
                continue
            sql = f"SELECT MIN({column}) AS min_value, MAX({column}) AS max_value FROM {self.table_ref(table)}"
            row = self.fetch_one(sql)
            ranges.append(f"{column}: {format_value(row.get('min_value'))}..{format_value(row.get('max_value'))}")
        return "; ".join(ranges)

    def sample_op_without_nro_cance_sg(self) -> list[dict[str, Any]]:
        required = (
            ("ORDEN_PAGO", "EJERCICIO"),
            ("ORDEN_PAGO", "NRO_OP"),
            ("ORDEN_PAGO", "NRO_CANCE"),
            ("ORDEN_PAGO", "RECO_DEU_COMPRA"),
            ("ORDEN_PAGO", "RECO_DEU_COMPRA_EJER"),
            ("SOLIC_GASTOS", "EJERCICIO"),
            ("SOLIC_GASTOS", "NRO_SOLIC"),
        )
        if not self.require_columns(required):
            return []
        sql = f"""
            SELECT op.EJERCICIO, op.NRO_OP, op.NRO_CANCE, op.RECO_DEU_COMPRA, op.RECO_DEU_COMPRA_EJER
            FROM {self.table_ref('ORDEN_PAGO')} op
            LEFT JOIN {self.table_ref('SOLIC_GASTOS')} sg
              ON op.EJERCICIO = sg.EJERCICIO AND op.NRO_CANCE = sg.NRO_SOLIC
            WHERE sg.EJERCICIO IS NULL
            {self.period_and('op', 'ORDEN_PAGO')}
        """
        return self.fetch_dicts(self.limit_sql(sql))

    def sample_reco_ambiguous(self) -> list[dict[str, Any]]:
        required = (
            ("ORDEN_PAGO", "EJERCICIO"),
            ("ORDEN_PAGO", "NRO_OP"),
            ("ORDEN_PAGO", "RECO_DEU_COMPRA"),
            ("ORDEN_PAGO", "RECO_DEU_COMPRA_EJER"),
            ("ORDEN_COMPRA", "EJERCICIO"),
            ("ORDEN_COMPRA", "UNI_COMPRA"),
            ("ORDEN_COMPRA", "NRO_OC"),
        )
        if not self.require_columns(required):
            return []
        sql = f"""
            SELECT op.EJERCICIO, op.NRO_OP, op.RECO_DEU_COMPRA, op.RECO_DEU_COMPRA_EJER,
                   COUNT(DISTINCT oc.UNI_COMPRA) AS uni_compra_count
            FROM {self.table_ref('ORDEN_PAGO')} op
            JOIN {self.table_ref('ORDEN_COMPRA')} oc
              ON COALESCE(op.RECO_DEU_COMPRA_EJER, op.EJERCICIO) = oc.EJERCICIO
             AND op.RECO_DEU_COMPRA = oc.NRO_OC
            {self.period_where('op', 'ORDEN_PAGO')}
            GROUP BY op.EJERCICIO, op.NRO_OP, op.RECO_DEU_COMPRA, op.RECO_DEU_COMPRA_EJER
            HAVING COUNT(DISTINCT oc.UNI_COMPRA) > 1
        """
        return self.fetch_dicts(self.limit_sql(sql))

    def sample_sg_multi_provider(self) -> list[dict[str, Any]]:
        required = (
            ("OC_ITEMS", "EJERCICIO"),
            ("OC_ITEMS", "UNI_COMPRA"),
            ("OC_ITEMS", "NRO_OC"),
            ("OC_ITEMS", "DELEG_SOLIC"),
            ("OC_ITEMS", "NRO_SOLIC"),
            ("ORDEN_COMPRA", "EJERCICIO"),
            ("ORDEN_COMPRA", "UNI_COMPRA"),
            ("ORDEN_COMPRA", "NRO_OC"),
            ("ORDEN_COMPRA", "COD_PROV"),
        )
        if not self.require_columns(required):
            return []
        sql = f"""
            SELECT oi.EJERCICIO, oi.DELEG_SOLIC, oi.NRO_SOLIC,
                   COUNT(DISTINCT oc.COD_PROV) AS provider_count
            FROM {self.table_ref('OC_ITEMS')} oi
            JOIN {self.table_ref('ORDEN_COMPRA')} oc
              ON oi.EJERCICIO = oc.EJERCICIO AND oi.UNI_COMPRA = oc.UNI_COMPRA AND oi.NRO_OC = oc.NRO_OC
            {self.period_where('oi', 'OC_ITEMS')}
            GROUP BY oi.EJERCICIO, oi.DELEG_SOLIC, oi.NRO_SOLIC
            HAVING COUNT(DISTINCT oc.COD_PROV) > 1
        """
        return self.fetch_dicts(self.limit_sql(sql))

    def sample_op_oc_provider_mismatch(self) -> list[dict[str, Any]]:
        required = (
            ("ORDEN_PAGO", "EJERCICIO"),
            ("ORDEN_PAGO", "NRO_OP"),
            ("ORDEN_PAGO", "RECO_DEU_COMPRA"),
            ("ORDEN_PAGO", "RECO_DEU_COMPRA_EJER"),
            ("ORDEN_PAGO", "COD_PROV"),
            ("ORDEN_COMPRA", "EJERCICIO"),
            ("ORDEN_COMPRA", "NRO_OC"),
            ("ORDEN_COMPRA", "COD_PROV"),
        )
        if not self.require_columns(required):
            return []
        sql = f"""
            SELECT op.EJERCICIO, op.NRO_OP, op.COD_PROV AS op_cod_prov,
                   oc.COD_PROV AS oc_cod_prov, op.RECO_DEU_COMPRA, op.RECO_DEU_COMPRA_EJER
            FROM {self.table_ref('ORDEN_PAGO')} op
            JOIN {self.table_ref('ORDEN_COMPRA')} oc
              ON COALESCE(op.RECO_DEU_COMPRA_EJER, op.EJERCICIO) = oc.EJERCICIO
             AND op.RECO_DEU_COMPRA = oc.NRO_OC
            WHERE op.COD_PROV <> oc.COD_PROV
            {self.period_and('op', 'ORDEN_PAGO')}
        """
        return self.fetch_dicts(self.limit_sql(sql))

    def sample_decimal_overflow(self) -> list[dict[str, Any]]:
        samples = []
        for table, column in NUMERIC_FIELDS:
            if not self.has_column(table, column):
                continue
            select_cols = self.sample_key_columns(table)
            sql = f"""
                SELECT {select_cols}, {column} AS overflow_value
                FROM {self.table_ref(table)} t
                WHERE {column} > :max_decimal
                {self.period_and('t', table)}
            """
            for row in self.fetch_dicts(self.limit_sql(sql), {"max_decimal": DECIMAL_10_2_MAX}):
                row["table"] = table
                row["column"] = column
                samples.append(row)
        return samples[: self.sample_limit]

    def sample_key_columns(self, table: str) -> str:
        preferred = {
            "PROVEEDORES": ["COD_PROV"],
            "PEDIDOS": ["EJERCICIO", "NUM_PED"],
            "PED_ITEMS": ["EJERCICIO", "NUM_PED", "ORDEN"],
            "SOLIC_GASTOS": ["EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC"],
            "ORDEN_COMPRA": ["EJERCICIO", "UNI_COMPRA", "NRO_OC"],
            "OC_ITEMS": ["EJERCICIO", "UNI_COMPRA", "NRO_OC", "ITEM_OC"],
            "ORDEN_PAGO": ["EJERCICIO", "NRO_OP"],
        }
        cols = [col for col in preferred.get(table, []) if self.has_column(table, col)]
        if not cols:
            cols = [col["name"] for col in self.columns_by_table.get(table, [])[:3]]
        return ", ".join(f"t.{col}" for col in cols) or "1 AS sample_key"

    def _oracle_columns(self, table: str) -> list[dict[str, Any]]:
        sql = """
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE, DATA_DEFAULT
            FROM ALL_TAB_COLUMNS
            WHERE OWNER = :owner AND TABLE_NAME = :table_name
            ORDER BY COLUMN_ID
        """
        rows = self.fetch_dicts(sql, {"owner": self.schema, "table_name": table})
        return [
            {
                "name": row.get("column_name"),
                "type": format_column_type(row),
                "nullable": row.get("nullable"),
                "default": row.get("data_default"),
            }
            for row in rows
        ]

    def _sqlite_columns(self, table: str) -> list[dict[str, Any]]:
        rows = self.fetch_dicts(f"PRAGMA table_info({table})")
        return [
            {
                "name": row.get("name"),
                "type": row.get("type") or "TEXT",
                "nullable": "N" if row.get("notnull") else "Y",
                "default": row.get("dflt_value"),
            }
            for row in rows
        ]

    def _oracle_constraints(self, table: str) -> dict[str, Any]:
        sql = """
                        SELECT c.CONSTRAINT_NAME, c.CONSTRAINT_TYPE, cc.COLUMN_NAME, cc.POSITION,
                                     rc.TABLE_NAME AS R_TABLE_NAME, rcc.COLUMN_NAME AS R_COLUMN_NAME
            FROM ALL_CONSTRAINTS c
            JOIN ALL_CONS_COLUMNS cc
              ON cc.OWNER = c.OWNER AND cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME
                        LEFT JOIN ALL_CONSTRAINTS rc
                            ON rc.OWNER = c.R_OWNER AND rc.CONSTRAINT_NAME = c.R_CONSTRAINT_NAME
                        LEFT JOIN ALL_CONS_COLUMNS rcc
                            ON rcc.OWNER = rc.OWNER
                         AND rcc.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
                         AND rcc.POSITION = cc.POSITION
            WHERE c.OWNER = :owner AND c.TABLE_NAME = :table_name AND c.CONSTRAINT_TYPE IN ('P', 'R')
            ORDER BY c.CONSTRAINT_TYPE, c.CONSTRAINT_NAME, cc.POSITION
        """
        pk = []
        fk = []
        for row in self.fetch_dicts(sql, {"owner": self.schema, "table_name": table}):
            if row.get("constraint_type") == "P":
                pk.append(row.get("column_name"))
            elif row.get("constraint_type") == "R":
                fk.append(
                    {
                        "constraint": row.get("constraint_name"),
                        "column": row.get("column_name"),
                        "references": format_fk_reference(row.get("r_table_name"), row.get("r_column_name")),
                    }
                )
        return {"pk": pk, "fk": fk}

    def _sqlite_pk(self, table: str) -> list[str]:
        rows = self.fetch_dicts(f"PRAGMA table_info({table})")
        return [row.get("name") for row in rows if row.get("pk")]

    def fetch_dicts(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(sql, params or {})
        description = cursor.description or []
        columns = [col[0].lower() for col in description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def fetch_one(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        rows = self.fetch_dicts(sql, params)
        return rows[0] if rows else {}

    def scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        cursor = self.conn.cursor()
        cursor.execute(sql, params or {})
        row = cursor.fetchone()
        return row[0] if row else None

    def table_ref(self, table: str) -> str:
        if self.backend == "oracle":
            return f"{self.schema}.{table}"
        return table

    def has_table(self, table: str) -> bool:
        return bool(self.columns_by_table.get(table))

    def has_column(self, table: str, column: str) -> bool:
        return column in {row.get("name") for row in self.columns_by_table.get(table, [])}

    def require_columns(self, required: tuple[tuple[str, str], ...]) -> bool:
        return all(self.has_column(table, column) for table, column in required)

    def period_where(self, alias: str, table: str) -> str:
        if self.period_start_year is None or not self.has_column(table, "EJERCICIO"):
            return ""
        return f"WHERE {alias}.EJERCICIO >= {self.period_start_year}"

    def period_and(self, alias: str, table: str) -> str:
        if self.period_start_year is None or not self.has_column(table, "EJERCICIO"):
            return ""
        return f"AND {alias}.EJERCICIO >= {self.period_start_year}"

    def blank_expression(self, alias: str, table: str, column: str) -> str:
        value = f"{alias}.{column}"
        if self.backend == "oracle" and not self.is_text_column(table, column):
            return f"{value} IS NULL"
        text_value = value if self.backend == "oracle" else f"CAST({value} AS TEXT)"
        return f"{value} IS NULL OR TRIM({text_value}) = ''"

    def is_text_column(self, table: str, column: str) -> bool:
        column_type = self.column_type(table, column).upper()
        return any(token in column_type for token in ("CHAR", "CLOB", "TEXT"))

    def column_type(self, table: str, column: str) -> str:
        for row in self.columns_by_table.get(table, []):
            if row.get("name") == column:
                return str(row.get("type") or "")
        return ""

    def limit_sql(self, sql: str) -> str:
        if self.backend == "oracle":
            return f"SELECT * FROM ({sql}) WHERE ROWNUM <= {self.sample_limit}"
        return f"{sql} LIMIT {self.sample_limit}"


def render_markdown(report: dict[str, Any]) -> str:
    metadata = report["metadata"]
    lines = [
        "---",
        "title: RAFAM source context",
        f"generated_at: {metadata['generated_at']}",
        f"backend: {metadata['backend']}",
        f"schema: {metadata['schema']}",
        f"period: {metadata['period']}",
        "status: generated",
        "---",
        "",
        "# RAFAM Source Context",
        "",
        "Documento autogenerado desde RAFAM para cerrar estructura, relaciones, dominios y calidad de datos usados por el sincronizador RAFAM -> Paxapos.",
        "",
        "## Metadata",
        "",
        markdown_table(
            [
                {"key": "generated_at", "value": metadata["generated_at"]},
                {"key": "backend", "value": metadata["backend"]},
                {"key": "schema", "value": metadata["schema"]},
                {"key": "period", "value": metadata["period"]},
                {"key": "sample_limit", "value": metadata["sample_limit"]},
                {"key": "script_commit", "value": metadata["script_commit"]},
            ],
            ["key", "value"],
        ),
        "",
        "## Resumen ejecutivo",
        "",
    ]
    lines.extend(render_executive_summary(report))
    lines.extend(
        [
            "",
            "## Contrato de extraccion del script",
            "",
            markdown_table(report["entity_contracts"], ["entity", "table", "id_field", "ts_field", "full_load", "pending_state_field", "pending_state_value", "pending_reprocess_days"]),
            "",
            "## Tablas core RAFAM",
            "",
            markdown_table(
                [
                    {
                        "table": row["table"],
                        "exists": row.get("exists"),
                        "columns": row.get("columns", ""),
                        "total_rows": row.get("total_rows", ""),
                        "period_rows": row.get("period_rows", ""),
                        "date_ranges": row.get("date_ranges", ""),
                    }
                    for row in report["table_profiles"]
                ],
                ["table", "exists", "columns", "total_rows", "period_rows", "date_ranges"],
            ),
            "",
            "## Modelo RAFAM canónico",
            "",
        ]
    )
    lines.extend(render_schema(report["schema"]))
    lines.extend(
        [
            "",
            "## Apartado especial REG_COMP, RG_COMP y comprobantes",
            "",
        ]
    )
    lines.extend(render_reg_comp_analysis(report.get("reg_comp_analysis", {})))
    lines.extend(
        [
            "",
            "## Joins reales medidos",
            "",
            render_metrics(report["relations"]),
            "",
            "## Resolucion OP-SG-OC",
            "",
            render_metrics(report["op_resolution"]),
            "",
            "## Dominios y catalogos RAFAM",
            "",
        ]
    )
    lines.extend(render_domains(report["domains"]))
    lines.extend(
        [
            "",
            "## Completitud de campos criticos",
            "",
            markdown_table(report["completeness"], ["table", "column", "total", "missing", "missing_pct"]),
            "",
            "## Calidad numerica",
            "",
            markdown_table(report["numeric_quality"], ["table", "column", "total", "min_value", "max_value", "negative_count", "zero_count", "decimal_overflow_count"]),
            "",
            "## Casos de borde",
            "",
        ]
    )
    lines.extend(render_edge_samples(report["edge_samples"]))
    lines.extend(
        [
            "",
            "## Decisiones y pendientes",
            "",
            markdown_table(
                decision_rows(report),
                ["topic", "status", "evidence", "next_action"],
            ),
            "",
            "## Glosario minimo",
            "",
            markdown_table(
                [
                    {"term": "SG", "meaning": "SOLIC_GASTOS, solicitud de gasto que se importa como Gasto Paxapos."},
                    {"term": "OC", "meaning": "ORDEN_COMPRA + OC_ITEMS, orden de compra y sus lineas."},
                    {"term": "OP", "meaning": "ORDEN_PAGO, pago/egreso asociado a gastos."},
                    {"term": "HDR", "meaning": "CTA_HOJA_DE_RUTA, vista RAFAM usada como puente PE-SG-OC-OP."},
                    {"term": "RECO_DEU_COMPRA", "meaning": "Campo de ORDEN_PAGO candidato para vincular OP con ORDEN_COMPRA.NRO_OC."},
                ],
                ["term", "meaning"],
            ),
            "",
        ]
    )
    return "\n".join(lines)


def render_executive_summary(report: dict[str, Any]) -> list[str]:
    table_profiles = report["table_profiles"]
    existing = sum(1 for row in table_profiles if row.get("exists"))
    missing = len(table_profiles) - existing
    measured_relations = [row for row in report["relations"] if row.get("status") == "measured"]
    op_paths = [row for row in report["op_resolution"] if row.get("status") == "measured"]
    return [
        f"- Tablas core presentes: {existing}; ausentes: {missing}.",
        f"- Relaciones RAFAM medidas: {len(measured_relations)}.",
        f"- Estrategias OP-SG-OC comparadas: {len(op_paths)}.",
        f"- El periodo analizado es: {report['metadata']['period']}.",
    ]


def render_schema(schema: dict[str, Any]) -> list[str]:
    lines = []
    for table in schema["tables"]:
        lines.extend(
            [
                f"### {table['table']}",
                "",
                markdown_table(
                    [{"pk": table["pk"], "fk_count": table["fk_count"]}],
                    ["pk", "fk_count"],
                ),
                "",
                markdown_table(table["columns"], ["name", "type", "nullable", "default"]),
                "",
                "FKs:",
                "",
                markdown_table(table.get("fks", []), ["constraint", "column", "references"]),
                "",
            ]
        )
    return lines


def render_reg_comp_analysis(analysis: dict[str, Any]) -> list[str]:
    if not analysis:
        return ["_Sin analisis REG_COMP/RG_COMP._"]
    lines = [
        "Este apartado no usa la semantica asumida por el codigo. Se basa en columnas, PK/FK y joins medidos contra RAFAM.",
        "",
        "### Preguntas a resolver",
        "",
        markdown_table(analysis.get("summary", []), ["question", "evidence", "status"]),
        "",
        "### Señales por tabla",
        "",
        markdown_table(
            analysis.get("table_signals", []),
            [
                "table",
                "exists",
                "pk",
                "has_nro_reg_comp",
                "has_nro_comprob",
                "has_oc_link",
                "has_uni_compra",
                "has_sg_link",
                "doc_columns",
                "date_columns",
                "amount_columns",
                "inferred_role",
            ],
        ),
        "",
        "### Joins candidatos medidos",
        "",
        render_metrics(analysis.get("relation_metrics", [])),
        "",
        "### Muestras de joins candidatos",
        "",
    ]
    for name, rows in analysis.get("samples", {}).items():
        lines.extend([f"#### {name}", "", markdown_table_auto(rows), ""])
    return lines


def render_metrics(metrics: list[dict[str, Any]]) -> str:
    main_rows = [
        {
            "name": metric.get("name"),
            "status": metric.get("status"),
            "expected": metric.get("expected", ""),
            "resolved_pct": metric.get("resolved_pct", ""),
            "unresolved_pct": metric.get("unresolved_pct", ""),
            "multi_match_pct": metric.get("multi_match_pct", ""),
            "total_sources": metric.get("total_sources", ""),
            "reason": metric.get("reason", ""),
        }
        for metric in metrics
    ]
    parts = [markdown_table(main_rows, ["name", "status", "expected", "resolved_pct", "unresolved_pct", "multi_match_pct", "total_sources", "reason"])]
    for metric in metrics:
        if metric.get("status") != "measured":
            continue
        parts.append(f"\n### Evidencia {metric['name']}\n")
        parts.append(metric.get("description", ""))
        parts.append("\n\nMuestras sin match:\n")
        parts.append(markdown_table(metric.get("sample_unresolved", []), ["source_key", "match_count"]))
        parts.append("\n\nMuestras multi-match:\n")
        parts.append(markdown_table(metric.get("sample_multi_match", []), ["source_key", "match_count"]))
    return "\n".join(parts)


def render_domains(domains: list[dict[str, Any]]) -> list[str]:
    lines = []
    for domain in domains:
        lines.extend(
            [
                f"### {domain['table']}.{domain['column']}",
                "",
                markdown_table(domain["top_values"], ["value", "total"]),
                "",
            ]
        )
    return lines


def render_edge_samples(samples: dict[str, list[dict[str, Any]]]) -> list[str]:
    lines = []
    for name, rows in samples.items():
        lines.extend([f"### {name}", "", markdown_table_auto(rows), ""])
    return lines


def decision_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    op_metrics = {row["name"]: row for row in report["op_resolution"] if row.get("status") == "measured"}
    reco_to_sg = op_metrics.get("reco_deu_compra_to_solic_gastos", {})
    nro_cance = op_metrics.get("nro_cance_to_solic_gastos", {})
    return [
        {
            "topic": "OP -> Gasto",
            "status": "pendiente_validacion" if not op_metrics else "medido",
            "evidence": f"NRO_CANCE={nro_cance.get('resolved_pct', '')}; RECO->SG={reco_to_sg.get('resolved_pct', '')}",
            "next_action": "Usar la estrategia con mayor cobertura y revisar muestras multi-match/conflictos.",
        },
        {
            "topic": "UNI_COMPRA en OP -> OC",
            "status": "pendiente_validacion",
            "evidence": "Ver reco_deu_compra_to_orden_compra.multi_match_pct y muestras ambiguas.",
            "next_action": "Si hay multi-match, no usar NRO_OC sin resolver UNI_COMPRA.",
        },
        {
            "topic": "Defaults de unidad de medida",
            "status": "pendiente_validacion",
            "evidence": "Ver dominio PED_ITEMS.UNI_MED y OC_ITEMS.UNI_MED.",
            "next_action": "Crear crosswalk UNI_MED -> unidades Paxapos si hay mas de un valor relevante.",
        },
    ]


def markdown_table_auto(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_Sin muestras._"
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return markdown_table(rows, columns)


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_Sin datos._"
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(markdown_cell(row.get(column, "")) for column in columns) + " |")
    return "\n".join([header, separator, *body])


def markdown_cell(value: Any) -> str:
    text = format_value(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return str(value).strip()


def format_column_type(row: dict[str, Any]) -> str:
    data_type = row.get("data_type") or ""
    precision = row.get("data_precision")
    scale = row.get("data_scale")
    length = row.get("data_length")
    if data_type == "NUMBER":
        if precision is not None and scale is not None:
            return f"NUMBER({precision},{scale})"
        if precision is not None:
            return f"NUMBER({precision})"
    if data_type in {"VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR"} and length:
        return f"{data_type}({length})"
    return data_type


def format_fk_reference(table_name: Any, column_name: Any) -> str:
    if not table_name:
        return ""
    if not column_name:
        return str(table_name)
    return f"{table_name}({column_name})"


def pct(part: int, total: int) -> str:
    if not total:
        return "0.00%"
    return f"{(part / total) * 100:.2f}%"


def to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def int_or_blank(value: Any) -> int | str:
    if value is None or value == "":
        return ""
    return int(value)


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def create_connection(args):
    if args.backend == "sqlite":
        path = args.sqlite_db or env("RAFAM_SOURCE_SQLITE_DB_PATH", "SQLITE_DB_PATH", default=str(REPO_ROOT / "state" / "dev_rafam.db"))
        return sqlite3.connect(path)

    import oracledb

    # Thick mode requerido para Oracle < 12.2
    try:
        oracle_client_dir = env("ORACLE_CLIENT_LIB_DIR", "ORACLE_CLIENT_DIR", default="")
        if oracle_client_dir:
            oracledb.init_oracle_client(lib_dir=oracle_client_dir)
            print(f"[thick mode] Oracle Instant Client habilitado desde: {oracle_client_dir}")
        else:
            oracledb.init_oracle_client()
            print("[thick mode] Oracle Instant Client habilitado desde LD_LIBRARY_PATH")
    except Exception as e:
        if "already been initialized" not in str(e):
            print(f"[thin mode] No se pudo inicializar Oracle Instant Client: {e}")
    host = env("RAFAM_SOURCE_HOST", "DB_HOST", default="10.10.91.241")
    port = int(env("RAFAM_SOURCE_PORT", "DB_PORT", default="1521"))
    service = env("RAFAM_SOURCE_SERVICE", "DB_SERVICE", default="BDRAFAM")
    user = env("RAFAM_SOURCE_USER", "DB_USER", default="")
    password = env("RAFAM_SOURCE_PASSWORD", "DB_PASSWORD", default="")
    if not user or not password:
        raise ValueError("Faltan RAFAM_SOURCE_USER/RAFAM_SOURCE_PASSWORD para conectar a Oracle")
    dsn = oracledb.makedsn(host, port, service_name=service)
    return oracledb.connect(user=user, password=password, dsn=dsn)


def env(*names: str, default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera contexto RAFAM canónico desde Oracle o SQLite")
    parser.add_argument("--backend", choices=["oracle", "sqlite"], default=env("RAFAM_SOURCE_BACKEND", "DB_BACKEND", default="oracle").lower())
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    parser.add_argument("--years", type=int, default=3, help="Ventana por EJERCICIO para metricas de negocio")
    parser.add_argument("--all-years", action="store_true", help="Analiza todos los ejercicios")
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--sqlite-db", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--skip-completeness", action="store_true", help="Salta la auditoria de NULL/vacios si Oracle tarda demasiado")
    parser.add_argument("--quiet", action="store_true", help="No imprime progreso por seccion")
    return parser.parse_args()


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    args = parse_args()
    years = None if args.all_years else args.years
    conn = create_connection(args)
    try:
        collector = RafamContextCollector(
            conn=conn,
            backend=args.backend,
            schema=args.schema,
            years=years,
            sample_limit=args.sample_limit,
            progress=not args.quiet,
            skip_completeness=args.skip_completeness,
        )
        report = collector.collect()
        markdown = render_markdown(report)
    finally:
        conn.close()

    if args.output:
        output_path = Path(args.output)
    else:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = DEFAULT_OUTPUT_DIR / f"rafam_context_{timestamp}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"RAFAM context generado: {output_path}")


if __name__ == "__main__":
    main()