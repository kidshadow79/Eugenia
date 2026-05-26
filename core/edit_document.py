"""
edit_document.py — Modele de donnees et persistance pour les documents edites

Chaque document edite est stocke dans :
  data/projects/{slug}/edit_docs/
    index.json          -- liste des docs {doc_id, title, created_at, last_modified}
    {doc_id}.md         -- contenu actuel (markdown)
    {doc_id}_b{0..4}.md -- ring de backups (max 5)
    {doc_id}_bmeta.json -- {cursor: int, count: int}

API publique :
  store = EditDocStore(project_dir)
  doc   = store.create_doc("Mon titre")
  store.push_backup(doc)
  doc.content = "Nouveau contenu"
  store.save_doc(doc)
  content = store.restore_last_backup(doc)
  docs    = store.list_docs()     -> [dict, ...]
  store.delete_doc(doc_id)
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_EDIT_DOCS_DIR = "edit_docs"
_MAX_BACKUPS   = 5


# ── Modele ────────────────────────────────────────────────────────────────────

@dataclass
class EditDocument:
    doc_id:        str
    title:         str
    content:       str
    created_at:    str
    last_modified: str


# ── Store ─────────────────────────────────────────────────────────────────────

class EditDocStore:
    """Gere la persistance des documents edites (contenu + backups)."""

    def __init__(self, project_dir: Path):
        self._dir = project_dir / _EDIT_DOCS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "index.json"

    # ── Index ─────────────────────────────────────────────────────────────────

    def _load_index(self) -> list[dict]:
        if not self._index_path.exists():
            return []
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("[EDIT] erreur lecture index : %s", exc)
            return []

    def _save_index(self, index: list[dict]) -> None:
        tmp = self._index_path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
            tmp.replace(self._index_path)
        except Exception as exc:
            logger.error("[EDIT] erreur sauvegarde index : %s", exc)
            raise

    def _upsert_index(self, doc: "EditDocument") -> None:
        index = self._load_index()
        entry = {
            "doc_id":        doc.doc_id,
            "title":         doc.title,
            "created_at":    doc.created_at,
            "last_modified": doc.last_modified,
        }
        for i, item in enumerate(index):
            if item["doc_id"] == doc.doc_id:
                index[i] = entry
                self._save_index(index)
                return
        index.insert(0, entry)
        self._save_index(index)

    # ── Chemins ───────────────────────────────────────────────────────────────

    def _content_path(self, doc_id: str) -> Path:
        return self._dir / f"{doc_id}.md"

    def _backup_path(self, doc_id: str, slot: int) -> Path:
        return self._dir / f"{doc_id}_b{slot}.md"

    def _bmeta_path(self, doc_id: str) -> Path:
        return self._dir / f"{doc_id}_bmeta.json"

    def _load_bmeta(self, doc_id: str) -> dict:
        p = self._bmeta_path(doc_id)
        if not p.exists():
            return {"cursor": 0, "count": 0}
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"cursor": 0, "count": 0}

    def _save_bmeta(self, doc_id: str, meta: dict) -> None:
        tmp = self._bmeta_path(doc_id).with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        tmp.replace(self._bmeta_path(doc_id))

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create_doc(self, title: str) -> EditDocument:
        """Cree un nouveau document vide et le persiste."""
        now    = datetime.now().isoformat(timespec="seconds")
        doc_id = uuid.uuid4().hex[:12]
        doc    = EditDocument(
            doc_id        = doc_id,
            title         = title,
            content       = "",
            created_at    = now,
            last_modified = now,
        )
        self._content_path(doc_id).write_text("", encoding="utf-8")
        self._upsert_index(doc)
        logger.info("[EDIT] document cree — id=%s titre=%s", doc_id, title)
        return doc

    def get_doc(self, doc_id: str) -> "EditDocument | None":
        """Charge un document depuis le disque. Retourne None si introuvable."""
        p = self._content_path(doc_id)
        if not p.exists():
            return None
        content = p.read_text(encoding="utf-8")
        index   = self._load_index()
        meta    = next((x for x in index if x["doc_id"] == doc_id), None)
        if meta is None:
            return None
        return EditDocument(
            doc_id        = doc_id,
            title         = meta["title"],
            content       = content,
            created_at    = meta["created_at"],
            last_modified = meta["last_modified"],
        )

    def save_doc(self, doc: EditDocument) -> None:
        """Persiste le contenu courant et met a jour l'index."""
        doc.last_modified = datetime.now().isoformat(timespec="seconds")
        tmp = self._content_path(doc.doc_id).with_suffix(".tmp")
        tmp.write_text(doc.content, encoding="utf-8")
        tmp.replace(self._content_path(doc.doc_id))
        self._upsert_index(doc)
        logger.debug("[EDIT] document sauvegarde — id=%s", doc.doc_id)

    def push_backup(self, doc: EditDocument) -> None:
        """
        Sauvegarde le contenu actuel dans le ring de backups avant modification.
        Le ring tourne sur _MAX_BACKUPS slots (0..4).
        """
        if not doc.content:
            return
        meta   = self._load_bmeta(doc.doc_id)
        slot   = meta["cursor"] % _MAX_BACKUPS
        target = self._backup_path(doc.doc_id, slot)
        target.write_text(doc.content, encoding="utf-8")
        meta["cursor"] = (slot + 1) % _MAX_BACKUPS
        meta["count"]  = min(meta["count"] + 1, _MAX_BACKUPS)
        self._save_bmeta(doc.doc_id, meta)
        logger.debug("[EDIT] backup cree — id=%s slot=%d count=%d",
                     doc.doc_id, slot, meta["count"])

    def restore_last_backup(self, doc: EditDocument) -> str | None:
        """
        Restaure le dernier backup dans doc.content et le supprime du ring.
        Retourne le contenu restaure, ou None si aucun backup disponible.
        """
        meta = self._load_bmeta(doc.doc_id)
        if meta["count"] == 0:
            return None
        # Le dernier backup ecrit est au slot (cursor - 1) % MAX
        last_slot = (meta["cursor"] - 1) % _MAX_BACKUPS
        p = self._backup_path(doc.doc_id, last_slot)
        if not p.exists():
            return None
        content = p.read_text(encoding="utf-8")
        # Retirer ce backup du ring
        p.unlink()
        meta["cursor"] = last_slot
        meta["count"]  = max(meta["count"] - 1, 0)
        self._save_bmeta(doc.doc_id, meta)
        doc.content = content
        logger.info("[EDIT] backup restaure — id=%s slot=%d restants=%d",
                    doc.doc_id, last_slot, meta["count"])
        return content

    def backup_count(self, doc_id: str) -> int:
        """Nombre de backups disponibles pour ce document."""
        return self._load_bmeta(doc_id)["count"]

    # ── Liste + suppression ───────────────────────────────────────────────────

    def list_docs(self) -> list[dict]:
        """Retourne la liste des docs (plus recent en premier)."""
        return list(self._load_index())

    def find_by_title(self, title: str) -> "EditDocument | None":
        """Cherche un document par titre (correspondance exacte, insensible a la casse)."""
        for entry in self._load_index():
            if entry["title"].lower() == title.lower():
                return self.get_doc(entry["doc_id"])
        return None

    def delete_doc(self, doc_id: str) -> None:
        """Supprime un document et tous ses backups."""
        self._content_path(doc_id).unlink(missing_ok=True)
        for slot in range(_MAX_BACKUPS):
            self._backup_path(doc_id, slot).unlink(missing_ok=True)
        self._bmeta_path(doc_id).unlink(missing_ok=True)
        index = [x for x in self._load_index() if x["doc_id"] != doc_id]
        self._save_index(index)
        logger.info("[EDIT] document supprime — id=%s", doc_id)

    def export_to_file(self, doc: EditDocument, dest: Path) -> None:
        """Exporte le contenu courant vers un fichier (md ou txt)."""
        dest.write_text(doc.content, encoding="utf-8")
        logger.info("[EDIT] export — id=%s -> %s", doc.doc_id, dest)
