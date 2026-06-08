"""
providers.py — Catalogue des providers IA pour EUGENIA

Source de vérité pour :
    - les base_url à passer au client OpenAI-compatible
    - les modèles chat disponibles par provider
    - les modèles embed disponibles par provider
    - les hints d'affichage (label, format de clé attendu)

Architecture d'appel :
    Tous les providers sont appelés via le SDK openai (openai.OpenAI)
    en passant base_url + api_key. Seul Anthropic nécessite un header
    supplémentaire "anthropic-version" — géré dans archiviste_writer/reader.

Ajout d'un provider :
    Ajouter une entrée dans PROVIDERS. Le reste de l'app s'adapte automatiquement.
"""

from typing import Optional


# ─── Catalogue ────────────────────────────────────────────────────────────────

PROVIDERS: dict[str, dict] = {
    "openai": {
        "label":       "OpenAI",
        "base_url":    None,                           # SDK openai par défaut
        "key_hint":    "sk-...",
        "key_url":     "https://platform.openai.com/api-keys",
        "chat_models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "gpt-5",
        ],
        "embed_models": [
            "text-embedding-3-large",
            "text-embedding-3-small",
        ],
    },

    "anthropic": {
        "label":       "Anthropic",
        "base_url":    "https://api.anthropic.com/v1",
        "key_hint":    "sk-ant-...",
        "key_url":     "https://console.anthropic.com/settings/keys",
        "extra_headers": {"anthropic-version": "2023-06-01"},  # requis par Anthropic
        "chat_models": [
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ],
        "embed_models": [],   # Anthropic ne propose pas d'endpoint embedding
    },

    "mistral": {
        "label":       "Mistral",
        "base_url":    "https://api.mistral.ai/v1",
        "key_hint":    "...",
        "key_url":     "https://console.mistral.ai/api-keys",
        "chat_models": [
            "mistral-large-latest",
            "mistral-medium-2505",
            "mistral-small-latest",
            "pixtral-large-latest",
            "codestral-latest",
            "mistral-tiny",
        ],
        "embed_models": [
            "mistral-embed",
        ],
    },

    "google": {
        "label":       "Google",
        "base_url":    "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_hint":    "AIza...",
        "key_url":     "https://aistudio.google.com/app/apikey",
        "chat_models": [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-pro",
        ],
        "embed_models": [
            "text-embedding-004",
        ],
    },

    "grok": {
        "label":       "Grok (xAI)",
        "base_url":    "https://api.x.ai/v1",
        "key_hint":    "xai-...",
        "key_url":     "https://console.x.ai/",
        "chat_models": [
            "grok-4",
            "grok-3-mini",
            "grok-3-mini-fast",
            "grok-2-012",
            "grok-2-vision-012",
        ],
        "embed_models": [],
    },

    "openrouter": {
        "label":       "OpenRouter",
        "base_url":    "https://openrouter.ai/api/v1",
        "key_hint":    "sk-or-...",
        "key_url":     "https://openrouter.ai/settings/keys",
        "extra_headers": {
            "HTTP-Referer": "https://github.com",
            "X-Title": "EUGENIA"
        },
        "chat_models": [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3.5-haiku",
            "mistralai/mistral-large",
            "google/gemini-1.5-pro",
            "meta-llama/llama-3.3-70b-instruct",
            "deepseek/deepseek-chat",
        ],
        "embed_models": [],
    },
}

# Ordre d'affichage dans les dropdowns
PROVIDER_ORDER = ["openai", "anthropic", "mistral", "google", "grok", "openrouter"]


# ─── Fonctions utilitaires ────────────────────────────────────────────────────

def get_provider_labels() -> list[tuple[str, str]]:
    """Retourne [(provider_id, label), ...] dans l'ordre PROVIDER_ORDER."""
    return [(pid, PROVIDERS[pid]["label"]) for pid in PROVIDER_ORDER]


def get_chat_models(provider_id: str) -> list[str]:
    """Retourne la liste des modèles chat pour un provider."""
    return PROVIDERS.get(provider_id, {}).get("chat_models", [])


def get_embed_models(provider_id: str) -> list[str]:
    """Retourne la liste des modèles embed pour un provider."""
    return PROVIDERS.get(provider_id, {}).get("embed_models", [])


def get_base_url(provider_id: str) -> Optional[str]:
    """Retourne la base_url pour un provider (None = OpenAI par défaut)."""
    return PROVIDERS.get(provider_id, {}).get("base_url")


def get_extra_headers(provider_id: str) -> dict:
    """Retourne les headers supplémentaires requis par certains providers (ex: Anthropic)."""
    return PROVIDERS.get(provider_id, {}).get("extra_headers", {})


def resolve_engine_config(section_cfg: dict) -> dict:
    """
    Convertit une section de config (nouveau format) en config engine (ancien format).

    Le résultat est passé directement à AIEngine, ArchivisteWriter, etc.

    Args:
        section_cfg: {"backend": "api", "provider": "openai", "api_key": "...", "model": "..."}

    Returns:
        {"api_key": "...", "base_url": "...", "model": "...", "extra_headers": {...}}
    """
    provider = section_cfg.get("provider", "openai")
    return {
        "api_key":       section_cfg.get("api_key", ""),
        "base_url":      get_base_url(provider),
        "model":         section_cfg.get("model", ""),
        "extra_headers": get_extra_headers(provider),
    }


def is_section_configured(section_cfg: dict) -> bool:
    """True si la section a une clé API et un modèle renseignés."""
    return bool(section_cfg.get("api_key") and section_cfg.get("model"))
