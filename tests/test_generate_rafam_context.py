import sqlite3

from scripts.generate_rafam_context import (
    RelationSpec,
    RafamContextCollector,
    markdown_table,
    render_markdown,
)


def test_markdown_table_escapes_pipes():
    result = markdown_table([{"name": "a|b", "total": 1}], ["name", "total"])

    assert "a\\|b" in result


def test_render_markdown_includes_required_sections():
    report = {
        "metadata": {
            "generated_at": "2026-05-05T00:00:00+00:00",
            "backend": "sqlite",
            "schema": "sqlite",
            "period": "ejercicio >= 2024",
            "sample_limit": 5,
            "script_commit": "test",
        },
        "entity_contracts": [],
        "table_profiles": [],
        "schema": {"tables": []},
        "relations": [],
        "op_resolution": [],
        "reg_comp_analysis": {},
        "domains": [],
        "completeness": [],
        "numeric_quality": [],
        "edge_samples": {},
    }

    markdown = render_markdown(report)

    assert "# RAFAM Source Context" in markdown
    assert "## Contrato de extraccion del script" in markdown
    assert "## Resolucion OP-SG-OC" in markdown
    assert "## Apartado especial REG_COMP, RG_COMP y comprobantes" in markdown
    assert "## Casos de borde" in markdown


def test_relation_metric_counts_unresolved_and_multi_match():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE PEDIDOS (EJERCICIO INTEGER, NUM_PED INTEGER);
        CREATE TABLE PED_ITEMS (EJERCICIO INTEGER, NUM_PED INTEGER, ORDEN INTEGER);

        INSERT INTO PEDIDOS VALUES (2026, 1);
        INSERT INTO PEDIDOS VALUES (2026, 2);
        INSERT INTO PED_ITEMS VALUES (2026, 1, 1);
        INSERT INTO PED_ITEMS VALUES (2026, 1, 2);
        """
    )
    collector = RafamContextCollector(conn, backend="sqlite", schema="OWNER_RAFAM", years=None, sample_limit=10)
    collector.columns_by_table = collector.collect_columns()
    spec = RelationSpec(
        name="test_relation",
        description="test",
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
    )

    metric = collector.measure_relation(spec)

    assert metric["total_sources"] == 2
    assert metric["resolved_sources"] == 1
    assert metric["unresolved_sources"] == 1
    assert metric["multi_match_sources"] == 1


def test_collect_completeness_scans_table_once_per_entity():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE PROVEEDORES (
            COD_PROV INTEGER,
            RAZON_SOCIAL TEXT,
            CUIT TEXT,
            COD_ESTADO TEXT,
            FECHA_ULT_COMP TEXT
        );

        INSERT INTO PROVEEDORES VALUES (1, 'Proveedor A', '20111111112', 'A', '2026-01-01');
        INSERT INTO PROVEEDORES VALUES (2, '', NULL, 'A', NULL);
        """
    )
    collector = RafamContextCollector(conn, backend="sqlite", schema="OWNER_RAFAM", years=None, sample_limit=10)
    collector.columns_by_table = collector.collect_columns()

    rows = collector.collect_completeness()
    by_column = {row["column"]: row for row in rows if row["table"] == "PROVEEDORES"}

    assert by_column["COD_PROV"]["missing"] == 0
    assert by_column["RAZON_SOCIAL"]["missing"] == 1
    assert by_column["CUIT"]["missing"] == 1
    assert by_column["FECHA_ULT_COMP"]["missing"] == 1


def test_oracle_blank_expression_does_not_to_char_non_text_columns():
    conn = sqlite3.connect(":memory:")
    collector = RafamContextCollector(conn, backend="oracle", schema="OWNER_RAFAM", years=None, sample_limit=10)
    collector.columns_by_table = {
        "ORDEN_PAGO": [
            {"name": "NRO_OP", "type": "NUMBER(10,0)"},
            {"name": "OBSERVACIONES", "type": "VARCHAR2(255)"},
        ]
    }

    assert collector.blank_expression("t", "ORDEN_PAGO", "NRO_OP") == "t.NRO_OP IS NULL"
    assert "TRIM(t.OBSERVACIONES)" in collector.blank_expression("t", "ORDEN_PAGO", "OBSERVACIONES")


def test_reg_comp_analysis_distinguishes_register_from_invoice_table():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE REG_COMP (
            EJERCICIO INTEGER,
            NRO_REG_COMP INTEGER,
            UNI_COMPRA INTEGER,
            NRO_OC INTEGER,
            COD_PROV INTEGER,
            IMPORTE_TOT REAL
        );
        CREATE TABLE RG_COMP (
            EJERCICIO INTEGER,
            NRO_REG_COMP INTEGER,
            NRO_OC INTEGER,
            COD_PROV INTEGER,
            JURISDICCION TEXT,
            FECH_REG_COMP TEXT
        );
        CREATE TABLE CTA_COMPROB (
            EJERCICIO INTEGER,
            TIPO TEXT,
            NRO_COMPROB TEXT,
            COD_PROV INTEGER,
            COD_PROV_REAL INTEGER,
            NRO_REG_COMP INTEGER,
            FECH_COMPROB TEXT,
            IMPORTE_COMPR REAL
        );
        CREATE TABLE ORDEN_COMPRA (
            EJERCICIO INTEGER,
            UNI_COMPRA INTEGER,
            NRO_OC INTEGER,
            COD_PROV INTEGER
        );

        INSERT INTO REG_COMP VALUES (2026, 10, 1, 500, 7, 1000);
        INSERT INTO RG_COMP VALUES (2026, 10, 500, 7, '111', '2026-01-02');
        INSERT INTO CTA_COMPROB VALUES (2026, 'FA', '0001-00000010', 7, 7, 10, '2026-01-03', 1000);
        INSERT INTO ORDEN_COMPRA VALUES (2026, 1, 500, 7);
        """
    )
    collector = RafamContextCollector(conn, backend="sqlite", schema="OWNER_RAFAM", years=None, sample_limit=10)
    collector.columns_by_table = collector.collect_columns()
    collector.constraints_by_table = collector.collect_constraints()

    analysis = collector.collect_reg_comp_analysis()
    signals = {row["table"]: row for row in analysis["table_signals"]}
    metrics = {row["name"]: row for row in analysis["relation_metrics"]}

    assert signals["REG_COMP"]["inferred_role"] == "registro_o_puente_por_columnas"
    assert signals["CTA_COMPROB"]["inferred_role"] == "comprobante_fiscal_por_columnas"
    assert metrics["reg_comp_to_cta_comprob"]["resolved_pct"] == "100.00%"
    assert metrics["reg_comp_to_orden_compra"]["resolved_pct"] == "100.00%"