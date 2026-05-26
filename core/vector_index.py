"""
VectorIndex -- Index FAISS par projet

Vectorise les text_small des chunks via l'API embed configuree par l'utilisateur
(Mistral, OpenAI, etc.) et permet une recherche semantique rapide.

Aucun modele local n'est utilise. Si ia_embed n'est pas configure,
les operations d'indexation et de recherche sont desactivees silencieusement.

Structure sur disque (dans data/projects/{slug}/) :
  vector_index.faiss   -- index FAISS brut
  vector_meta.json     -- metadonnees associees a chaque vecteur
                          [{source_id, chunk_index, text_small, text_parent}, ...]
  embed_model.txt      -- nom du modele API ayant genere l'index

API publique :
  idx = VectorIndex(project_dir)
  idx.set_embed_config(config)             -- configure le modele API (obligatoire)
  idx.add_chunks(source_id, chunks)        -- indexe/re-indexe les chunks d'une source
  idx.search(query, k=5)                   -- retourne les k chunks les plus proches
  idx.remove_source(source_id)             -- retire tous les vecteurs d'une source
  idx.is_empty()                           -- True si aucun vecteur
  idx.is_configured()                      -- True si un modele embed API est pret
"""

import json
import logging
import numpy as np
from pathlib import Path
from typing import Any

import faiss
from openai import OpenAI

from core.chunk_manager import ChunkResult

logger = logging.getLogger(__name__)

_FAISS_FILE       = "vector_index.faiss"
_META_FILE        = "vector_meta.json"
_EMBED_MODEL_FILE = "embed_model.txt"


