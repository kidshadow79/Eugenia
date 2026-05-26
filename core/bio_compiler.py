"""
bio_compiler.py — Compilation de la memoire relationnelle en groupes thematiques

Lit author_notes + author_entities depuis SQLite et produit :
    data/authors/{slug}/author_bio_compiled.json

Structure JSON :
{
    "compiled_at": "...",
    "groups": {
        "PREFERENCES": {
            "description": "...",
            "keywords": [...],
            "facts": [{"content": "...", "source_type": "note"|"entity", "source_id": 1}]
        },
        ...
    }
}

Appeler compile_bio() :
    - Au demarrage (apres RelationalDB init)
    - Apres chaque /mem memorise avec succes
    - Apres chaque scan de conversations
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from core.relational_db import RelationalDB

logger = logging.getLogger(__name__)

_BIO_FILE = "author_bio_compiled.json"

# Meta par categorie de note
_NOTE_META: dict[str, dict] = {
    "style": {
        "description": "Style d'ecriture, ton et preferences stylistiques de l'auteur",
        "keywords": ["style", "ecriture", "phrase", "ton", "rythme", "prose", "ecrire"],
    },
    "habitudes": {
        "description": "Habitudes de travail et rituels de l'auteur",
        "keywords": ["habitude", "routine", "travail", "session", "ecrire", "matin", "soir"],
    },
    "preferences": {
        "description": "Preferences, gouts et aversions de l'auteur",
        "keywords": ["aime", "prefere", "gout", "deteste", "evite", "refuse", "veut", "aversion"],
    },
    "contexte": {
        "description": "Contexte personnel et professionnel de l'auteur",
        "keywords": ["contexte", "vie", "situation", "projet", "roman", "travail", "auteur"],
    },
    "objectifs": {
        "description": "Objectifs et aspirations de l'auteur pour son oeuvre",
        "keywords": ["objectif", "but", "viser", "envie", "ambition", "publier", "finir"],
    },
}

# Meta par type d'entite
_ENTITY_META: dict[str, dict] = {
    "person": {
        "description": "Personnes reelles que l'auteur mentionne dans ses echanges",
        "keywords": ["personne", "ami", "famille", "editeur", "collegue", "relation", "quelqu'un"],
    },
    "place": {
        "description": "Lieux reels importants pour l'auteur",
        "keywords": ["lieu", "endroit", "ville", "maison", "bureau", "pays", "region"],
    },
    "event": {
        "description": "Evenements reels vecus ou mentionnes par l'auteur",
        "keywords": ["evenement", "moment", "date", "passe", "histoire", "souvenir", "vecu"],
    },
    "other": {
        "description": "Autres references et elements divers mentionnes par l'auteur",
        "keywords": ["autre", "reference", "divers", "objet", "outil"],
    },
}

# Correspondance category/entity_type → nom de groupe (MAJUSCULES)
_GROUP_NAMES: dict[str, str] = {
    "style":       "STYLE",
    "habitudes":   "HABITUDES",
    "preferences": "PREFERENCES",
    "contexte":    "CONTEXTE",
    "objectifs":   "OBJECTIFS",
    "person":      "PERSONNES",
    "place":       "LIEUX",
    "event":       "EVENEMENTS",
    "other":       "AUTRES",
}


def compile_bio(author_dir: Path, relational_db: RelationalDB) -> Path:
    """
    Compile la memoire relationnelle SQLite en groupes thematiques JSON.

    Args:
        author_dir:    dossier de l'auteur (data/authors/{slug}/)
        relational_db: instance RelationalDB ouverte

    Returns:
        chemin du fichier JSON produit
    """
    groups: dict[str, dict] = {}

    # ── Notes → groupes par categorie ─────────────────────────────────────────
    for note in relational_db.get_all_notes():
        cat   = note["category"]
        gname = _GROUP_NAMES.get(cat, cat.upper())
        meta  = _NOTE_META.get(cat, {"description": cat.capitalize(), "keywords": [cat]})

        if gname not in groups:
            groups[gname] = {
                "description": meta["description"],
                "keywords":    list(meta["keywords"]),
                "facts":       [],
            }
        groups[gname]["facts"].append({
            "content":     note["content"],
            "source_type": "note",
            "source_id":   note["id"],
        })

    # ── Entites → groupes par type ─────────────────────────────────────────────
    for ent in relational_db.get_all_entities():
        etype = ent["entity_type"]
        gname = _GROUP_NAMES.get(etype, etype.upper())
        meta  = _ENTITY_META.get(etype, {"description": etype.capitalize(), "keywords": [etype]})

        if gname not in groups:
            groups[gname] = {
                "description": meta["description"],
                "keywords":    list(meta["keywords"]),
                "facts":       [],
            }
            
        # Ajout dynamique du nom de l'entite comme mot-cle
        label_kw = ent["label"].lower().strip()
        if label_kw and label_kw not in groups[gname]["keywords"]:
            groups[gname]["keywords"].append(label_kw)
            
        groups[gname]["facts"].append({
            "content":     f"{ent['label']} : {ent['content']}",
            "source_type": "entity",
            "source_id":   ent["id"],
        })

    payload = {
        "compiled_at": datetime.now().isoformat(),
        "groups":      groups,
    }

    out_path = author_dir / _BIO_FILE
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    total_facts = sum(len(g["facts"]) for g in groups.values())
    logger.info(
        "bio_compiler — %d groupe(s), %d fait(s) compile(s) -> %s",
        len(groups), total_facts, out_path.name,
    )
    return out_path
