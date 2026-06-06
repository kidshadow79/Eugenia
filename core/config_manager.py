"""
ConfigManager — Lecture et sauvegarde de la configuration globale EUGENIA

Deux fichiers distincts dans data/config/ :

    app_config.json  ← GITIGNORE  — clés API, provider, modèle
    prompts.json     ← VERSIONNÉ  — prompts système (personnalisables)

Séparation intentionnelle :
    - app_config.json ne doit jamais être commité (données sensibles).
    - prompts.json est commitable. Les utilisateurs partagent leurs
      personnalisations. Les valeurs par défaut voyagent avec le repo.

Réinitialisation des prompts : bouton "Réinitialiser" dans l'UI → restaure
les valeurs de _PROMPT_DEFAULTS (intégrées dans ce fichier).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT       = Path(__file__).parent.parent
_CONFIG_DIR = _ROOT / "data" / "config"

_CONFIG_FILE  = _CONFIG_DIR / "app_config.json"   # gitignored
_PROMPTS_FILE = _CONFIG_DIR / "prompts.json"       # versionné


# ─── Valeurs par défaut — config IA ──────────────────────────────────────────

_SECTION_DEFAULTS = {
    "backend":  "api",
    "provider": "openai",
    "api_key":  "",
    "model":    "",
}

_CONFIG_DEFAULTS: dict = {
    "ia_principale": {**_SECTION_DEFAULTS, "model": "gpt-4o-mini"},
    "ia_archiviste": {**_SECTION_DEFAULTS, "model": "gpt-4o-mini"},
    "ia_embed":      {**_SECTION_DEFAULTS, "model": "text-embedding-3-small"},
    "web_search": {
        "provider":    "duckduckgo",
        "api_key":     "",
        "max_results": 5,
    },
    "theme":         "dark",
    "language":      "fr",
    "font_size":     13,
    "font_family":   "Segoe UI",
    "chat_lh":       1.6,
    "color_overrides": {"dark": {}, "light": {}},
    "memory": {
        "faiss_dedup_enabled":   True,
        "faiss_dedup_threshold": 0.93,
    },
}


# ─── Valeurs par défaut — prompts ────────────────────────────────────────────
# Source de vérité pour le bouton "Réinitialiser".
# Ces valeurs sont aussi écrites dans prompts.json à la première utilisation.

_PROMPT_DEFAULTS: dict[str, str] = {
    "ia_principale": (
        "Tu es EUGENIA, une IA compagnon pour les auteurs.\n"
        "Ton role est d'accompagner, d'encourager et de brainstormer avec l'auteur, mais jamais d'ecrire son texte a sa place.\n"
        "Tu connais l'auteur et son projet. Si l'auteur te pose une question directe sur ton avis, tes pensées ou ton fonctionnement, reponds-y franchement.\n"
        "Quand on te montre un extrait, donne ton avis constructif, identifie des pistes de travail, ou pose des questions ouvertes.\n"
        "Tu parles avec chaleur, sans condescendance. Tu memorises ce qu'on te dit d'une session a l'autre.\n"
        "Pour mémoriser expressément une information cruciale sur l'auteur ou le projet, utilise la balise: [MEMORISER] information à retenir"
    ),
    "archiviste_writer": (
        "Tu es l'Archiviste, le subconscient analytique d'un assistant d'écriture.\n\n"
        "Ta mission : analyser un extrait de roman et en extraire les éléments narratifs structurés.\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après.\n\n"
        'Format attendu :\n'
        '{\n'
        '  "resume": "2-3 phrases factuelles résumant les événements clés de ce passage",\n'
        '  "characters": [{"label": "Nom du personnage", "content": "Description, rôle"}],\n'
        '  "places":     [{"label": "Nom du lieu",       "content": "Description, ambiance"}],\n'
        '  "events":     [{"label": "Titre court",       "content": "Ce qui se passe"}],\n'
        '  "decisions":  [{"label": "Décision courte",   "content": "Implication narrative"}],\n'
        '  "contradictions": [{"label": "Contradiction", "content": "Ce qui est incohérent"}]\n'
        '}\n\n'
        "Règles :\n"
        "- N'invente rien. Extrais uniquement ce qui est présent dans le texte.\n"
        "- Les listes peuvent être vides si rien de pertinent n'est trouvé.\n"
        '- "resume" : 2-3 phrases courtes, factuelles, sans style littéraire. '
        'Couvre les faits principaux du passage (qui, quoi, où, enjeu).\n'
        '- "decisions" = choix stylistiques ou narratifs explicites de l\'auteur.\n'
        '- "contradictions" = seulement si tu as un contexte Bible à comparer.\n'
        "- Labels courts, contenus détaillés."
    ),
    "archiviste_reader": (
        "Tu es l'Archiviste, le subconscient d'un assistant d'écriture pour auteurs.\n\n"
        "Ta mission : à partir d'une Bible de projet et d'une question de l'auteur,\n"
        "rédiger une note de contexte COURTE et UTILE pour l'IA principale.\n\n"
        "Règles :\n"
        "- Maximum 150 mots.\n"
        "- Ne répète pas toute la Bible — sélectionne ce qui est PERTINENT pour cette question.\n"
        "- Si rien dans la Bible ne concerne la question → réponds uniquement : RIEN\n"
        '- Formule à la troisième personne, style factuel ("Elara est une elfe de 300 ans...")\n'
        "- Mentionne les contradictions si elles concernent le sujet de la question."
    ),
    "archiviste_relational": (
        "Tu es l'Archiviste, le subconscient d'un assistant d'écriture.\n\n"
        "Ta mission : analyser une conversation entre un auteur et son IA pour en extraire\n"
        "des informations sur l'AUTEUR (pas sur le roman qu'il écrit).\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après.\n\n"
        'Format attendu :\n'
        '{\n'
        '  "notes": [\n'
        '    {"category": "style",     "content": "Préfère les phrases courtes"},\n'
        '    {"category": "habitudes", "content": "Écrit le matin"}\n'
        '  ],\n'
        '  "entities": [\n'
        '    {"type": "person", "label": "Sophie", "content": "Son éditrice chez Gallimard"}\n'
        '  ]\n'
        '}\n\n'
        'Catégories de notes : "style", "habitudes", "contexte", "preferences", "objectifs"\n'
        'Types d\'entités : "person", "place", "event", "other"\n\n'
        "Règles :\n"
        "- N'extrais QUE ce que l'auteur dit sur LUI-MÊME.\n"
        "- Ignore tout ce qui concerne le roman ou les personnages fictifs.\n"
        "- Les deux listes peuvent être vides si rien de pertinent.\n"
        "- Formule de façon concise et factuelle."
    ),
    "session_summarizer": (
        "Tu es l'assistant de mémoire d'EUGENIA.\n\n"
        "Ta mission : résumer la conversation ci-dessous en UN SEUL BLOC riche et détaillé (200-400 mots).\n\n"
        "Inclure impérativement :\n"
        "- Les sujets principaux abordés (scénario, personnages, mais aussi discussions hors-texte).\n"
        "- Les décisions ou constats importants de l'auteur.\n"
        "- Les informations personnelles, familiales ou intimes partagées par l'auteur (ex: histoires de famille, anecdotes réelles).\n"
        "- Les questions ouvertes laissées sans réponse.\n\n"
        "Règles :\n"
        "- Style neutre et factuel, à la troisième personne.\n"
        "- Pas de bullet points, un seul paragraphe fluide mais exhaustif.\n"
        "- Commence par : 'Session du [date].'\n"
        "- Si la conversation est vide ou hors-sujet : réponds uniquement 'RIEN'"
    ),
    "style_profiler": (
        "Tu es un analyste littéraire spécialisé dans le style d'écriture.\n\n"
        "Ta mission : analyser l'échantillon de texte fourni et rédiger un profil de style\n"
        "en 150-250 mots pour guider un assistant IA.\n\n"
        "Analyser :\n"
        "- Longueur et rythme des phrases (courtes/longues, variées, staccato...)\n"
        "- Registre de langue (soutenu, courant, familier)\n"
        "- Usage de la ponctuation (tirets, points de suspension, virgules abondantes...)\n"
        "- Temps verbaux dominants (passé simple, imparfait, présent...)\n"
        "- Figures de style récurrentes (métaphores, anaphores, ellipses...)\n"
        "- Ton général (épique, intimiste, humoristique, sombre...)\n\n"
        "Format de réponse : un seul paragraphe fluide commencant par 'Style de l'auteur :'\n"
        "Pas de bullet points. Style factuel et précis."
    ),
}


# ─── Config IA (app_config.json) ─────────────────────────────────────────────

def load_config() -> dict:
    """
    Charge la config IA (app_config.json).
    Si absent ou ancien format → retourne les defaults.
    Ne contient PAS les prompts.
    """
    if not _CONFIG_FILE.exists():
        logger.debug("load_config — fichier absent, defaults utilisés")
        return _copy_config_defaults()

    with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Migration ancien format flat
    if "ia_principale" not in raw and "api_key" in raw:
        logger.info("load_config — migration depuis l'ancien format")
        migrated = _copy_config_defaults()
        for section in ("ia_principale", "ia_archiviste"):
            migrated[section]["api_key"] = raw.get("api_key", "")
            migrated[section]["model"]   = raw.get("model", "gpt-4o-mini")
        return migrated

    result = _copy_config_defaults()
    for section in ("ia_principale", "ia_archiviste", "ia_embed"):
        if section in raw and isinstance(raw[section], dict):
            # Exclure la clé "prompts" si elle s'y était glissée
            clean = {k: v for k, v in raw[section].items() if k != "prompts"}
            result[section].update(clean)
    # Theme (cle plate, pas un sous-dict)
    if "theme" in raw and isinstance(raw["theme"], str):
        result["theme"] = raw["theme"]
    # Langue (cle plate)
    if "language" in raw and isinstance(raw["language"], str):
        result["language"] = raw["language"]
    # Taille police (cle plate)
    if "font_size" in raw:
        try:
            fs = int(raw["font_size"])
            if 12 <= fs <= 16:
                result["font_size"] = fs
        except (ValueError, TypeError):
            pass
    # Famille police (cle plate)
    if "font_family" in raw and isinstance(raw["font_family"], str):
        result["font_family"] = raw["font_family"]
    # Interligne chat (cle plate)
    if "chat_lh" in raw:
        try:
            lh = float(raw["chat_lh"])
            if 1.0 <= lh <= 2.2:
                result["chat_lh"] = lh
        except (ValueError, TypeError):
            pass
    # Surcharges couleurs
    if "color_overrides" in raw and isinstance(raw["color_overrides"], dict):
        result["color_overrides"] = {
            "dark": dict(raw["color_overrides"].get("dark", {})),
            "light": dict(raw["color_overrides"].get("light", {})),
        }
    # Section memory (optionnelle, avec defaults si absente)
    if "memory" in raw and isinstance(raw["memory"], dict):
        result["memory"].update(raw["memory"])
    # Section web_search
    if "web_search" in raw and isinstance(raw["web_search"], dict):
        result["web_search"].update(raw["web_search"])
    # Clés plates de préférences UI (badge, scroll, OCR...)
    # Ces clés ne sont pas dans _CONFIG_DEFAULTS mais sont écrites par save_config.
    _UI_INT_KEYS = {
        "badge_opacity": 85,
        "scroll_speed":  5,
        "badge_margin_r": 30,
        "badge_x_offset": 0,
        "ego_heartbeat_minutes": 3,
    }
    for key, default in _UI_INT_KEYS.items():
        if key in raw:
            try:
                result[key] = int(raw[key])
            except (ValueError, TypeError):
                result[key] = default
    if "ocr_engine" in raw and isinstance(raw["ocr_engine"], str):
        result["ocr_engine"] = raw["ocr_engine"]
    logger.debug("load_config — OK (providers: %s / %s / %s)",
                 result["ia_principale"].get("provider"),
                 result["ia_archiviste"].get("provider"),
                 result["ia_embed"].get("provider"))
    return result


def save_config(config: dict) -> None:
    """
    Sauvegarde la config IA (app_config.json).
    Si config contient une clé "prompts", elle est ignorée (fichier séparé).
    """
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    safe = {k: v for k, v in config.items() if k != "prompts"}
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)
    logger.info("save_config — app_config.json sauvegardé")


def _copy_config_defaults() -> dict:
    return {k: dict(v) if isinstance(v, dict) else v for k, v in _CONFIG_DEFAULTS.items()}


# ─── Prompts (prompts.json) ───────────────────────────────────────────────────

def load_prompts() -> dict[str, str]:
    """
    Charge les prompts depuis prompts.json.
    Les cles presentes dans _PROMPT_DEFAULTS mais absentes du fichier
    (ajouts posterieurs) sont injectees depuis les defaults et persistees
    automatiquement — migration transparente sans perte de personnalisation.
    """
    if not _PROMPTS_FILE.exists():
        # Premier lancement : creer le fichier avec tous les defaults
        save_prompts(dict(_PROMPT_DEFAULTS))
        return dict(_PROMPT_DEFAULTS)

    with open(_PROMPTS_FILE, "r", encoding="utf-8") as f:
        raw: dict = json.load(f)

    # Detecter les nouvelles cles absentes du fichier
    missing = {k: v for k, v in _PROMPT_DEFAULTS.items() if k not in raw}
    if missing:
        raw.update(missing)
        _write_prompts_file(raw)
        logger.info(
            "load_prompts — %d nouvelle(s) cle(s) migree(s) vers prompts.json : %s",
            len(missing), list(missing.keys()),
        )

    logger.debug("load_prompts — OK (%d prompts)", len(raw))
    return raw


def save_prompts(prompts: dict[str, str]) -> None:
    """Sauvegarde les prompts dans prompts.json (versionnable)."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _write_prompts_file(prompts)
    logger.info("save_prompts — prompts.json sauvegardé (%d prompts)", len(prompts))


