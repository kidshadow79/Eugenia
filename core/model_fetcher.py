"""
model_fetcher.py — Récupération dynamique des modèles disponibles

Stratégie par provider :
    - OpenAI-compatible (openai, mistral, grok, openrouter) :
        OpenAI SDK → client.models.list()
    - Anthropic :
        httpx → GET https://api.anthropic.com/v1/models
    - Google :
        httpx → GET https://generativelanguage.googleapis.com/v1beta/models?key=...

Usage :
    worker = ModelFetchWorker(provider_id="openai", api_key="sk-...", embed_mode=False)
    worker.models_ready.connect(my_slot)   # slot(list[str])
    worker.fetch_error.connect(my_slot)    # slot(str)
    worker.start()
"""

import httpx
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from openai import OpenAI

from core.providers import PROVIDERS, get_base_url

logger = logging.getLogger(__name__)


# ─── Filtres chat / embed ──────────────────────────────────────────────────────

_CHAT_EXCLUDE = ("embed", "whisper", "tts", "dall-e", "moderation", "babbage", "ada")
_EMBED_INCLUDE = ("embed",)


def _filter_chat(model_ids: list[str]) -> list[str]:
    return [m for m in model_ids if not any(x in m.lower() for x in _CHAT_EXCLUDE)]


def _filter_embed(model_ids: list[str]) -> list[str]:
    return [m for m in model_ids if any(x in m.lower() for x in _EMBED_INCLUDE)]


# ─── Fonctions de fetch par stratégie ─────────────────────────────────────────

def _fetch_openai_compatible(api_key: str, base_url: str | None, embed_mode: bool, extra_headers: dict | None = None) -> list[str]:
    """
    Utilise le SDK openai — fonctionne pour tout endpoint /v1/models compatible.
    """
    client = OpenAI(
        api_key=api_key.strip() if api_key else "",
        base_url=base_url,
        default_headers=extra_headers
    )
    all_ids = sorted(m.id for m in client.models.list().data)
    return _filter_embed(all_ids) if embed_mode else _filter_chat(all_ids)


def _fetch_anthropic(api_key: str, embed_mode: bool) -> list[str]:
    """Appel direct à l'API Anthropic (non OpenAI-compatible)."""
    if embed_mode:
        return []   # Anthropic n'a pas de modèles d'embedding
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    r = httpx.get(
        "https://api.anthropic.com/v1/models",
        headers=headers,
        params={"limit": 100},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    return sorted(m["id"] for m in data if m.get("type") == "model")


def _fetch_google(api_key: str, embed_mode: bool) -> list[str]:
    """Appel direct à l'API Google Generative Language."""
    r = httpx.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": api_key, "pageSize": 100},
        timeout=15,
    )
    r.raise_for_status()
    models = r.json().get("models", [])
    if embed_mode:
        return sorted(
            m["name"].replace("models/", "")
            for m in models
            if "embedContent" in m.get("supportedGenerationMethods", [])
        )
    else:
        return sorted(
            m["name"].replace("models/", "")
            for m in models
            if "generateContent" in m.get("supportedGenerationMethods", [])
        )


# ─── Worker QThread ───────────────────────────────────────────────────────────

class ModelFetchWorker(QThread):
    """
    Récupère la liste des modèles dans un thread séparé.

    Signaux :
        models_ready(list[str])  : modèles récupérés avec succès
        fetch_error(str)         : message d'erreur lisible
    """

    models_ready = pyqtSignal(list)
    fetch_error  = pyqtSignal(str)

    def __init__(self, provider_id: str, api_key: str, embed_mode: bool = False):
        super().__init__()
        self._provider_id = provider_id
        self._api_key     = api_key
        self._embed_mode  = embed_mode

    def run(self):
        logger.debug("ModelFetchWorker — début fetch provider=%s embed=%s",
                     self._provider_id, self._embed_mode)
        try:
            models = self._do_fetch()
            if models:
                logger.info("ModelFetchWorker — %d modèle(s) récupérés (provider=%s)",
                            len(models), self._provider_id)
                self.models_ready.emit(models)
            else:
                logger.warning("ModelFetchWorker — aucun modèle retourné (provider=%s)",
                               self._provider_id)
                self.fetch_error.emit("Aucun modèle retourné par l'API.")
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 401:
                logger.error("ModelFetchWorker — 401 clé invalide (provider=%s)", self._provider_id)
                self.fetch_error.emit("Clé API invalide ou non autorisée.")
            else:
                logger.error("ModelFetchWorker — HTTP %s (provider=%s)", status, self._provider_id)
                self.fetch_error.emit(f"Erreur HTTP {status}.")
        except Exception as e:
            # Ne jamais exposer la clé API dans le message
            logger.error("ModelFetchWorker — %s (provider=%s)", type(e).__name__, self._provider_id)
            self.fetch_error.emit(f"Erreur de connexion ({type(e).__name__}).")

    def _do_fetch(self) -> list[str]:
        pid = self._provider_id

        if pid == "anthropic":
            return _fetch_anthropic(self._api_key, self._embed_mode)

        if pid == "google":
            return _fetch_google(self._api_key, self._embed_mode)

        # Tous les autres : OpenAI-compatible
        base_url = get_base_url(pid)
        from core.providers import get_extra_headers
        extra_headers = get_extra_headers(pid) or None
        return _fetch_openai_compatible(self._api_key, base_url, self._embed_mode, extra_headers)
