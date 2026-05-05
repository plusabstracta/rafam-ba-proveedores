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
        "domains": [],
        "completeness": [],
        "numeric_quality": [],
        "edge_samples": {},
    }

    markdown = render_markdown(report)

    assert "# RAFAM Source Context" in markdown
    assert "## Contrato de extraccion del script" in markdown
    assert "## Resolucion OP-SG-OC" in markdown
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