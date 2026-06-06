"""
stats_panel.py — Panneau Statistiques (page du ContextPanel)

Deux sections :
  - Documents suivis : liste des .docx déposés avec leurs stats
  - Stats personnalisées : stats créées via /stat

Chaque ligne = titre + valeur résumée.
Clic sur une ligne → overlay graphique (StatsChartOverlay).

Signaux publics :
  doc_dropped(path: str)                      — fichier .docx déposé dans la zone
  refresh_requested()                         — bouton Rafraichir
  chart_requested(kind: str, item_id: str)    — clic sur un item ("doc" ou "custom")
  delete_requested(kind: str, item_id: str)   — suppression d'un item
"""

import logging
from pathlib import Path

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.stats_engine import CustomStatEntry, DocStatEntry
from core.i18n import tr

logger = logging.getLogger(__name__)


class _DropZone(QWidget):
    """Petite zone drag-and-drop pour un .docx."""

    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setFixedHeight(52)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label = QLabel(tr("Glisser un .docx ici"))
        self._label.setObjectName("DropLabel")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

    def _set_drag_over(self, active: bool) -> None:
        self.setProperty("drag_over", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._extract_docx(event):
            event.acceptProposedAction()
            self._set_drag_over(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_over(False)
        paths = self._extract_docx(event)
        if paths:
            event.acceptProposedAction()
            self.file_dropped.emit(paths[0])
        else:
            event.ignore()

    @staticmethod
    def _extract_docx(event) -> list[str]:
        paths = []
        if not event.mimeData().hasUrls():
            return paths
        for url in event.mimeData().urls():
            if url.isLocalFile():
                p = url.toLocalFile()
                if Path(p).suffix.lower() == ".docx":
                    paths.append(p)
        return paths


class StatsPanel(QWidget):
    """Panneau de statistiques — zone gauche de l'interface."""

    doc_dropped       = pyqtSignal(str)          # chemin .docx
    refresh_requested = pyqtSignal()
    chart_requested   = pyqtSignal(str, str)     # kind ("doc"|"custom"), item_id
    delete_requested  = pyqtSignal(str, str)     # kind ("doc"|"custom"), item_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatsPanelRoot")
        self.setAcceptDrops(True)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(6, 4, 6, 4)
        inner_layout.setSpacing(6)

        # ── Zone dépôt ──────────────────────────────────────────────
        self._drop_zone = _DropZone()
        self._drop_zone.file_dropped.connect(self.doc_dropped)
        inner_layout.addWidget(self._drop_zone)

        # ── Section Sources pour /stat ────────────────────────────
        hdr_sources = QLabel(tr("SOURCES POUR /STAT"))
        hdr_sources.setObjectName("SectionHeader")
        inner_layout.addWidget(hdr_sources)

        sources_row = QHBoxLayout()
        sources_row.setContentsMargins(8, 2, 8, 2)
        sources_row.setSpacing(14)
        self._cb_docs = QCheckBox(tr("Docs importés"))
        self._cb_docs.setObjectName("StatSource")
        self._cb_docs.setChecked(True)
        self._cb_docs.setToolTip(tr("Injecter le contenu des documents suivis lors d'un /stat"))
        sources_row.addWidget(self._cb_docs)
        self._cb_bible = QCheckBox(tr("Bible"))
        self._cb_bible.setObjectName("StatSource")
        self._cb_bible.setChecked(False)
        self._cb_bible.setToolTip(tr("Injecter la Bible complète du projet lors d'un /stat"))
        sources_row.addWidget(self._cb_bible)
        sources_row.addStretch()
        inner_layout.addLayout(sources_row)

        # Bouton parcourir
        browse_row = QHBoxLayout()
        browse_row.setContentsMargins(0, 0, 0, 0)
        browse_row.addStretch()
        self._browse_btn = QPushButton(tr("Parcourir..."))
        self._browse_btn.setObjectName("BtnBrowse")
        self._browse_btn.setIcon(qta.icon("fa5s.archive", color="#888888"))
        self._browse_btn.setIconSize(QSize(12, 12))
        self._browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._browse_btn.clicked.connect(self._on_browse)
        browse_row.addWidget(self._browse_btn)
        inner_layout.addLayout(browse_row)

        # ── Section Documents suivis ─────────────────────────────────
        hdr_docs = QLabel(tr("DOCUMENTS SUIVIS"))
        hdr_docs.setObjectName("SectionHeader")
        inner_layout.addWidget(hdr_docs)

        self._docs_list = QListWidget()
        self._docs_list.setObjectName("StatsList")
        self._docs_list.setMaximumHeight(200)
        self._docs_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self._docs_list.itemDoubleClicked.connect(
            lambda item: self._emit_chart("doc", item.data(Qt.ItemDataRole.UserRole))
        )
        self._docs_list.currentRowChanged.connect(
            lambda _: self._update_doc_delete_state()
        )
        inner_layout.addWidget(self._docs_list)

        self._docs_empty = QLabel(tr("Aucun document suivi."))
        self._docs_empty.setObjectName("EmptyHint")
        inner_layout.addWidget(self._docs_empty)

        doc_btn_row = QHBoxLayout()
        doc_btn_row.setContentsMargins(0, 0, 0, 0)
        self._doc_chart_btn = QPushButton()
        self._doc_chart_btn.setObjectName("BtnRefresh")
        self._doc_chart_btn.setIcon(qta.icon("fa5s.chart-line", color="#888888"))
        self._doc_chart_btn.setIconSize(QSize(12, 12))
        self._doc_chart_btn.setToolTip(tr("Voir le graphique"))
        self._doc_chart_btn.setEnabled(False)
        self._doc_chart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._doc_chart_btn.clicked.connect(self._on_doc_chart_click)
        doc_btn_row.addWidget(self._doc_chart_btn)
        doc_btn_row.addStretch()
        self._doc_delete_btn = QPushButton()
        self._doc_delete_btn.setObjectName("BtnDelete")
        self._doc_delete_btn.setIcon(qta.icon("fa5s.trash-alt", color="#c94f4f"))
        self._doc_delete_btn.setIconSize(QSize(12, 12))
        self._doc_delete_btn.setToolTip(tr("Supprimer ce document et ses stats"))
        self._doc_delete_btn.setEnabled(False)
        self._doc_delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._doc_delete_btn.clicked.connect(self._on_doc_delete_click)
        doc_btn_row.addWidget(self._doc_delete_btn)
        inner_layout.addLayout(doc_btn_row)

        # ── Séparateur ───────────────────────────────────────────────
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #3e3e42;")
        inner_layout.addWidget(sep)

        # ── Section Stats personnalisées ─────────────────────────────
        hdr_custom = QLabel(tr("STATS PERSONNALISEES"))
        hdr_custom.setObjectName("SectionHeader")
        inner_layout.addWidget(hdr_custom)

        hint = QLabel(tr('Utilisez /stat dans le chat pour créer une stat.'))
        hint.setObjectName("EmptyHint")
        hint.setWordWrap(True)
        inner_layout.addWidget(hint)

        self._custom_list = QListWidget()
        self._custom_list.setObjectName("StatsList")
        self._custom_list.setMaximumHeight(200)
        self._custom_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self._custom_list.itemDoubleClicked.connect(
            lambda item: self._emit_chart("custom", item.data(Qt.ItemDataRole.UserRole))
        )
        self._custom_list.currentRowChanged.connect(
            lambda _: self._update_custom_delete_state()
        )
        inner_layout.addWidget(self._custom_list)

        self._custom_empty = QLabel(tr("Aucune stat personnalisée."))
        self._custom_empty.setObjectName("EmptyHint")
        inner_layout.addWidget(self._custom_empty)

        custom_btn_row = QHBoxLayout()
        custom_btn_row.setContentsMargins(0, 0, 0, 0)
        self._custom_chart_btn = QPushButton()
        self._custom_chart_btn.setObjectName("BtnRefresh")
        self._custom_chart_btn.setIcon(qta.icon("fa5s.chart-pie", color="#888888"))
        self._custom_chart_btn.setIconSize(QSize(12, 12))
        self._custom_chart_btn.setToolTip(tr("Voir le graphique"))
        self._custom_chart_btn.setEnabled(False)
        self._custom_chart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._custom_chart_btn.clicked.connect(self._on_custom_chart_click)
        custom_btn_row.addWidget(self._custom_chart_btn)
        custom_btn_row.addStretch()
        self._custom_delete_btn = QPushButton()
        self._custom_delete_btn.setObjectName("BtnDelete")
        self._custom_delete_btn.setIcon(qta.icon("fa5s.trash-alt", color="#c94f4f"))
        self._custom_delete_btn.setIconSize(QSize(12, 12))
        self._custom_delete_btn.setToolTip(tr("Supprimer cette stat"))
        self._custom_delete_btn.setEnabled(False)
        self._custom_delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._custom_delete_btn.clicked.connect(self._on_custom_delete_click)
        custom_btn_row.addWidget(self._custom_delete_btn)
        inner_layout.addLayout(custom_btn_row)

        inner_layout.addStretch()

        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        # ── Pied : bouton Rafraîchir ─────────────────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(6, 2, 6, 2)
        footer.addStretch()
        self._refresh_btn = QPushButton(tr("Rafraichir"))
        self._refresh_btn.setObjectName("BtnRefresh")
        self._refresh_btn.setIcon(qta.icon("fa5s.sync-alt", color="#888888"))
        self._refresh_btn.setIconSize(QSize(12, 12))
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self.refresh_requested)
        footer.addWidget(self._refresh_btn)
        root.addLayout(footer)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    @property
    def use_docs(self) -> bool:
        """True si la case 'Docs importés' est cochée."""
        return self._cb_docs.isChecked()

    @property
    def use_bible(self) -> bool:
        """True si la case 'Bible' est cochée."""
        return self._cb_bible.isChecked()

    def refresh_display(
        self,
        doc_stats: list[DocStatEntry],
        custom_stats: list[CustomStatEntry],
    ) -> None:
        """Met à jour les deux listes d'affichage."""
        self._populate_docs(doc_stats)
        self._populate_customs(custom_stats)

    # ------------------------------------------------------------------
    # Peuplement des listes
    # ------------------------------------------------------------------

    def _populate_docs(self, entries: list[DocStatEntry]) -> None:
        self._docs_list.clear()
        has = bool(entries)
        self._docs_list.setVisible(has)
        self._docs_empty.setVisible(not has)
        for entry in entries:
            wc = entry.latest_word_count
            delta = entry.word_count_delta
            wc_str = f"{wc:,}" if wc is not None else "—"
            if delta is not None:
                sign = "+" if delta >= 0 else ""
                wc_str += f"  ({sign}{delta:,})"
            mots_text = tr("mots")
            text = f"{entry.title}\n{wc_str} {mots_text}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, entry.doc_id)
            item.setToolTip(tr("Double-clic pour ouvrir le graphique\n{}").format(entry.path))
            self._docs_list.addItem(item)
        self._update_doc_delete_state()

    def _populate_customs(self, entries: list[CustomStatEntry]) -> None:
        self._custom_list.clear()
        has = bool(entries)
        self._custom_list.setVisible(has)
        self._custom_empty.setVisible(not has)
        for entry in entries:
            text = f"{entry.name}\n{entry.summary_value}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, entry.stat_id)
            item.setToolTip(tr("Double-clic pour ouvrir le graphique\n{}").format(entry.description))
            self._custom_list.addItem(item)
        self._update_custom_delete_state()

    # ------------------------------------------------------------------
    # Gestion des états de boutons
    # ------------------------------------------------------------------

    def _update_doc_delete_state(self) -> None:
        has_selection = self._docs_list.currentRow() >= 0
        self._doc_delete_btn.setEnabled(has_selection)
        self._doc_chart_btn.setEnabled(has_selection)

    def _update_custom_delete_state(self) -> None:
        has_selection = self._custom_list.currentRow() >= 0
        self._custom_delete_btn.setEnabled(has_selection)
        self._custom_chart_btn.setEnabled(has_selection)

    # ------------------------------------------------------------------
    # Émission de signaux
    # ------------------------------------------------------------------

    def _emit_chart(self, kind: str, item_id: str) -> None:
        if item_id:
            self.chart_requested.emit(kind, item_id)

    def _on_doc_chart_click(self) -> None:
        item = self._docs_list.currentItem()
        if item:
            self._emit_chart("doc", item.data(Qt.ItemDataRole.UserRole))

    def _on_custom_chart_click(self) -> None:
        item = self._custom_list.currentItem()
        if item:
            self._emit_chart("custom", item.data(Qt.ItemDataRole.UserRole))

    def _on_doc_delete_click(self) -> None:
        item = self._docs_list.currentItem()
        if item:
            self.delete_requested.emit("doc", item.data(Qt.ItemDataRole.UserRole))

    def _on_custom_delete_click(self) -> None:
        item = self._custom_list.currentItem()
        if item:
            self.delete_requested.emit("custom", item.data(Qt.ItemDataRole.UserRole))

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Sélectionner un document"), "", tr("Documents Word (*.docx)")
        )
        if path:
            self.doc_dropped.emit(path)
