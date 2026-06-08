"""
archiviste_reader.py — Mode lecture de l'Archiviste

Responsabilité unique : avant chaque réponse de l'IA principale,
consulter la Bible et produire une note de contexte à injecter
en tant que message system.

Si la Bible est vide → retourne "" immédiatement (pas d'appel API).
Si la Bible contient des données pertinentes → note concise injectée.

La note est courte (~200 mots max) pour ne pas polluer le prompt principal.

Signal émis :
    context_note_ready(str) : note à injecter (peut être "" si rien de pertinent)

Usage (depuis ArchivisteOrchestrator) :
    reader = ArchivisteReader(config, bible_db)
    reader.context_note_ready.connect(handler)
    reader.build_context_note(user_question)
    # → handler reçoit la note (ou "")
"""

from PyQt6.QtCore import QThread, pyqtSignal, QObject
from openai import OpenAI
import logging

from core.bible_db import BibleDB
from core.config_manager import load_prompt

logger = logging.getLogger(__name__)

# ─── Prompt système (mode lecture) ──────────────────────────────────────────

_SYSTEM_PROMPT_READER = """Tu es l'Archiviste, le subconscient d'un assistant d'écriture pour auteurs.

Ta mission : à partir d'une Bible de projet et d'une question de l'auteur,
rédiger une note de contexte COURTE et UTILE pour l'IA principale.

Règles :
- Maximum 150 mots.
- Ne répète pas toute la Bible — sélectionne ce qui est PERTINENT pour cette question.
- Si rien dans la Bible ne concerne la question → réponds uniquement : RIEN
- Formule à la troisième personne, style factuel ("Elara est une elfe de 300 ans...")
- Mentionne les contradictions si elles concernent le sujet de la question.
"""

_USER_PROMPT_READER = """Bible du projet :
---
{bible_summary}
---

Question de l'auteur : {question}

Rédige la note de contexte (150 mots max, ou RIEN si non pertinent)."""


class _ReaderCallWorker(QThread):
    """Thread d'appel API pour la génération de la note de contexte."""

    note_ready     = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, client: OpenAI, model: str,
                 bible_summary: str, question: str, system_prompt: str):
        super().__init__()
        self._client = client
        self._model = model
        self._bible_summary = bible_summary
        self._question = question
        self._system_prompt = system_prompt

    def run(self):
        logger.info("[ARCHIVISTE:APPEL] lecture Bible model=%s question=%s",
                    self._model, self._question[:60])
        user_content = _USER_PROMPT_READER.format(
            bible_summary=self._bible_summary,
            question=self._question,
        )
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user",   "content": user_content},
        ]
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.2,
                max_tokens=300,
            )
            note = (response.choices[0].message.content or "").strip()
            # Si l'Archiviste répond "RIEN", on retourne une chaîne vide
            if note.upper() == "RIEN" or not note:
                logger.info("[ARCHIVISTE:RETOUR] lecteur -> RIEN (Bible non pertinente pour cette question)")
                self.note_ready.emit("")
            else:
                logger.info("[ARCHIVISTE:RETOUR] lecteur -> note injectee (%d chars)", len(note))
                self.note_ready.emit(
                    f"[MÉMOIRE DE TRAVAIL (LE ROMAN) - Ce contexte concerne uniquement le récit fictif]\n"
                    f"<memoire_travail>\n{note}\n</memoire_travail>"
                )
        except Exception as e:
            logger.error("[ARCHIVISTE:RETOUR] lecteur -> ERREUR API : %s", e)
            self.error_occurred.emit(f"[Archiviste/lecture] Erreur API : {e}")
            self.note_ready.emit("")


class ArchivisteReader(QObject):
    """
    Produit une note de contexte issue de la Bible avant chaque réponse.

    Flux :
        main_window appelle build_context_note(question)
        → si Bible vide → émet context_note_ready("") immédiatement
        → sinon → thread API → émet context_note_ready(note)
    """

    context_note_ready = pyqtSignal(str)   # "" ou note de contexte
    error_occurred     = pyqtSignal(str)

    def __init__(self, config: dict, bible_db: BibleDB, parent=None):
        """
        Args:
            config:   dict avec keys "api_key", "base_url" (ou None), "model"
            bible_db: instance BibleDB du projet courant
        """
        super().__init__(parent)
        self._bible_db = bible_db
        self._model = config.get("model", "gpt-4o-mini")
        self._system_prompt = load_prompt("archiviste_reader")
        api_key_val = config.get("api_key", "")
        self._client = OpenAI(
            api_key=api_key_val.strip() if api_key_val else "",
            base_url=config.get("base_url") or None,
            default_headers=config.get("extra_headers") or None,
        )
        self._worker: _ReaderCallWorker | None = None

    # ─── API publique ─────────────────────────────────────────────────────────

    def build_context_note(self, question: str, bible_context: str = "") -> None:
        """
        Construit la note de contexte à partir des hits FAISS Bible.

        Args:
            question:      message que l'auteur s'apprête à envoyer
            bible_context: entrées Bible pré-sélectionnées par FAISS.
                           Si vide → rien n'est injecté. Pas de fallback.

        La Bible n'est injectée que de deux façons :
          1. FAISS mémorisé + hits pertinents → bible_context non vide ici
          2. Commande /bible explicite → gérée dans main_window, hors Reader
        """
        if not bible_context:
            self.context_note_ready.emit("")
            return

        if self._worker and self._worker.isRunning():
            logger.debug("ArchivisteReader — déjà occupé, note sautée")
            self.context_note_ready.emit("")
            return

        logger.info("[ARCHIVISTE:LECTURE] construction note de contexte pour : %s", question[:60])
        self._worker = _ReaderCallWorker(
            self._client, self._model, bible_context, question, self._system_prompt
        )
        self._worker.note_ready.connect(self.context_note_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.start()

    def update_config(self, config: dict) -> None:
        """Met à jour la config API."""
        self._model = config.get("model", "gpt-4o-mini")
        api_key_val = config.get("api_key", "")
        self._client = OpenAI(
            api_key=api_key_val.strip() if api_key_val else "",
            base_url=config.get("base_url") or None,
            default_headers=config.get("extra_headers") or None,
        )
