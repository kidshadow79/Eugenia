"""
edit_panel.py — Panneau d'edition co-auteur (substitut de l'EditorZone)

Layout :
  [Barre titre : LineEdit titre | compteur mots | btn Backup | btn Export | btn Fermer]
  [Toolbar micro-commandes : Raccourcis | Lyrique | Corrige | Developpe | separateur | toggle Split]
  [Zone split : gauche=QPlainTextEdit(markdown) | droite=QTextBrowser(rendu HTML live)]
  [Barre statut : nb backups disponibles | derniere modification]

Signaux publics :
  closed()                          -- l'auteur ferme le panneau -> retour EditorZone
  save_requested(path: str)         -- exporter vers un fichier disque
  ai_command_requested(cmd, sel)    -- micro-commande IA (cmd=label, sel=texte selectionne)
"""

import logging
import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPlainTextEdit, QTextBrowser, QLineEdit,
    QPushButton, QLabel, QFileDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QTextCursor
import qtawesome as qta

from core.edit_document import EditDocument, EditDocStore
from ui.font_config import FontConfig

logger = logging.getLogger(__name__)

# Micro-commandes rapides (label affiché, texte envoyé à l'IA)
_MICRO_COMMANDS = [
    ("Raccourcis",   "Raccourcis ce passage, supprime les redondances sans perdre le sens."),
    ("Plus lyrique", "Rends ce passage plus lyrique et poetique, enrichis le vocabulaire."),
    ("Corrige",      "Corrige les fautes d'orthographe, de grammaire et de style de ce passage."),
    ("Developpe",    "Developpe ce passage, ajoute des details et de la profondeur."),
]


def _build_edit_panel_style(fc: FontConfig) -> str:
    return f"""
QWidget#EditPanel {{
    background-color: #1e1e1e;
}}
QWidget#EditTitleBar {{
    background-color: #252526;
    border-bottom: 1px solid #3e3e42;
}}
QWidget#EditToolbar {{
    background-color: #2d2d2d;
    border-bottom: 1px solid #3e3e42;
}}
QLineEdit#DocTitle {{
    background-color: transparent;
    border: none;
    color: #e0e0e0;
    font-size: {fc.size + 1}px;
    font-weight: bold;
    padding: 4px 6px;
}}
QLineEdit#DocTitle:focus {{
    border-bottom: 1px solid #0e639c;
}}
QPlainTextEdit#MarkdownEditor {{
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: "Consolas", "Courier New", monospace;
    font-size: {fc.sm}px;
    border: none;
    padding: 8px;
}}
QTextBrowser#HtmlPreview {{
    background-color: #252526;
    color: #cccccc;
    font-size: {fc.size}px;
    border: none;
    border-left: 1px solid #3e3e42;
    padding: 8px;
}}
QPushButton#EditToolBtn {{
    background-color: transparent;
    color: #aaaaaa;
    border: none;
    padding: 4px 8px;
    font-size: {fc.xs}px;
    border-radius: 3px;
}}
QPushButton#EditToolBtn:hover {{
    background-color: #3e3e42;
    color: #e0e0e0;
}}
QPushButton#EditCloseBtn {{
    background-color: transparent;
    color: #888888;
    border: none;
    padding: 4px 8px;
    border-radius: 3px;
}}
QPushButton#EditCloseBtn:hover {{
    background-color: #5a1d1d;
    color: #f48771;
}}
QLabel#EditStatusBar {{
    color: #555555;
    font-size: {fc.xs}px;
    padding: 2px 8px;
    background-color: #1e1e1e;
    border-top: 1px solid #2d2d2d;
}}
"""


