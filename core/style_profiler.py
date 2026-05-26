"""
StyleProfiler -- Analyse du style d'écriture de l'auteur

Analyse un echantillon du manuscrit (top chunks les plus representatifs)
et genere un profil de style persist\u00e9 en JSON.

Structure sur disque :
  data/projects/{slug}/style_profile.json
  {
    "generated_at": "2026-05-05T20:03:15",
    "source_ids":   ["roman-ch1.docx", ...],
    "profile":      "Texte libre décrivant le style..."
  }

Le profil est injecte en contexte systeme au demarrage de chaque session.

API publique :
  profiler = StyleProfiler(project_dir, engine_config)
  profiler.analyze(chunks_sample)        -- lance l'analyse, emet profile_ready
  profiler.load_profile()                -- retourne le texte du profil ou ""
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, QObject
from openai import OpenAI

from core.config_manager import load_prompt

logger = logging.getLogger(__name__)

_PROFILE_FILE = "style_profile.json"


# ------------------------------------------------------------------
# Worker QThread
# ------------------------------------------------------------------

class _StyleWorker(QThread):
    done  = pyqtSignal(str)   # profile_text
    error = pyqtSignal(str)   # message d'erreur

    def __init__(self, sample_text: str, client: OpenAI,
                 model: str, system_prompt: str):
        super().__init__()
        self._sample = sample_text
        self._client = client
        self._model = model
        self._system_prompt = system_prompt

    def run(self):
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.2,
                max_tokens=600,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user",   "content": self._sample},
                ],
            )
            profile = response.choices[0].message.content.strip()
            self.done.emit(profile)
        except Exception as exc:
            logger.error("StyleWorker — echec : %s", exc)
            self.error.emit(str(exc))


# ------------------------------------------------------------------
# StyleProfiler
# ------------------------------------------------------------------

class StyleProfiler(QObject):
    profile_ready = pyqtSignal(str)   # profile_text

    def __init__(self, project_dir: Path, engine_config: dict):
        super().__init__()
        self._dir = project_dir
        self._path = project_dir / _PROFILE_FILE
        self._client = OpenAI(
            api_key=engine_config["api_key"],
            base_url=engine_config.get("base_url"),
        )
        self._model = engine_config["model"]
        self._system_prompt = load_prompt("style_profiler")
        self._worker: _StyleWorker | None = None

    # ------------------------------------------------------------------
    # Analyse
    # ------------------------------------------------------------------

    def analyze(self, text_sample: str, source_ids: list[str] | None = None) -> None:
        """Lance l'analyse en arriere-plan sur text_sample."""
        if not text_sample.strip():
            logger.debug("StyleProfiler.analyze — echantillon vide, ignore")
            return

        self._source_ids = source_ids or []
        self._worker = _StyleWorker(
            sample_text=text_sample,
            client=self._client,
            model=self._model,
            system_prompt=self._system_prompt,
        )
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(lambda e: logger.error("StyleProfiler — %s", e))
        self._worker.start()
        logger.info("StyleProfiler.analyze — lance (modele=%s)", self._model)

    def _on_done(self, profile_text: str) -> None:
        self._persist(profile_text)
        self.profile_ready.emit(profile_text)

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------

    def _persist(self, profile_text: str) -> None:
        data = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_ids":   getattr(self, "_source_ids", []),
            "profile":      profile_text,
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("StyleProfiler._persist — profil sauvegarde")

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def load_profile(self) -> str:
        """Retourne le texte du profil de style, ou chaine vide si absent."""
        if not self._path.exists():
            return ""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("profile", "")
        except Exception as exc:
            logger.error("StyleProfiler.load_profile — %s", exc)
            return ""
