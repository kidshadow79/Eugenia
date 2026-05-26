"""
SessionManager — Gestion des auteurs et projets sur disque

Structure de données sur disque :
    data/
    ├── authors/
    │   └── {slug}/
    │       ├── author.json          ← métadonnées auteur
    │       └── memory_relational/   ← mémoire de l'auteur (étape 6)
    └── projects/
        └── {slug}/
            ├── project.json         ← métadonnées projet (avec author_uuid)
            ├── memory_work/         ← mémoire du projet (étape 6)
            └── snapshots/           ← sauvegardes horodatées

Conventions :
- Slug : "Mon Roman SF" → "mon-roman-sf"  (lowercase, tirets, ASCII)
- UUID : généré à la création, stable même si l'utilisateur renomme
"""

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

# Chemins absolus basés sur la position de ce fichier
_ROOT = Path(__file__).parent.parent          # c:\APP\EUGENIA
DATA_DIR = _ROOT / "data"
AUTHORS_DIR = DATA_DIR / "authors"
PROJECTS_DIR = DATA_DIR / "projects"


def _slugify(name: str) -> str:
    """
    Convertit un nom libre en slug utilisable comme nom de dossier.
    "Mon Roman SF" → "mon-roman-sf"
    Remplace accents et caractères spéciaux par leur équivalent ASCII basique.
    """
    # Normalisation basique des accents les plus courants (fr)
    replacements = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'î': 'i', 'ï': 'i',
        'ô': 'o', 'ö': 'o',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c', 'ñ': 'n',
    }
    name = name.lower().strip()
    for src, dst in replacements.items():
        name = name.replace(src, dst)
    name = re.sub(r'[^\w\s-]', '', name)      # retire tout sauf alphanum, espace, tiret
    name = re.sub(r'[\s_]+', '-', name)        # espace/underscore → tiret
    name = re.sub(r'-+', '-', name)            # tirets multiples → un seul
    name = name.strip('-')
    return name or "sans-nom"


# ------------------------------------------------------------------ #
#  Auteurs                                                             #
# ------------------------------------------------------------------ #

def list_authors() -> list[dict]:
    """Retourne la liste de tous les auteurs enregistrés, triée par nom."""
    authors = []
    if not AUTHORS_DIR.exists():
        return []
    for author_dir in AUTHORS_DIR.iterdir():
        if not author_dir.is_dir():
            continue
        json_path = author_dir / "author.json"
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                authors.append(json.load(f))
    return sorted(authors, key=lambda a: a['name'].lower())


def create_author(name: str) -> dict:
    """
    Crée un nouvel auteur sur disque et retourne son dict.
    Lève ValueError si un auteur avec ce slug existe déjà.
    """
    slug = _slugify(name)
    author_dir = AUTHORS_DIR / slug
    if author_dir.exists():
        raise ValueError(f"Un auteur avec le nom « {name} » existe déjà.")

    author_dir.mkdir(parents=True)
    (author_dir / "memory_relational").mkdir()

    author = {
        "uuid": str(uuid.uuid4()),
        "name": name,
        "slug": slug,
        "created_at": datetime.now().isoformat(),
    }
    with open(author_dir / "author.json", 'w', encoding='utf-8') as f:
        json.dump(author, f, ensure_ascii=False, indent=2)
    return author


# ------------------------------------------------------------------ #
#  Projets                                                             #
# ------------------------------------------------------------------ #

def list_projects(author_uuid: str) -> list[dict]:
    """Retourne les projets appartenant à un auteur donné, triés par nom."""
    projects = []
    if not PROJECTS_DIR.exists():
        return []
    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        json_path = proj_dir / "project.json"
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                p = json.load(f)
            if p.get('author_uuid') == author_uuid:
                projects.append(p)
    return sorted(projects, key=lambda p: p['name'].lower())


def create_project(name: str, author_uuid: str,
                   categories: list[str] | None = None) -> dict:
    """
    Crée un nouveau projet sur disque et retourne son dict.
    Lève ValueError si un projet avec ce slug existe déjà.

    categories : liste des clés de catégories Bible choisies par l'utilisateur.
                 Si None, utilise DEFAULT_CATEGORIES (rétrocompatiblité).
    """
    from core.project_types import DEFAULT_CATEGORIES  # import local — évite le cycle
    slug = _slugify(name)
    proj_dir = PROJECTS_DIR / slug
    if proj_dir.exists():
        raise ValueError(f"Un projet avec le nom « {name} » existe déjà.")

    proj_dir.mkdir(parents=True)
    (proj_dir / "memory_work").mkdir()
    (proj_dir / "snapshots").mkdir()

    project = {
        "uuid": str(uuid.uuid4()),
        "name": name,
        "slug": slug,
        "author_uuid": author_uuid,
        "created_at": datetime.now().isoformat(),
        "last_sync": None,           # utilisé par l'Ingest (étape 7)
        "categories": categories if categories is not None else DEFAULT_CATEGORIES,
    }
    with open(proj_dir / "project.json", 'w', encoding='utf-8') as f:
        json.dump(project, f, ensure_ascii=False, indent=2)
    return project


def get_project_categories(slug: str) -> list[str]:
    """
    Retourne les catégories Bible d'un projet.
    Fallback sur DEFAULT_CATEGORIES si absent (projets anciens).
    """
    from core.project_types import DEFAULT_CATEGORIES
    proj_dir = PROJECTS_DIR / slug
    json_path = proj_dir / "project.json"
    if not json_path.exists():
        return list(DEFAULT_CATEGORIES)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("categories") or list(DEFAULT_CATEGORIES)


def delete_project(slug: str) -> None:
    """
    Supprime définitivement un projet et toutes ses données (Bible, chunks, snapshots).
    Lève FileNotFoundError si le projet n'existe pas.
    """
    proj_dir = PROJECTS_DIR / slug
    if not proj_dir.exists():
        raise FileNotFoundError(f"Projet introuvable : {slug}")

    import gc
    gc.collect()
    shutil.rmtree(proj_dir)


def delete_author(slug: str) -> None:
    """
    Supprime définitivement un auteur, sa mémoire relationnelle,
    et TOUS ses projets (Bible, chunks, snapshots inclus).
    Lève FileNotFoundError si l'auteur n'existe pas.
    """
    author_dir = AUTHORS_DIR / slug
    if not author_dir.exists():
        raise FileNotFoundError(f"Auteur introuvable : {slug}")

    # Lire l'uuid avant suppression pour retrouver les projets
    author_json = author_dir / "author.json"
    with open(author_json, "r", encoding="utf-8") as f:
        author = json.load(f)
    author_uuid = author["uuid"]

    # Supprimer tous les projets de cet auteur
    if PROJECTS_DIR.exists():
        for proj_dir in PROJECTS_DIR.iterdir():
            if not proj_dir.is_dir():
                continue
            pjson = proj_dir / "project.json"
            if pjson.exists():
                with open(pjson, "r", encoding="utf-8") as f:
                    p = json.load(f)
                if p.get("author_uuid") == author_uuid:
                    shutil.rmtree(proj_dir)

    import gc
    gc.collect()
    # Supprimer le dossier auteur
    shutil.rmtree(author_dir)
