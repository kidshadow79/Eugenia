"""
chunk_manager.py — Découpage de texte et détection delta pour la Bible EUGENIA

Basé sur le pattern Parent Document Retrieval d'OGMA (project_rag/project_chunker.py).

Deux niveaux de chunks pour chaque texte ingéré :
    - text_small  (~200 tokens) : grain fin, prévu pour recherche FAISS future
    - text_parent (~800 tokens) : contexte riche, injecté au LLM

Détection delta (réinjection d'un texte déjà ingéré) :
    - Chaque chunk a un hash sha256(text_small)
    - Stocker {chunk_index: hash} dans chunks.json du projet
    - À la réinjection : comparer → ne re-scanner que les chunks modifiés/nouveaux

Usage :
    mgr = ChunkManager(project_dir)
    chunks = mgr.chunk_text(texte_brut)   # → liste de ChunkResult
    new_chunks = mgr.filter_delta("source-id", chunks)   # → uniquement les nouveaux
    mgr.save_hashes("source-id", chunks)   # → persist

    # Plus tard, réinjection :
    new_chunks = mgr.filter_delta("source-id", rechunked)  # seuls les modifiés
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────

# 1 token ≈ 4 caractères (approximation valable pour le français)
_CHARS_PER_TOKEN = 4

# Tailles cibles par défaut
_SMALL_TOKENS = 200     # ~800 caractères
_PARENT_TOKENS = 800    # ~3200 caractères
_OVERLAP_TOKENS = 50    # ~200 caractères de chevauchement entre chunks parents

# Nom du fichier de persistance des hashes
_HASHES_FILE = "chunks_hashes.json"


# ─── Types ────────────────────────────────────────────────────────────────────

@dataclass
class ChunkResult:
    """Un chunk produit par le découpage."""
    chunk_index: int
    text_small: str      # ~200 tokens — grain fin
    text_parent: str     # ~800 tokens — contexte riche
    hash: str            # sha256(text_small) — clé de détection delta
    text_index: str = "" # résumé factuel généré par l'Archiviste (vectorisé en priorité)


# ─── Fonctions internes ───────────────────────────────────────────────────────

def _token_estimate(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_into_sentences(text: str) -> list[str]:
    """
    Découpe un texte en phrases sur . ! ? — adapté au français romanesque.
    Gère aussi les sauts de paragraphe (double newline) comme séparateurs naturels.
    """
    # D'abord, couper sur les paragraphes (double newline ou simple newline après ponctuation)
    paragraphs = re.split(r'\n{2,}', text)
    sentences = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # Puis couper sur . ! ? suivi d'espace ou fin
        parts = re.split(r'(?<=[.!?…»])\s+', para)
        sentences.extend(s.strip() for s in parts if s.strip())
    return sentences


def _build_parent_chunks(segments: list[str]) -> list[str]:
    """Assemble les segments en blocs de taille _PARENT_TOKENS avec chevauchement."""
    parent_chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for seg in segments:
        seg_tokens = _token_estimate(seg)
        if current_tokens + seg_tokens > _PARENT_TOKENS and current:
            parent_chunks.append(" ".join(current))
            # Overlap : garder les dernières phrases jusqu'à _OVERLAP_TOKENS
            overlap: list[str] = []
            overlap_tokens = 0
            for s in reversed(current):
                st = _token_estimate(s)
                if overlap_tokens + st > _OVERLAP_TOKENS:
                    break
                overlap.insert(0, s)
                overlap_tokens += st
            current = overlap
            current_tokens = overlap_tokens
        current.append(seg)
        current_tokens += seg_tokens

    if current:
        parent_chunks.append(" ".join(current))

    return parent_chunks


def _build_small_chunks(parent_text: str) -> list[str]:
    """Découpe un chunk parent en petits chunks de taille _SMALL_TOKENS."""
    sentences = _split_into_sentences(parent_text)
    small_chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sent in sentences:
        sent_tokens = _token_estimate(sent)
        if current_tokens + sent_tokens > _SMALL_TOKENS and current:
            small_chunks.append(" ".join(current))
            current = []
            current_tokens = 0
        current.append(sent)
        current_tokens += sent_tokens

    if current:
        small_chunks.append(" ".join(current))

    return small_chunks or [parent_text]


# ─── Classe principale ────────────────────────────────────────────────────────

class ChunkManager:
    """
    Gère le découpage et la détection delta pour un projet.

    Les hashes sont persistés dans :
        data/projects/{slug}/memory_work/chunks_hashes.json

    Format :
    {
        "source-id-1": {"0": "sha256...", "1": "sha256...", ...},
        "source-id-2": {...}
    }
    """

    def __init__(self, project_dir: Path):
        """
        Args:
            project_dir: dossier du projet (data/projects/{slug}/)
        """
        self._work_dir = project_dir / "memory_work"
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._hashes_path = self._work_dir / _HASHES_FILE
        self._hashes: dict[str, dict[str, str]] = self._load_hashes()

    # ─── Découpage ────────────────────────────────────────────────────────────

    def chunk_text(self, text: str) -> list[ChunkResult]:
        """
        Découpe un texte brut en liste de ChunkResult.
        Adapté au texte romanesque français.

        Args:
            text: texte brut à découper

        Returns:
            Liste de ChunkResult (peut être vide si texte vide)
        """
        if not text or not text.strip():
            return []

        segments = _split_into_sentences(text)
        if not segments:
            # Dernier recours : une phrase = un bloc entier
            segments = [text.strip()]

        parent_chunks = _build_parent_chunks(segments)
        results: list[ChunkResult] = []
        chunk_index = 0

        for parent_text in parent_chunks:
            small_chunks = _build_small_chunks(parent_text)
            for small_text in small_chunks:
                results.append(ChunkResult(
                    chunk_index=chunk_index,
                    text_small=small_text.strip(),
                    text_parent=parent_text.strip(),
                    hash=_sha256(small_text.strip()),
                ))
                chunk_index += 1

        return results

    # ─── Détection delta ──────────────────────────────────────────────────────

    def filter_delta(self, source_id: str, chunks: list[ChunkResult]) -> list[ChunkResult]:
        """
        Filtre une liste de chunks pour ne retourner que les nouveaux ou modifiés.

        Comparaison par hash :
            - chunk absent de l'historique → nouveau → inclus
            - hash différent de l'historique → modifié → inclus
            - hash identique (même source_id) → inchangé → exclu
            - hash identique dans UNE AUTRE source → doublon cross-source → exclu

        Args:
            source_id: identifiant de la source (ex: "clipboard", "roman-ch1.docx")
            chunks: liste de ChunkResult produits par chunk_text()

        Returns:
            Sous-liste des chunks à (re)traiter par l'Archiviste
        """
        known_this_source = self._hashes.get(source_id, {})
        # Ensemble plat de tous les hashes déjà connus toutes sources confondues
        all_known_hashes: set[str] = {
            h
            for src, idx_map in self._hashes.items()
            for h in idx_map.values()
        }
        result = []
        for c in chunks:
            same_position_hash = known_this_source.get(str(c.chunk_index))
            if same_position_hash == c.hash:
                # Même source, même position, même contenu → inchangé
                continue
            if c.hash in all_known_hashes:
                # Contenu déjà vu dans une autre source → doublon cross-source
                logger.debug(
                    "ChunkManager.filter_delta — doublon cross-source ignore "
                    "(source=%s chunk=%s)", source_id, c.chunk_index
                )
                continue
            result.append(c)
        return result

    def save_chunk_hash(self, source_id: str, chunk: ChunkResult) -> None:
        """Sauvegarde le hash d'un seul chunk (progression temps réel)."""
        if source_id not in self._hashes:
            self._hashes[source_id] = {}
        self._hashes[source_id][str(chunk.chunk_index)] = chunk.hash
        self._persist_hashes()

    def save_hashes(self, source_id: str, chunks: list[ChunkResult]) -> None:
        """
        Persiste les hashes d'une source après traitement.
        À appeler UNIQUEMENT une fois que l'Archiviste a traité les chunks avec succès.

        Args:
            source_id: identifiant de la source
            chunks: liste complète des chunks traités (tous, pas seulement les delta)
        """
        self._hashes[source_id] = {str(c.chunk_index): c.hash for c in chunks}
        self._persist_hashes()

    def get_chunk_ids_for_source(self, source_id: str) -> list[str]:
        """
        Retourne la liste des source_chunk stockes en Bible pour un source_id donne.
        Ex: source_id='roman.docx' avec indices 0,1,2 → ['chunk-0', 'chunk-1', 'chunk-2']

        Retourne [] si la source est inconnue.
        """
        indices = self._hashes.get(source_id, {})
        return [f"chunk-{idx}" for idx in indices]

    def clear_source(self, source_id: str) -> None:
        """Supprime les hashes d'une source (force re-scan complet à la prochaine injection)."""
        if source_id in self._hashes:
            del self._hashes[source_id]
            self._persist_hashes()

    def known_sources(self) -> list[str]:
        """Liste des source_id déjà traités."""
        return list(self._hashes.keys())

    # ─── Persistance ──────────────────────────────────────────────────────────

    def _load_hashes(self) -> dict[str, dict[str, str]]:
        if not self._hashes_path.exists():
            return {}
        try:
            with open(self._hashes_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _persist_hashes(self) -> None:
        with open(self._hashes_path, "w", encoding="utf-8") as f:
            json.dump(self._hashes, f, ensure_ascii=False, indent=2)

    def __repr__(self) -> str:
        total = sum(len(v) for v in self._hashes.values())
        return f"ChunkManager({self._work_dir}, sources={len(self._hashes)}, chunks_tracked={total})"
