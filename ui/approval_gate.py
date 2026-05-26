"""
approval_gate.py — Système d'approbation avant écriture dans l'éditeur

Deux modes (configurables par session ou par action) :
    SESSION  : action immédiate + notification discrète en bas de l'AIPanel
    PER_ACTION : dialog diff non-bloquant — l'auteur voit avant/après et valide

Le dialog est non-modal (QDialog sans exec()) pour ne pas figer l'UIPanel.
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QTextEdit, QCheckBox, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QTextCharFormat, QColor, QTextCursor
from ui.font_config import FontConfig
import qtawesome as qta

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Mode d'approbation
# ──────────────────────────────────────────────────────────────────────────────

class ApprovalMode:
    SESSION    = "session"     # approuve tout pour la session
    PER_ACTION = "per_action"  # demande à chaque action


def _build_gate_style(fc: FontConfig) -> str:
    return f"""
QDialog#ApprovalDialog {{
    background-color: #252526;
}}
QLabel#GateTitle {{
    color: #d4d4d4;
    font-size: {fc.sm}px;
    font-weight: bold;
    padding: 8px 12px 4px 12px;
}}
QLabel#GateSection {{
    color: #858585;
    font-size: {fc.xs}px;
    font-weight: bold;
    padding: 2px 12px;
    letter-spacing: 1px;
}}
QTextEdit#GateText {{
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #3e3e42;
    border-radius: 3px;
    font-size: {fc.sm}px;
    padding: 6px;
}}
QPushButton#AcceptBtn {{
    background-color: #0e639c;
    color: white;
    border: none;
    border-radius: 3px;
    padding: 5px 16px;
    font-size: {fc.sm}px;
}}
QPushButton#AcceptBtn:hover {{ background-color: #1177bb; }}
QPushButton#RejectBtn {{
    background-color: transparent;
    color: #858585;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 5px 16px;
    font-size: {fc.sm}px;
}}
QPushButton#RejectBtn:hover {{ color: #d4d4d4; border-color: #888; }}
QPushButton#EditBtn {{
    background-color: transparent;
    color: #4ec9b0;
    border: 1px solid #2d6a4f;
    border-radius: 3px;
    padding: 5px 12px;
    font-size: {fc.sm}px;
}}
QPushButton#EditBtn:hover {{ background-color: #1e3a2f; }}
QCheckBox {{
    color: #858585;
    font-size: {fc.xs}px;
    padding: 4px 12px;
}}
QCheckBox::indicator {{ width: 13px; height: 13px; }}
"""


class ApprovalGate(QWidget):
    """
    Gestionnaire d'approbation.

    Instancier une fois dans MainWindow, passer aux composants qui en ont besoin.

    Utilisation :
        gate.request(
            original="...",      # texte original (peut être "")
            proposed="...",      # texte proposé par l'IA
            action="replace",    # "replace" | "insert"
            on_accept=callback,  # callback(final_text: str)
            on_reject=None,      # optionnel
        )
    """

    # Mode a changé (pour persister)
    mode_changed = pyqtSignal(str)   # ApprovalMode.SESSION ou PER_ACTION

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = ApprovalMode.PER_ACTION
        self._dialog: "_ApprovalDialog | None" = None

    # ──────────────────────────────────────────────────────────────────
    # Configuration
    # ──────────────────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        logger.info("ApprovalGate — mode : %s", mode)

    @property
    def mode(self) -> str:
        return self._mode

    # ──────────────────────────────────────────────────────────────────
    # Requête d'approbation
    # ──────────────────────────────────────────────────────────────────

    def request(
        self,
        proposed: str,
        on_accept,
        original: str = "",
        action: str = "insert",
        on_reject=None,
        parent_widget: QWidget | None = None,
    ) -> None:
        """
        Demande une approbation avant d'écrire dans l'éditeur.

        Args:
            proposed:       texte que l'IA veut écrire
            on_accept:      callback(final_text: str) — appelé si validé
            original:       texte actuellement sélectionné (pour diff, peut être "")
            action:         "replace" ou "insert"
            on_reject:      callback optionnel si l'auteur refuse
            parent_widget:  widget parent pour positionner le dialog
        """
        if self._mode == ApprovalMode.SESSION:
            logger.info(
                "ApprovalGate — SESSION : action '%s' approuvée automatiquement (%d chars)",
                action, len(proposed),
            )
            on_accept(proposed)
            return

        # Mode PER_ACTION : ouvrir le dialog diff
        if self._dialog and self._dialog.isVisible():
            self._dialog.close()

        self._dialog = _ApprovalDialog(
            original=original,
            proposed=proposed,
            action=action,
            on_accept=on_accept,
            on_reject=on_reject,
            on_session_mode=self._on_session_requested,
            parent=parent_widget,
        )
        self._dialog.show()
        # Centrer sur la fenêtre parent si disponible
        if parent_widget and parent_widget.isVisible():
            pg = parent_widget.frameGeometry()
            dg = self._dialog.frameGeometry()
            self._dialog.move(
                pg.center().x() - dg.width() // 2,
                pg.center().y() - dg.height() // 2,
            )
        self._dialog.raise_()
        self._dialog.activateWindow()

    def _on_session_requested(self) -> None:
        """L'auteur a coché 'Approuver pour cette session'."""
        self._mode = ApprovalMode.SESSION
        logger.info("ApprovalGate — basculé en mode SESSION pour cette session")
        self.mode_changed.emit(ApprovalMode.SESSION)