def reset_prompt(key: str) -> str:
    """
    Réinitialise un prompt à sa valeur par défaut.
    Met à jour prompts.json et retourne la valeur par défaut.
    """
    prompts = load_prompts()
    default = _PROMPT_DEFAULTS.get(key, "")
    prompts[key] = default
    save_prompts(prompts)
    return default


# ─── Sauvegardes de configuration ────────────────────────────────────────────

def save_settings_backup(
    path: str,
    api_data: dict | None,
    prompts_data: dict | None,
) -> None:
    """
    Exporte un backup de configuration dans un fichier JSON.

    Args:
        path:         chemin absolu du fichier de sortie (.json)
        api_data:     sections IA extraites de app_config (None = non inclus)
        prompts_data: dict des prompts système (None = non inclus)
    """
    from datetime import datetime

    content: list[str] = []
    payload: dict = {
        "_type":    "eugenia_settings_backup",
        "_version": "1.0",
        "_date":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if api_data is not None:
        payload["api"] = api_data
        content.append("api")
    if prompts_data is not None:
        payload["instructions"] = prompts_data
        content.append("instructions")
    payload["_content"] = content

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    logger.info("save_settings_backup — OK : %s (%s)", path, content)


def load_settings_backup(path: str) -> dict:
    """
    Charge un fichier de backup EUGENIA.

    Returns:
        dict contenant zéro ou plusieurs des clés : "api", "instructions"

    Raises:
        ValueError  si le fichier n'est pas un backup EUGENIA valide
        json.JSONDecodeError / OSError  si lecture impossible
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("_type") != "eugenia_settings_backup":
        raise ValueError(
            "Ce fichier n'est pas un backup EUGENIA valide "
            f"(type trouvé : {data.get('_type')!r})."
        )
    logger.info(
        "load_settings_backup — OK : %s (contenu : %s)",
        path, data.get("_content", []),
    )
    return data


def load_prompt(key: str) -> str:
    """
    Retourne le prompt pour la cle donnee.
    Leve KeyError uniquement si la cle n'existe pas dans _PROMPT_DEFAULTS
    (cle vraiment inconnue, pas juste absente du fichier).
    """
    if key not in _PROMPT_DEFAULTS:
        raise KeyError(f"load_prompt : cle inconnue '{key}' — non definie dans _PROMPT_DEFAULTS")
    prompts = load_prompts()
    return prompts[key]


def _write_prompts_file(prompts: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)


# ─── Compat descendante ───────────────────────────────────────────────────────

def load_ai_config() -> dict:
    """Compatibilité — préférer load_config() pour le nouveau code."""
    from core.providers import resolve_engine_config
    cfg = load_config()
    return resolve_engine_config(cfg["ia_principale"])

