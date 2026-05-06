"""Extrae CAT_UNI_MED de Oracle RAFAM y genera docs/cat_uni_med.md."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


def main():
    oracle_dsn = os.getenv("ORACLE_DSN")
    oracle_user = os.getenv("ORACLE_USER")
    oracle_pass = os.getenv("ORACLE_PASSWORD")

    if not all([oracle_dsn, oracle_user, oracle_pass]):
        print("ERROR: Configurar ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD en .env")
        sys.exit(1)

    url = f"oracle+oracledb://{oracle_user}:{oracle_pass}@{oracle_dsn}"
    engine = create_engine(url)

    query = text("SELECT CODIGO, DESCRIPCION FROM OWNER_RAFAM.CAT_UNI_MED ORDER BY CODIGO")

    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    output = Path(__file__).resolve().parent.parent / "docs" / "cat_uni_med.md"
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w") as f:
        f.write("# CAT_UNI_MED — Unidades de Medida RAFAM\n\n")
        f.write(f"Total: {len(rows)} registros\n\n")
        f.write("| CODIGO | DESCRIPCION |\n")
        f.write("|--------|-------------|\n")
        for row in rows:
            f.write(f"| {row[0]} | {row[1]} |\n")

    print(f"Generado: {output} ({len(rows)} registros)")


if __name__ == "__main__":
    main()
