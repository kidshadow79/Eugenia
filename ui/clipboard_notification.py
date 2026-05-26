"""
ClipboardNotification — Popup discret "Envoyer à EUGENIA ?"

Apparaît en bas à gauche de l'écran quand le ClipboardMonitor détecte
un nouveau texte. Se ferme automatiquement après AUTO_CLOSE_MS si
l'utilisateur ne réagit pas.

Deux boutons :
  [Envoyer]  → injecte le texte dans la conversation IA
  [Ignorer]  → ferme le popup, ne fait rien

Le texte n'est PAS envoyé automatiquement — l'auteur décide toujours.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QScreen
from ui.font_config import FontConfig

AUTO_CLOSE_MS = 8000   # fermeture automatique après 8 secondes
MARGIN = 20            # marge par rapport au bord de l'écran
PREVIEW_MAX_CHARS = 120


def _build_notif_style(fc: FontConfig) -> str:
    from ui.theme_config import ThemeConfig
    from ui.themes import get_colors
    from core.config_manager import load_config

    cfg   = load_config()
    theme = cfg.get("theme", "dark")
    c     = {**get_colors(theme), **ThemeConfig.instance().get_overrides(theme)}
    bg    = c.get("notif_bg",   c["bg_elevated"])
    text  = c.get("notif_text", c["text_primary"])
    acc   = c.get("accent",     "#0e639c")
    acc_h = c.get("accent_hover", "#1177bb")
    bri   = c.get("text_bright",  "#ffffff")
    dim   = c.get("text_dim",     "#858585")
    brd   = c.get("border_input", "#555555")
    sm    = fc.sm

    return f"""
QWidget#ClipboardNotif {{
    background-color: {bg};
    border: 1px solid {acc};
    border-radius: 6px;
}}
QLabel#NotifTitle {{
    color: {text};
    font-size: {sm}px;
    font-weight: bold;
}}
QLabel#NotifPreview {{
    color: {text};
    font-size: {sm}px;
    font-style: italic;
}}
QPushButton#SendBtn {{
    background-color: {acc};
    color: {bri};
    border: none;
    border-radius: 3px;
    padding: 5px 14px;
    font-size: {sm}px;
}}
QPushButton#SendBtn:hover {{ background-color: {acc_h}; }}
QPushButton#IgnoreBtn {{
    background-color: transparent;
    color: {dim};
    border: 1px solid {brd};
    border-radius: 3px;
    padding: 5px 14px;
    font-size: {sm}px;
}}
QPushButton#IgnoreBtn:hover {{ color: {text}; }}
"""


class ClipboardNotification(QWidget):
    """
    Popup non-bloquant positionné en bas à gauche de l'écran.

    Signaux :
      send_requested(str)  → l'auteur clique "Envoyer"
    """

    send_requested = pyqtSignal(str)

    def __init__(self, text: str, screen: QScreen):
        super().__init__()
        self._text = text
        self.setObjectName("ClipboardNotif")
        self.setStyleSheet(_build_notif_style(FontConfig.instance()))

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._setup_ui(text)
        self._position(screen)

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self.close)
        self._auto_timer.start(AUTO_CLOSE_MS)

    def _setup_ui(self, text: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("📋  Texte copié — envoyer à EUGENIA ?")
        title.setObjectName("NotifTitle")
        layout.addWidget(title)

        preview = text[:PREVIEW_MAX_CHARS].replace("\n", " ")
        if len(text) > PREVIEW_MAX_CHARS:
            preview += "…"
        preview_label = QLabel(f"« {preview} »")
        preview_label.setObjectName("NotifPreview")
        preview_label.setWordWrap(True)
        preview_label.setMaximumWidth(340)
        layout.addWidget(preview_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        send_btn = QPushButton("Envoyer")
        send_btn.setObjectName("SendBtn")
        send_btn.clicked.connect(self._on_send)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        ignore_btn = QPushButton("Ignorer")
        ignore_btn.setObjectName("IgnoreBtn")
        ignore_btn.clicked.connect(self.close)
        ignore_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_row.addStretch()
        btn_row.addWidget(send_btn)
        btn_row.addWidget(ignore_btn)
        layout.addLayout(btn_row)

        self.adjustSize()

    def _position(self, screen: QScreen):
        """Positionne le popup en bas à gauche de l'écran."""
        geo = screen.availableGeometry()
        self.adjustSize()
        x = geo.left() + MARGIN
        y = geo.bottom() - self.height() - MARGIN
        self.move(x, y)

    def _on_send(self):
        self._auto_timer.stop()
        self.send_requested.emit(self._text)
        self.close()
