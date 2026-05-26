"""
ingest_worker.py — Worker QThread pour l'ingest d'un document

Orchestration complète de l'import d'un .docx :
    1. Lecture du fichier (docx_reader)
    2. Chunking + détection delta (chunk_manager)
    3. Envoi des chunks nouveaux/modifiés à l'Archiviste

Séparation intentionnelle : ce worker s'arrête après le chunking.
C'est l'Archiviste (archiviste_writer) qui fait les appels API.
Ce module ne connaît pas l'IA — il ne fait que préparer la donnée.

Signaux émis :
    text_ready(str, str, int)   : (texte_brut, source_id, nb_chunks_total)
    delta_ready(str, list)      : (source_id, chunks_delta) — à passer à Archiviste
    no_changes(str)             : source_id — document déjà à jour, rien à faire
    word_count_ready(int)       : nb de mots estimé (affiché avant import)
    error(str)                  : message d'erreur lisible

Usage :
    worker = IngestWorker(path, chunk_mgr)
    worker.delta_ready.connect(archiviste.process_delta)
    worker.error.connect(ui.show_error)
    worker.start()
"""

import logging
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.docx_reader import read_document, estimate_word_count
from core.chunk_manager import ChunkManager, ChunkResult

logger = logging.getLogger(__name__)


class IngestWorker(QThread):
    """
    Thread d'ingest d'un document .docx.

    Lit le fichier, chunke, filtre le delta — émet le résultat.
    Tout se passe dans run() pour ne pas bloquer l'UI.
    """

    # Texte brut extrait + source_id + nb chunks total
    text_ready       = pyqtSignal(str, str, int)
    # Delta à passer à l'Archiviste : (source_id, liste de ChunkResult, liste tous chunks)
    delta_ready      = pyqtSignal(str, list, list)  # source_id, delta, all_chunks
    # Aucun chunk nouveau — document déjà ingéré et inchangé
    no_changes       = pyqtSignal(str)
    # Nb de mots estimé (avant ingest, pour affichage dans l'UI)
    word_count_ready = pyqtSignal(int)
    # Erreur bloquante
    error            = pyqtSignal(str)

    def __init__(self, path: Path, chunk_mgr: ChunkManager, parent=None):
        """
        Args:
            path:      chemin absolu vers le .docx
            chunk_mgr: ChunkManager du projet courant
        """
        super().__init__(parent)
        self._path      = path
        self._chunk_mgr = chunk_mgr

    def run(self) -> None:
        source_id = self._path.name   # ex: "chapitre-01.docx"
        logger.info("IngestWorker — démarrage ingest : %s", source_id)

        # ─── Étape 1 : lire le fichier ────────────────────────────────────────
        try:
            text = read_document(self._path)
        except (ValueError, ImportError) as e:
            logger.error("IngestWorker — lecture échouée : %s", e)
            self.error.emit(str(e))
            return

        words = estimate_word_count(text)
        self.word_count_ready.emit(words)
        logger.debug("IngestWorker — %d mots estimés dans %s", words, source_id)

        # ─── Étape 2 : chunking ───────────────────────────────────────────────
        chunks: list[ChunkResult] = self._chunk_mgr.chunk_text(text)
        if not chunks:
            logger.warning("IngestWorker — aucun chunk produit pour %s", source_id)
            self.error.emit(f"Aucun contenu extractible dans {self._path.name}.")
            return

        logger.debug("IngestWorker — %d chunks produits", len(chunks))
        self.text_ready.emit(text, source_id, len(chunks))

        # ─── Étape 3 : détection delta ────────────────────────────────────────
        delta = self._chunk_mgr.filter_delta(source_id, chunks)
        if not delta:
            logger.info("IngestWorker — %s déjà à jour, pas de delta", source_id)
            self.no_changes.emit(source_id)
            return

        logger.info("IngestWorker — %d chunk(s) à traiter (sur %d total)",
                    len(delta), len(chunks))

        # Les hashes sont sauvegardés APRÈS traitement réussi (dans IngestDialog)
        self.delta_ready.emit(source_id, delta, chunks)
