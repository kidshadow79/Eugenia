"""
archiviste_relational.py — Memoire relationnelle

Deux modes d'utilisation :
  1. extract_from_conversation(text)  — analyse une conversation complete
     (declenche lors des resumations ou scan a la fermeture)
  2. memorize_direct(text)            — memorise un element cite via /mem
     (l'Archiviste decide lui-meme : relationnelle ou travail)

Signaux :
    entries_added(int)           : nb d'entrees ajoutees
    nothing_found()              : aucune info pertinente
    mem_routed_to_work(str)      : l'element /mem concerne le roman (pas l'auteur)
    error_occurred(str)          : erreur API
"""

import json
import re
import logging
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from openai import OpenAI

from core.relational_db import RelationalDB
from core.config_manager import load_prompt

logger = logging.getLogger(__name__)

# ─── Prompt système (mode résumation → mémoire relationnelle) ─────────────

_SYSTEM_PROMPT_RELATIONAL = """Tu es l'Archiviste, le subconscient d'un assistant d'écriture.

Ta mission : analyser une conversation entre un auteur et son IA pour en extraire
des informations sur l'AUTEUR (pas sur le roman qu'il écrit). Il s'agit de la mémoire RELATIONNELLE,
distincte de la mémoire de travail (qui concerne le roman).

Tu dois explicitement capturer les entités du monde réel liées à l'auteur :
membres de sa famille (ex: sa grand-mère, son frère), amis, proches, lieux réels qu'il fréquente,
ou tout autre aspect tangible de sa vraie vie.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après.

Format attendu :
{
  "notes": [
    {"category": "style", "content": "Préfère les phrases courtes"},
    {"category": "habitudes", "content": "Écrit le matin"},
    {"category": "contexte", "content": "Travaille sur un roman historique en parallèle"},
    {"category": "preferences", "content": "Aime les romans de Thomas Hardy"},
    {"category": "famille", "content": "Très proche de sa grand-mère"}
  ],
  "entities": [
    {"type": "person", "label": "Sophie", "content": "Son éditrice chez Gallimard"},
    {"type": "person", "label": "Grand-mère", "content": "Membre de sa famille dont il parle souvent"},
    {"type": "place",  "label": "Lyon",    "content": "Sa ville de résidence"}
  ]
}

Catégories de notes : "style", "habitudes", "contexte", "preferences", "objectifs", "famille", "proches"
Types d'entités : "person", "place", "event", "other"

Règles :
- N'extrais QUE ce que l'auteur dit sur LUI-MÊME et sur le MONDE RÉEL.
- Ignore tout ce qui concerne le roman ou les personnages fictifs (cela va dans la mémoire de travail).
- Les deux listes peuvent être vides si rien de pertinent.
- Formule de façon concise et factuelle.
"""

_USER_PROMPT_RELATIONAL = """Conversation entre l'auteur et l'IA :
---
{conversation_text}
---

Extrais les informations sur l'auteur (JSON uniquement)."""

# ─── Routage /mem ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_MEM_ROUTING = """Tu es l'Archiviste, le subconscient d'un assistant d'ecriture.

L'auteur vient de demander de memoriser un element. Determine si cet element
concerne l'AUTEUR lui-meme (memoire relationnelle) ou le ROMAN qu'il ecrit
(memoire de travail), puis extrait-en la structure appropriee.

Reponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou apres.

Si c'est une information sur l'AUTEUR :
{
  "memory_type": "relational",
  "category": "style"|"habitudes"|"preferences"|"contexte"|"objectifs",
  "content": "formulation concise et factuelle"
}

Si c'est une information sur le ROMAN (personnage, lieu, evenement, decision) :
{
  "memory_type": "work",
  "content": "l'information brute telle que formulee"
}

Regles :
- "relational" = ce que l'auteur dit sur LUI-MEME (ses habitudes, ses gouts, sa vie, ses interlocuteurs reels)
- "work" = tout ce qui concerne les personnages fictifs, le monde du roman, les decisions narratives, la structure du recit
- En cas de doute : si le sujet est clairement fictif (personnage, lieu imagine, intrigue) -> "work". Sinon -> "relational".
"""

_USER_PROMPT_MEM_ROUTING = """L'auteur a demande de memoriser :
---
{text}
---

