"""
AIPanel — Panneau conversation IA (colonne 4)

Contient :
- Un historique de conversation (lecture seule)
- Un champ de saisie multi-lignes
- Un bouton Envoyer (désactivé pendant que l'IA répond)
- Un indicateur "EUGENIA réfléchit…"

Branché sur AIEngine via set_engine().
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QSplitter, QStackedWidget, QFileDialog
)
from PyQt6.QtCore import Qt, QSettings, QSize, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QFont, QPainter, QTextBlockFormat, QTextCursor
import qtawesome as qta
from ui.font_config import FontConfig
from core.i18n import tr


def _apply_chat_line_height(chat: "QTextEdit", lh: float) -> None:
    """Applique l'interligne (line-height) sur tous les blocs du QTextEdit."""
    fmt = QTextBlockFormat()
    fmt.setLineHeight(lh * 100, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    cursor = QTextCursor(chat.document())
    cursor.beginEditBlock()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeBlockFormat(fmt)
    cursor.endEditBlock()


def _build_embed_footer_style(fc: FontConfig) -> str:
    return f"""
QPushButton#EmbedBtn {{
    font-size: {fc.xs}px;
}}
QPushButton#DocModeBtn {{
    font-size: {fc.xs}px;
}}
QPushButton#InsertBtn {{
    font-size: {fc.xs}px;
}}
"""

def _build_ai_panel_style(fc: FontConfig) -> str:
    return f"""
QWidget#AIPanel {{
    background-color: #252526;
}}
QLabel#AITitle {{
    color: #bbbbbb;
    font-size: {fc.xs}px;
    font-weight: bold;
    padding: 10px 12px 6px 12px;
    letter-spacing: 1px;
    border-bottom: 1px solid #3e3e42;
}}
QTextEdit#ChatHistory {{
    background-color: #1e1e1e;
    border: none;
    color: #cccccc;
    padding: 8px;
    font-size: {fc.size}px;
}}
QWidget#InputArea {{
    background-color: #2d2d2d;
    border-top: 1px solid #3e3e42;
}}
QTextEdit#ChatInput {{
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 4px;
    color: #cccccc;
    padding: 6px;
    font-size: {fc.size}px;
}}
QTextEdit#ChatInput:focus {{
    border: 1px solid #0e639c;
}}
QPushButton#SendButton {{
    background-color: #0e639c;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: {fc.size}px;
}}
QPushButton#SendButton:hover {{
    background-color: #1177bb;
}}
QPushButton#SendButton:pressed {{
    background-color: #0a4f80;
}}
QPushButton#AttachBtn {{
    background: transparent;
    color: #777777;
    border: none;
    border-radius: 3px;
    font-size: 16px;
    padding: 2px 4px;
}}
QPushButton#AttachBtn:hover {{
    color: #aaaaaa;
    background-color: #3a3a3a;
}}
QPushButton#GhostScanBtn, QPushButton#GhostHideBtn {{
    background: transparent;
    color: #777777;
    border: none;
    border-radius: 3px;
    font-size: 13px;
    padding: 2px 5px;
}}
QPushButton#GhostScanBtn:hover, QPushButton#GhostHideBtn:hover {{
    color: #aaaaaa;
    background-color: #3a3a3a;
}}
QPushButton#GhostScanBtn:disabled {{
    color: #444444;
}}
QPushButton#EditDocBtn {{
    background: transparent;
    color: #777777;
    border: none;
    border-radius: 3px;
    font-size: 14px;
    padding: 2px 5px;
}}
QPushButton#EditDocBtn:hover {{
    color: #d4a657;
    background-color: #3a3a3a;
}}
QPushButton#ScreenshotBtn {{
    background: transparent;
    color: #777777;
    border: none;
    border-radius: 3px;
    font-size: 14px;
    padding: 2px 5px;
}}
QPushButton#ScreenshotBtn:hover {{
    color: #aaaaaa;
    background-color: #3a3a3a;
}}
QPushButton#ScreenshotBtn:disabled {{
    color: #444444;
}}
QWidget#AttachPill {{
    background-color: #3a3a3a;
    border: 1px solid #555555;
    border-radius: 4px;
}}
QLabel#PillLabel {{
    color: #cccccc;
    font-size: {fc.xs}px;
    padding: 2px 4px;
}}
QPushButton#PillClose {{
    background: transparent;
    color: #888888;
    border: none;
    font-size: {fc.sm}px;
    padding: 0px 4px;
    font-weight: bold;
}}
QPushButton#PillClose:hover {{
    color: #ff6b6b;
}}
QPushButton#PillPersist {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 1px;
}}
QPushButton#PillPersist:hover {{
    border-color: #555555;
}}
QPushButton#PillPersist:checked {{
    border-color: #ccaa55;
}}
QPushButton#InsertBtn {{
    background-color: transparent;
    color: #4ec9b0;
    border: 1px solid #2d6a4f;
    border-radius: 3px;
    font-size: {fc.xs}px;
    padding: 3px 10px;
}}
QPushButton#InsertBtn:hover {{
    background-color: #1e3a2f;
    color: #6de0c8;
}}
QLabel#ThinkingLabel {{
    color: #4ec9b0;
    font-size: {fc.xs}px;
    font-style: italic;
    padding: 4px 12px;
}}
"""


class AIPanel(QWidget):
    # Emis quand l'auteur valide un message
    send_requested = pyqtSignal(str)
    # Emis quand l'utilisateur clique Attacher / Detacher
    attach_editor_requested = pyqtSignal()
    detach_editor_requested = pyqtSignal()
    # Emis quand l'utilisateur clique 'Nouveau document a editer'
    edit_requested = pyqtSignal()
    # Emis quand l'auteur clique 'Insérer dans l'éditeur'
    insert_in_editor_requested = pyqtSignal(str)
    # Emis quand le mode document change (True = activé)
    document_mode_changed = pyqtSignal(bool)
    # Emis quand le titre EUGENIA est clique (repli/deploi)
    toggle_requested = pyqtSignal()
    # Ghost Writer
    ghost_scan_requested   = pyqtSignal()
    ghost_toggle_requested = pyqtSignal()
    # Capture éditeur
    screenshot_requested   = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("AIPanel")
        self.setMinimumWidth(120)
        self._engine = None   # branche via set_engine()
        self._attached_file: dict | None = None  # {type, content, filename, mime, b64}
        self._setup_ui()

    def set_engine(self, engine):
        """Branche le moteur IA. Appelé par MainWindow après création de l'AIEngine."""
        self._engine = engine

    def apply_font_config(self, fc: FontConfig) -> None:
        """Propage la nouvelle config police aux sous-widgets avec style local."""
        self._embed_footer.setStyleSheet(_build_embed_footer_style(fc))
        _apply_chat_line_height(self.chat_history, fc.chat_lh)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Stack : page 0 = panneau normal, page 1 = label vertical replié ──
        self._stack = QStackedWidget()

        # ── Page 0 : contenu normal ──────────────────────────────────────────
        normal_page = QWidget()
        normal_layout = QVBoxLayout(normal_page)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_layout.setSpacing(0)

        # Titre cliquable
        title = _ClickableLabel("EUGENIA")
        title.setObjectName("AITitle")
        title.setToolTip("Cliquer pour replier le panneau")
        title.clicked.connect(self.toggle_requested)
        normal_layout.addWidget(title)

        # Splitter vertical historique / saisie
        self._chat_splitter = QSplitter(Qt.Orientation.Vertical)
        self._chat_splitter.setChildrenCollapsible(False)
        self._chat_splitter.setHandleWidth(5)

        top_pane = QWidget()
        top_pane.setObjectName("ChatTopPane")
        top_layout = QVBoxLayout(top_pane)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        self.chat_history = QTextEdit()
        self.chat_history.setObjectName("ChatHistory")
        self.chat_history.setReadOnly(True)
        self.chat_history.setPlaceholderText(tr("La conversation apparaîtra ici…"))
        top_layout.addWidget(self.chat_history)

        self._thinking_label = QLabel(tr("EUGENIA réfléchit…"))
        self._thinking_label.setObjectName("ThinkingLabel")
        self._thinking_label.hide()
        top_layout.addWidget(self._thinking_label)

        self._chat_splitter.addWidget(top_pane)

        input_area = QWidget()
        input_area.setObjectName("InputArea")
        input_layout = QVBoxLayout(input_area)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(6)

        self.chat_input = _ChatInput(on_send=self._on_send)
        self.chat_input.setObjectName("ChatInput")
        self.chat_input.setPlaceholderText(tr("Écris ton message… (Entrée pour envoyer, Maj+Entrée pour sauter une ligne)"))
        input_layout.addWidget(self.chat_input)

        # ── Pill d'attachement (caché par défaut) ────────────────────────────
        self._attach_pill = QWidget()
        self._attach_pill.setObjectName("AttachPill")
        pill_layout = QHBoxLayout(self._attach_pill)
        pill_layout.setContentsMargins(6, 3, 4, 3)
        pill_layout.setSpacing(4)
        self._pill_label = QLabel()
        self._pill_label.setObjectName("PillLabel")
        pill_layout.addWidget(self._pill_label)
        pill_layout.addStretch()
        self._pill_persist_check = QPushButton()
        self._pill_persist_check.setObjectName("PillPersist")
        self._pill_persist_check.setCheckable(True)
        self._pill_persist_check.setIcon(qta.icon("fa5s.thumbtack", color="#555555", color_active="#ccaa55"))
        self._pill_persist_check.setIconSize(QSize(13, 13))
        self._pill_persist_check.setToolTip(
            tr("Conserver dans le contexte après envoi\n"
               "et sauvegarder dans snapshots/")
        )
        self._pill_persist_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pill_persist_check.toggled.connect(self._on_pill_persist_changed)
        pill_layout.addWidget(self._pill_persist_check)
        self._pill_close_btn = QPushButton()
        self._pill_close_btn.setObjectName("PillClose")
        self._pill_close_btn.setIcon(qta.icon("fa5s.times", color="#777777"))
        self._pill_close_btn.setIconSize(QSize(12, 12))
        self._pill_close_btn.setToolTip(tr("Retirer la pièce jointe"))
        self._pill_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pill_close_btn.clicked.connect(self._on_detach)
        pill_layout.addWidget(self._pill_close_btn)
        self._attach_pill.hide()
        input_layout.addWidget(self._attach_pill)

        # ── Rangée bas : bouton trombone + Envoyer ───────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        self._attach_btn = QPushButton()
        self._attach_btn.setObjectName("AttachBtn")
        self._attach_btn.setIcon(qta.icon("fa5s.paperclip", color="#858585", color_disabled="#444444"))
        self._attach_btn.setIconSize(QSize(16, 16))
        self._attach_btn.setToolTip(tr("Joindre un fichier texte ou image à ce message"))
        self._attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._attach_btn.clicked.connect(self._on_attach_clicked)
        bottom_row.addWidget(self._attach_btn)

        # Boutons Ghost Writer
        self._ghost_scan_btn = QPushButton()
        self._ghost_scan_btn.setObjectName("GhostScanBtn")
        self._ghost_scan_btn.setIcon(qta.icon("fa5s.search", color="#858585", color_disabled="#444444"))
        self._ghost_scan_btn.setIconSize(QSize(16, 16))
        self._ghost_scan_btn.setToolTip(
            tr("Scanner la page pour ancrer les annotations Ghost Writer\n"
               "sur les passages correspondants dans l'éditeur.")
        )
        self._ghost_scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ghost_scan_btn.clicked.connect(self._on_ghost_scan_clicked)
        bottom_row.addWidget(self._ghost_scan_btn)

        self._ghost_hide_btn = QPushButton()
        self._ghost_hide_btn.setObjectName("GhostHideBtn")
        self._ghost_hide_btn.setIcon(qta.icon("fa5s.eye", color="#858585", color_disabled="#444444"))
        self._ghost_hide_btn.setIconSize(QSize(16, 16))
        self._ghost_hide_btn.setToolTip(
            tr("Afficher / masquer les annotations Ghost Writer.")
        )
        self._ghost_hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ghost_hide_btn.clicked.connect(self._on_ghost_hide_clicked)
        self._ghost_annotations_visible = True
        bottom_row.addWidget(self._ghost_hide_btn)

        self._edit_doc_btn = QPushButton()
        self._edit_doc_btn.setObjectName("EditDocBtn")
        self._edit_doc_btn.setIcon(qta.icon("fa5s.pen", color="#858585"))
        self._edit_doc_btn.setIconSize(QSize(15, 15))
        self._edit_doc_btn.setToolTip(tr("Ouvrir un nouveau document en mode edition co-auteur"))
        self._edit_doc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_doc_btn.clicked.connect(self.edit_requested)
        bottom_row.addWidget(self._edit_doc_btn)

        bottom_row.addStretch()

        self._screenshot_btn = QPushButton()
        self._screenshot_btn.setObjectName("ScreenshotBtn")
        self._screenshot_btn.setIcon(qta.icon("fa5s.camera", color="#858585", color_disabled="#444444"))
        self._screenshot_btn.setIconSize(QSize(16, 16))
        self._screenshot_btn.setToolTip(
            tr("Capturer la zone éditeur et l'joindre au prochain message.")
        )
        self._screenshot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._screenshot_btn.setEnabled(False)  # activé quand un éditeur est attaché
        self._screenshot_btn.clicked.connect(self.screenshot_requested)
        bottom_row.addWidget(self._screenshot_btn)

        self._send_btn = QPushButton(tr("Envoyer"))
        self._send_btn.setObjectName("SendButton")
        self._send_btn.clicked.connect(self._on_send)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        bottom_row.addWidget(self._send_btn)

        input_layout.addLayout(bottom_row)

        self._chat_splitter.addWidget(input_area)
        self._chat_splitter.setSizes([750, 250])
        self._restore_chat_splitter()
        self._chat_splitter.splitterMoved.connect(self._save_chat_splitter)
        normal_layout.addWidget(self._chat_splitter, stretch=1)

        # Footer embed
        self._embed_footer = QWidget()
        self._embed_footer.setObjectName("EmbedFooter")
        self._embed_footer.setFixedHeight(34)
        footer_layout = QHBoxLayout(self._embed_footer)
        footer_layout.setContentsMargins(6, 4, 6, 4)
        footer_layout.setSpacing(6)

        self._embed_btn = QPushButton()
        self._embed_btn.setObjectName("EmbedBtn")
        self._embed_btn.setIcon(qta.icon("fa5s.plug", color="#777777"))
        self._embed_btn.setIconSize(QSize(14, 14))
        self._embed_btn.setToolTip(tr("Attacher l'editeur de texte externe (Word, etc.)"))
        self._embed_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._embed_btn.clicked.connect(self._on_embed_clicked)
        self._is_attached = False
        footer_layout.addWidget(self._embed_btn)

        self._insert_btn = QPushButton(tr("Insérer"))
        self._insert_btn.setObjectName("InsertBtn")
        self._insert_btn.setIcon(qta.icon("fa5s.arrow-down", color="#858585"))
        self._insert_btn.setIconSize(QSize(13, 13))
        self._insert_btn.setToolTip(
            tr("Insère la dernière réponse EUGENIA dans l'éditeur attaché.\n"
               "Si du texte est sélectionné dans l'éditeur, il sera remplacé.")
        )
        self._insert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._insert_btn.setVisible(False)
        self._last_ai_response: str = ""
        self._insert_btn.clicked.connect(
            lambda: self.insert_in_editor_requested.emit(self._last_ai_response)
        )
        footer_layout.addWidget(self._insert_btn)

        footer_layout.addStretch()

        self._doc_mode_btn = QPushButton()
        self._doc_mode_btn.setObjectName("DocModeBtn")
        self._doc_mode_btn.setCheckable(True)
        self._doc_mode_btn.setIcon(qta.icon("fa5s.file-alt", color="#777777"))
        self._doc_mode_btn.setIconSize(QSize(14, 14))
        self._doc_mode_btn.setToolTip(
            tr("Mode document :\n"
               "- Le contenu de l'editeur est lu et injecte dans chaque message\n"
               "- Les reponses EUGENIA sont automatiquement proposees pour insertion")
        )
        self._doc_mode_btn.setEnabled(False)
        self._doc_mode_btn.toggled.connect(self.document_mode_changed)
        footer_layout.addWidget(self._doc_mode_btn)
        normal_layout.addWidget(self._embed_footer)

        self._stack.addWidget(normal_page)   # index 0

        # ── Page 1 : label vertical (état replié) ────────────────────────────
        self._vertical_label = _VerticalLabel("EUGENIA")
        self._vertical_label.clicked.connect(self.toggle_requested)
        self._stack.addWidget(self._vertical_label)  # index 1

        layout.addWidget(self._stack)

    # ------------------------------------------------------------------ #
    # Persistance du splitter interne                                      #
    # ------------------------------------------------------------------ #

    def _restore_chat_splitter(self):
        s = QSettings("EUGENIA", "Layout")
        state = s.value("ai_panel/splitter")
        if state is not None and not state.isEmpty():
            self._chat_splitter.restoreState(state)

    def _save_chat_splitter(self):
        s = QSettings("EUGENIA", "Layout")
        s.setValue("ai_panel/splitter", self._chat_splitter.saveState())

    def set_collapsed(self, collapsed: bool) -> None:
        """Bascule entre le panneau normal (page 0) et le label vertical (page 1)."""
        if collapsed:
            self._stack.setCurrentIndex(1)
            self.setFixedWidth(24)
        else:
            self.setMinimumWidth(120)
            self.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
            self._stack.setCurrentIndex(0)

    def set_editor_attached(self, attached: bool) -> None:
        """Appele par MainWindow pour mettre a jour les icones du footer."""
        self._is_attached = attached
        if attached:
            self._embed_btn.setIcon(qta.icon("fa5s.unlink", color="#d4a657"))
            self._embed_btn.setToolTip(tr("Detacher l'editeur externe"))
            self._doc_mode_btn.setEnabled(True)
            self._screenshot_btn.setEnabled(True)
        else:
            self._embed_btn.setIcon(qta.icon("fa5s.plug", color="#777777"))
            self._embed_btn.setToolTip(tr("Attacher l'editeur de texte externe (Word, etc.)"))
            self._doc_mode_btn.setEnabled(False)
            self._doc_mode_btn.setChecked(False)
            self._screenshot_btn.setEnabled(False)

    # ------------------------------------------------------------------ #
    # Pièce jointe                                                         #
    # ------------------------------------------------------------------ #

    def _on_attach_clicked(self):
        """Ouvre un sélecteur de fichier et attache le résultat."""
        from core.file_reader import read_file_for_context
        ext_filter = (
            tr("Fichiers supportés (*.txt *.md *.py *.json *.docx "
               "*.js *.ts *.html *.css *.xml *.csv *.log *.sql "
               "*.jpg *.jpeg *.png *.webp *.gif);;") +
            tr("Texte (*.txt *.md *.py *.json *.docx);;") +
            tr("Image (*.jpg *.jpeg *.png *.webp *.gif);;") +
            tr("Tous les fichiers (*)")
        )
        path, _ = QFileDialog.getOpenFileName(self, tr("Joindre un fichier"), "", ext_filter)
        if not path:
            return
        file_data = read_file_for_context(path)
        if file_data is None:
            self.append_injected(tr("Erreur"), tr("Impossible de lire ce fichier (type non supporté ou vide)."))
            return
        self._pill_persist_check.setChecked(False)
        self._attached_file = file_data
        self._pill_persist_check.setChecked(False)
        self._set_pill(file_data)

    def _on_detach(self):
        """Retire la pièce jointe en cours."""
        self._pill_persist_check.setChecked(False)
        self._attached_file = None
        self._attach_pill.hide()

    def _set_pill(self, file_data: dict):
        """Affiche la pill avec le nom et l'icône du fichier attaché."""
        icon = "🖼️" if file_data["type"] == "image" else "📄"
        name = file_data["filename"]
        # Tronquer si trop long
        display = name if len(name) <= 40 else f"…{name[-37:]}"
        self._pill_label.setText(f"{icon} {display}")
        self._attach_pill.show()

    def pop_attachment(self) -> dict | None:
        """
        Retourne la pièce jointe courante.
        Si la persistance est activée, elle est conservée pour le prochain message.
        Sinon, elle est effacée (comportement normal).
        Appelé par MainWindow juste avant l'injection dans l'engine.
        """
        att = self._attached_file
        if att is None:
            return None
        if self._pill_persist_check.isChecked():
            # Garder en contexte — ne pas effacer, ne pas masquer la pill
            return att
        # Comportement normal : effacer après envoi
        self._attached_file = None
        self._attach_pill.hide()
        return att

    def _on_pill_persist_changed(self, state: int) -> None:
        """Sauvegarde la capture sur disque quand la persistance est activée."""
        if not state:  # décochée → rien à faire
            return
        att = self._attached_file
        if att is None or att.get("type") != "image" or not att.get("b64"):
            return
        import base64
        import logging
        from pathlib import Path
        from datetime import datetime
        snapshots_dir = Path(__file__).parent.parent / "snapshots"
        snapshots_dir.mkdir(exist_ok=True)
        stem = Path(att.get("filename", "snapshot.png")).stem
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = snapshots_dir / f"{stem}_{ts}.png"
        dest.write_bytes(base64.b64decode(att["b64"]))
        logging.getLogger(__name__).info("[SNAPSHOT] sauvegardé : %s", dest)

    def set_screenshot(self, file_data: dict) -> None:
        """Reçoit la capture d'écran de l'éditeur (fournie par MainWindow) et l'attache."""
        self._pill_persist_check.setChecked(False)  # reset à chaque nouvelle capture
        self._attached_file = file_data
        self._set_pill(file_data)

    def _on_embed_clicked(self):
        if self._is_attached:
            self.detach_editor_requested.emit()
        else:
            self.attach_editor_requested.emit()

    # ------------------------------------------------------------------ #
    # Envoi / reception                                                    #
    # ------------------------------------------------------------------ #

    def _on_send(self):
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        if self._engine and self._engine.is_busy:
            return

        self._append_user(text)
        self.chat_input.clear()
        self._set_busy(True)

        if self._engine:
            # Émettre le signal — main_window orchestre Archiviste + engine.send()
            self.send_requested.emit(text)
        else:
            self._append_ai(tr("⚙️  Aucun moteur IA configuré. Va dans Paramètres → IA pour renseigner ta clé API."))
            self._set_busy(False)

    def on_ai_response(self, text: str):
        """Appelé par MainWindow quand l'AIEngine a une réponse."""
        self._append_ai(text)
        self._last_ai_response = text
        self._insert_btn.setVisible(True)
        self._set_busy(False)

    def on_ai_error(self, error: str):
        """Appelé par MainWindow en cas d'erreur API."""
        self._append_ai(tr("❌ Erreur : {}").format(error))
        self._set_busy(False)

    def append_injected(self, label: str, preview: str):
        """
        Affiche une notification dans le chat quand du texte est injecté
        via clipboard ou ingest (sans afficher tout le contenu).
        """
        self.chat_history.append(
            f'<p style="color:#555555;font-size:11px;font-style:italic;">'
            + tr("📎 {} injecté dans la conversation").format(tr(label)) + f'<br>'
            f'<span style="color:#444444;">{preview[:80]}{"…" if len(preview) > 80 else ""}</span>'
            f'</p>'
        )
        self._scroll_to_bottom()

    # ------------------------------------------------------------------ #
    # Helpers d'affichage                                                  #
    # ------------------------------------------------------------------ #

    def _append_user(self, text: str):
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.chat_history.append(
            f'<p><span style="color:#569cd6;font-weight:bold;">' + tr("Toi") + f'</span><br>{safe}</p>'
        )
        _apply_chat_line_height(self.chat_history, FontConfig.instance().chat_lh)
        self._scroll_to_bottom()

    def _append_ai(self, text: str):
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.chat_history.append(
            f'<p><span style="color:#4ec9b0;font-weight:bold;">' + tr("EUGENIA") + f'</span><br>{safe}</p>'
        )
        _apply_chat_line_height(self.chat_history, FontConfig.instance().chat_lh)
        self._scroll_to_bottom()

    def clear_chat(self) -> None:
        """Vide le panneau de chat pour une nouvelle conversation."""
        self.chat_history.clear()
        self._last_ai_response = ""
        self._insert_btn.setVisible(False)

    def load_history(self, messages: list[dict]) -> None:
        """
        Recharge une conversation passée dans la zone de chat.
        Utilisé lors de la reprise d'une session existante.
        """
        self.chat_history.clear()
        self._last_ai_response = ""
        self._insert_btn.setVisible(False)
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                self._append_user(content)
            elif role == "assistant":
                self._append_ai(content)
                self._last_ai_response = content
        if self._last_ai_response:
            self._insert_btn.setVisible(True)

    def _scroll_to_bottom(self):
        self.chat_history.verticalScrollBar().setValue(
            self.chat_history.verticalScrollBar().maximum()
        )

    def _set_busy(self, busy: bool):
        self._send_btn.setEnabled(not busy)
        self.chat_input.setEnabled(not busy)
        self._attach_btn.setEnabled(not busy)
        self._screenshot_btn.setEnabled(not busy and self._is_attached)
        self._thinking_label.setVisible(busy)

    def _on_ghost_scan_clicked(self) -> None:
        clr, clr_dis = self._icon_clr()
        self._ghost_scan_btn.setEnabled(False)
        self._ghost_scan_btn.setIcon(qta.icon("fa5s.spinner", color=clr, color_disabled=clr))
        self.ghost_scan_requested.emit()

    def ghost_scan_finished(self) -> None:
        """Appelé par MainWindow quand le scan est terminé."""
        clr, clr_dis = self._icon_clr()
        self._ghost_scan_btn.setEnabled(True)
        self._ghost_scan_btn.setIcon(qta.icon("fa5s.search", color=clr, color_disabled=clr_dis))

    def set_ghost_active(self, active: bool) -> None:
        """Active ou désactive le bouton Scan selon l'état du système Ghost Writer."""
        self._ghost_scan_btn.setEnabled(active)
        self._ghost_scan_btn.setToolTip(
            tr("Scanner la page pour repositionner les annotations.")
            if active
            else tr("Activer les annotations pour utiliser le scan.")
        )

    def _on_ghost_hide_clicked(self) -> None:
        clr, clr_dis = self._icon_clr()
        self._ghost_annotations_visible = not self._ghost_annotations_visible
        icon_name = "fa5s.eye" if self._ghost_annotations_visible else "fa5s.eye-slash"
        self._ghost_hide_btn.setIcon(qta.icon(icon_name, color=clr, color_disabled=clr_dis))
        self._ghost_hide_btn.setToolTip(
            tr("Masquer les annotations Ghost Writer.")
            if self._ghost_annotations_visible
            else tr("Afficher les annotations Ghost Writer.")
        )
        self.ghost_toggle_requested.emit()

    def _icon_clr(self) -> tuple[str, str]:
        """Retourne (clr_normal, clr_disabled) selon le thème courant + surcharges utilisateur."""
        from ui.themes import get_colors
        from ui.theme_config import ThemeConfig
        theme = getattr(self, "_current_theme", "dark")
        overrides = ThemeConfig.instance().get_overrides(theme)
        c = {**get_colors(theme), **overrides}
        return c.get("icon_color", "#858585"), c.get("text_muted", "#444444")

    def set_busy(self, busy: bool) -> None:
        """API publique pour que MainWindow puisse débloquer l'état 'réfléchit'."""
        self._set_busy(busy)

    def apply_theme(self, theme: str) -> None:
        """Met à jour les icônes qtawesome selon le thème actif et ses surcharges utilisateur."""
        from ui.themes import get_colors
        from ui.theme_config import ThemeConfig
        self._current_theme = theme
        overrides = ThemeConfig.instance().get_overrides(theme)
        c = {**get_colors(theme), **overrides}
        clr = c.get("icon_color", "#858585")
        clr_dis = c.get("text_muted", "#444444")
        clr_accent = c.get("accent", "#0e639c")

        self._attach_btn.setIcon(qta.icon("fa5s.paperclip", color=clr, color_disabled=clr_dis))
        self._screenshot_btn.setIcon(qta.icon("fa5s.camera", color=clr, color_disabled=clr_dis))
        self._ghost_scan_btn.setIcon(qta.icon("fa5s.search", color=clr, color_disabled=clr_dis))
        eye_icon = "fa5s.eye" if self._ghost_annotations_visible else "fa5s.eye-slash"
        self._ghost_hide_btn.setIcon(qta.icon(eye_icon, color=clr, color_disabled=clr_dis))
        self._insert_btn.setIcon(qta.icon("fa5s.arrow-down", color=clr))
        self._pill_close_btn.setIcon(qta.icon("fa5s.times", color=clr))
        self._pill_persist_check.setIcon(
            qta.icon("fa5s.thumbtack", color=clr_dis, color_active=clr_accent)
        )


class _ClickableLabel(QLabel):
    """QLabel qui emet clicked() au clic gauche."""
    clicked = pyqtSignal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _VerticalLabel(QWidget):
    """Widget affichant chaque lettre empilee verticalement (style ideogramme)."""
    clicked = pyqtSignal()

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("Cliquer pour deployer EUGENIA"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().color(self.palette().ColorRole.Text)
        painter.setPen(color)
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        fm = painter.fontMetrics()
        char_h = fm.height()
        total_h = char_h * len(self._text)
        y_start = (self.height() - total_h) // 2

        for i, ch in enumerate(self._text):
            char_w = fm.horizontalAdvance(ch)
            x = (self.width() - char_w) // 2
            y = y_start + i * char_h + fm.ascent()
            painter.drawText(x, y, ch)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _ChatInput(QTextEdit):
    """
    Champ de saisie avec gestion du clavier :
    - Entrée seul       → envoyer le message
    - Maj + Entrée      → saut de ligne
    """
    def __init__(self, on_send):
        super().__init__()
        self._on_send = on_send

    def keyPressEvent(self, event: QKeyEvent):
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._on_send()
        else:
            super().keyPressEvent(event)
