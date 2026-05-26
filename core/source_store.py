"""
SourceStore -- Persistance des metadonnees de sources ingérees

Stocke dans data/projects/{slug}/sources.json la liste des documents
ingeres avec leur metadonnees. Le ChunkManager reste la reference pour
les hashes/delta ; ce fichier ne sert qu'a l'affichage UI.

Format sources.json :
  {
    "roman-ch1.docx": {
      "source_id":  "roman-ch1.docx",
      "filename":   "Roman Chapitre 1.docx",
      "path":       "C:\\Users\\...\\Roman Chapitre 1.docx",
      "ingested_at": "2026-05-05T20:03:15",
      "nb_chunks":  42
    },
    ...
  }

API publique :
  store = SourceStore(project_dir)
  store.upsert(source_id, filename, path, nb_chunks)
  store.list_sources()   -> [dict, ...]
  store.remove(source_id)
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_SOURCES_FILE = "sources.json"


class SourceStore:
    def __init__(self, project_dir: Path):
        self._path = project_dir / _SOURCES_FILE
        self._data: dict[str, dict] = self._load()

    # ------------------------------------------------------------------
    # Lecture / ecriture
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def upsert(self, source_id: str, filename: str, path: str, nb_chunks: int,
               bible_source: bool = True) -> None:
        """Cree ou met a jour l'entree pour ce source_id."""
        entry = self._data.get(source_id, {})
        entry.update({
            "source_id":    source_id,
            "filename":     filename,
            "path":         path,
            "ingested_at":  datetime.now().isoformat(timespec="seconds"),
            "nb_chunks":    nb_chunks,
            "bible_source": bible_source,
        })
        self._data[source_id] = entry
        self._save()
        logger.info("SourceStore.upsert — %s (%d chunks, bible=%s)",
                    source_id, nb_chunks, bible_source)

    def list_sources(self) -> list[dict]:
        """Retourne la liste triee par date d'ingest (plus recent en premier)."""
        items = list(self._data.values())
        return sorted(items, key=lambda x: x.get("ingested_at", ""), reverse=True)

    def mark_orphan(self, source_id: str) -> None:
        """Marque une source comme orpheline : retiree de la librairie, memoire FAISS conservee."""
        if source_id not in self._data:
            raise KeyError(f"SourceStore.mark_orphan : source_id inconnu '{source_id}'")
        self._data[source_id]["orphan"] = True
        self._save()
        logger.info("SourceStore.mark_orphan — %s marque orphelin", source_id)

    def remove(self, source_id: str) -> None:
        """Supprime l'entree. Leve si absente."""
        if source_id not in self._data:
            raise KeyError(f"SourceStore.remove : source_id inconnu '{source_id}'")
        del self._data[source_id]
        self._save()
        logger.info("SourceStore.remove — %s supprime", source_id)

    def get(self, source_id: str) -> dict:
        """Retourne l'entree. Leve si absente."""
        if source_id not in self._data:
            raise KeyError(f"SourceStore.get : source_id inconnu '{source_id}'")
        return self._data[source_id]

    def is_bible_source(self, source_id: str) -> bool:
        """Retourne True si la source alimente la Bible (defaut: True pour retrocompat)."""
        entry = self._data.get(source_id)
        if entry is None:
            return False
        return entry.get("bible_source", True)

    def toggle_mute(self, source_id: str) -> bool:
        """
        Bascule l'etat mute d'une source.
        Retourne True si la source est maintenant muee, False sinon.
        """
        if source_id not in self._data:
            raise KeyError(f"SourceStore.toggle_mute : source_id inconnu '{source_id}'")
        current = self._data[source_id].get("muted", False)
        self._data[source_id]["muted"] = not current
        self._save()
        state = "muee" if not current else "reactivee"
        logger.info("SourceStore.toggle_mute — %s %s", source_id, state)
        return not current

    def get_muted(self) -> set[str]:
        """Retourne l'ensemble des source_id actuellement en sourdine."""
        return {sid for sid, entry in self._data.items() if entry.get("muted", False)}
