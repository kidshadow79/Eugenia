"""
project_types.py — Catalogue des catégories de Bible disponibles

Chaque catégorie est un dict :
    key             : identifiant technique (= nom de table SQLite)
    label           : nom affiché dans l'UI
    emoji           : icône
    tab_label       : libellé court pour l'onglet BiblePanel
    col_headers     : en-têtes des colonnes du tableau (label, contenu)
    empty_hint      : message si la catégorie est vide
    prompt_fragment : ligne JSON à injecter dans le prompt de l'Archiviste Writer

L'utilisateur choisit MAX_CATEGORIES catégories à la création d'un projet.
Les projets existants sans champ "categories" utilisent DEFAULT_CATEGORIES.
"""

MAX_CATEGORIES = 5
MIN_CATEGORIES = 2

# Catégories par défaut — rétrocompatibilité avec les projets existants
DEFAULT_CATEGORIES = ["characters", "places", "events", "decisions", "contradictions"]

# ─── Catalogue complet ────────────────────────────────────────────────────────

CATEGORY_CATALOG: list[dict] = [
    {
        "key":         "characters",
        "label":       "Personnages",
        "emoji":       "👤",
        "tab_label":   "Perso.",
        "col_headers": ["Nom", "Description"],
        "empty_hint":  "Aucun personnage dans la Bible.",
        "prompt_fragment": (
            '  "characters": [{"label": "Nom du personnage", '
            '"content": "Description physique, psychologique, rôle"}],'
        ),
    },
    {
        "key":         "places",
        "label":       "Lieux",
        "emoji":       "🗺",
        "tab_label":   "Lieux",
        "col_headers": ["Lieu", "Description"],
        "empty_hint":  "Aucun lieu dans la Bible.",
        "prompt_fragment": (
            '  "places": [{"label": "Nom du lieu", '
            '"content": "Description, ambiance, localisation"}],'
        ),
    },
    {
        "key":         "events",
        "label":       "Évènements",
        "emoji":       "📅",
        "tab_label":   "Chrono.",
        "col_headers": ["Évènement", "Description"],
        "empty_hint":  "Aucun évènement dans la Bible.",
        "prompt_fragment": (
            '  "events": [{"label": "Titre court de l\'évènement", '
            '"content": "Ce qui se passe, enjeu narratif"}],'
        ),
    },
    {
        "key":         "decisions",
        "label":       "Décisions",
        "emoji":       "✏️",
        "tab_label":   "Déc.",
        "col_headers": ["Décision", "Détail"],
        "empty_hint":  "Aucune décision dans la Bible.",
        "prompt_fragment": (
            '  "decisions": [{"label": "Décision courte", '
            '"content": "Implication narrative ou éditoriale"}],'
        ),
    },
    {
        "key":         "contradictions",
        "label":       "Contradictions",
        "emoji":       "⚠️",
        "tab_label":   "Contra.",
        "col_headers": ["Contradiction", "Détail"],
        "empty_hint":  "Aucune contradiction détectée.",
        "prompt_fragment": (
            '  "contradictions": [{"label": "Intitulé court", '
            '"content": "Ce qui est incohérent par rapport à la Bible existante"}],'
        ),
    },
    {
        "key":         "themes",
        "label":       "Thèmes",
        "emoji":       "🎭",
        "tab_label":   "Thèmes",
        "col_headers": ["Thème", "Développement"],
        "empty_hint":  "Aucun thème dans la Bible.",
        "prompt_fragment": (
            '  "themes": [{"label": "Nom du thème", '
            '"content": "Comment il se manifeste dans ce passage"}],'
        ),
    },
    {
        "key":         "objects",
        "label":       "Objets / Artefacts",
        "emoji":       "🔮",
        "tab_label":   "Objets",
        "col_headers": ["Objet", "Description"],
        "empty_hint":  "Aucun objet / artefact dans la Bible.",
        "prompt_fragment": (
            '  "objects": [{"label": "Nom de l\'objet", '
            '"content": "Description, importance narrative"}],'
        ),
    },
    {
        "key":         "concepts",
        "label":       "Concepts / Notions",
        "emoji":       "💡",
        "tab_label":   "Concepts",
        "col_headers": ["Concept", "Définition"],
        "empty_hint":  "Aucun concept dans la Bible.",
        "prompt_fragment": (
            '  "concepts": [{"label": "Nom du concept", '
            '"content": "Définition, contexte d\'utilisation dans le texte"}],'
        ),
    },
    {
        "key":         "sources",
        "label":       "Sources / Références",
        "emoji":       "📚",
        "tab_label":   "Sources",
        "col_headers": ["Référence", "Détail"],
        "empty_hint":  "Aucune source dans la Bible.",
        "prompt_fragment": (
            '  "sources": [{"label": "Auteur, titre ou URL", '
            '"content": "Argument, page, contexte de la citation"}],'
        ),
    },
    {
        "key":         "authors_cited",
        "label":       "Auteurs cités",
        "emoji":       "✍️",
        "tab_label":   "Auteurs",
        "col_headers": ["Auteur", "Contribution"],
        "empty_hint":  "Aucun auteur cité dans la Bible.",
        "prompt_fragment": (
            '  "authors_cited": [{"label": "Nom de l\'auteur", '
            '"content": "Discipline, thèse principale citée"}],'
        ),
    },
    {
        "key":         "hypotheses",
        "label":       "Hypothèses",
        "emoji":       "🔬",
        "tab_label":   "Hypoth.",
        "col_headers": ["Hypothèse", "Détail"],
        "empty_hint":  "Aucune hypothèse dans la Bible.",
        "prompt_fragment": (
            '  "hypotheses": [{"label": "Intitulé de l\'hypothèse", '
            '"content": "Formulation, statut (validée, réfutée, ouverte)"}],'
        ),
    },
    {
        "key":         "components",
        "label":       "Composants / Modules",
        "emoji":       "⚙️",
        "tab_label":   "Comp.",
        "col_headers": ["Composant", "Description"],
        "empty_hint":  "Aucun composant dans la Bible.",
        "prompt_fragment": (
            '  "components": [{"label": "Nom du composant", '
            '"content": "Rôle, dépendances, état"}],'
        ),
    },
    {
        "key":         "risks",
        "label":       "Risques",
        "emoji":       "🚨",
        "tab_label":   "Risques",
        "col_headers": ["Risque", "Description"],
        "empty_hint":  "Aucun risque dans la Bible.",
        "prompt_fragment": (
            '  "risks": [{"label": "Intitulé du risque", '
            '"content": "Impact potentiel, mesures envisagées"}],'
        ),
    },
]

