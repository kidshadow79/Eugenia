"""
ghost_matcher.py — Matching entre ancres d'annotations et blocs OCR

Logique :
  - Pour chaque annotation, on cherche son ancre dans le corpus OCR scanné.
  - L'ancre est une suite de 6-8 mots extraite du texte original.
  - Les blocs OCR peuvent fragmenter cette suite sur plusieurs lignes.
  - On teste des fenêtres glissantes de 1, 2 ou 3 blocs consécutifs (triés par y)
    avec rapidfuzz.fuzz.partial_ratio.
  - Seuil de confiance : 85 — en dessous, l'ancre n'est pas considérée trouvée.

Usage :
    results = match_annotations(annotations, blocks)
    for r in results:
        overlay.place_badge(r.annotation_id, r.label, r.note, r.center_y)
"""

import re
import unicodedata
import logging
from dataclasses import dataclass

from rapidfuzz import fuzz

from core.ghost_scanner import ScanBlock
from core.annotation_store import Annotation

logger = logging.getLogger(__name__)

# ─── Paramètres ───────────────────────────────────────────────────────────────

_MATCH_THRESHOLD  = 85    # seuil relevé : partial_ratio(fingerprint, fenêtre)
                          # doit être élevé car on s'assure que la fenêtre est
                          # toujours plus longue que le fingerprint
_WINDOW_SIZES     = (3, 4, 5, 6)  # fenêtres larges → window_text > fingerprint
_FINGERPRINT_WORDS = 8    # mots distinctifs du début de l'ancre


# ─── Résultat ─────────────────────────────────────────────────────────────────

@dataclass
class MatchResult:
    """Résultat d'un matching ancre → bloc OCR."""
    annotation_id: int
    label:         str
    note:          str
    center_y:      int   # coordonnée y (relative au calque) pour placer le badge
    score:         int   # score de confiance rapidfuzz (0-100)


# ─── Extraction de la phrase-clé ──────────────────────────────────────────────

def _extract_fingerprint(anchor: str, max_words: int = _FINGERPRINT_WORDS) -> str:
    """
    Extrait une phrase-clé courte depuis le début de l'ancre.

    Pourquoi : l'ancre est souvent le texte entier copié (long paragraphe).
    Avec partial_ratio(ancre_longue, bloc_court_OCR), TOUT le texte de la page
    obtient un score élevé car chaque mot de la page est dans l'ancre quelque
    part. On extrait donc seulement les N premiers mots de la première ligne
    non vide — c'est le passage le plus distinctif et le début du passage visé.
    """
    for line in anchor.splitlines():
        line = line.strip()
        if line:
            words = line.split()
            return " ".join(words[:max_words])
    # Fallback : premiers mots du texte complet
    return " ".join(anchor.split()[:max_words])


# ─── Normalisation ────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """
    Normalise un texte pour la comparaison :
    - décompose les accents (NFD) puis les supprime
    - met en minuscules
    - réduit les espaces multiples
    """
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ─── Matching ─────────────────────────────────────────────────────────────────

def match_annotations(
    annotations: list[Annotation],
    blocks: list[ScanBlock],
    threshold: int = _MATCH_THRESHOLD,
) -> list[MatchResult]:
    """
    Pour chaque annotation, cherche son ancre dans la liste des blocs OCR.

    Stratégie :
      - Trie les blocs par y (ordre de lecture).
      - Teste des fenêtres glissantes de 1, 2 et 3 blocs consécutifs.
      - Concatène le texte de la fenêtre et calcule partial_ratio avec l'ancre.
      - Conserve le meilleur score et le center_y du bloc central de la fenêtre.
      - Si score >= threshold : retourne un MatchResult.

    Les annotations dont l'ancre n'est pas trouvée (score trop bas ou texte
    OCR absent) sont silencieusement ignorées — c'est normal si la page
    affichée ne contient pas encore cet extrait.

    Args:
        annotations : liste d'Annotation (issue d'AnnotationStore.get_for_document)
        blocks      : liste de ScanBlock (issue de GhostScanner.scan_done)
        threshold   : score minimum pour un match valide

    Returns:
        Liste de MatchResult, triée par center_y croissant.
    """
    if not annotations or not blocks:
        return []

    sorted_blocks = sorted(blocks, key=lambda b: b.y)
    n = len(sorted_blocks)
    results: list[MatchResult] = []

    for ann in annotations:
        fingerprint_norm = _normalize(_extract_fingerprint(ann.anchor))
        if not fingerprint_norm:
            continue

        best_score    = 0
        best_center_y = 0

        for window_size in _WINDOW_SIZES:
            for i in range(n - window_size + 1):
                window      = sorted_blocks[i : i + window_size]
                window_text = _normalize(" ".join(b.text for b in window))

                # partial_ratio(needle, haystack) : recherche needle dans haystack.
                # On s'assure que fingerprint est le "needle" (plus court).
                # Si la fenêtre est plus courte (peu de blocs détectés), on ignore
                # plutôt que de laisser rapidfuzz inverser la comparaison et créer
                # des faux positifs.
                if len(window_text) < len(fingerprint_norm):
                    continue

                score = fuzz.partial_ratio(fingerprint_norm, window_text)

                if score > best_score:
                    best_score    = score
                    best_center_y = window[0].center_y

        if best_score >= threshold:
            logger.info(
                "GhostMatcher — ann.%d MATCHEE score=%d y=%d : %r",
                ann.id, best_score, best_center_y, fingerprint_norm[:50],
            )
            results.append(MatchResult(
                annotation_id = ann.id,
                label         = ann.label,
                note          = ann.note,
                center_y      = best_center_y,
                score         = best_score,
            ))
        else:
            logger.info(
                "GhostMatcher — ann.%d non trouvee (score=%d) : %r",
                ann.id, best_score, fingerprint_norm[:50],
            )

    results.sort(key=lambda r: r.center_y)
    return results

