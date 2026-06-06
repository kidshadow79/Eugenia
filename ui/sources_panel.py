"""
SourcesPanel -- Panneau Sources (page du ContextPanel)

Affiche la liste des documents ingeres avec :
- nom du fichier
- date d'ingest
- nombre de chunks
- bouton "Re-ingerer" (relance l'ingest dialog sur ce fichier)
- bouton "Supprimer" (retire de la Bible + du store)

Signaux publics :
  reingest_requested(source_id: str, path: str)
"""

import logging
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QCheckBox, QDialog, QDialogButtonBox, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QBrush, QColor, QFont
import qtawesome as qta

from core.source_store import SourceStore
from ui.font_config import FontConfig
from core.i18n import tr

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Dialog de confirmation de suppression
# ──────────────────────────────────────────────────────────────────────────────

class _DeleteSourceDialog(QDialog):
    """
    Dialog de confirmation avant suppression d'un document source.
    Deux options independantes :
      - retirer de la librairie (toujours effectue)
      - supprimer la memoire vectorielle FAISS associee
    """

    def __init__(self, filename: str, nb_chunks: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Supprimer la source"))
        self.setModal(True)
        self.setFixedWidth(420)
        self.setStyleSheet(_build_dialog_dark_style(FontConfig.instance()))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # Titre
        title = QLabel(tr("Supprimer « {} » ?").format(filename))
        title.setObjectName("Title")
        title.setWordWrap(True)
        layout.addWidget(title)

        # Sous-titre
        sub = QLabel(tr("Ce document sera retire de la librairie."))
        sub.setObjectName("Sub")
        layout.addWidget(sub)

        # Avertissement Bible
        bible_warn = QLabel(
            tr("⚠️ Si vous supprimez aussi la memoire vectorielle,\n"
               "les entrees de la Bible issues de ce document\n"
               "(personnages, lieux, evenements...) seront egalement supprimees.")
        )
        bible_warn.setObjectName("Sub")
        bible_warn.setWordWrap(True)
        layout.addWidget(bible_warn)

        # Separateur visuel
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #3e3e3e;")
        layout.addWidget(sep)

        # Case memoire FAISS
        blocs_label = tr("{} bloc").format(nb_chunks) if nb_chunks <= 1 else tr("{} blocs").format(nb_chunks)
        self._chk_memory = QCheckBox(
            tr("Supprimer aussi la memoire vectorielle associee\n({} FAISS lies a ce document)").format(blocs_label)
        )
        self._chk_memory.setChecked(True)
        layout.addWidget(self._chk_memory)

        # Boutons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        delete_btn = btn_box.addButton(tr("Supprimer"), QDialogButtonBox.ButtonRole.AcceptRole)
        delete_btn.setProperty("danger", "true")
        delete_btn.style().unpolish(delete_btn)
        delete_btn.style().polish(delete_btn)
        btn_box.rejected.connect(self.reject)
        delete_btn.clicked.connect(self.accept)
        layout.addWidget(btn_box)

    @property
    def remove_memory(self) -> bool:
        return self._chk_memory.isChecked()


class _DeleteOrphanDialog(QDialog):
    """
    Dialog de confirmation avant suppression definitive d'une memoire FAISS orpheline.
    Affiche quand le document source a ete retire mais la memoire FAISS conservee.
    """

    def __init__(self, filename: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Supprimer la memoire"))
        self.setModal(True)
        self.setFixedWidth(420)
        self.setStyleSheet(_build_dialog_dark_style(FontConfig.instance()))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        title = QLabel(tr("Supprimer la memoire de « {} » ?").format(filename))
        title.setObjectName("Title")
        title.setWordWrap(True)
        layout.addWidget(title)

        sub = QLabel(
            tr("Ce document est conserve uniquement en memoire vectorielle (FAISS).\n"
               "Cette suppression est definitive et supprimera egalement\n"
               "les entrees de la Bible issues de ce document\n"
               "(personnages, lieux, evenements...).")
        )
        sub.setObjectName("Sub")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #3e3e3e;")
        layout.addWidget(sep)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        delete_btn = btn_box.addButton(tr("Supprimer"), QDialogButtonBox.ButtonRole.AcceptRole)
        delete_btn.setProperty("danger", "true")
        delete_btn.style().unpolish(delete_btn)
        delete_btn.style().polish(delete_btn)
        btn_box.rejected.connect(self.reject)
        delete_btn.clicked.connect(self.accept)
        layout.addWidget(btn_box)

SOURCES_STYLE = None  # conservé pour compatibilité ascendante


def _build_sources_style(fc: "FontConfig") -> str:
    return f"""
QListWidget {{ font-size: {fc.sm}px; }}
QPushButton#SrcBtn {{ font-size: {fc.sm}px; }}
QPushButton#SrcBtnDanger {{ font-size: {fc.sm}px; }}
QLabel#EmptyLabel {{ font-size: {fc.sm}px; }}
QLabel#DropOverlay {{
    font-size: {fc.lg}px;
    background-color: rgba(14, 99, 156, 120);
    color: #4ec9b0;
    font-weight: bold;
    border: 2px dashed #4ec9b0;
    border-radius: 4px;
}}
"""

_DIALOG_DARK_STYLE = None  # conservé pour compatibilité interne


def _build_dialog_dark_style(fc: "FontConfig") -> str:
    return f"""
QDialog {{
    background-color: #252526;
}}
QLabel#Title {{
    color: #e0e0e0;
    font-size: {fc.size}px;
    font-weight: bold;
}}
QLabel#Sub {{
    color: #aaaaaa;
    font-size: {fc.xs}px;
}}
QCheckBox {{
    color: #cccccc;
    font-size: {fc.sm}px;
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid #555;
    border-radius: 3px;
    background-color: #1e1e1e;
}}
QCheckBox::indicator:checked {{
    background-color: #e07070;
    border-color: #c05050;
}}
QPushButton {{
    background-color: #2d2d2d;
    color: #cccccc;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 5px 16px;
    font-size: {fc.sm}px;
    min-width: 80px;
}}
QPushButton:hover {{ background-color: #3e3e3e; }}
QPushButton[danger="true"] {{
    background-color: #5a1f1f;
    color: #e07070;
    border-color: #7a3535;
}}
QPushButton[danger="true"]:hover {{ background-color: #7a2a2a; }}
"""


class SourcesPanel(QWidget):
    reingest_requested    = pyqtSignal(str, str)   # source_id, path
    import_requested      = pyqtSignal()            # bouton Importer un document
    import_path_requested = pyqtSignal(str)         # glisser-deposer : chemin complet
    remove_requested      = pyqtSignal(str, bool)   # source_id, remove_memory
    mute_requested        = pyqtSignal(str)         # source_id : bascule sourdine
    edit_open_requested   = pyqtSignal(str)         # doc_id : ouvrir doc edite
    delete_edit_doc_requested = pyqtSignal(str)     # doc_id : supprimer doc edite

    def __init__(self):
        super().__init__()
        self.setObjectName("SourcesPanel")
        self.setStyleSheet(_build_sources_style(FontConfig.instance()))
        self._store: SourceStore | None = None
        self.setAcceptDrops(True)
        self._setup_ui()
        self._setup_drop_overlay()

    def apply_font_config(self, fc: FontConfig) -> None:
        self.setStyleSheet(_build_sources_style(fc))

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def set_store(self, store: SourceStore) -> None:
        """Branche le store. Appele par MainWindow."""
        self._store = store
        self._refresh()

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(4)

        self._empty_label = QLabel(tr("Aucun document ingere.\n\nUtilisez l'icone Sources\npour importer un .docx."))
        self._empty_label.setObjectName("EmptyLabel")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._list = QListWidget()
        layout.addWidget(self._list)

        # Bouton Importer
        import_btn = QPushButton(tr("+ Importer un document .docx"))
        import_btn.setObjectName("SrcBtn")
        import_btn.clicked.connect(self.import_requested)
        import_layout = QHBoxLayout()
        import_layout.setContentsMargins(8, 0, 8, 0)
        import_layout.addWidget(import_btn)
        layout.addLayout(import_layout)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setContentsMargins(8, 4, 8, 8)

        self._reingest_btn = QPushButton(tr("Re-ingerer"))
        self._reingest_btn.setObjectName("SrcBtn")
        self._reingest_btn.setEnabled(False)
        self._reingest_btn.clicked.connect(self._on_reingest)

        self._mute_btn = QPushButton(tr("Sourdine"))
        self._mute_btn.setIcon(qta.icon("fa5s.volume-mute", color="white"))
        self._mute_btn.setObjectName("SrcBtn")
        self._mute_btn.setToolTip(
            tr("Met ce document en sourdine : il reste en mémoire mais\n"
               "n'est plus injecté dans le contexte des conversations.")
        )
        self._mute_btn.clicked.connect(self._on_mute)

        self._remove_btn = QPushButton(tr("Supprimer"))
        self._remove_btn.setObjectName("SrcBtnDanger")
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._on_remove)

        btn_row.addWidget(self._reingest_btn)
        btn_row.addWidget(self._mute_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._remove_btn)
        layout.addLayout(btn_row)

        self._list.currentItemChanged.connect(self._on_selection_changed)

        # ── Section Documents edites ──────────────────────────────────────────
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #3e3e42;")
        layout.addWidget(sep)

        edit_header = QLabel(tr("Documents edites"))
        edit_header.setObjectName("EmptyLabel")
        edit_header.setAlignment(Qt.AlignmentFlag.AlignLeft)
        edit_header.setStyleSheet("color: #888888; font-size: 11px; padding: 4px 8px 2px 8px;")
        layout.addWidget(edit_header)

        self._edit_list = QListWidget()
        self._edit_list.setMaximumHeight(160)
        self._edit_list.setToolTip(tr("Double-clic pour rouvrir un document en mode edition"))
        self._edit_list.itemDoubleClicked.connect(self._on_edit_doc_double_clicked)
        self._edit_list.currentItemChanged.connect(
            lambda cur, _: self._edit_delete_btn.setEnabled(cur is not None)
        )
        layout.addWidget(self._edit_list)

        edit_btn_row = QHBoxLayout()
        edit_btn_row.setContentsMargins(8, 2, 8, 6)
        edit_btn_row.addStretch()
        self._edit_delete_btn = QPushButton(tr("Supprimer"))
        self._edit_delete_btn.setObjectName("SrcBtnDanger")
        self._edit_delete_btn.setEnabled(False)
        self._edit_delete_btn.setToolTip(tr("Supprimer definitivement ce document edite"))
        self._edit_delete_btn.clicked.connect(self._on_edit_doc_delete)
        edit_btn_row.addWidget(self._edit_delete_btn)
        layout.addLayout(edit_btn_row)

        self._edit_empty_lbl = QLabel(tr("Aucun document edite."))
        self._edit_empty_lbl.setObjectName("EmptyLabel")
        self._edit_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit_empty_lbl.hide()
        layout.addWidget(self._edit_empty_lbl)

    def _setup_drop_overlay(self) -> None:
        """Cree le label overlay affiche pendant un glisser-deposer valide."""
        self._drop_overlay = QLabel(tr("↓  Deposer le .docx ici"), self)
        self._drop_overlay.setObjectName("DropOverlay")
        self._drop_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_overlay.hide()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._drop_overlay.setGeometry(0, 0, self.width(), self.height())

    # ------------------------------------------------------------------
    # Drag & Drop
    # ------------------------------------------------------------------

    @staticmethod
    def _docx_paths_from_event(event) -> list[str]:
        """Extrait les chemins .docx valides depuis l'evenement drag."""
        paths = []
        if not event.mimeData().hasUrls():
            return paths
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if Path(path).suffix.lower() == ".docx":
                    paths.append(path)
        return paths

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._docx_paths_from_event(event):
            event.acceptProposedAction()
            self._drop_overlay.show()
            self._drop_overlay.raise_()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._docx_paths_from_event(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._drop_overlay.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._drop_overlay.hide()
        paths = self._docx_paths_from_event(event)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        if len(paths) > 1:
            logger.warning(
                "SourcesPanel.dropEvent — %d fichiers deposes, seul le premier sera importe",
                len(paths),
            )
        self.import_path_requested.emit(paths[0])

    # ------------------------------------------------------------------
    # Rafraichissement
    # ------------------------------------------------------------------

    def _refresh(self):
        self._list.clear()
        if self._store is None:
            return
        sources = self._store.list_sources()
        # Masquer le label vide s'il reste des orphelins (ils comptent)
        non_orphan = [s for s in sources if not s.get("orphan", False)]
        self._empty_label.setVisible(len(sources) == 0)
        self._list.setVisible(len(sources) > 0)
        for s in sources:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s["source_id"])
            is_orphan = s.get("orphan", False)
            item.setData(Qt.ItemDataRole.UserRole + 1, is_orphan)
            ts = s.get("ingested_at", "")[:16].replace("T", " ")
            nb = s.get("nb_chunks", "?")
            if is_orphan:
                item.setText(tr("{}\n{}  •  mémoire FAISS uniquement").format(s['filename'], ts))
                item.setToolTip(
                    tr("Ce document a ete retire de la librairie mais\n"
                       "sa memoire vectorielle (FAISS) est conservee.\n"
                       "Cliquez Supprimer pour effacer aussi la memoire.")
                )
                font = QFont()
                font.setItalic(True)
                item.setFont(font)
                item.setForeground(QBrush(QColor("#666666")))
                item.setIcon(qta.icon("fa5s.unlink", color="#666666"))
            else:
                is_bible = s.get("bible_source", True)
                blocs_text = tr("{} bloc").format(nb) if nb <= 1 else tr("{} blocs").format(nb)
                item.setText(tr("{}\n{}  •  {}").format(s['filename'], ts, blocs_text))
                item.setIcon(qta.icon("fa5s.journal-whills" if is_bible else "fa5s.archive", color="#4ec9b0" if is_bible else "#858585"))
            self._list.addItem(item)

    def refresh(self) -> None:
        self._refresh()

    def refresh_edit_docs(self, docs: list[dict]) -> None:
        """Met a jour la liste des documents edites (appelee par MainWindow)."""
        self._edit_list.clear()
        if not docs:
            self._edit_list.hide()
            self._edit_empty_lbl.show()
            return
        self._edit_empty_lbl.hide()
        self._edit_list.show()
        for doc in docs:
            ts = doc.get("last_modified", "")[:16].replace("T", " ")
            item = QListWidgetItem(f"{doc['title']}\n{ts}")
            item.setData(Qt.ItemDataRole.UserRole, doc["doc_id"])
            self._edit_list.addItem(item)

    def _on_edit_doc_double_clicked(self, item: QListWidgetItem) -> None:
        doc_id = item.data(Qt.ItemDataRole.UserRole)
        if doc_id:
            self.edit_open_requested.emit(doc_id)

    def _on_edit_doc_delete(self) -> None:
        item = self._edit_list.currentItem()
        if item is None:
            return
        doc_id = item.data(Qt.ItemDataRole.UserRole)
        if doc_id:
            self.delete_edit_doc_requested.emit(doc_id)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_selection_changed(self, current, _previous):
        has = current is not None
        is_orphan = (
            current.data(Qt.ItemDataRole.UserRole + 1)
            if current is not None else False
        )
        self._reingest_btn.setEnabled(has and not is_orphan)
        self._mute_btn.setEnabled(has and not is_orphan)
        # Mettre a jour le libelle du bouton sourdine selon l'etat courant
        if has and not is_orphan and self._store is not None:
            sid = current.data(Qt.ItemDataRole.UserRole)
            try:
                is_muted = self._store.get(sid).get("muted", False)
                self._mute_btn.setText(tr("Activer") if is_muted else tr("Sourdine"))
                self._mute_btn.setIcon(qta.icon("fa5s.volume-up" if is_muted else "fa5s.volume-mute", color="white"))
                if is_muted:
                    self._mute_btn.setToolTip(tr("Document en sourdine : il n'est plus lu par l'IA. Cliquez pour l'activer."))
                else:
                    self._mute_btn.setToolTip(tr("Document active : il est lu par l'IA. Cliquez pour le mettre en sourdine."))
            except KeyError:
                self._mute_btn.setText(tr("Sourdine"))
                self._mute_btn.setIcon(qta.icon("fa5s.volume-mute", color="white"))
                self._mute_btn.setToolTip(tr("Document active : il est lu par l'IA. Cliquez pour le mettre en sourdine."))
        else:
            self._mute_btn.setText(tr("Sourdine"))
            self._mute_btn.setIcon(qta.icon("fa5s.volume-mute", color="white"))
            self._mute_btn.setToolTip(tr("Met ce document en sourdine."))
        self._remove_btn.setEnabled(has)

    def _current_source(self) -> dict | None:
        item = self._list.currentItem()
        if item is None or self._store is None:
            return None
        sid = item.data(Qt.ItemDataRole.UserRole)
        try:
            return self._store.get(sid)
        except KeyError:
            return None

    def _on_reingest(self):
        src = self._current_source()
        if src is None:
            return
        path = src.get("path", "")
        if not Path(path).exists():
            QMessageBox.warning(
                self,
                tr("Fichier introuvable"),
                tr("Le fichier n'existe plus a cet emplacement :\n{}").format(path),
            )
            return
        self.reingest_requested.emit(src["source_id"], path)

    def _on_mute(self):
        src = self._current_source()
        if src is None:
            return
        self.mute_requested.emit(src["source_id"])

    def _on_remove(self):
        src = self._current_source()
        if src is None:
            return
        if src.get("orphan", False):
            dlg = _DeleteOrphanDialog(filename=src["filename"], parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            self.remove_requested.emit(src["source_id"], True)
        else:
            dlg = _DeleteSourceDialog(
                filename=src["filename"],
                nb_chunks=src.get("nb_chunks", 0),
                parent=self,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            self.remove_requested.emit(src["source_id"], dlg.remove_memory)
