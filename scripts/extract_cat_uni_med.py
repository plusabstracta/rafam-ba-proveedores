"""Extrae CAT_UNI_MED de Oracle RAFAM y genera docs/cat_uni_med.md."""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

import oracledb

DB_HOST = os.getenv("RAFAM_SOURCE_HOST", os.getenv("DB_HOST", "10.10.91.241"))
DB_PORT = int(os.getenv("RAFAM_SOURCE_PORT", os.getenv("DB_PORT", "1521")))
DB_SERVICE = os.getenv("RAFAM_SOURCE_SERVICE", os.getenv("DB_SERVICE", "BDRAFAM"))
DB_USER = os.getenv("RAFAM_SOURCE_USER")
DB_PASSWORD = os.getenv("RAFAM_SOURCE_PASSWORD")


def main():
    if not DB_USER or not DB_PASSWORD:
        print("ERROR: Configurar RAFAM_SOURCE_USER y RAFAM_SOURCE_PASSWORD en .env")
        sys.exit(1)

    # Thick mode requerido para Oracle < 12.2
    oracle_client_dir = os.getenv("ORACLE_CLIENT_DIR")
    oracledb.init_oracle_client(lib_dir=oracle_client_dir or None)

    dsn = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE)
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=dsn)
    print(f"Conectado a [{DB_SERVICE}] en {DB_HOST}:{DB_PORT}")

    cursor = conn.cursor()
    cursor.execute("SELECT CODIGO, DESCRIPCION FROM OWNER_RAFAM.CAT_UNI_MED ORDER BY CODIGO")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    output = REPO_ROOT / "docs" / "cat_uni_med.md"
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
