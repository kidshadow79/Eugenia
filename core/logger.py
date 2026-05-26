"""
logger.py — Configuration centralisée du logging EUGENIA

Appeler setup_logging() une seule fois depuis main.py, avant tout autre import.

Sortie :
    - Console  (stderr) : niveau INFO et au-dessus — messages courts
    - Fichier  logs/eugenia.log : niveau DEBUG — tout
      (RotatingFileHandler, 5 Mo × 3 fichiers)

Utilisation dans chaque module :
    import logging
    logger = logging.getLogger(__name__)
    logger.debug("...")
    logger.info("...")
    logger.warning("...")
    logger.error("...", exc_info=True)
"""

import logging
import logging.handlers
from pathlib import Path

_LOGS_DIR = Path(__file__).parent.parent / "logs"

_FILE_FMT   = "[%(asctime)s] [%(levelname)-8s] %(name)s — %(message)s"
_FILE_DATE  = "%Y-%m-%d %H:%M:%S"
_CON_FMT    = "[%(asctime)s] [%(levelname)-8s] %(name)s — %(message)s"
_CON_DATE   = "%H:%M:%S"

_setup_done = False


def setup_logging(level: int = logging.DEBUG) -> None:
    """
    Initialise les handlers root. Idempotent : appels successifs ignorés.

    Args:
        level: niveau minimum pour le fichier (défaut DEBUG).
               La console affiche toujours INFO+ pour rester lisible.
    """
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    _LOGS_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)   # laisser les handlers filtrer

    # ─── Handler fichier (tout, rotatif) ──────────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        _LOGS_DIR / "eugenia.log",
        maxBytes=5 * 1024 * 1024,   # 5 Mo
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(_FILE_FMT, _FILE_DATE))

    # ─── Handler console (INFO+) ───────────────────────────────────────────────
    con_handler = logging.StreamHandler()
    con_handler.setLevel(logging.INFO)
    con_handler.setFormatter(logging.Formatter(_CON_FMT, _CON_DATE))

    root.addHandler(file_handler)
    root.addHandler(con_handler)

    # Réduire le bruit des libs tierces
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialisé — fichier : %s", _LOGS_DIR / "eugenia.log"
    )
