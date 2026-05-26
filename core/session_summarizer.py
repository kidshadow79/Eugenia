"""
SessionSummarizer -- Résumation automatique de session

A la fermeture de l'app (ou sur demande), genere un resume compact
de la conversation en cours via l'IA principale, puis le persiste.

Structure sur disque :
  data/projects/{slug}/session_summaries/
      2026-05-05_20-03-12.md    <- un fichier par session resumee

Format du fichier :
  # Resume de session — 05/05/2026 20:03
  ...texte du resume...

API publique :
  summarizer = SessionSummarizer(project_dir, engine_config)
  summarizer.summarize(session_id, messages, on_done, on_error)
     -> lance un QThread, appelle on_done(session_id, summary_text) a la fin

Le resume de la derniere session est charge au demarrage et injecte
en contexte systeme pour donner a EUGENIA la memoire de la session precedente.
"""

import logging
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal, QObject
from openai import OpenAI

from core.config_manager import load_prompt

logger = logging.getLogger(__name__)

_SUMMARIES_DIR = "session_summaries"


# ------------------------------------------------------------------
# Worker QThread
# ------------------------------------------------------------------

class _SummaryWorker(QThread):
    done = pyqtSignal(str, str)   # session_id, summary_text
    error = pyqtSignal(str)       # message d'erreur

    def __init__(self, session_id: str, messages: list[dict],
                 client: OpenAI, model: str, system_prompt: str):
        super().__init__()
        self._session_id = session_id
        self._messages = messages
        self._client = client
        self._model = model
        self._system_prompt = system_prompt

    def run(self):
        try:
            # Construit le contenu a resumer
            lines = []
            for m in self._messages:
                content = m.get("content", "")
                if isinstance(content, list):
                    text_parts = [
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                    content = " ".join(text_parts)
                lines.append(f"[{m.get('role', 'user').upper()}] {content}")
            transcript = "\n".join(lines)
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.3,
                max_tokens=800,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user",   "content": transcript},
                ],
            )
            summary = response.choices[0].message.content.strip()
            self.done.emit(self._session_id, summary)
        except Exception as exc:
            logger.error("SummaryWorker — echec : %s", exc)
            self.error.emit(str(exc))


# ------------------------------------------------------------------
# SessionSummarizer
# ------------------------------------------------------------------

class SessionSummarizer(QObject):
    summary_done = pyqtSignal(str, str)   # session_id, summary_text

    def __init__(self, project_dir: Path, engine_config: dict):
        super().__init__()
        self._dir = project_dir / _SUMMARIES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._client = OpenAI(
            api_key=engine_config["api_key"],
            base_url=engine_config.get("base_url"),
        )
        self._model = engine_config["model"]
        self._system_prompt = load_prompt("session_summarizer")
        self._worker: _SummaryWorker | None = None

    # ------------------------------------------------------------------
    # Lancer un resume
    # ------------------------------------------------------------------

    def summarize(self, session_id: str, messages: list[dict],
                  on_done=None, on_error=None) -> None:
        """Lance la résumation en arrière-plan."""
        if not messages:
            logger.debug("SessionSummarizer.summarize — messages vides, ignore")
            return

        if self._worker and self._worker.isRunning():
            logger.warning("SessionSummarizer.summarize — worker deja en cours, ignore l'appel")
            return

        self._worker = _SummaryWorker(
            session_id=session_id,
            messages=messages,
            client=self._client,
            model=self._model,
            system_prompt=self._system_prompt,
        )

        def _on_done(sid: str, text: str):
            self._persist(sid, text)
            self.summary_done.emit(sid, text)
            if on_done:
                on_done(sid, text)

        self._worker.done.connect(_on_done)
        if on_error:
            self._worker.error.connect(on_error)
        self._worker.start()
        logger.info("SessionSummarizer.summarize — lance pour session %s", session_id)

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------

    def _persist(self, session_id: str, text: str) -> None:
        """Sauvegarde le résumé dans un fichier .md horodate."""
        path = self._dir / f"{session_id}.md"
        ts = self._id_to_ts(session_id)
        content = f"# Resume de session — {ts}\n\n{text}\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("SessionSummarizer._persist — resume sauvegarde : %s", path)

    # ------------------------------------------------------------------
    # Chargement du dernier resume (contexte session suivante)
    # ------------------------------------------------------------------

    def load_last_summary(self) -> str:
        """
        Retourne le texte du résumé de la session la plus récente.
        Retourne une chaine vide s'il n'y en a pas.
        """
        files = sorted(self._dir.glob("*.md"), reverse=True)
        if not files:
            return ""
        try:
            with open(files[0], "r", encoding="utf-8") as f:
                return f.read()
        except Exception as exc:
            logger.error("SessionSummarizer.load_last_summary — %s", exc)
            return ""

    def load_recent_summaries(self, limit: int = 3) -> list[str]:
        """
        Retourne les textes des N résumés les plus récents (les plus récents en premier).
        """
        files = sorted(self._dir.glob("*.md"), reverse=True)
        results = []
        for file in files[:limit]:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    results.append(f.read())
            except Exception as exc:
                logger.error("SessionSummarizer.load_recent_summaries — %s", exc)
        return results
        try:
            with open(files[0], "r", encoding="utf-8") as f:
                return f.read()
        except Exception as exc:
            logger.error("SessionSummarizer.load_last_summary — %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Utilitaire
    # ------------------------------------------------------------------

    @staticmethod
    def _id_to_ts(session_id: str) -> str:
        try:
            dt = datetime.strptime(session_id, "%Y-%m-%d_%H-%M-%S")
            return dt.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return session_id
