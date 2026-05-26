"""
StylePanel -- Panneau Profil de Style (page du ContextPanel)

Affiche le profil de style genere et permet de le regenerer.
Le profil est calcule a partir des chunks ingeres dans l'index FAISS.
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.font_config import FontConfig

logger = logging.getLogger(__name__)


def _build_style_panel_style(fc: FontConfig) -> str:
    return f"""
QTextEdit#ProfileView {{ font-size: {fc.sm}px; }}
QPushButton#StyleBtn {{ font-size: {fc.sm}px; }}
QLabel#EmptyLabel {{ font-size: {fc.sm}px; }}
QLabel#StatusLabel {{ font-size: {fc.xs}px; }}
"""


class StylePanel(QWidget):
    analyze_requested = pyqtSignal()   # MainWindow lance l'analyse

    def __init__(self):
        super().__init__()
        self.setObjectName("StylePanel")
        self.setStyleSheet(_build_style_panel_style(FontConfig.instance()))
        self._setup_ui()

    def apply_font_config(self, fc: FontConfig) -> None:
        self.setStyleSheet(_build_style_panel_style(fc))

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(4)

        self._empty_label = QLabel(
            "Aucun profil de style genere.\n\n"
            "Ingérez d'abord un document,\n"
            "puis cliquez sur 'Analyser le style'."
        )
        self._empty_label.setObjectName("EmptyLabel")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._profile_view = QTextEdit()
        self._profile_view.setObjectName("ProfileView")
        self._profile_view.setReadOnly(True)
        self._profile_view.hide()
        layout.addWidget(self._profile_view)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        self._status_label.hide()
        layout.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 4, 8, 8)

        self._analyze_btn = QPushButton("Analyser le style")
        self._analyze_btn.setObjectName("StyleBtn")
        self._analyze_btn.clicked.connect(self._on_analyze)

        btn_row.addWidget(self._analyze_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def show_profile(self, text: str) -> None:
        """Affiche le profil de style (appele par MainWindow)."""
        if not text:
            return
        self._empty_label.hide()
        self._profile_view.setPlainText(text)
        self._profile_view.show()
        self._status_label.hide()
        self._analyze_btn.setEnabled(True)
        self._analyze_btn.setText("Regenerer")

    def set_analyzing(self) -> None:
        """Indique que l'analyse est en cours."""
        self._analyze_btn.setEnabled(False)
        self._analyze_btn.setText("Analyse en cours…")
        self._status_label.setText("Analyse du style en cours…")
        self._status_label.show()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_analyze(self):
        self.set_analyzing()
        self.analyze_requested.emit()
