"""
i18n.py — Gestion de l'internationalisation (traduction statique par dictionnaire)
"""

import json
import logging
from pathlib import Path
from core.config_manager import load_config

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent
_LOCALES_DIR = _ROOT / "data" / "locales"

_CURRENT_LANG = "fr"
_TRANSLATIONS: dict[str, str] = {}

def init_i18n(lang: str = None) -> str:
    """
    Initialise le dictionnaire de traduction pour la langue demandée.
    Si lang est None, lit la langue depuis la configuration utilisateur.
    Retourne la langue effectivement chargée.
    """
    global _CURRENT_LANG, _TRANSLATIONS
    
    if not lang:
        try:
            cfg = load_config()
            lang = cfg.get("language", "fr")
        except Exception:
            lang = "fr"
            
    _CURRENT_LANG = lang
    
    file_path = _LOCALES_DIR / f"{lang}.json"
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                _TRANSLATIONS = json.load(f)
            logger.info("i18n — Langue chargée : %s (%d clés)", lang, len(_TRANSLATIONS))
        except Exception as e:
            logger.error("i18n — Impossible de charger le fichier %s: %s", file_path, e)
            _TRANSLATIONS = {}
    else:
        logger.debug("i18n — Fichier de langue non trouvé: %s (fallback vers clés d'origine)", file_path)
        _TRANSLATIONS = {}
        
    return _CURRENT_LANG

def get_current_language() -> str:
    return _CURRENT_LANG

def tr(text: str) -> str:
    """
    Traduit le texte donné en utilisant le dictionnaire actif.
    Si le dictionnaire ne contient pas la traduction ou si la langue est 'fr'
    (et non traduite), retourne le texte d'origine.
    """
    return _TRANSLATIONS.get(text, text)

# Initialisation par défaut lors de l'import
init_i18n()
