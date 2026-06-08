"""
rolling_summarizer.py — Résumé glissant de conversation pour EUGENIA

Adapté du système ConversationSummarizer d'OGMA (version synchrone, QThread).

Principe fenêtre glissante :
  - Accumule les messages user/assistant
  - Quand le nombre de messages non résumés >= TRIGGER (défaut 20),
    résume un BLOC de BLOCK_SIZE messages via l'Archiviste
  - L'historique envoyé à l'API = résumés compressés + KEEP_RECENT messages récents
  - Les résumés sont persistés dans un fichier .meta.json à côté du .jsonl

Architecture :
  RollingSummarizer          — gestionnaire principal (QObject)
  _SummaryWorker(QThread)   — appel API asynchrone pour créer un résumé
"""

import hashlib
import json
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from openai import OpenAI

logger = logging.getLogger(__name__)

# ─── Paramètres ──────────────────────────────────────────────────────────────

BLOCK_SIZE   = 10   # résumer par blocs de 10 messages
TRIGGER      = 20   # déclencher quand >= 20 messages non résumés
KEEP_RECENT  = 15   # toujours garder les N derniers messages en clair
MAX_TOKENS   = 400  # budget tokens pour chaque résumé

_SYSTEM_PROMPT = """Tu es un assistant de synthèse. Tu reçois un extrait de conversation
entre un auteur et EUGENIA (son IA d'aide à l'écriture).
Résume cet échange en maximum 200 mots :
- Style factuel et condensé
- Préserve les décisions, questions ouvertes, informations sur le projet
- Ignore les politesses et bavardages
- Écris à la troisième personne ("l'auteur a mentionné...", "EUGENIA a proposé...")
Réponds UNIQUEMENT avec le résumé, sans titre ni explication."""


# ─── Worker QThread ───────────────────────────────────────────────────────────

class _SummaryWorker(QThread):
    done  = pyqtSignal(str, str, int, int)  # cache_key, summary_text, start, end
    error = pyqtSignal(str)

    def __init__(self, client: OpenAI, model: str,
                 messages: list[dict], start: int, end: int, cache_key: str):
        super().__init__()
        self._client    = client
        self._model     = model
        self._messages  = messages
        self._start     = start
        self._end       = end
        self._cache_key = cache_key

    def run(self):
        logger.debug(
            "[SUMMARIZER:WORKER] démarrage — bloc messages %d→%d, model=%s",
            self._start, self._end, self._model,
        )
        # Formater le bloc à résumer
        lines = []
        for m in self._messages:
            role = "Auteur" if m.get("role") == "user" else "EUGENIA"
            content = m.get("content", "")
            
            # Gestion multimodale : extraire le texte des listes
            if isinstance(content, list):
                text_parts = [
                    part.get("text", "") 
                    for part in content 
                    if isinstance(part, dict) and part.get("type") == "text"
                ]
                content = " ".join(text_parts)
                
            if isinstance(content, str) and content.strip():
                lines.append(f"[{role}] {content.strip()}")
        transcript = "\n\n".join(lines)
        if not transcript:
            logger.warning("[SUMMARIZER:WORKER] bloc %d-%d vide — abandon", self._start, self._end)
            self.error.emit("bloc vide")
            return

        logger.debug(
            "[SUMMARIZER:WORKER] transcript prêt : %d chars, %d tours de parole",
            len(transcript), len(lines),
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.3,
                max_tokens=MAX_TOKENS,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": transcript},
                ],
            )
            summary = (response.choices[0].message.content or "").strip()
            usage = getattr(response, "usage", None)
            tokens_info = (
                f"prompt={usage.prompt_tokens} completion={usage.completion_tokens} total={usage.total_tokens}"
                if usage else "tokens=N/A"
            )
            if summary:
                logger.info(
                    "[SUMMARIZER:WORKER] ✓ résumé créé — msgs %d-%d | %d chars | %s",
                    self._start, self._end, len(summary), tokens_info,
                )
                logger.debug(
                    "[SUMMARIZER:WORKER] aperçu résumé : %s",
                    summary[:120] + ("…" if len(summary) > 120 else ""),
                )
                self.done.emit(self._cache_key, summary, self._start, self._end)
            else:
                logger.error(
                    "[SUMMARIZER:WORKER] résumé vide retourné par l'API — %s", tokens_info
                )
                self.error.emit("résumé vide retourné par l'API")
        except Exception as exc:
            logger.error(
                "[SUMMARIZER:WORKER] ✗ erreur API bloc %d-%d : %s",
                self._start, self._end, exc, exc_info=True,
            )
            self.error.emit(str(exc))


# ─── Gestionnaire principal ───────────────────────────────────────────────────

