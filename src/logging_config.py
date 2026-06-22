"""logging_config.py â ConfiguraciÃ³n de logging a archivo con rotaciÃ³n mensual.

Separa la lÃ³gica de file logging del CLI para que main.py solo se preocupe
por parsear argumentos y despachar comandos.

El archivo se determina asÃ­:
  - Si RAFAM_LOG_FILE estÃ¡ seteado â usa ese path fijo (sin rotaciÃ³n)
  - Sino â construye rafam-{entity}-YYYY-MM.log dentro de RAFAM_LOG_DIR
  - Si RAFAM_LOG_DISABLE=true â no escribe a archivo

RotaciÃ³n mensual real: cada ejecuciÃ³n abre el archivo del mes en curso.
Al cambiar de mes se crea automÃ¡ticamente el del mes siguiente.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from src.utils import env_bool

logger = logging.getLogger(__name__)


def setup_file_logging(args) -> None:
    """Adjunta un FileHandler con rotaciÃ³n mensual al logger raÃ­z.

    Args:
        args: Namespace de argparse con .command y opcionalmente .entity.
    """
    if env_bool("RAFAM_LOG_DISABLE", "false"):
        return

    log_dir = os.getenv("RAFAM_LOG_DIR", "logs").strip()
    log_file_override = os.getenv("RAFAM_LOG_FILE", "").strip()

    if log_file_override:
        log_path = Path(log_file_override)
    else:
        if not log_dir:
            return
        cmd = getattr(args, "command", "app") or "app"
        if cmd == "run":
            entity = (getattr(args, "entity", None) or "all").strip() or "all"
            base_name = f"rafam-{entity}"
        else:
            base_name = f"rafam-{cmd}"
        month_suffix = datetime.now().strftime("%Y-%m")
        log_path = Path(log_dir) / f"{base_name}-{month_suffix}.log"

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        handler.setLevel(logging.getLogger().level)
        logging.getLogger().addHandler(handler)
        logger.info("Logging a archivo: %s", log_path)
    except OSError as exc:
        logger.warning("No se pudo abrir archivo de log %s: %s", log_path, exc)
