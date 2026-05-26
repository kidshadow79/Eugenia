"""
ingest_dialog.py — Dialog d'import d'un document .docx dans la Bible

Flux :
    1. L'auteur clique "Sources" dans l'IconBar → ContextPanel affiche SourcesPanel
       (ou directement via menu) → bouton "Importer un document"
    2. Ce dialog s'ouvre, l'auteur choisit son .docx
    3. Pendant l'ingest : barre de progression + status
    4. À la fin : résumé (nb chunks traités, nb entités écrites)

Signal émis :
    ingest_done(str, int)  : (source_id, nb_entites_ecrites)

Usage (depuis main_window ou sources_panel) :
    dlg = IngestDialog(chunk_mgr, archiviste, parent=self)
    dlg.ingest_done.connect(handler)
    dlg.exec()
"""

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QFileDialog, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
import qtawesome as qta

from core.ingest_worker import IngestWorker
from core.archiviste import Archiviste
from core.chunk_manager import ChunkManager
from core.docx_reader import SUPPORTED_EXTENSIONS
from ui.font_config import FontConfig

logger = logging.getLogger(__name__)

_FILE_FILTER = (
    "Documents supportés (*.docx *.txt *.md *.pdf *.json);;"
    "Word (*.docx);;"
    "Texte brut (*.txt *.md);;"
    "PDF (*.pdf);;"
    "JSON (*.json);;"
    "Tous les fichiers (*.*)"
)


def _build_dialog_style(fc: FontConfig) -> str:
    return f"""
QDialog {{
    background-color: #252526;
    color: #cccccc;
}}
QLabel {{
    color: #cccccc;
    font-size: {fc.size}px;
}}
QLabel#Title {{
    color: #4ec9b0;
    font-size: {fc.lg}px;
    font-weight: bold;
    padding-bottom: 4px;
}}
QLabel#StatusLabel {{
    color: #858585;
    font-size: {fc.sm}px;
    font-style: italic;
}}
QLabel#SummaryLabel {{
    color: #4ec9b0;
    font-size: {fc.sm}px;
}}
QProgressBar {{
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 3px;
    height: 10px;
    text-align: center;
    color: #cccccc;
    font-size: {fc.xs}px;
}}
QProgressBar::chunk {{
    background-color: #0e639c;
    border-radius: 3px;
}}
QPushButton#PrimaryBtn {{
    background-color: #0e639c;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 7px 20px;
    font-size: {fc.size}px;
}}
QPushButton#PrimaryBtn:hover {{ background-color: #1177bb; }}
QPushButton#PrimaryBtn:disabled {{
    background-color: #3c3c3c;
    color: #555555;
}}
QPushButton#SecondaryBtn {{
    background-color: transparent;
    color: #858585;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 7px 20px;
    font-size: {fc.size}px;
}}
QPushButton#SecondaryBtn:hover {{ color: #cccccc; border-color: #888888; }}
QFrame#Separator {{
    color: #3e3e42;
}}
"""