# ──────────────────────────────────────────────────────────────────────────────
# Dialog de diff
# ──────────────────────────────────────────────────────────────────────────────

class _ApprovalDialog(QDialog):
    """Dialog non-bloquant avec affichage avant/après."""

    def __init__(
        self,
        original: str,
        proposed: str,
        action: str,
        on_accept,
        on_reject,
        on_session_mode,
        parent=None,
    ):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("ApprovalDialog")
        self.setWindowTitle("Suggestion EUGENIA")
        self.setMinimumWidth(480)
        self.setMaximumWidth(640)
        self.setStyleSheet(_build_gate_style(FontConfig.instance()))

        self._parent_ref = parent  # pour centrage manuel
        self._on_accept    = on_accept
        self._on_reject    = on_reject
        self._on_session   = on_session_mode
        self._proposed     = proposed

        self._setup_ui(original, proposed, action)

    def _setup_ui(self, original: str, proposed: str, action: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(4)

        action_label = "Remplacer la sélection" if action == "replace" else "Insérer à la position du curseur"
        title = QLabel(f"✏  {action_label}")
        title.setObjectName("GateTitle")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3e3e42;")
        layout.addWidget(sep)

        # Section AVANT (si texte original)
        if original.strip():
            lbl_before = QLabel("AVANT")
            lbl_before.setObjectName("GateSection")
            layout.addWidget(lbl_before)

            self._before_edit = QTextEdit()
            self._before_edit.setPlainText(original)
            self._before_edit.setObjectName("GateText")
            self._before_edit.setReadOnly(True)
            self._before_edit.setFixedHeight(90)
            layout.addWidget(self._before_edit)

        # Section APRÈS
        lbl_after = QLabel("APRÈS")
        lbl_after.setObjectName("GateSection")
        layout.addWidget(lbl_after)

        self._after_edit = QTextEdit()
        self._after_edit.setPlainText(proposed)
        self._after_edit.setObjectName("GateText")
        self._after_edit.setFixedHeight(120)
        layout.addWidget(self._after_edit)

        # Option session
        self._session_check = QCheckBox("Approuver automatiquement pour cette session")
        layout.addWidget(self._session_check)

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 4, 12, 0)
        btn_row.setSpacing(8)

        self._reject_btn = QPushButton("Rejeter")
        self._reject_btn.setObjectName("RejectBtn")
        self._reject_btn.clicked.connect(self._on_reject_clicked)
        btn_row.addWidget(self._reject_btn)

        btn_row.addStretch()

        self._edit_btn = QPushButton("Modifier")
        self._edit_btn.setObjectName("EditBtn")
        self._edit_btn.setCheckable(True)
        self._edit_btn.setToolTip("Rendre le texte proposé éditable")
        self._edit_btn.clicked.connect(self._on_edit_toggled)
        btn_row.addWidget(self._edit_btn)

        self._accept_btn = QPushButton("Accepter")
        self._accept_btn.setIcon(qta.icon("fa5s.check", color="white"))
        self._accept_btn.setObjectName("AcceptBtn")
        self._accept_btn.clicked.connect(self._on_accept_clicked)
        btn_row.addWidget(self._accept_btn)

        layout.addLayout(btn_row)

        # Désactiver l'édition par défaut
        self._after_edit.setReadOnly(True)

    def _on_accept_clicked(self) -> None:
        final_text = self._after_edit.toPlainText()
        if self._session_check.isChecked():
            self._on_session()
        cb = self._on_accept
        logger.info("ApprovalGate — accepté (%d chars)", len(final_text))
        # Fermer D'ABORD pour libérer le focus système,
        # puis déclencher le callback après 350 ms
        self.close()
        QTimer.singleShot(350, lambda: cb(final_text))

    def _on_reject_clicked(self) -> None:
        logger.info("ApprovalGate — rejeté")
        if self._on_reject:
            self._on_reject()
        self.close()

    def _on_edit_toggled(self, checked: bool) -> None:
        self._after_edit.setReadOnly(not checked)
        if checked:
            self._after_edit.setFocus()
