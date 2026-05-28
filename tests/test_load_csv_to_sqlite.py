from __future__ import annotations

import csv

from sqlalchemy import create_engine, inspect, text

from scripts.load_csv_to_sqlite import load_csvs


def test_load_csvs_keeps_cta_comprob_liquido_and_neto(tmp_path):
    csv_path = tmp_path / "cta_comprob_20260528_130732.csv"
    header = [
        "EJERCICIO", "TIPO", "NRO_COMPROB", "COD_PROV", "NRO_REG_COMP",
        "FECH_MOVIM", "FECH_COMPROB", "FECH_VENCIM", "FECH_CONFORMAC",
        "PORC_BONIF", "FECH_BONIF", "IMPORTE_COMPR", "IMPORTE_PAGADO",
        "RINDE_IVA", "PORC_IVA", "PORC_CRED_FISCAL", "LIST_LIBRO_IVA",
        "FECH_LIST_IVA", "COD_PROV_REAL", "RAZON_SOCIAL", "CUIT", "DETALLE",
        "IMPORTE_LIQUIDO", "IMPORTE_NETO", "IMPORTE_SIN_IVA", "JOIN_EXTRA",
    ]
    row = {
        "EJERCICIO": "2026",
        "TIPO": "FA",
        "NRO_COMPROB": "0001-00000077",
        "COD_PROV": "100",
        "NRO_REG_COMP": "77",
        "FECH_MOVIM": "2026-04-02 00:00:00",
        "FECH_COMPROB": "2026-04-02 00:00:00",
        "FECH_VENCIM": "2026-05-02 00:00:00",
        "FECH_CONFORMAC": "2026-04-02 00:00:00",
        "PORC_BONIF": "0",
        "FECH_BONIF": "",
        "IMPORTE_COMPR": "1210",
        "IMPORTE_PAGADO": "1210",
        "RINDE_IVA": "N",
        "PORC_IVA": "21",
        "PORC_CRED_FISCAL": "0",
        "LIST_LIBRO_IVA": "0",
        "FECH_LIST_IVA": "",
        "COD_PROV_REAL": "",
        "RAZON_SOCIAL": "Proveedor",
        "CUIT": "20111111111",
        "DETALLE": "Factura",
        "IMPORTE_LIQUIDO": "700",
        "IMPORTE_NETO": "800",
        "IMPORTE_SIN_IVA": "900",
        "JOIN_EXTRA": "descartar",
    }
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=header)
        writer.writeheader()
        writer.writerow(row)

    db_path = tmp_path / "dev_rafam.db"
    load_csvs(tmp_path, db_path)

    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    columns = {column["name"] for column in inspect(engine).get_columns("CTA_COMPROB")}

    assert "IMPORTE_LIQUIDO" in columns
    assert "IMPORTE_NETO" in columns
    assert "IMPORTE_SIN_IVA" in columns
    assert "JOIN_EXTRA" not in columns

    with engine.connect() as conn:
        loaded = conn.execute(text("""
            SELECT IMPORTE_LIQUIDO, IMPORTE_NETO, IMPORTE_SIN_IVA
            FROM CTA_COMPROB
        """)).mappings().one()

    assert loaded["IMPORTE_LIQUIDO"] == "700"
    assert loaded["IMPORTE_NETO"] == "800"
    assert loaded["IMPORTE_SIN_IVA"] == "900"