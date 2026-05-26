"""
archiviste.py — Orchestrateur de l'Archiviste EUGENIA

Point d'entrée unique pour toute la logique de l'Archiviste.
Dispatch vers les sous-modules selon le contexte.

Sous-modules :
    archiviste_writer.py     ← mode écriture (ingest → Bible)
    archiviste_reader.py     ← mode lecture (avant chaque réponse)
    archiviste_relational.py ← mémoire relationnelle (lors résumations)

Responsabilité de cet orchestrateur :
    - Instancier et tenir à jour les sous-modules
    - Exposer les méthodes appelées par main_window
    - Remonter les signaux des sous-modules vers main_window
    - Gérer le cycle de vie des bases de données

Usage (depuis main_window.py) :
    archiviste = Archiviste(config, session)
    archiviste.contradiction_found.connect(self._on_contradiction)
    archiviste.context_note_ready.connect(self._on_context_note)

    # Après un envoi clipboard :
    archiviste.ingest_text(texte_clipboard)

    # Avant chaque envoi à l'IA principale :
    archiviste.build_context_note(question_utilisateur)

    # Lors d'une résumation :
    archiviste.summarize_conversation(texte_conversation)

    # Nettoyage à la fermeture :
    archiviste.close()
"""

from pathlib import Path
import logging
from PyQt6.QtCore import pyqtSignal, QObject

from core.bible_db import BibleDB
from core.relational_db import RelationalDB
from core.chunk_manager import ChunkManager
from core.archiviste_writer import ArchivisteWriter
from core.archiviste_reader import ArchivisteReader
from core.archiviste_relational import ArchivisteRelational
from core.session_manager import PROJECTS_DIR, AUTHORS_DIR

logger = logging.getLogger(__name__)


