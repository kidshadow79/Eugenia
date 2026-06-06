"""
bible_panel.py — Panneau Bible avec onglets dynamiques

Les onglets sont générés à partir des catégories du projet (bible_db._tables).
Chaque catégorie utilise le widget générique _BibleTableWidget.

Usage :
    panel = BiblePanel()
    panel.set_bible_db(archiviste.bible_db)
    archiviste.bible_updated.connect(panel.on_bible_updated)
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QMessageBox,
    QDialog, QLineEdit, QTextEdit, QDialogButtonBox, QFormLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor
import qtawesome as qta

from core.bible_db import BibleDB
from core.project_types import get_category, DEFAULT_CATEGORIES
from ui.font_config import FontConfig
from core.i18n import tr


def _build_table_style(fc: FontConfig) -> str:
    return f"""
QPushButton#DeleteRowBtn {{
    background-color: transparent;
    color: #f48771;
    border: none;
    font-size: {fc.size}px;
    padding: 0px;
}}
QPushButton#DeleteRowBtn:hover {{ color: #ff6b6b; }}
QLabel#EmptyHint {{ color: #888888; font-size: {fc.sm}px; }}
QPushButton#AddEntryBtn {{
    background-color: transparent;
    color: #888888;
    border: none;
    font-size: {fc.xs}px;
    padding: 2px 8px;
}}
QPushButton#AddEntryBtn:hover {{ color: #aaaaaa; }}
"""



# Mapping catégorie → icône qtawesome
_CAT_ICONS = {
    "characters":      "fa5s.mask",
    "places":          "fa5s.compass",
    "events":          "fa5s.bolt",
    "decisions":       "fa5s.directions",
    "contradictions":  "fa5s.puzzle-piece",
    "themes":          "fa5s.theater-masks",
    "objects":         "fa5s.key",
    "concepts":        "fa5s.atom",
    "sources":         "fa5s.bookmark",
    "authors_cited":   "fa5s.quote-right",
    "hypotheses":      "fa5s.vial",
    "components":      "fa5s.cubes",
    "risks":           "fa5s.shield-alt",
}

# Entrées protégées contre la suppression manuelle (insérées par l'IA)
_MEM_SOURCES = ("mem_direct", "mem_bible", "clipboard")


# ─────────────────────────────────────────────────────────────────────────────
# Widget générique de table Bible
# ─────────────────────────────────────────────────────────────────────────────

class _BibleTableWidget(QWidget):
    """
    Table générique pour n'importe quelle catégorie Bible.
    col_headers : [header_label, header_content]
    """

    entry_changed = pyqtSignal()  # émis après add / edit / delete

    def __init__(self, table_key: str, col_headers: list[str],
                 empty_hint: str, parent=None):
        super().__init__(parent)
        self._table_key = table_key
        self._col_headers = col_headers
        self._empty_hint_text = empty_hint or tr("Aucune entrée dans « {} ».").format(table_key)
        self._bible_db: BibleDB | None = None
        self.setStyleSheet(_build_table_style(FontConfig.instance()))
        self._setup_ui()

    def apply_font_config(self, fc: FontConfig) -> None:
        self.setStyleSheet(_build_table_style(fc))

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._empty_hint = QLabel(self._empty_hint_text)
        self._empty_hint.setObjectName("EmptyHint")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setWordWrap(True)
        layout.addWidget(self._empty_hint)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(
            [tr(self._col_headers[0]), tr(self._col_headers[1]) if len(self._col_headers) > 1 else tr("Détail"), ""]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Fixed
        )
        self._table.setColumnWidth(2, 32)
        self._table.verticalHeader().setDefaultSectionSize(34)
        self._table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table.hide()
        layout.addWidget(self._table)

        add_bar = QHBoxLayout()
        add_bar.setContentsMargins(8, 4, 8, 4)
        add_bar.addStretch()
        self._add_btn = QPushButton(tr(" Ajouter"))
        self._add_btn.setObjectName("AddEntryBtn")
        self._add_btn.setIcon(qta.icon("fa5s.plus", color="#888888"))
        self._add_btn.clicked.connect(self._add_entry)
        add_bar.addWidget(self._add_btn)
        layout.addLayout(add_bar)

    # ─── API publique ─────────────────────────────────────────────────────────

    def refresh(self, bible_db: BibleDB) -> None:
        self._bible_db = bible_db
        rows = bible_db.get_all(self._table_key)
        self._table.setRowCount(0)

        if not rows:
            self._empty_hint.show()
            self._table.hide()
            return

        self._empty_hint.hide()
        self._table.show()

        for row_data in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            label   = row_data.get("label", "")
            content = row_data.get("content", "")
            source  = row_data.get("source_chunk", "") or ""

            item_label = QTableWidgetItem(label)
            item_label.setFlags(item_label.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, 0, item_label)

            item_content = QTableWidgetItem(content)
            item_content.setFlags(item_content.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(r, 1, item_content)

            # Bouton suppression (grisé si source protégée)
            is_protected = any(s in source for s in _MEM_SOURCES)
            del_btn = QPushButton()
            del_btn.setObjectName("DeleteRowBtn")
            del_btn.setIcon(qta.icon("fa5s.trash-alt", color="#888888"))
            del_btn.setFixedSize(24, 24)
            del_btn.setEnabled(not is_protected)
            del_btn.setToolTip(
                tr("Entrée protégée (mémoire IA)") if is_protected
                else tr("Supprimer « {} »").format(label)
            )
            captured_label = label
            del_btn.clicked.connect(lambda _, lbl=captured_label: self._delete_row(lbl))
            self._table.setCellWidget(r, 2, del_btn)

    # ─── Interne ──────────────────────────────────────────────────────────────

    def _delete_row(self, label: str) -> None:
        if self._bible_db is None:
            return
        reply = QMessageBox.question(
            self,
            tr("Supprimer l'entrée"),
            tr("Supprimer « {} » de la Bible ?\nCette action est irréversible.").format(label),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._bible_db.delete(self._table_key, label)
            self.refresh(self._bible_db)
            self.entry_changed.emit()

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if self._bible_db is None:
            return
        label_item = self._table.item(row, 0)
        content_item = self._table.item(row, 1)
        if label_item is None:
            return
        self._edit_entry(label_item.text(), content_item.text() if content_item else "")

    def _entry_dialog(self, title: str,
                       label_init: str = "", content_init: str = "") -> tuple | None:
        """Ouvre un dialog add/edit. Retourne (label, content) ou None si annulé."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(420)
        form = QFormLayout(dlg)
        form.setSpacing(8)
        form.setContentsMargins(12, 12, 12, 12)
        label_edit = QLineEdit(label_init)
        label_edit.setPlaceholderText(tr("Ex : Elara, Château de Verre, ..."))
        form.addRow(tr("Label :"), label_edit)
        content_edit = QTextEdit(content_init)
        content_edit.setMinimumHeight(90)
        content_edit.setPlaceholderText(tr("Description détaillée..."))
        form.addRow(tr("Contenu :"), content_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            lbl = label_edit.text().strip()
            cnt = content_edit.toPlainText().strip()
            if lbl and cnt:
                return lbl, cnt
        return None

    def _add_entry(self) -> None:
        if self._bible_db is None:
            return
        result = self._entry_dialog(tr("Ajouter dans « {} »").format(tr(self._table_key)))
        if result:
            label, content = result
            self._bible_db.upsert(self._table_key, label, content, source_chunk="manual")
            self.refresh(self._bible_db)
            self.entry_changed.emit()

    def _edit_entry(self, old_label: str, old_content: str) -> None:
        if self._bible_db is None:
            return
        result = self._entry_dialog(
            tr("Modifier « {} »").format(old_label),
            label_init=old_label,
            content_init=old_content,
        )
        if result:
            new_label, new_content = result
            if new_label != old_label:
                self._bible_db.delete(self._table_key, old_label)
            self._bible_db.upsert(self._table_key, new_label, new_content, source_chunk="manual")
            self.refresh(self._bible_db)
            self.entry_changed.emit()

# ─────────────────────────────────────────────────────────────────────────────
# BiblePanel
# ─────────────────────────────────────────────────────────────────────────────

class BiblePanel(QWidget):
    """Panneau principal Bible — onglets générés dynamiquement."""

    bible_manually_changed = pyqtSignal()  # add / edit / delete manuel → sync FAISS

    def __init__(self):
        super().__init__()
        self._bible_db: BibleDB | None = None
        self._tab_widgets: dict[str, _BibleTableWidget] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.setDocumentMode(True)
        self._tabs.setIconSize(QSize(16, 16))

        layout.addWidget(self._tabs)

    # ─── Construction des onglets ─────────────────────────────────────────────

    def _build_tabs(self, tables: list[str]) -> None:
        """Génère les onglets à partir de la liste de tables du projet."""
        self._tabs.clear()
        self._tab_widgets.clear()

        for key in tables:
            cat = get_category(key)
            if cat is None:
                cat = {
                    "tab_label":   tr(key.capitalize()),
                    "col_headers": ["Label", "Contenu"],
                    "empty_hint":  tr("Aucune entrée dans « {} ».").format(key),
                }
            w = _BibleTableWidget(
                table_key=key,
                col_headers=cat["col_headers"],
                empty_hint=tr(cat["empty_hint"]),
            )
            w.entry_changed.connect(self.bible_manually_changed)
            self._tab_widgets[key] = w
            idx = self._tabs.addTab(w, tr(cat["tab_label"]))
            # Icône qtawesome sur l'onglet
            icon_name = _CAT_ICONS.get(key)
            if icon_name:
                self._tabs.setTabIcon(idx, qta.icon(icon_name, color="#888888"))

    # ─── API publique ─────────────────────────────────────────────────────────

    def set_bible_db(self, bible_db: BibleDB) -> None:
        """
        Connecte la Bible et génère les onglets selon les catégories du projet.
        Appeler une fois après création de l'Archiviste.
        """
        self._bible_db = bible_db
        self._build_tabs(list(bible_db._tables))
        self._refresh_all()

    def on_bible_updated(self, table: str, total: int) -> None:
        """Connecter à archiviste.bible_updated. Rafraîchit l'onglet concerné."""
        if self._bible_db is None:
            return
        w = self._tab_widgets.get(table)
        if w:
            w.refresh(self._bible_db)
        # Badge numérique sur l'onglet contradictions
        if table == "contradictions" and table in self._tab_widgets:
            keys = list(self._tab_widgets.keys())
            idx = keys.index("contradictions")
            cat = get_category("contradictions")
            base_label = cat["tab_label"] if cat else "⚠ Contra."
            label = f"{base_label} ({total})" if total > 0 else base_label
            self._tabs.setTabText(idx, label)

    def _refresh_all(self) -> None:
        if self._bible_db is None:
            return
        for w in self._tab_widgets.values():
            w.refresh(self._bible_db)

    def apply_font_config(self, fc: FontConfig) -> None:
        for w in self._tab_widgets.values():
            w.apply_font_config(fc)

