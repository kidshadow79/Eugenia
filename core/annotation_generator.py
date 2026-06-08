"""
annotation_generator.py — Génération intelligente d'annotations Ghost Writer

L'Archiviste reçoit la demande en langage naturel de l'auteur + le contexte
(extrait partagé), et rédige lui-même une annotation concise et actionnable.

Signal émis :
    annotation_ready(str, str)  : label, note
    error_occurred(str)         : message d'erreur

Usage :
    gen = AnnotationGenerator(config, user_request, context_clip)
    gen.annotation_ready.connect(handler)
    gen.error_occurred.connect(err_handler)
    gen.start()
"""

import json
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from openai import OpenAI

logger = logging.getLogger(__name__)

# ─── Prompt ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """Tu es l'Archiviste, le subconscient d'un assistant d'écriture pour auteurs.

L'auteur te demande de créer une annotation sur son manuscrit.
Tu dois rédiger une annotation COURTE, PRÉCISE et ACTIONNABLE.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après :
{
  "label": "...",
  "note": "..."
}

Règles :
- label : 3 à 6 mots maximum, style titre court (ex. : "Recherche : banquets antiques")
- note : 1 à 3 phrases maximum, formulée à l'impératif ou infinitif, concrete et utile
- N'invente rien : base-toi sur la demande et le contexte fourni
- Si un extrait de texte est fourni en contexte, l'annotation lui est ancrée
"""

_USER_PROMPT = """Demande de l'auteur : {request}

Contexte (extrait du manuscrit en cours) :
---
{context}
---

Rédige l'annotation (JSON uniquement)."""


class AnnotationGenerator(QThread):
    """
    Thread unique : appel LLM Archiviste → retourne label + note pour un badge.
    """

    annotation_ready = pyqtSignal(str, str)   # label, note
    error_occurred   = pyqtSignal(str)

    def __init__(self, config: dict, user_request: str, context_clip: str, parent=None):
        """
        Args:
            config:        dict avec keys "api_key", "base_url" (ou None), "model"
            user_request:  message brut de l'auteur (ex. "écris une annotation sur…")
            context_clip:  dernier extrait partagé dans le contexte IA
        """
        super().__init__(parent)
        api_key_val = config.get("api_key", "")
        self._client = OpenAI(
            api_key=api_key_val.strip() if api_key_val else "",
            base_url=config.get("base_url") or None,
            default_headers=config.get("extra_headers") or None,
        )
        self._model        = config.get("model", "mistral-small-latest")
        self._request      = user_request
        self._context_clip = context_clip

    def run(self):
        logger.info("[GHOST:ANNOT] génération annotation model=%s request=%r",
                    self._model, self._request[:60])
        user_content = _USER_PROMPT.format(
            request=self._request,
            context=self._context_clip[:800] if self._context_clip else "(aucun extrait partagé)",
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": user_content},
                ],
                temperature=0.3,
                max_tokens=150,
            )
            raw = (response.choices[0].message.content or "").strip()
            # Nettoyer le markdown éventuel (```json ... ```)
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            data   = json.loads(raw)
            label  = str(data.get("label", "")).strip()
            note   = str(data.get("note",  "")).strip()

            if not label or not note:
                raise ValueError(f"JSON incomplet : {raw!r}")

            logger.info("[GHOST:ANNOT] annotation générée — label=%r note=%r", label, note[:60])
            self.annotation_ready.emit(label, note)

        except json.JSONDecodeError as exc:
            msg = f"AnnotationGenerator — JSON invalide : {exc} — raw={raw!r}"
            logger.error(msg)
            self.error_occurred.emit(msg)
        except Exception as exc:
            msg = f"AnnotationGenerator — erreur : {exc}"
            logger.error(msg)
            self.error_occurred.emit(msg)
