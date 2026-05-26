"""
query_cleaner.py — Nettoyage sémantique des requêtes FAISS

Supprime le bruit conversationnel avant la recherche vectorielle pour
concentrer le signal sémantique et améliorer la précision des résultats.

Adapté du système clean_conversational_noise() d'OGMA/memory_manager.py.

Usage :
    from core.query_cleaner import clean_query
    cleaned = clean_query("tu te souviens quand Léo perd son chien ?")
    # → "Léo perd chien"
"""

import re
import logging

logger = logging.getLogger(__name__)

# ─── Stopwords conversationnels ───────────────────────────────────────────────
# Mots à fort bruit, faible signal sémantique dans le contexte d'un roman.

_STOPWORDS_CONVERSATIONAL = {
    # Verbes conversationnels
    "souviens", "rappelles", "rappelle", "évoque", "évoques", "évoquent",
    "penses", "pense", "pensez", "crois", "croit", "croient",
    "sais", "sait", "savez", "dis", "dit", "dites", "disent",
    # Formules interrogatives
    "qu'est-ce", "qu'est", "est-ce", "comment", "pourquoi",
    "quoi", "quel", "quelle", "quels", "quelles", "où",
    # Mots certitude/opinion
    "sûr", "sûre", "sûrs", "certain", "certaine", "certains",
    "probable", "probablement", "peut-être",
    # Verbes de dialogue (dilution)
    "parlé", "parle", "parlons", "discuté", "discute", "discutons",
    "échangé", "échange", "échangeons", "conversation", "discussion",
    # Verbes liaison faible
    "avoir", "as", "avons", "avez", "ont",
    "être", "es", "sommes", "êtes", "sont", "suis", "est",
    "faire", "fais", "fait", "faisons", "faites", "font",
    "aller", "vas", "va", "allons", "allez", "vont",
    "venir", "viens", "vient", "venons", "venez", "viennent",
    # Interjections
    "ah", "oh", "eh", "hé", "hein", "euh", "hum", "bah", "bon", "bof",
    "ouf", "tiens", "voilà", "ben",
    # Formules politesse
    "pardon", "désolé", "désolée", "excusez", "excuse", "merci",
    "stp", "svp",
    # Verbes intention/désir
    "voulais", "voudrais", "veux", "veut", "voulons", "voulez", "veulent",
    "aimerais", "aime", "aimes", "aiment", "aimez",
    "pourrais", "peux", "peut", "pouvons", "pouvez", "peuvent",
    "dire", "demander", "savoir", "vois", "voit", "voyez", "voient",
}

_STOPWORDS_STANDARD = {
    # Articles
    "le", "la", "les", "l", "un", "une", "des", "du", "de", "d",
    # Pronoms sujets
    "je", "j", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    # Pronoms objets
    "me", "m", "te", "t", "se", "s", "lui", "leur", "y", "en", "moi", "toi",
    # Prépositions courantes
    "à", "au", "aux", "dans", "sur", "sous", "par", "pour", "avec", "sans",
    "chez", "vers", "entre", "contre", "pendant", "depuis", "lors",
    # Conjonctions
    "et", "ou", "mais", "donc", "or", "ni", "car", "que", "qui", "qu",
    # Adverbes génériques
    "quand", "toujours", "jamais", "encore", "déjà", "maintenant",
    "hier", "demain", "là", "ici",
    # Mots vides fréquents
    "c'est", "c", "ce", "cela", "ça", "ceci",
    "tout", "toute", "tous", "toutes", "très", "plus", "moins",
}

# Possessifs conservés — utiles pour le contexte ("mon personnage", "ma scène")
_KEEP_POSSESSIFS = {"mon", "ma", "mes", "son", "sa", "ses"}

_ALL_STOPWORDS = _STOPWORDS_CONVERSATIONAL | _STOPWORDS_STANDARD


def clean_query(query: str) -> str:
    """
    Nettoie une requête utilisateur pour la recherche FAISS.

    Supprime le bruit conversationnel (articles, pronoms, verbes de liaison,
    formules interrogatives) pour concentrer le signal sémantique.

    Garde les possessifs (mon/ma/mes/son/sa/ses) et tous les mots > 1 char
    non listés comme stopwords.

    En cas de nettoyage trop agressif (< 2 mots conservés), repasse en mode
    doux (stopwords standard uniquement) pour éviter une requête vide.

    Exemples :
        "tu te souviens quand Léo perd son chien ?"
        → "Léo perd son chien"

        "qu'est-ce qui se passe lors de l'accident de voiture ?"
        → "passe accident voiture"

        "dis-moi ce que fait Emma dans le chapitre 3"
        → "Emma chapitre 3"

    Args:
        query: texte brut de l'utilisateur

    Returns:
        Requête nettoyée (signal concentré), ou query originale si vide.
    """
    if not query or not query.strip():
        return query

    # Normalisation bas de casse + suppression ponctuation (remplace apostrophes par espaces)
    normalized = re.sub(r"[^\w\s]", " ", query.lower())
    words = normalized.split()

    # Filtrage strict
    filtered = [
        w for w in words
        if (w not in _ALL_STOPWORDS or w in _KEEP_POSSESSIFS)
        and (len(w) > 1 or w.isdigit())
    ]

    # Fallback doux si trop peu de mots (conserve les stopwords standards mais nettoie les conversationnels)
    if len(filtered) < 2:
        filtered = [
            w for w in words
            if w not in _STOPWORDS_CONVERSATIONAL
            and (len(w) > 1 or w.isdigit())
        ]

    cleaned = " ".join(filtered).strip() if filtered else query.strip()

    if cleaned != query.strip():
        logger.debug(
            "[QUERY:CLEAN] '%s' → '%s'",
            query[:80], cleaned[:80],
        )

    return cleaned
