"""
profile_manager.py — Profil etendu de l'auteur

Separation de memoire (principe fondateur EUGENIA) :

  memory_relational/relational.db  <- portrait organique de l'auteur,
      construit progressivement par l'Archiviste (notes + entites).
      Transversal a tous les projets.

  author_profile.json              <- amorce manuelle optionnelle.
      Sert uniquement d'outil de saisie dans l'onglet Profil.
      NE PAS injecter dans le prompt systeme : c'est la relational_db
      qui fait foi.

Au demarrage, l'IA principale recoit :
  - uniquement le nom de l'auteur si la base relationnelle est vide
  - les notes + entites de la base relationnelle si elle contient des donnees
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.relational_db import RelationalDB

logger = logging.getLogger(__name__)

_ROOT        = Path(__file__).parent.parent
_AUTHORS_DIR = _ROOT / "data" / "authors"

_PROFILE_DEFAULTS: dict = {
    "bio":          "",
    "preferences":  "",
    "tone":         "",
    "topics":       "",
    "updated_at":   None,
}

# Labels lisibles pour les categories de notes
_CATEGORY_LABELS: dict[str, str] = {
    "style":       "Style d'ecriture",
    "habitudes":   "Habitudes",
    "preferences": "Preferences",
    "contexte":    "Contexte",
    "objectifs":   "Objectifs",
}

# Labels lisibles pour les types d'entites
_ENTITY_LABELS: dict[str, str] = {
    "person": "Personnes",
    "place":  "Lieux",
    "event":  "Evenements",
    "other":  "Autres",
}


# ------------------------------------------------------------------ #
#  CRUD profil (amorce manuelle — onglet Parametres > Profil)         #
# ------------------------------------------------------------------ #

def load_profile(author_slug: str) -> dict:
    path = _AUTHORS_DIR / author_slug / "author_profile.json"
    if not path.exists():
        return dict(_PROFILE_DEFAULTS)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for k, v in _PROFILE_DEFAULTS.items():
        data.setdefault(k, v)
    return data


def save_profile(author_slug: str, data: dict) -> None:
    author_dir = _AUTHORS_DIR / author_slug
    if not author_dir.exists():
        raise FileNotFoundError(f"Auteur introuvable : {author_slug}")
    payload = {
        **_PROFILE_DEFAULTS,
        **{k: data.get(k, "") for k in _PROFILE_DEFAULTS if k != "updated_at"},
        "updated_at": datetime.now().isoformat(),
    }
    path = author_dir / "author_profile.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("profile_manager — profil sauvegarde (slug=%s)", author_slug)


# ------------------------------------------------------------------ #
#  Injection dans le prompt systeme — source : relational_db          #
# ------------------------------------------------------------------ #

def build_profile_injection(
    author_name: str,
    relational_db: "RelationalDB",
) -> str:
    """
    Construit le bloc de contexte a injecter en tete du prompt systeme
    de l'IA principale, a partir de la memoire relationnelle SQLite.

    Si la base est vide → uniquement le nom (EUGENIA apprendra en discutant).
    Si la base a des donnees → portrait complet sous forme lisible.

    Format genere :
        ## Ce que je sais de l'auteur
        Nom : {author_name}
        [Style d'ecriture]
        - Prefere les phrases courtes et percutantes
        [Personnes]
        - Sophie : son editrice chez Gallimard
        ---
    """
    if relational_db.is_empty():
        return f"## Ce que je sais de l'auteur\nNom : {author_name}\n---\n\n"

    lines: list[str] = [f"Nom : {author_name}"]

    # --- Notes par categorie ---
    notes = relational_db.get_all_notes()
    by_cat: dict[str, list[str]] = {}
    for n in notes:
        by_cat.setdefault(n["category"], []).append(n["content"])

    for cat, items in by_cat.items():
        label = _CATEGORY_LABELS.get(cat, cat.capitalize())
        lines.append(f"[{label}]")
        for item in items:
            lines.append(f"- {item}")

    # --- Entites par type ---
    entities = relational_db.get_all_entities()
    by_type: dict[str, list[str]] = {}
    for e in entities:
        by_type.setdefault(e["entity_type"], []).append(
            f"{e['label']} : {e['content']}"
        )

    for etype, items in by_type.items():
        label = _ENTITY_LABELS.get(etype, etype.capitalize())
        lines.append(f"[{label}]")
        for item in items:
            lines.append(f"- {item}")

    body = "\n".join(lines)
    return f"## Ce que je sais de l'auteur\n{body}\n---\n\n"
