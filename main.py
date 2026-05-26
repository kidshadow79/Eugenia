"""
EUGENIA - Point d'entree principal
En hommage a Eugenie (1900-1922)
"""

import sys
import os
import logging

# --- Garde UTF-8 (Windows cp1252 par defaut) ---
# A placer AVANT tout autre import pour eviter UnicodeEncodeError sur console Windows.
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# Initialiser le logging AVANT tout autre import du projet
from core.logger import setup_logging
setup_logging()

logger = logging.getLogger(__name__)

from core.config_manager import _PROMPTS_FILE, _PROMPT_DEFAULTS, _write_prompts_file
if not _PROMPTS_FILE.exists():
    logger.info("main — prompts.json absent, création initiale")
    _write_prompts_file(dict(_PROMPT_DEFAULTS))

from PyQt6.QtWidgets import QApplication
from ui.startup_dialog import StartupDialog
from ui.main_window import MainWindow
from ui.themes import build_stylesheet
from core.config_manager import load_config


def main():
    logger.info("=== Démarrage EUGENIA v%s ===", "0.1.0")
    app = QApplication(sys.argv)
    app.setApplicationName("EUGENIA")
    app.setApplicationVersion("0.1.0")

    # Appliquer le theme global avant tout widget
    cfg = load_config()
    theme = cfg.get("theme", "dark")
    app.setStyleSheet(build_stylesheet(theme))

    # Étape 0 : écran de chargement (Splash)
    from ui.splash_screen import EugeniaSplashScreen
    from PyQt6.QtCore import QEventLoop, QTimer
    splash = EugeniaSplashScreen(theme=theme)
    splash.show()
    app.processEvents()
    
    # Présentation du Splash (2 secondes)
    loop = QEventLoop()
    QTimer.singleShot(2000, loop.quit)
    loop.exec()
    splash.close()

    # Étape 1 : écran de démarrage
    dialog = StartupDialog()
    if dialog.exec() != StartupDialog.DialogCode.Accepted:
        logger.info("Utilisateur a fermé le dialog de démarrage — arrêt propre")
        sys.exit(0)   # l'utilisateur a fermé le dialog → on quitte proprement

    # Étape 2 : ouvrir la fenêtre principale avec la session active
    session = {
        "author": dialog.selected_author,
        "project": dialog.selected_project,
    }
    logger.info(
        "Session démarrée — auteur: %s | projet: %s",
        session["author"].get("name", "?"),
        session["project"].get("name", "?"),
    )
    
    # Étape 3 : Splash screen pendant l'initialisation du moteur IA et Archiviste
    splash_load = EugeniaSplashScreen(theme=theme)
    splash_load.set_message("Chargement de l'environnement EUGENIA...")
    splash_load.show()
    app.processEvents()

    window = MainWindow(session=session)
    window.show()
    
    # Petit délai pour laisser la fenêtre se dessiner avant de fermer le splash
    QTimer.singleShot(500, splash_load.close)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