class VectorIndex:
    def __init__(self, project_dir: Path):
        self._dir = project_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._faiss_path       = self._dir / _FAISS_FILE
        self._meta_path        = self._dir / _META_FILE
        self._embed_model_path = self._dir / _EMBED_MODEL_FILE
        self._index: Any = None
        self._meta: list[dict] = []
        self._dim: int = 0
        self._dedup_enabled:   bool  = True
        self._dedup_threshold: float = 0.93
        self._embed_model:  str | None = None
        self._embed_client: OpenAI | None = None
        self._load()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_embed_config(self, config: dict) -> None:
        """
        Configure le modele d'embedding API.

        Appele depuis main_window avec resolve_engine_config(cfg['ia_embed']).
        Si api_key ou model est vide, l'index est desactive (aucun modele local
        de substitution).

        IMPORTANT : si le modele change alors qu'un index existe deja, l'index
        est invalide (dimensions differentes). Un warning est emis dans les logs.
        L'utilisateur doit purger et re-ingerer manuellement.
        """
        api_key  = config.get("api_key", "").strip()
        model    = config.get("model", "").strip()
        base_url = config.get("base_url") or None

        if not api_key or not model:
            self._embed_client = None
            self._embed_model  = None
            logger.warning(
                "VectorIndex.set_embed_config — ia_embed non configure "
                "(cle API ou modele manquant). Indexation desactivee."
            )
            return

        # Avertir si le modele change alors qu'un index existe
        persisted = self._load_persisted_model_name()
        if persisted and persisted != model and self._index is not None:
            logger.warning(
                "VectorIndex.set_embed_config — modele change (%s -> %s) "
                "mais l'index FAISS existant a ete cree avec l'ancien modele. "
                "Purger l'index et re-ingerer les sources.",
                persisted, model,
            )

        self._embed_client = OpenAI(api_key=api_key, base_url=base_url)
        self._embed_model  = model
        logger.info(
            "VectorIndex.set_embed_config — API embed : model=%s base_url=%s",
            model, base_url or "(defaut OpenAI)",
        )

    def set_dedup_config(self, enabled: bool, threshold: float) -> None:
        """Met a jour la configuration de deduplication semantique."""
        self._dedup_enabled   = bool(enabled)
        self._dedup_threshold = max(0.50, min(0.99, float(threshold)))
        logger.info(
            "VectorIndex.set_dedup_config — enabled=%s threshold=%.2f",
            self._dedup_enabled, self._dedup_threshold,
        )

    def is_configured(self) -> bool:
        """True si un modele embed API est configure et pret."""
        return self._embed_client is not None and bool(self._embed_model)

    # ------------------------------------------------------------------
    # Encodage via API
    # ------------------------------------------------------------------

    def _encode(self, texts: list[str]) -> np.ndarray:
        """
        Vectorise via l'API embed configuree.
        Leve RuntimeError si aucun modele n'est configure.
        """
        if not self.is_configured():
            raise RuntimeError(
                "VectorIndex : aucun modele embed API configure. "
                "Configurer ia_embed dans les Parametres."
            )
        response = self._embed_client.embeddings.create(  # type: ignore[union-attr]
            model=self._embed_model,
            input=texts,
        )
        vectors = np.array(
            [item.embedding for item in response.data], dtype=np.float32
        )
        
        # Normalisation L2 (Indispensable pour utiliser Inner Product comme Cosine Similarity)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vectors = vectors / norms
        
        logger.debug(
            "VectorIndex._encode — %s : %d vecteurs dim=%d",
            self._embed_model, len(texts), vectors.shape[1],
        )
        return vectors

    def _load_persisted_model_name(self) -> str | None:
        if self._embed_model_path.exists():
            return self._embed_model_path.read_text(encoding="utf-8").strip()
        return None

    def _persist_model_name(self) -> None:
        if self._embed_model:
            self._embed_model_path.write_text(self._embed_model, encoding="utf-8")

    # ------------------------------------------------------------------
    # Chargement / sauvegarde
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._faiss_path.exists() and self._meta_path.exists():
            self._index = faiss.read_index(str(self._faiss_path))
            with open(self._meta_path, "r", encoding="utf-8") as f:
                self._meta = json.load(f)
            self._dim = self._index.d
            logger.info(
                "VectorIndex — charge : %d vecteurs (dim=%d)", len(self._meta), self._dim
            )
        else:
            self._index = None
            self._meta = []

    def _save(self) -> None:
        if self._index is None:
            return
        faiss.write_index(self._index, str(self._faiss_path))
        with open(self._meta_path, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, ensure_ascii=False, indent=2)

    def _init_index(self, dim: int) -> None:
        """Cree un index IP plat (exact, adapte aux petits corpus <100k vecteurs)."""
        self._dim = dim
        self._index = faiss.IndexFlatIP(dim)

    # ------------------------------------------------------------------
    # Indexation
    # ------------------------------------------------------------------

    def add_chunks(self, source_id: str, chunks: list[ChunkResult]) -> None:
        """
        Vectorise et indexe les chunks d'une source via l'API embed.
        Utilise text_index (resume factuel) si disponible, sinon text_small.
        Sans effet si ia_embed n'est pas configure.
        """
        if not chunks:
            return
        if not self.is_configured():
            logger.warning(
                "VectorIndex.add_chunks — ia_embed non configure, '%s' non indexe",
                source_id,
            )
            return

        self.remove_source(source_id)

        # Priorite : text_index (resume factuel) > text_small (prose brute)
        texts = [c.text_index if c.text_index else c.text_small for c in chunks]
        has_index = sum(1 for c in chunks if c.text_index)
        logger.info(
            "[FAISS:VECT] START '%s' — %d chunks (%d avec resume factuel) [model=%s]",
            source_id, len(chunks), has_index, self._embed_model,
        )

        try:
            embeddings = self._encode(texts)
        except Exception as exc:
            logger.error("VectorIndex.add_chunks — echec encodage : %s", exc)
            return

        dim = embeddings.shape[1]
        if self._index is None:
            self._init_index(dim)
        elif dim != self._dim:
            logger.error(
                "VectorIndex.add_chunks — dimension incompatible (%d != %d). "
                "Purger l'index et re-ingerer.", dim, self._dim,
            )
            return

        self._index.add(embeddings)
        for chunk in chunks:
            self._meta.append({
                "source_id":   source_id,
                "chunk_index": chunk.chunk_index,
                "text_small":  chunk.text_small,
                "text_parent": chunk.text_parent,
                "text_index":  chunk.text_index,
            })

        self._save()
        self._persist_model_name()
        logger.info(
            "[FAISS:VECT] OK '%s' — %d vecteurs ajoutés (total index=%d) [model=%s]",
            source_id, len(chunks), len(self._meta), self._embed_model,
        )

    def add_bible_entries(self, entries: list[dict]) -> None:
        """
        Vectorise toutes les entrees de la Bible sous source_id='bible'.
        Full rebuild a chaque appel (remove + re-add).

        entries : liste de dicts {table, label, content, ...}
                  depuis bible_db.get_all_tables()
        """
        if not self.is_configured():
            logger.warning(
                "VectorIndex.add_bible_entries — ia_embed non configure, ignore"
            )
            return

        n_before = sum(1 for m in self._meta if m["source_id"] == "bible")
        logger.info(
            "[FAISS:VECT] START Bible — %d entrées à vectoriser, %d vecteurs Bible existants à remplacer [model=%s]",
            len(entries), n_before, self._embed_model,
        )
        self.remove_source("bible")
        if not entries:
            logger.info("VectorIndex.add_bible_entries — Bible vide, rien a vectoriser")
            return

        texts = [
            f"{e['label']} : {e['content'][:300]}"
            for e in entries
        ]
        try:
            embeddings = self._encode(texts)
        except Exception as exc:
            logger.error("VectorIndex.add_bible_entries — echec encodage : %s", exc)
            return

        dim = embeddings.shape[1]
        if self._index is None:
            self._init_index(dim)
        elif dim != self._dim:
            logger.error(
                "VectorIndex.add_bible_entries — dimension incompatible (%d != %d). "
                "Purger l'index et re-ingerer.", dim, self._dim,
            )
            return

        self._index.add(embeddings)
        for i, e in enumerate(entries):
            self._meta.append({
                "source_id":   "bible",
                "chunk_index": i,
                "text_small":  f"{e['label']} : {e['content'][:200]}",
                "text_parent": f"[{e['table'].upper()}] {e['label']} : {e['content']}",
                "text_index":  "",
                "bible_table": e["table"],
                "bible_label": e["label"],
            })

        self._save()
        self._persist_model_name()
        logger.info(
            "[FAISS:VECT] OK Bible — %d entrées vectorisées (total index=%d) [model=%s]",
            len(entries), len(self._meta), self._embed_model,
        )

    def is_bible_memorized(self) -> bool:
        """True si des entrees Bible sont presentes dans l'index FAISS."""
        return any(m["source_id"] == "bible" for m in self._meta)

    def search(self, query: str, k: int = 5) -> list[dict]:
        """
        Retourne les k chunks les plus proches de la query.
        Retourne [] si l'index est vide ou ia_embed non configure.
        """
        if self._index is None or self._index.ntotal == 0:
            return []
        if not self.is_configured():
            logger.warning("VectorIndex.search — ia_embed non configure, recherche impossible")
            return []

        try:
            vec = self._encode([query])
        except Exception as exc:
            logger.error("VectorIndex.search — echec encodage query : %s", exc)
            return []

        k_real = min(k, self._index.ntotal)
        distances, indices = self._index.search(vec, k_real)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._meta):
                continue
            entry = dict(self._meta[idx])
            entry["score"] = float(dist)
            results.append(entry)

        return results

    def filter_semantic_delta(
        self,
        chunks: list[ChunkResult],
        threshold: float | None = None,
    ) -> list[ChunkResult]:
        """
        Filtre les chunks semantiquement trop proches d'un contenu deja indexe.

        Si `threshold` est None, utilise `self._dedup_threshold` (config UI).
        Si la deduplication est desactivee (`_dedup_enabled=False`), retourne tous les chunks.
        """
        if self._index is None or self._index.ntotal == 0 or not chunks:
            return chunks
        if not self.is_configured():
            logger.debug("[FAISS:DEDUP] ia_embed non configure — deduplication ignoree")
            return chunks
        if not self._dedup_enabled:
            logger.debug("[FAISS:DEDUP] désactivé — tous les chunks acceptés")
            return chunks

        effective_threshold = threshold if threshold is not None else self._dedup_threshold

        try:
            embeddings = self._encode([c.text_small for c in chunks])
        except Exception as exc:
            logger.error("[FAISS:DEDUP] echec encodage : %s — tous les chunks acceptes", exc)
            return chunks

        result = []
        for i, chunk in enumerate(chunks):
            dists, _ = self._index.search(embeddings[i : i + 1], k=1)
            cos_sim = float(dists[0][0])
            if cos_sim >= effective_threshold:
                logger.debug(
                    "[FAISS:DEDUP] chunk=%s similaire a existant (cos=%.3f >= %.2f) — ignore",
                    chunk.chunk_index, cos_sim, effective_threshold,
                )
            else:
                result.append(chunk)

        skipped = len(chunks) - len(result)
        if skipped:
            logger.info(
                "[FAISS:DEDUP] %d chunk(s) semantiquement dupliques ignores (seuil=%.2f)",
                skipped, effective_threshold,
            )
        return result

    # ------------------------------------------------------------------
    # Suppression
    # ------------------------------------------------------------------

    def remove_source(self, source_id: str) -> None:
        """
        Retire tous les vecteurs associes a source_id.
        FAISS IndexFlatL2 ne supporte pas la suppression directe :
        on reconstruit l'index sans les vecteurs de cette source.
        """
        if self._index is None:
            return

        keep_indices = [i for i, m in enumerate(self._meta) if m["source_id"] != source_id]
        removed = len(self._meta) - len(keep_indices)
        if removed == 0:
            return

        logger.info(
            "[FAISS:DEL] '%s' — %d vecteur(s) à supprimer (index avant=%d)",
            source_id, removed, len(self._meta),
        )

        if not keep_indices:
            self._index = None
            self._meta = []
            # Supprimer les fichiers si index vide
            if self._faiss_path.exists():
                self._faiss_path.unlink()
            if self._meta_path.exists():
                self._meta_path.unlink()
            logger.info("[FAISS:DEL] '%s' supprimé — index maintenant vide", source_id)
            return

        # Reconstruire l'index avec les vecteurs restants
        # On doit lire les vecteurs existants de facon securisee
        old_index = self._index
        all_vecs = old_index.reconstruct_n(0, old_index.ntotal)
        kept_vecs = all_vecs[keep_indices]

        self._init_index(self._dim)
        self._index.add(kept_vecs.astype(np.float32))
        self._meta = [self._meta[i] for i in keep_indices]
        self._save()
        logger.info(
            "[FAISS:DEL] '%s' supprimé — %d vecteurs retirés, %d restants",
            source_id, removed, len(self._meta),
        )

    def is_empty(self) -> bool:
        return self._index is None or self._index.ntotal == 0