class IngestDialog(QDialog):
    """
    Dialog modal pour importer un document dans la Bible.
    Formats supportés : .docx, .txt, .md, .pdf, .json
    Supporte le glisser-déposer d'un fichier.
    """

    ingest_done = pyqtSignal(str, int)   # (source_id, nb_entites)

    def __init__(self, chunk_mgr: ChunkManager, archiviste: Archiviste | None,
                 parent=None, prefill_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Importer un document")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setAcceptDrops(True)

        self._chunk_mgr  = chunk_mgr
        self._archiviste = archiviste
        self._worker: IngestWorker | None = None
        self._entities_written = 0
        self._source_id = ""
        self._total_chunks = 0
        self._all_chunks: list = []
        self._bible_mode: bool = True       # True = alimente la Bible
        self._pending_path: Path | None = None  # attente choix mode
        # Metadonnees exposees apres ingest (pour SourceStore)
        self.meta: dict = {}

        fc = FontConfig.instance()
        self.setStyleSheet(_build_dialog_style(fc))
        self._build_ui(fc)
        self._set_state("idle")

        if prefill_path:
            path = Path(prefill_path)
            self._file_label.setText(str(path))
            self._file_label.setStyleSheet(f"color: #cccccc; font-size: {FontConfig.instance().sm}px;")
            self._source_id = path.name
            self._entities_written = 0
            self._pending_path = path
            self._set_state("asking")

    # ─── Construction UI ──────────────────────────────────────────────────────

    def _build_ui(self, fc: FontConfig) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Titre
        title = QLabel("Importer un document dans la Bible")
        title.setObjectName("Title")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Importez un fichier pour que l'Archiviste analyse son contenu\n"
            "et enrichisse automatiquement la Bible du projet.\n"
            "Formats acceptés\u202f: .docx, .txt, .md, .pdf, .json"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: #858585; font-size: {fc.sm}px;")
        layout.addWidget(desc)

        # Séparateur
        sep = QFrame()
        sep.setObjectName("Separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Zone drag & drop
        self._drop_zone = QLabel(
            "📂\u2002Glissez un fichier ici\n"
            "ou cliquez sur \u00ab\u00a0Choisir un fichier\u00a0\u00bb"
        )
        self._drop_zone.setObjectName("DropZone")
        self._drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_zone.setMinimumHeight(72)
        self._drop_zone.setStyleSheet(
            "QLabel#DropZone {"
            "  border: 2px dashed #3e3e42;"
            "  border-radius: 6px;"
            "  color: #555555;"
            "  font-size: 12px;"
            "  padding: 8px;"
            "  background-color: #1e1e1e;"
            "}"
            "QLabel#DropZone[drag=true] {"
            "  border-color: #0e639c;"
            "  color: #0e639c;"
            "  background-color: #0d2a3e;"
            "}"
        )
        layout.addWidget(self._drop_zone)

        # Fichier sélectionné
        self._file_label = QLabel("Aucun fichier sélectionné")
        self._file_label.setStyleSheet(f"color: #858585; font-size: {fc.sm}px; font-style: italic;")
        self._file_label.setWordWrap(True)
        layout.addWidget(self._file_label)

        # ── Zone de choix du mode (cachée jusqu'au choix du fichier) ──────────
        self._mode_frame = QFrame()
        self._mode_frame.setObjectName("Separator")
        self._mode_frame.setFrameShape(QFrame.Shape.NoFrame)
        mode_layout = QVBoxLayout(self._mode_frame)
        mode_layout.setContentsMargins(0, 6, 0, 6)
        mode_layout.setSpacing(8)
        mode_question = QLabel("Ce document doit-il alimenter la Bible du projet ?")
        mode_question.setStyleSheet(f"color: #cccccc; font-size: {fc.sm}px; font-weight: bold;")
        mode_layout.addWidget(mode_question)
        mode_hint = QLabel(
            "Bible : l'Archiviste va extraire personnages, lieux, événements…\n"
            "Référence : le document sera en mémoire vectorielle uniquement."
        )
        mode_hint.setStyleSheet(f"color: #858585; font-size: {fc.xs}px;")
        mode_layout.addWidget(mode_hint)
        mode_btns = QHBoxLayout()
        mode_btns.setSpacing(8)
        self._btn_yes_bible = QPushButton("Oui, alimenter la Bible")
        self._btn_yes_bible.setIcon(qta.icon("fa5s.journal-whills", color="white"))
        self._btn_yes_bible.setObjectName("PrimaryBtn")
        self._btn_yes_bible.clicked.connect(lambda: self._on_mode_chosen(True))
        self._btn_no_bible = QPushButton("Non, référence uniquement")
        self._btn_no_bible.setIcon(qta.icon("fa5s.archive", color="white"))
        self._btn_no_bible.setObjectName("SecondaryBtn")
        self._btn_no_bible.clicked.connect(lambda: self._on_mode_chosen(False))
        mode_btns.addWidget(self._btn_yes_bible)
        mode_btns.addWidget(self._btn_no_bible)
        mode_layout.addLayout(mode_btns)
        self._mode_frame.hide()
        layout.addWidget(self._mode_frame)

        # Barre de progression
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indéterminé par défaut
        self._progress.hide()
        layout.addWidget(self._progress)

        # Status
        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.hide()
        layout.addWidget(self._status_label)

        # Résumé (affiché après ingest)
        self._summary_label = QLabel("")
        self._summary_label.setObjectName("SummaryLabel")
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_label.setWordWrap(True)
        self._summary_label.hide()
        layout.addWidget(self._summary_label)

        layout.addStretch()

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_choose = QPushButton("Choisir un fichier...")
        self._btn_choose.setObjectName("PrimaryBtn")
        self._btn_choose.clicked.connect(self._on_choose)
        self._btn_close = QPushButton("Fermer")
        self._btn_close.setObjectName("SecondaryBtn")
        self._btn_close.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(self._btn_close)
        btn_row.addWidget(self._btn_choose)
        layout.addLayout(btn_row)

    # ─── Drag & Drop ──────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and Path(urls[0].toLocalFile()).suffix.lower() in SUPPORTED_EXTENSIONS:
                event.acceptProposedAction()
                self._drop_zone.setProperty("drag", True)
                self._drop_zone.setStyle(self._drop_zone.style())
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._drop_zone.setProperty("drag", False)
        self._drop_zone.setStyle(self._drop_zone.style())

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        self._drop_zone.setProperty("drag", False)
        self._drop_zone.setStyle(self._drop_zone.style())
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        self._load_path(path)

    # ─── États ────────────────────────────────────────────────────────────────

    def _set_state(self, state: str, msg: str = "") -> None:
        if state == "idle":
            self._progress.hide()
            self._status_label.hide()
            self._summary_label.hide()
            self._mode_frame.hide()
            self._btn_choose.setEnabled(True)
            self._btn_choose.setText("Choisir un fichier...")

        elif state == "asking":
            self._progress.hide()
            self._status_label.hide()
            self._summary_label.hide()
            self._mode_frame.show()
            self._btn_choose.setEnabled(False)
            self._btn_choose.setText("En attente...")

        elif state == "loading":
            self._progress.setRange(0, 0)
            self._progress.show()
            self._status_label.setText(msg or "Lecture du fichier...")
            self._status_label.show()
            self._summary_label.hide()
            self._btn_choose.setEnabled(False)

        elif state == "running":
            self._progress.show()
            self._status_label.setText(msg or "L'Archiviste analyse le document...")
            self._status_label.show()
            self._summary_label.hide()
            self._btn_choose.setEnabled(False)

        elif state == "done":
            self._progress.hide()
            self._status_label.hide()
            self._summary_label.setText(msg)
            self._summary_label.show()
            self._btn_choose.setEnabled(True)
            self._btn_choose.setText("Importer un autre fichier")

        elif state == "no_changes":
            self._progress.hide()
            self._status_label.hide()
            self._summary_label.setText(msg or "Aucune modification détectée — Bible déjà à jour.")
            self._summary_label.show()
            self._btn_choose.setEnabled(True)
            self._btn_choose.setText("Choisir un fichier...")

        elif state == "error":
            self._progress.hide()
            self._status_label.hide()
            self._summary_label.setStyleSheet(f"color: #f48771; font-size: {FontConfig.instance().sm}px;")
            self._summary_label.setText(f"Erreur : {msg}")
            self._summary_label.show()
            self._btn_choose.setEnabled(True)
            self._btn_choose.setText("Réessayer")

    # ─── Actions ──────────────────────────────────────────────────────────────

    def _on_mode_chosen(self, bible_mode: bool) -> None:
        """Appelé quand l'auteur choisit le mode d'ingest."""
        self._bible_mode = bible_mode
        self._mode_frame.hide()
        path = self._pending_path
        self._pending_path = None
        if path:
            self._start_ingest(path)

    def _on_choose(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un document",
            "",
            _FILE_FILTER,
        )
        if not path_str:
            return
        self._load_path(Path(path_str))

    def _load_path(self, path: Path) -> None:
        """Commun à l'ouverture par bouton et par drag & drop."""
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            self._set_state(
                "error",
                f"Format non supporté\u202f: {path.suffix}. "
                f"Formats acceptés\u202f: {", ".join(sorted(SUPPORTED_EXTENSIONS))}",
            )
            return
        self._file_label.setText(str(path))
        self._file_label.setStyleSheet(f"color: #cccccc; font-size: {FontConfig.instance().sm}px;")
        self._source_id = path.name
        self._entities_written = 0

        logger.info("IngestDialog — fichier choisi\u202f: %s", path.name)
        self._pending_path = path
        self._set_state("asking")

    def _start_ingest(self, path: Path) -> None:
        self._set_state("loading", f"Lecture de {path.name}...")

        self._worker = IngestWorker(path, self._chunk_mgr, parent=self)
        self._worker.word_count_ready.connect(self._on_word_count)
        self._worker.text_ready.connect(self._on_text_ready)
        self._worker.delta_ready.connect(self._on_delta_ready)
        self._worker.no_changes.connect(self._on_no_changes)
        self._worker.error.connect(self._on_ingest_error)
        self._worker.start()

    # ─── Slots workers ────────────────────────────────────────────────────────

    def _on_word_count(self, words: int) -> None:
        self._status_label.setText(f"Fichier chargé — ~{words:,} mots détectés")

    def _on_text_ready(self, _text: str, source_id: str, nb_chunks: int) -> None:
        self._set_state("loading", f"Chunking terminé — {nb_chunks} bloc(s) à analyser")

    def _on_delta_ready(self, source_id: str, delta: list, all_chunks: list) -> None:
        nb = len(delta)
        self._total_chunks = nb
        self._entities_written = 0
        self._all_chunks = all_chunks

        # ── Mode référence uniquement : pas d'extraction Bible ────────────────
        if not self._bible_mode:
            for chunk in all_chunks:
                self._chunk_mgr.save_chunk_hash(self._source_id, chunk)
            self.meta = {
                "filename":     Path(self._file_label.text()).name,
                "path":         self._file_label.text(),
                "nb_chunks":    len(all_chunks),
                "bible_source": False,
            }
            nb_all = len(all_chunks)
            self._set_state(
                "done",
                f"Import terminé — {nb_all} bloc(s) ajouté(s) en mémoire vectorielle "
                f"(sans extraction Bible).",
            )
            logger.info("IngestDialog — mode référence : %d blocs, Bible ignorée", nb_all)
            self.ingest_done.emit(self._source_id, 0)
            return

        # ── Mode Bible : flux normal ───────────────────────────────────────────
        # Barre déterminée : on connaît le total
        self._progress.setRange(0, nb)
        self._progress.setValue(0)
        self._progress.setFormat(f"0 / {nb} blocs")
        self._set_state("running",
                        f"L'Archiviste analyse {nb} bloc(s) du document...")

        if self._archiviste is None:
            self._set_state("error",
                            "L'Archiviste n'est pas configuré (clé API manquante).")
            return

        # Brancher le compteur d'entités avant de lancer
        self._archiviste.bible_updated.connect(self._on_bible_updated)
        self._archiviste.error_occurred.connect(self._on_archiviste_error)

        # Connecter all_chunks_done sur le writer interne pour détecter la fin
        self._archiviste._writer.all_chunks_done.connect(self._on_all_chunks_done)
        self._archiviste._writer.chunk_processed.connect(self._on_chunk_processed)

        # Envoyer les chunks avec callback de sauvegarde progressive
        def _save_chunk(chunk):
            self._chunk_mgr.save_chunk_hash(self._source_id, chunk)
        self._archiviste._writer.process_chunks(delta, on_chunk_saved=_save_chunk)

    def _on_no_changes(self, source_id: str) -> None:
        logger.info("IngestDialog — aucun delta pour %s", source_id)
        self._set_state("no_changes")

    def _on_bible_updated(self, table: str, _total: int) -> None:
        self._entities_written += 1

    def _on_chunk_processed(self, done: int, total: int) -> None:
        self._progress.setValue(done)
        self._progress.setFormat(f"{done} / {total} blocs")
        self._status_label.setText(
            f"Bloc {done}/{total} analysé — {self._entities_written} entrée(s) écrite(s)"
        )

    def _on_all_chunks_done(self) -> None:
        # Les hashes ont déjà été sauvegardés progressivement chunk par chunk
        self._disconnect_archiviste()
        n = self._entities_written
        if n > 0:
            msg = f"Import terminé — {n} entrée(s) ajoutée(s) à la Bible."
        else:
            msg = "Import terminé — aucune nouvelle entité détectée."
        self._set_state("done", msg)
        logger.info("IngestDialog — ingest terminé : %d entité(s)", n)
        # Stocker les metadonnees pour que MainWindow puisse les recuperer
        self.meta = {
            "filename":     Path(self._file_label.text()).name,
            "path":         self._file_label.text(),
            "nb_chunks":    len(self._all_chunks),
            "bible_source": True,
        }
        self.ingest_done.emit(self._source_id, n)

    def _on_ingest_error(self, msg: str) -> None:
        logger.error("IngestDialog — erreur ingest : %s", msg)
        self._set_state("error", msg)

    def _on_archiviste_error(self, msg: str) -> None:
        logger.error("IngestDialog — erreur Archiviste : %s", msg)
        self._status_label.setText(f"Attention : {msg}")

    # ─── Nettoyage ────────────────────────────────────────────────────────────

    def _disconnect_archiviste(self) -> None:
        if self._archiviste is None:
            return
        try:
            self._archiviste.bible_updated.disconnect(self._on_bible_updated)
        except RuntimeError:
            pass
        try:
            self._archiviste.error_occurred.disconnect(self._on_archiviste_error)
        except RuntimeError:
            pass
        try:
            self._archiviste._writer.all_chunks_done.disconnect(self._on_all_chunks_done)
        except RuntimeError:
            pass
        try:
            self._archiviste._writer.chunk_processed.disconnect(self._on_chunk_processed)
        except RuntimeError:
            pass

    def closeEvent(self, event):
        self._disconnect_archiviste()
        super().closeEvent(event)