Determine le type de memoire et extrait la structure (JSON uniquement)."""


class _MemRoutingWorker(QThread):
    """Thread de routage et d'extraction pour une commande /mem."""

    routed = pyqtSignal(dict)      # {"memory_type": "relational"|"work", ...}
    error  = pyqtSignal(str)

    def __init__(self, client: OpenAI, model: str, text: str):
        super().__init__()
        self._client = client
        self._model  = model
        self._text   = text

    def run(self):
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.1,
                max_tokens=256,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT_MEM_ROUTING},
                    {"role": "user",   "content": _USER_PROMPT_MEM_ROUTING.format(
                        text=self._text
                    )},
                ],
            )
            raw = response.choices[0].message.content or "{}"
            result = json.loads(raw)
            self.routed.emit(result)
        except Exception as e:
            logger.error("MemRoutingWorker — erreur : %s", e)
            self.error.emit(str(e))


class _RelationalCallWorker(QThread):
    """Thread d'appel API pour l'extraction de mémoire relationnelle."""

    extraction_done = pyqtSignal(dict)
    error_occurred  = pyqtSignal(str)

    def __init__(self, client: OpenAI, model: str, conversation_text: str, system_prompt: str):
        super().__init__()
        self._client = client
        self._model = model
        self._conversation_text = conversation_text
        self._system_prompt = system_prompt

    def run(self):
        logger.debug("RelationalWorker — appel API modèle=%s", self._model)
        logger.info("[ARCHIVISTE:APPEL] extraction conversation (%d chars)", len(self._conversation_text))
        user_content = _USER_PROMPT_RELATIONAL.format(
            conversation_text=self._conversation_text
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
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                self.error_occurred.emit(
                    f"[Archiviste/relationnel] JSON introuvable : {raw[:120]}"
                )
                return
            result = json.loads(match.group(0))
            n_notes = len(result.get("notes", []))
            n_ents  = len(result.get("entities", []))
            logger.info("RelationalWorker — extraction OK : %d notes, %d entités",
                        n_notes, n_ents)
            self.extraction_done.emit(result)
        except json.JSONDecodeError as e:
            logger.error("RelationalWorker — JSON invalide : %s", e)
            self.error_occurred.emit(f"[Archiviste/relationnel] JSON invalide : {e}")
        except Exception as e:
            logger.error("RelationalWorker — erreur API : %s", e)
            self.error_occurred.emit(f"[Archiviste/relationnel] Erreur API : {e}")


class ArchivisteRelational(QObject):
    """
    Extrait la mémoire relationnelle (infos sur l'auteur) depuis une conversation.

    Déclenché uniquement pendant la résumation — pas à chaque message.
    """

    entries_added      = pyqtSignal(int)    # nb d'entrées effectivement ajoutées (après dédup)
    nothing_found      = pyqtSignal()       # aucune info utile dans cette conversation
    mem_routed_to_work = pyqtSignal(str)    # /mem redirige vers la memoire de travail (contenu brut)
    error_occurred     = pyqtSignal(str)

    def __init__(self, config: dict, relational_db: RelationalDB, parent=None):
        """
        Args:
            config:        dict avec keys "api_key", "base_url", "model"
            relational_db: instance RelationalDB de l'auteur courant
        """
        super().__init__(parent)
        self._relational_db = relational_db
        self._model = config.get("model", "gpt-4o-mini")
        self._system_prompt = load_prompt("archiviste_relational")
        api_key_val = config.get("api_key", "")
        self._client = OpenAI(
            api_key=api_key_val.strip() if api_key_val else "",
            base_url=config.get("base_url") or None,
            default_headers=config.get("extra_headers") or None,
        )
        self._worker: _RelationalCallWorker | None = None

    # ─── API publique ─────────────────────────────────────────────────────────

    def extract_from_conversation(self, conversation_text: str) -> None:
        """Analyse une conversation complete et extrait la memoire relationnelle."""
        if not conversation_text or not conversation_text.strip():
            self.nothing_found.emit()
            return
        if self._worker and self._worker.isRunning():
            logger.debug("ArchivisteRelational — deja occupe, appel ignore")
            return
        logger.info("[ARCHIVISTE:APPEL] extract_from_conversation (%d chars)",
                    len(conversation_text))
        self._worker = _RelationalCallWorker(
            self._client, self._model, conversation_text, self._system_prompt
        )
        self._worker.extraction_done.connect(self._on_extraction_done)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.start()

    def memorize_direct(self, text: str) -> None:
        """
        Memorise un element cite via /mem.
        L'Archiviste route lui-meme vers relational ou work.
        Signaux emis : entries_added (relational OK) | mem_routed_to_work (roman) | error_occurred
        """
        if not text or not text.strip():
            self.nothing_found.emit()
            return
        if getattr(self, "_mem_routing_worker", None) is not None and self._mem_routing_worker.isRunning():
            logger.debug("ArchivisteRelational — /mem routing déjà en cours, appel ignoré")
            return
        logger.info("[ARCHIVISTE:APPEL] memorize_direct (/mem) : %s", text[:80])
        self._mem_routing_worker = _MemRoutingWorker(self._client, self._model, text)
        self._mem_routing_worker.routed.connect(self._on_mem_routed)
        self._mem_routing_worker.error.connect(self.error_occurred)
        self._mem_routing_worker.start()

    # ─── Interne ──────────────────────────────────────────────────────────────

    def _on_extraction_done(self, data: dict) -> None:
        """Écrit les données extraites dans la base relationnelle (avec déduplication)."""
        added = 0

        notes = data.get("notes", [])
        if isinstance(notes, list):
            for note in notes:
                category = (note.get("category") or "contexte").strip()
                content  = (note.get("content")  or "").strip()
                if content:
                    if self._relational_db.upsert_note(category, content):
                        added += 1

        entities = data.get("entities", [])
        if isinstance(entities, list):
            for ent in entities:
                etype   = (ent.get("type")    or "other").strip()
                label   = (ent.get("label")   or "").strip()
                content = (ent.get("content") or "").strip()
                if label and content:
                    if self._relational_db.upsert_entity(etype, label, content):
                        added += 1

        if added > 0:
            logger.info("ArchivisteRelational — %d entrée(s) ajoutée(s) en mémoire relationnelle", added)
            self.entries_added.emit(added)
        else:
            logger.debug("ArchivisteRelational — aucune info pertinente")
            logger.debug("[MEM:DOUBLON] toutes les entrees extraites etaient deja en base")
            self.nothing_found.emit()

    def update_config(self, config: dict) -> None:
        """Met à jour la config API."""
        self._model = config.get("model", "gpt-4o-mini")
        api_key_val = config.get("api_key", "")
        self._client = OpenAI(
            api_key=api_key_val.strip() if api_key_val else "",
            base_url=config.get("base_url") or None,
            default_headers=config.get("extra_headers") or None,
        )

    def _on_mem_routed(self, data: dict) -> None:
        """Recoit le resultat du routage /mem et agit selon le type."""
        memory_type = data.get("memory_type", "relational")
        content     = (data.get("content") or "").strip()

        if not content:
            self.nothing_found.emit()
            return

        if memory_type == "work":
            logger.info("ArchivisteRelational — /mem route vers memoire de travail : %s", content[:60])
            self.mem_routed_to_work.emit(content)
            return

        # memory_type == "relational"
        category = (data.get("category") or "contexte").strip()
        added = 1 if self._relational_db.upsert_note(category, content) else 0
        if added:
            logger.info("ArchivisteRelational — /mem memorise (relational/%s) : %s",
                        category, content[:60])
            self.entries_added.emit(added)
        else:
            logger.debug("ArchivisteRelational — /mem doublon ignore : %s", content[:60])
            self.nothing_found.emit()