class Archiviste(QObject):
    """
    Archiviste EUGENIA — subconscient actif de l'assistant d'écriture.

    Deux modes :
        Mode lecture  : build_context_note(question) → injecte une note avant l'IA principale
        Mode écriture : ingest_text(texte) → extrait entités → Bible SQLite
        Mode résumation : summarize_conversation(conv) → mémoire relationnelle auteur

    Signaux remontés vers main_window :
        context_note_ready(str)       ← note à injecter (peut être "")
        contradiction_found(str)      ← alerte contradiction détectée
        bible_updated(str, int)       ← (table, total) après chaque écriture
        relational_entries_added(int) ← nb entrées relationnelles ajoutées
        error_occurred(str)           ← erreur non fatale (à logger)
    """

    # ─── Signaux publics ──────────────────────────────────────────────────────
    context_note_ready      = pyqtSignal(str)
    contradiction_found     = pyqtSignal(str)
    bible_updated           = pyqtSignal(str, int)
    relational_entries_added = pyqtSignal(int)
    error_occurred          = pyqtSignal(str)

    def __init__(self, config: dict, session: dict, parent=None):
        """
        Args:
            config:  dict AI config — {"api_key", "base_url", "model"}
            session: dict session — {"author": str, "author_slug": str,
                                     "project": str, "project_slug": str}
        """
        super().__init__(parent)
        self._config = config
        self._session = session

        # ─── Chemins ──────────────────────────────────────────────────────────
        project_dir = PROJECTS_DIR / session["project_slug"]
        author_dir  = AUTHORS_DIR  / session["author_slug"]

        # ─── Bases de données ─────────────────────────────────────────────────
        self._bible_db      = BibleDB(project_dir)          # lit project.json auto
        self._relational_db = RelationalDB(author_dir)
        self._chunk_mgr     = ChunkManager(project_dir)

        # ─── Sous-modules ─────────────────────────────────────────────────────
        self._writer     = ArchivisteWriter(config, self._bible_db,
                                            categories=list(self._bible_db._tables),
                                            parent=self)
        self._reader     = ArchivisteReader(config, self._bible_db, parent=self)
        self._relational = ArchivisteRelational(config, self._relational_db, parent=self)
        self._vector_index = None   # branché après init via set_vector_index()

        # ─── Connexions signaux → signaux ─────────────────────────────────────
        self._writer.contradiction_found.connect(self.contradiction_found)
        self._writer.bible_updated.connect(self.bible_updated)
        self._writer.error_occurred.connect(self.error_occurred)

        self._reader.context_note_ready.connect(self.context_note_ready)
        self._reader.error_occurred.connect(self.error_occurred)

        self._relational.entries_added.connect(self.relational_entries_added)
        self._relational.error_occurred.connect(self.error_occurred)

        logger.info(
            "Archiviste initialisé — projet=%s auteur=%s model=%s",
            session.get("project_slug", "?"),
            session.get("author_slug", "?"),
            config.get("model", "?"),
        )

    # ─── API publique — mode lecture ──────────────────────────────────────────

    def build_context_note(self, question: str, bible_context: str = "") -> None:
        """
        Construit une note de contexte avant que l'IA principale réponde.

        Si bible_context est fourni (pre-selectionne par FAISS), il est utilise
        directement par le Reader au lieu du dump complet de la Bible.

        Args:
            question:      message que l'auteur s'apprête à envoyer
            bible_context: contexte Bible pre-selectionne (optionnel)
        """
        self._reader.build_context_note(question, bible_context=bible_context)

    # ─── API publique — mode écriture ─────────────────────────────────────────

    def ingest_text(self, text: str, source_id: str = "clipboard") -> None:
        """
        Analyse un texte (clipboard ou ingest document) et met à jour la Bible.

        Filtrage en 3 passes :
          1. Delta hash par source (inchangé depuis la dernière ingéstion)
          2. Cross-source hash (même text_small dans une autre source)
          3. Similarité semantique FAISS (quasi-doublon formulé différemment)

        Args:
            text:      texte brut à ingérer
            source_id: identifiant de source ("clipboard" ou nom de fichier)
        """
        chunks = self._chunk_mgr.chunk_text(text)
        if not chunks:
            logger.debug("Archiviste.ingest_text — texte vide ou trop court, ignoré")
            return

        delta = self._chunk_mgr.filter_delta(source_id, chunks)
        if not delta:
            logger.debug("Archiviste.ingest_text — pas de delta source=%s", source_id)
            return

        # Passe 3 : filtrage sémantique FAISS (si index disponible)
        if self._vector_index is not None:
            delta = self._vector_index.filter_semantic_delta(delta)
            if not delta:
                logger.debug(
                    "Archiviste.ingest_text — tous les chunks filtres par FAISS (source=%s)",
                    source_id,
                )
                return

        logger.info("Archiviste.ingest_text — %d chunk(s) à traiter (source=%s)",
                    len(delta), source_id)

        # Pour éviter la superposition, on déconnecte l'ancien callback si existant
        if hasattr(self, "_last_on_done"):
            try:
                self._writer.all_chunks_done.disconnect(self._last_on_done)
            except TypeError:
                pass

        successful_chunks = []

        def _on_chunk_saved(chunk):
            successful_chunks.append(chunk)

        def _on_done():
            if successful_chunks:
                self._chunk_mgr.save_hashes(source_id, successful_chunks)
            try:
                self._writer.all_chunks_done.disconnect(_on_done)
            except TypeError:
                pass

        self._last_on_done = _on_done
        self._writer.all_chunks_done.connect(_on_done)
        self._writer.process_chunks(delta, on_chunk_saved=_on_chunk_saved)

    # ─── API publique — mode résumation ──────────────────────────────────────

    def summarize_conversation(self, conversation_text: str) -> None:
        """
        Analyse une conversation terminée pour en extraire la mémoire relationnelle.

        À appeler lors de la résumation de conversation (tous les N messages),
        PAS à chaque message.

        Args:
            conversation_text: texte de la conversation formatté
                               ("user: ...\nassistant: ...")
        """
        self._relational.extract_from_conversation(conversation_text)

    # ─── Accès aux bases (pour la UI Bible) ──────────────────────────────────

    @property
    def bible_db(self) -> BibleDB:
        """Accès direct à la Bible (pour bible_panel.py)."""
        return self._bible_db

    @property
    def relational_db(self) -> RelationalDB:
        """Accès direct à la mémoire relationnelle."""
        return self._relational_db

    # ─── Mise à jour config ───────────────────────────────────────────────────

    def update_config(self, config: dict) -> None:
        """Met à jour la config IA sur tous les sous-modules."""
        self._config = config
        self._writer.update_config(config)
        self._reader.update_config(config)
        self._relational.update_config(config)

    def set_vector_index(self, vector_index) -> None:
        """Branche l'index FAISS pour le filtrage sémantique a l'ingest."""
        self._vector_index = vector_index
        logger.debug("Archiviste — VectorIndex branché (vide=%s)", vector_index.is_empty())

    # ─── Cycle de vie ─────────────────────────────────────────────────────────

    def close(self) -> None:
        """Ferme les connexions SQLite. Appeler avant de quitter l'application."""
        logger.info("Archiviste — fermeture des bases SQLite")
        self._bible_db.close()
        self._relational_db.close()
