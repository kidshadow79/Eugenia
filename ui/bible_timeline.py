"""
bible_timeline.py — Onglet Événements / Chronologie de la Bible
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt
from core.bible_db import BibleDB
from ui.font_config import FontConfig

_MEM_SOURCES = ("mem_direct", "mem_bible", "clipboard")


def _build_style(fc: FontConfig) -> str:
    return f"""
QTableWidget {{
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: none;
    font-size: {fc.sm}px;
    gridline-color: #3e3e42;
}}
QTableWidget::item {{ padding: 4px 8px; }}
QTableWidget::item:selected {{ background-color: #094771; color: #ffffff; }}
QHeaderView::section {{
    background-color: #252526;
    color: #bbbbbb;
    font-size: {fc.xs}px;
    font-weight: bold;
    padding: 4px 8px;
    border: none;
    border-bottom: 1px solid #3e3e42;
}}
QLabel#EmptyHint {{ color: #555555; font-size: {fc.sm}px; }}
"""


class BibleTimelineWidget(QWidget):
    """Onglet Événements — tableau titre / description."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(_build_style(FontConfig.instance()))
        self._bible_db: BibleDB | None = None
        self._setup_ui()

    def apply_font_config(self, fc: FontConfig) -> None:
        self.setStyleSheet(_build_style(fc))

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._empty_hint = QLabel("Aucun événement dans la Bible.\nEnvoyez du texte via le presse-papiers pour l'alimenter.")
        self._empty_hint.setObjectName("EmptyHint")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setWordWrap(True)
        layout.addWidget(self._empty_hint)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Événement", "Description", ""])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(2, 60)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setWordWrap(True)
        self._table.hide()
        layout.addWidget(self._table)

    def refresh(self, bible_db: BibleDB) -> None:
        self._bible_db = bible_db
        rows = bible_db.get_all("events")
        if not rows:
            self._table.hide()
            self._empty_hint.show()
            return
        self._empty_hint.hide()
        self._table.show()
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(r["label"]))
            self._table.setItem(i, 1, QTableWidgetItem(r["content"]))
            src = r.get("source_chunk") or ""
            can_delete = any(src.startswith(s) for s in _MEM_SOURCES) or src == ""
            btn = QPushButton("x")
            btn.setEnabled(can_delete)
            btn.setToolTip("Supprimer" if can_delete else "Source protegee")
            btn.setFixedWidth(40)
            label = r["label"]
            btn.clicked.connect(lambda _, lb=label: self._delete(lb))
            self._table.setCellWidget(i, 2, btn)
        self._table.resizeRowsToContents()

    def _delete(self, label: str) -> None:
        if self._bible_db is None:
            return
        reply = QMessageBox.question(
            self, "Supprimer", f"Supprimer '{label}' de la Bible ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._bible_db.delete("events", label)
            self.refresh(self._bible_db)