class RollingSummarizer(QObject):
    """
    Gère la résumation glissante d'une session de conversation.

    Signaux :
        summary_ready()   — un nouveau résumé vient d'être créé et persisté
        summary_error(str) — erreur non bloquante

    Usage :
        summarizer = RollingSummarizer(engine_config, meta_path)
        summarizer.summary_ready.connect(on_ready)

        # Après chaque réponse IA :
        all_messages = conv_store.load_session(session_id)
        summarizer.maybe_summarize(all_messages)

        # Avant l'appel API :
        messages_for_api = summarizer.build_optimized_history(
            system_prompt, injections, all_messages
        )
    """

    summary_ready = pyqtSignal()    # un résumé vient d'être ajouté
    summary_error = pyqtSignal(str)

    def __init__(self, engine_config: dict, meta_path: Path, parent=None):
        super().__init__(parent)
        api_key_val = engine_config.get("api_key", "")
        self._client = OpenAI(
            api_key=api_key_val.strip() if api_key_val else "",
            base_url=engine_config.get("base_url") or None,
            default_headers=engine_config.get("extra_headers") or None,
        )
        self._model     = engine_config["model"]
        self._meta_path = meta_path

        # État en mémoire
        self._summaries: list[dict] = []   # [{start, end, text, cache_key}]
        self._cache: dict[str, str] = {}   # cache_key → text
        self._last_summarized: int  = 0    # index du dernier message résumé
        self.last_ego_scanned: int = 0
        self._worker: _SummaryWorker | None = None

        self._load_meta()

    # ── Persistance ──────────────────────────────────────────────────────────

    def _load_meta(self) -> None:
        if not self._meta_path.exists():
            logger.debug("[SUMMARIZER:META] pas de fichier méta : %s", self._meta_path)
            return
        try:
            with open(self._meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._summaries = data.get("summaries", [])
            self._last_summarized = data.get("last_summarized", 0)
            self.last_ego_scanned = data.get("last_ego_scanned", 0)
            for s in self._summaries:
                if s.get("cache_key") and s.get("text"):
                    self._cache[s["cache_key"]] = s["text"]
            logger.info(
                "[SUMMARIZER:META] chargé : %d résumés | last_summarized=%d | fichier=%s",
                len(self._summaries), self._last_summarized, self._meta_path.name,
            )
            for i, s in enumerate(self._summaries):
                logger.debug(
                    "[SUMMARIZER:META]   résumé[%d] msgs %d-%d : %s",
                    i, s.get("start", "?"), s.get("end", "?"),
                    (s.get("text", ""))[:80] + "…",
                )
        except Exception as exc:
            logger.error(
                "[SUMMARIZER:META] ✗ échec chargement '%s' : %s",
                self._meta_path, exc, exc_info=True,
            )

    def _save_meta(self) -> None:
        try:
            with open(self._meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "summaries":       self._summaries,
                        "last_summarized": self._last_summarized,
                    "last_ego_scanned": self.last_ego_scanned,
                    },
                    f, ensure_ascii=False, indent=2,
                )
            logger.debug(
                "[SUMMARIZER:META] sauvegardé : %d résumés, last=%d → %s",
                len(self._summaries), self._last_summarized, self._meta_path.name,
            )
        except Exception as exc:
            logger.error(
                "[SUMMARIZER:META] ✗ échec sauvegarde '%s' : %s",
                self._meta_path, exc, exc_info=True,
            )

    # ── API publique ──────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Réinitialise pour une nouvelle session (sans toucher le fichier méta)."""
        logger.info(
            "[SUMMARIZER] reset — %d résumés effacés, last_summarized remis à 0",
            len(self._summaries),
        )
        self._summaries.clear()
        self._cache.clear()
        self._last_summarized = 0
        self.last_ego_scanned = 0
        self.last_ego_scanned = 0
        if self._worker and self._worker.isRunning():
            logger.warning("[SUMMARIZER] reset pendant un worker actif — arrêt du worker")
            self._worker.quit()
        self._worker = None

    def load_for_session(self, meta_path: Path) -> None:
        """Change le fichier méta (reprise d'une session existante)."""
        logger.info("[SUMMARIZER] load_for_session — nouveau fichier méta : %s", meta_path.name)
        self.reset()
        self._meta_path = meta_path
        self._load_meta()

    def maybe_summarize(self, all_messages: list[dict]) -> None:
        """
        Appelé après chaque réponse IA.
        Lance un résumé si le seuil TRIGGER est atteint et qu'aucun worker
        n'est déjà en cours.
        """
        valid = [m for m in all_messages if m.get("role") in ("user", "assistant")]
        unsummarized = len(valid) - self._last_summarized

        logger.debug(
            "[SUMMARIZER:CHECK] total=%d valides | résumés jusqu'à=%d | non résumés=%d | seuil=%d",
            len(valid), self._last_summarized, unsummarized, TRIGGER,
        )

        if self._worker and self._worker.isRunning():
            logger.debug("[SUMMARIZER:CHECK] worker déjà actif — vérification ignorée")
            return

        if unsummarized < TRIGGER:
            logger.info(
                "[SUMMARIZER:CHECK] %d/%d msgs avant prochain résumé",
                unsummarized, TRIGGER,
            )
            return

        # Choisir le bloc à résumer
        start = self._last_summarized
        end   = start + BLOCK_SIZE
        if end > len(valid):
            logger.debug(
                "[SUMMARIZER:CHECK] bloc %d-%d incomplet (seulement %d msgs) — attente",
                start, end, len(valid) - start,
            )
            return

        block    = valid[start:end]
        cache_key = self._make_cache_key(block)

        # Cache hit → pas d'appel API
        if cache_key in self._cache:
            logger.info(
                "[SUMMARIZER:CHECK] cache hit bloc %d-%d (key=%s) — skip API",
                start, end, cache_key,
            )
            self._last_summarized = max(self._last_summarized, end)
            self._save_meta()
            return

        logger.info(
            "[SUMMARIZER:CHECK] ▶ déclenchement — %d msgs non résumés | bloc %d-%d | model=%s",
            unsummarized, start, end, self._model,
        )
        self._worker = _SummaryWorker(
            self._client, self._model, block, start, end, cache_key
        )
        self._worker.done.connect(self._on_summary_done)
        self._worker.error.connect(self._on_summary_error)
        self._worker.start()

    def build_optimized_history(
        self,
        system_prompt: str,
        all_messages: list[dict],
    ) -> list[dict]:
        """
        Construit la liste de messages à envoyer à l'API :
          [system] + [résumés compressés comme system notes]
          + [KEEP_RECENT messages récents]

        Remplace l'historique complet et réduit drastiquement la consommation
        de tokens pour les longues sessions.
        """
        valid = [m for m in all_messages if m.get("role") in ("user", "assistant")]

        # Si la session est courte, pas de compression — historique complet
        if len(valid) <= KEEP_RECENT:
            logger.debug(
                "[SUMMARIZER:BUILD] session courte (%d msgs ≤ %d) — historique complet",
                len(valid), KEEP_RECENT,
            )
            return [{"role": "system", "content": system_prompt}] + valid

        # Résumés disponibles (triés chronologiquement)
        sorted_summaries = sorted(self._summaries, key=lambda s: s.get("start", 0))
        summary_texts = [s["text"] for s in sorted_summaries if s.get("text")]

        # Messages récents (toujours en clair)
        keep_from    = max(self._last_summarized, len(valid) - KEEP_RECENT)
        recent       = valid[keep_from:]

        history: list[dict] = [{"role": "system", "content": system_prompt}]

        if summary_texts:
            block = "\n\n---\n\n".join(
                f"[Résumé bloc {i+1}]\n{t}" for i, t in enumerate(summary_texts)
            )
            history.append({
                "role": "system",
                "content": (
                    "[MÉMOIRE DE TRAVAIL — résumés des échanges précédents]\n"
                    "Ces résumés condensent les échanges passés de cette session "
                    "pour préserver le contexte sans surcharger la fenêtre.\n\n"
                    + block
                ),
            })

        history.extend(recent)

        logger.info(
            "[SUMMARIZER:BUILD] historique optimisé — %d résumé(s) | %d msgs récents "
            "(keep_from=%d sur %d total) | %d msg(s) envoyés à l'API",
            len(summary_texts), len(recent), keep_from, len(valid), len(history),
        )
        return history

    # ── Interne ───────────────────────────────────────────────────────────────

    def _on_summary_done(self, cache_key: str, text: str, start: int, end: int) -> None:
        self._cache[cache_key] = text
        self._summaries.append({
            "start":     start,
            "end":       end,
            "text":      text,
            "cache_key": cache_key,
        })
        self._last_summarized = max(self._last_summarized, end)
        self._save_meta()
        logger.info(
            "[SUMMARIZER] ✓ résumé persisté — msgs %d-%d | total résumés : %d | last_summarized=%d",
            start, end, len(self._summaries), self._last_summarized,
        )
        self.summary_ready.emit()

    def _on_summary_error(self, msg: str) -> None:
        logger.error("[SUMMARIZER] ✗ erreur worker : %s", msg)
        self.summary_error.emit(msg)

    @staticmethod
    def _make_cache_key(messages: list[dict]) -> str:
        content = "".join(
            m.get("role", "") + str(m.get("content", "")) for m in messages
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    # ── Utilitaire : chemin méta pour une session ──────────────────────────────

    @staticmethod
    def meta_path_for(session_jsonl: Path) -> Path:
        """Retourne le chemin du fichier méta pour un fichier JSONL de session."""
        return session_jsonl.with_suffix(".meta.json")
