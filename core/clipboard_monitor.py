"""
ClipboardMonitor — Surveille le presse-papier et détecte les nouveaux textes

Fonctionne avec un QTimer (polling toutes les 500ms dans le thread Qt principal).
Émet le signal text_detected(str) quand un nouveau texte > MIN_CHARS est copié.

Philosophie EUGENIA : on ne signale que les copies volontaires significatives.
Les micro-copies (moins de MIN_CHARS caractères) sont ignorées silencieusement.
"""

import logging
import pyperclip
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger(__name__)

MIN_CHARS = 50          # seuil en dessous duquel on ignore
POLL_INTERVAL_MS = 500  # fréquence de vérification


class ClipboardMonitor(QObject):
    """
    Surveille le presse-papier. Émet text_detected(str) quand un nouveau
    texte significatif est détecté.

    Usage :
        monitor = ClipboardMonitor()
        monitor.text_detected.connect(mon_callback)
        monitor.start()
    """

    text_detected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._last_text: str = ""
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._check)
        # Initialiser avec le contenu actuel pour éviter de notifier au démarrage
        try:
            self._last_text = pyperclip.paste() or ""
        except Exception as exc:
            logger.warning("[CLIPBOARD] init — lecture presse-papier impossible : %s", exc)
            self._last_text = ""

    def start(self):
        """Démarre la surveillance."""
        self._timer.start()

    def stop(self):
        """Arrête la surveillance."""
        self._timer.stop()

    def _check(self):
        """Appelé toutes les 500ms par le QTimer."""
        try:
            current = pyperclip.paste() or ""
        except Exception as exc:
            logger.warning("[CLIPBOARD] lecture presse-papier impossible : %s", exc)
            return

        # Nouveau texte, différent de la dernière fois, et assez long
        if current != self._last_text and len(current) >= MIN_CHARS:
            self._last_text = current
            self.text_detected.emit(current)
        elif current != self._last_text:
            # Mettre à jour quand même pour éviter de notifier sur un vieux texte
            self._last_text = current