# Index par key pour accès rapide
_CATALOG_INDEX: dict[str, dict] = {c["key"]: c for c in CATEGORY_CATALOG}


# ─── API ─────────────────────────────────────────────────────────────────────

def get_category(key: str) -> dict | None:
    """Retourne la définition d'une catégorie par sa clé, ou None."""
    return _CATALOG_INDEX.get(key)


def get_categories(keys: list[str]) -> list[dict]:
    """Retourne les définitions dans l'ordre donné, ignore les clés inconnues."""
    return [_CATALOG_INDEX[k] for k in keys if k in _CATALOG_INDEX]


def build_writer_prompt(categories: list[str]) -> str:
    """
    Construit le prompt système de l'Archiviste Writer en fonction
    des catégories sélectionnées pour ce projet.

    Le champ "resume" est TOUJOURS inclus (synthèse factuelle du passage).
    Les catégories inconnues sont ignorées silencieusement.
    """
    cats = get_categories(categories)
    if not cats:
        cats = get_categories(DEFAULT_CATEGORIES)

    fragments = "\n".join(c["prompt_fragment"] for c in cats)
    keys_list = ", ".join(f'"{c["key"]}"' for c in cats)

    has_contradictions = "contradictions" in categories
    contradiction_rule = (
        '\n- "contradictions" : UNIQUEMENT si le texte contredit DIRECTEMENT et FACTUELLEMENT '
        'une entrée de la Bible fournie ci-dessus (même fait, valeurs différentes). '
        'Toute inférence, interprétation ou paradoxe théorique est INTERDIT ici.'
        if has_contradictions else ""
    )

    return (
        "Tu es l'Archiviste, un extracteur de faits strict et minimaliste.\n\n"
        "Ta mission : lire un extrait de texte et en extraire UNIQUEMENT les faits "
        "explicitement écrits dedans.\n\n"
        "Règle absolue : tu n'infères RIEN. Tu n'interprètes RIEN. Tu n'imagines RIEN.\n"
        "Si une information n'est pas textuellement présente dans l'extrait, "
        "tu laisses la liste vide.\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après.\n\n"
        "Format attendu :\n"
        "{\n"
        '  "resume": "2-3 phrases factuelles résumant UNIQUEMENT ce qui est écrit dans le texte",\n'
        f"{fragments}\n"
        "}\n\n"
        "Règles strictes :\n"
        "- INTERDIT : inférer, supposer, interpréter, compléter, illustrer ou paraphraser.\n"
        "- INTERDIT : inclure un fait qui n'est pas explicitement écrit dans l'extrait.\n"
        "- Si une liste est vide : c'est CORRECT. Un extrait peut ne rien contenir d'extractible.\n"
        f"- Les listes {keys_list} doivent être vides si rien de concret n'est mentionné.\n"
        '- "resume" : 2-3 phrases courtes, 100% fidèles au texte. Aucun ajout.\n'
        f"- Labels courts et exacts, contenus cités quasi textuellement.{contradiction_rule}"
    )
