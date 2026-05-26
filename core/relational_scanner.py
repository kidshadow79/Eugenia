"""
relational_scanner.py — Scan des conversations non analysees pour la memoire relationnelle

Responsabilite unique :
    Parcourir les sessions de conversation non encore scannees (d'un projet)
    et en extraire les informations sur l'auteur via ArchivisteRelational.

Declencheurs :
    - Fermeture propre de l'application (closeEvent MainWindow)
    - Commande /mem dans le chat

Principe :
    - Une session scannee est marquee dans conversation_store.relational_scan_index.json
    - Si la base relationnelle detecte un doublon (hash identique), il n'est pas re-insere
    - Le scan est sequentiel (une session a la fois) pour ne pas surcharger l'API

Signaux :
    scan_complete(int)    : emis quand toutes les sessions en attente sont traitees
                            (int = nombre total d'entrees ajoutees)
    scan_error(str)       : erreur sur une session (log + continue)
    progress(str)         : message de statut lisible pour l'UI (optionnel)
"""

import logging
from PyQt6.QtCore import QObject, pyqtSignal, QThread

from core.conversation_store import ConversationStore
from core.relational_db import RelationalDB
from core.archiviste_relational import ArchivisteRelational

logger = logging.getLogger(__name__)


class _ScanWorker(QThread):
    """
    Thread qui scan UNE session et retourne le nombre d'entrees ajoutees.
    Appele sequentiellement par RelationalScanner pour chaque session en attente.
    """

    done  = pyqtSignal(str, int)   # session_id, nb_added
    error = pyqtSignal(str, str)   # session_id, message_erreur

    def __init__(self, session_id: str, messages: list[dict],
                 archiviste: ArchivisteRelational):
        super().__init__()
        self._session_id = session_id
        self._messages   = messages
        self._archiviste = archiviste
        self._added      = 0

    def run(self):
        # Construire le transcript lisible
        lines = []
        for m in self._messages:
            role = "Auteur" if m.get("role") == "user" else "EUGENIA"
            content = m.get("content", "").strip()
            if content:
                lines.append(f"[{role}] {content}")
        transcript = "\n".join(lines)

        if not transcript.strip():
            self.done.emit(self._session_id, 0)
            return

        # Brancher les signaux pour recuperer le resultat synchrone dans ce thread
        self._added = 0
        self._archiviste.entries_added.connect(self._on_added)
        self._archiviste.nothing_found.connect(self._on_nothing)
        self._archiviste.error_occurred.connect(self._on_error)

        self._archiviste.extract_from_conversation(transcript)

        # Attendre la fin du worker interne (qui est lui-meme un QThread)
        # On boucle jusqu'a ce que le worker interne soit fini
        internal = self._archiviste._worker
        if internal and internal.isRunning():
            internal.wait()

    def _disconnect_archiviste(self) -> None:
        """Deconnecte les signaux de l'archiviste pour eviter les double-fires."""
        for sig, slot in [
            (self._archiviste.entries_added,  self._on_added),
            (self._archiviste.nothing_found,  self._on_nothing),
            (self._archiviste.error_occurred, self._on_error),
        ]:
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def _on_added(self, n: int) -> None:
        self._disconnect_archiviste()
        self._added = n
        self.done.emit(self._session_id, n)

    def _on_nothing(self) -> None:
        self._disconnect_archiviste()
        self.done.emit(self._session_id, 0)

    def _on_error(self, msg: str) -> None:
        self._disconnect_archiviste()
        self.error.emit(self._session_id, msg)


class RelationalScanner(QObject):
    """
    Orchestre le scan sequentiel de toutes les sessions non encore analysees.

    Usage :
        scanner = RelationalScanner(conv_store, archiviste)
        scanner.scan_complete.connect(on_done)
        scanner.run_pending()   # lance le scan asynchrone
    """

    scan_complete = pyqtSignal(int)   # total d'entrees ajoutees
    scan_error    = pyqtSignal(str)   # message d'erreur non bloquant
    progress      = pyqtSignal(str)   # statut lisible pour l'UI

    def __init__(self, conv_store: ConversationStore,
                 archiviste: ArchivisteRelational, parent=None):
        super().__init__(parent)
        self._store      = conv_store
        self._archiviste = archiviste
        self._pending:   list[str] = []
        self._total_added: int = 0
        self._worker: _ScanWorker | None = None

    # ------------------------------------------------------------------ #
    #  API publique                                                        #
    # ------------------------------------------------------------------ #

    def run_pending(self) -> None:
        """
        Lance le scan de toutes les sessions non scannees.
        Sans effet si aucune session n'est en attente ou si un scan est deja en cours.
        """
        if self._worker and self._worker.isRunning():
            logger.debug("RelationalScanner — scan deja en cours, ignore")
            return

        self._pending = self._store.list_unscanned_sessions()
        if not self._pending:
            logger.debug("RelationalScanner — aucune session en attente")
            self.scan_complete.emit(0)
            return

        logger.info("RelationalScanner — %d session(s) a scanner", len(self._pending))
        self.progress.emit(f"Scan memoire : {len(self._pending)} conversation(s) en attente...")
        self._total_added = 0
        self._scan_next()

    # ------------------------------------------------------------------ #
    #  Interne — pipeline sequentiel                                      #
    # ------------------------------------------------------------------ #

    def _scan_next(self) -> None:
        """Demarre le scan de la prochaine session en attente."""
        if not self._pending:
            logger.info("RelationalScanner — scan termine, %d entree(s) ajoutee(s)",
                        self._total_added)
            self.scan_complete.emit(self._total_added)
            return

        session_id = self._pending[0]
        try:
            messages = self._store.load_session(session_id)
        except FileNotFoundError:
            logger.warning("RelationalScanner — session introuvable : %s (marquee scannee)", session_id)
            self._store.mark_relational_scanned(session_id)
            self._pending.pop(0)
            self._scan_next()
            return

        logger.debug("RelationalScanner — scan session %s (%d messages)",
                     session_id, len(messages))
        self.progress.emit(f"Analyse : {session_id}...")

        self._worker = _ScanWorker(session_id, messages, self._archiviste)
        self._worker.done.connect(self._on_session_done)
        self._worker.error.connect(self._on_session_error)
        self._worker.start()

    def _on_session_done(self, session_id: str, added: int) -> None:
        if not self._pending:
            logger.debug("RelationalScanner — _on_session_done appele sur liste vide (signal tardif), ignore")
            return
        self._total_added += added
        self._store.mark_relational_scanned(session_id)
        self._pending.pop(0)
        if added:
            logger.info("RelationalScanner — session %s : %d entree(s) ajoutee(s)",
                        session_id, added)
        self._scan_next()

    def _on_session_error(self, session_id: str, msg: str) -> None:
        if not self._pending:
            logger.debug("RelationalScanner — _on_session_error appele sur liste vide (signal tardif), ignore")
            return
        logger.error("RelationalScanner — erreur session %s : %s", session_id, msg)
        self.scan_error.emit(f"Erreur scan {session_id} : {msg}")
        # On marque quand meme comme scannee pour ne pas boucler indefiniment
        self._store.mark_relational_scanned(session_id)
        self._pending.pop(0)
        self._scan_next()