class EditPanel(QWidget):
    """
    Panneau d'edition co-auteur.
    Remplace l'EditorZone dans le splitter central quand le mode edition est actif.
    """

    closed               = pyqtSignal()
    save_requested       = pyqtSignal(str)           # chemin absolu choisi par l'auteur
    ai_command_requested = pyqtSignal(str, str)      # (commande_label, texte_selectionne)

    def __init__(self, store: EditDocStore):
        super().__init__()
        self.setObjectName("EditPanel")
        self._store = store
        self._doc: EditDocument | None = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(400)   # debounce 400 ms
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._setup_ui()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        fc = FontConfig.instance()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_title_bar(fc))
        root.addWidget(self._build_toolbar(fc))
        root.addWidget(self._build_editor_area(), stretch=1)
        root.addWidget(self._build_status_bar(fc))

        self.setStyleSheet(_build_edit_panel_style(fc))

    def _build_title_bar(self, fc: FontConfig) -> QWidget:
        bar = QWidget()
        bar.setObjectName("EditTitleBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        self._title_edit = QLineEdit("Sans titre")
        self._title_edit.setObjectName("DocTitle")
        self._title_edit.setPlaceholderText("Titre du document…")
        self._title_edit.textChanged.connect(self._on_title_changed)
        lay.addWidget(self._title_edit, stretch=1)

        self._word_count_lbl = QLabel("0 mots")
        self._word_count_lbl.setObjectName("EditCloseBtn")
        lay.addWidget(self._word_count_lbl)

        btn_back = QPushButton(qta.icon("fa5s.undo", color="#888"), "")
        btn_back.setObjectName("EditCloseBtn")
        btn_back.setToolTip("Restaurer le backup precedent")
        btn_back.setIconSize(QSize(14, 14))
        btn_back.setFixedSize(28, 28)
        btn_back.clicked.connect(self._on_restore_backup)
        lay.addWidget(btn_back)
        self._btn_back = btn_back

        btn_export = QPushButton(qta.icon("fa5s.download", color="#888"), "")
        btn_export.setObjectName("EditCloseBtn")
        btn_export.setToolTip("Exporter le document (.md)")
        btn_export.setIconSize(QSize(14, 14))
        btn_export.setFixedSize(28, 28)
        btn_export.clicked.connect(self._on_export)
        lay.addWidget(btn_export)

        btn_close = QPushButton(qta.icon("fa5s.times", color="#888"), "")
        btn_close.setObjectName("EditCloseBtn")
        btn_close.setToolTip("Fermer le mode edition")
        btn_close.setIconSize(QSize(14, 14))
        btn_close.setFixedSize(28, 28)
        btn_close.clicked.connect(self.closed.emit)
        lay.addWidget(btn_close)

        return bar

    def _build_toolbar(self, fc: FontConfig) -> QWidget:
        bar = QWidget()
        bar.setObjectName("EditToolbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(4)

        for label, cmd in _MICRO_COMMANDS:
            btn = QPushButton(label)
            btn.setObjectName("EditToolBtn")
            btn.clicked.connect(lambda _=False, c=cmd: self._on_micro_command(c))
            lay.addWidget(btn)

        # Separateur
        sep = QLabel("|")
        sep.setObjectName("EditToolBtn")
        lay.addWidget(sep)

        # Toggle split / vue unique
        self._btn_split = QPushButton(qta.icon("fa5s.columns", color="#888"), " Split")
        self._btn_split.setObjectName("EditToolBtn")
        self._btn_split.setIconSize(QSize(13, 13))
        self._btn_split.setCheckable(True)
        self._btn_split.setChecked(True)
        self._btn_split.toggled.connect(self._on_toggle_split)
        lay.addWidget(self._btn_split)

        lay.addStretch()
        return bar

    def _build_editor_area(self) -> QSplitter:
        self._split = QSplitter(Qt.Orientation.Horizontal)
        self._split.setChildrenCollapsible(False)
        self._split.setHandleWidth(4)

        # Gauche : editeur markdown brut
        self._md_editor = QPlainTextEdit()
        self._md_editor.setObjectName("MarkdownEditor")
        self._md_editor.setPlaceholderText("Le document apparaitra ici…")
        self._md_editor.textChanged.connect(self._on_text_changed)
        self._split.addWidget(self._md_editor)

        # Droite : rendu HTML live
        self._html_preview = QTextBrowser()
        self._html_preview.setObjectName("HtmlPreview")
        self._html_preview.setOpenExternalLinks(True)
        self._split.addWidget(self._html_preview)

        self._split.setSizes([500, 500])
        return self._split

    def _build_status_bar(self, fc: FontConfig) -> QLabel:
        self._status_lbl = QLabel("Aucun document charge")
        self._status_lbl.setObjectName("EditStatusBar")
        return self._status_lbl

    # ── Chargement / mise a jour document ─────────────────────────────────────

    def load_document(self, doc: EditDocument) -> None:
        """Charge un document dans le panneau."""
        self._doc = doc
        self._title_edit.blockSignals(True)
        self._title_edit.setText(doc.title)
        self._title_edit.blockSignals(False)
        self._md_editor.blockSignals(True)
        self._md_editor.setPlainText(doc.content)
        self._md_editor.blockSignals(False)
        self._refresh_preview()
        self._update_word_count()
        self._update_status()

    def set_content(self, content: str) -> None:
        """
        Met a jour le contenu depuis l'IA (apres backup deja cree par main_window).
        Positionne le curseur au debut.
        """
        if self._doc is None:
            return
        self._doc.content = content
        self._md_editor.blockSignals(True)
        self._md_editor.setPlainText(content)
        self._md_editor.blockSignals(False)
        cursor = self._md_editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self._md_editor.setTextCursor(cursor)
        self._refresh_preview()
        self._update_word_count()
        self._update_status()

    def current_content(self) -> str:
        """Retourne le contenu courant de l'editeur."""
        return self._md_editor.toPlainText()

    def current_title(self) -> str:
        return self._title_edit.text().strip() or "Sans titre"

    def selected_text(self) -> str:
        """Retourne le texte selectionne dans l'editeur, ou le texte complet si rien."""
        sel = self._md_editor.textCursor().selectedText()
        return sel if sel else self._md_editor.toPlainText()

    # ── Handlers internes ─────────────────────────────────────────────────────

    def _on_text_changed(self) -> None:
        if self._doc is not None:
            self._doc.content = self._md_editor.toPlainText()
        self._preview_timer.start()
        self._update_word_count()

    def _on_title_changed(self, text: str) -> None:
        if self._doc is not None:
            self._doc.title = text.strip() or "Sans titre"

    def _on_toggle_split(self, checked: bool) -> None:
        self._html_preview.setVisible(checked)

    def _on_micro_command(self, cmd: str) -> None:
        sel = self.selected_text()
        self.ai_command_requested.emit(cmd, sel)

    def _on_restore_backup(self) -> None:
        if self._doc is None:
            return
        restored = self._store.restore_last_backup(self._doc)
        if restored is not None:
            self.set_content(restored)
            self._update_status()
            logger.info("[EDIT] backup restaure via bouton Back")
        else:
            logger.info("[EDIT] aucun backup disponible")

    def _on_export(self) -> None:
        if self._doc is None:
            return
        title  = self._doc.title.replace(" ", "_")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter le document",
            f"{title}.md",
            "Markdown (*.md);;Texte brut (*.txt);;Tous (*.*)",
        )
        if path:
            self.save_requested.emit(path)

    # ── Rendu preview ─────────────────────────────────────────────────────────

    def _refresh_preview(self) -> None:
        """Convertit le markdown en HTML basique et l'affiche dans la preview."""
        md = self._md_editor.toPlainText()
        self._html_preview.setHtml(_md_to_html(md))

    # ── Compteur de mots / statut ─────────────────────────────────────────────

    def _update_word_count(self) -> None:
        text  = self._md_editor.toPlainText()
        words = len(text.split()) if text.strip() else 0
        self._word_count_lbl.setText(f"{words} mots")

    def _update_status(self) -> None:
        if self._doc is None:
            self._status_lbl.setText("Aucun document charge")
            return
        nb = self._store.backup_count(self._doc.doc_id)
        modified = self._doc.last_modified
        self._status_lbl.setText(
            f"Derniere modification : {modified}   |   Backups disponibles : {nb}/{5}"
        )
        self._btn_back.setEnabled(nb > 0)


# ── Convertisseur Markdown -> HTML (minimal, sans dependance externe) ─────────

def _md_to_html(md: str) -> str:
    """
    Conversion markdown -> HTML minimaliste.
    Couvre : titres H1-H6, gras, italique, code inline, blocs code,
    listes non ordonnees, paragraphes, separateurs.
    """
    lines   = md.split("\n")
    html    = []
    in_code = False
    in_list = False

    for raw in lines:
        line = raw

        # Bloc de code ```
        if line.strip().startswith("```"):
            if in_code:
                html.append("</code></pre>")
                in_code = False
            else:
                if in_list:
                    html.append("</ul>")
                    in_list = False
                html.append("<pre><code>")
                in_code = True
            continue

        if in_code:
            html.append(_html_escape(line))
            continue

        # Fermer liste si la ligne n'est pas un item
        if in_list and not re.match(r"^\s*[-*+] ", line):
            html.append("</ul>")
            in_list = False

        # Titres
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            text  = _inline_md(m.group(2))
            html.append(f"<h{level}>{text}</h{level}>")
            continue

        # Separateur
        if re.match(r"^---+$", line.strip()):
            html.append("<hr>")
            continue

        # Liste non ordonnee
        m = re.match(r"^\s*[-*+] (.*)", line)
        if m:
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{_inline_md(m.group(1))}</li>")
            continue

        # Ligne vide -> saut de paragraphe
        if not line.strip():
            html.append("<br>")
            continue

        # Paragraphe normal
        html.append(f"<p>{_inline_md(line)}</p>")

    if in_list:
        html.append("</ul>")
    if in_code:
        html.append("</code></pre>")

    css = (
        "<style>"
        "body{font-family:sans-serif;font-size:13px;color:#cccccc;background:#252526;padding:8px;}"
        "h1,h2,h3{color:#e0e0e0;} h1{font-size:1.4em;} h2{font-size:1.2em;} h3{font-size:1.1em;}"
        "pre{background:#1e1e1e;padding:8px;border-radius:4px;overflow:auto;}"
        "code{background:#1e1e1e;padding:2px 4px;border-radius:3px;font-family:monospace;}"
        "ul{padding-left:20px;} li{margin:2px 0;}"
        "hr{border:none;border-top:1px solid #3e3e42;margin:10px 0;}"
        "p{margin:4px 0;line-height:1.6;}"
        "</style>"
    )
    return css + "\n".join(html)


def _inline_md(text: str) -> str:
    """Applique le formatage inline (gras, italique, code) sur une ligne."""
    text = _html_escape(text)
    # Gras **...**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italique *...*
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Code `...`
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
