"""
ConversationStore — Persistance des conversations IA sur disque

Format : un fichier JSONL par conversation, nomme par horodatage.
  data/projects/{slug}/conversations/
      2026-05-05_20-03-12.jsonl
      2026-05-06_09-15-44.jsonl
      relational_scan_index.json   <- IDs deja scannes pour la memoire relationnelle

Chaque ligne d'un JSONL :
  {"role": "user"|"assistant", "content": "...", "ts": "2026-05-05T20:03:15"}

API publique :
  store = ConversationStore(project_slug)
  store.start_session()               -> cree un nouveau fichier
  store.append(role, content)         -> ajoute un message a la session courante
  store.list_sessions()               -> [{"id": ..., "ts": ..., "preview": ...}, ...]
  store.load_session(id)              -> [{"role":..., "content":..., "ts":...}, ...]
  store.delete_session(id)            -> supprime le fichier
  store.list_unscanned_sessions()     -> IDs non encore scannes pour la relational_db
  store.mark_relational_scanned(id)   -> marque une session comme scannee
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from core.session_manager import PROJECTS_DIR

logger = logging.getLogger(__name__)


class ConversationStore:
    _SCAN_INDEX = "relational_scan_index.json"

    def __init__(self, project_slug: str):
        self._dir = PROJECTS_DIR / project_slug / "conversations"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._current_path: Path | None = None

    # ------------------------------------------------------------------
    # Session courante
    # ------------------------------------------------------------------

    def start_session(self) -> str:
        """Cree un nouveau fichier JSONL horodate. Retourne l'id de session."""
        session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._current_path = self._dir / f"{session_id}.jsonl"
        logger.info("ConversationStore.start_session — %s", session_id)
        return session_id

    def resume_session(self, session_id: str) -> list[dict]:
        """
        Bascule sur une session existante pour la continuer.
        Les nouveaux messages seront appendés au fichier existant.
        Retourne la liste des messages existants (pour les afficher dans l'UI).
        """
        path = self._dir / f"{session_id}.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"ConversationStore.resume_session : session introuvable '{session_id}'")
        self._current_path = path
        messages = self.load_session(session_id)
        logger.info("ConversationStore.resume_session — %s (%d messages)", session_id, len(messages))
        return messages

    def append(self, role: str, content: str) -> None:
        """Ajoute un message a la session courante. Lance si start_session n'a pas ete appele."""
        if self._current_path is None:
            raise RuntimeError("ConversationStore.append : aucune session active (appeler start_session())")
        entry = {
            "role": role,
            "content": content,
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        with open(self._current_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @property
    def has_active_session(self) -> bool:
        return self._current_path is not None

    @property
    def current_path(self) -> "Path | None":
        """Chemin du fichier JSONL de la session active (None si pas de session)."""
        return self._current_path

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def _load_titles(self) -> dict[str, str]:
        titles_file = self._dir / "titles.json"
        if titles_file.exists():
            with open(titles_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_titles(self, titles: dict[str, str]) -> None:
        titles_file = self._dir / "titles.json"
        with open(titles_file, "w", encoding="utf-8") as f:
            json.dump(titles, f, ensure_ascii=False, indent=2)

    def rename_session(self, session_id: str, new_title: str) -> None:
        titles = self._load_titles()
        if new_title:
            titles[session_id] = new_title
        else:
            titles.pop(session_id, None)
        self._save_titles(titles)

    def list_sessions(self) -> list[dict]:
        """
        Retourne la liste des sessions triee du plus recent au plus ancien.
        Chaque entree : {"id": str, "ts": str, "preview": str, "title": str}
        """
        sessions = []
        titles = self._load_titles()
        for p in sorted(self._dir.glob("*.jsonl"), reverse=True):
            session_id = p.stem
            preview = self._read_preview(p)
            ts = self._id_to_ts(session_id)
            title = titles.get(session_id, "")
            sessions.append({"id": session_id, "ts": ts, "preview": preview, "title": title})
        return sessions

    def load_session(self, session_id: str) -> list[dict]:
        """Charge tous les messages d'une session. Leve si le fichier n'existe pas."""
        path = self._dir / f"{session_id}.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"ConversationStore.load_session : session introuvable '{session_id}'")
        messages = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
        return messages

    def delete_session(self, session_id: str) -> None:
        """Supprime une session. Leve si le fichier n'existe pas."""
        path = self._dir / f"{session_id}.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"ConversationStore.delete_session : session introuvable '{session_id}'")
        path.unlink()
        logger.info("ConversationStore.delete_session — %s supprimee", session_id)
        if self._current_path == path:
            self._current_path = None

    # ------------------------------------------------------------------
    # Suivi des scans de memoire relationnelle
    # ------------------------------------------------------------------

    def _scan_index_path(self) -> Path:
        return self._dir / self._SCAN_INDEX

    def _load_scan_index(self) -> set[str]:
        p = self._scan_index_path()
        if not p.exists():
            return set()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data) if isinstance(data, list) else set()
        except Exception:
            return set()

    def _save_scan_index(self, scanned: set[str]) -> None:
        with open(self._scan_index_path(), "w", encoding="utf-8") as f:
            json.dump(sorted(scanned), f, ensure_ascii=False)

    def list_unscanned_sessions(self) -> list[str]:
        """
        Retourne les IDs de sessions non encore scannes pour la memoire relationnelle.
        Exclut la session en cours (pas encore terminee).
        Tries du plus ancien au plus recent (scan chronologique).
        """
        scanned = self._load_scan_index()
        current_id = self._current_path.stem if self._current_path else None
        all_ids = sorted(
            p.stem for p in self._dir.glob("*.jsonl")
            if p.stem not in scanned and p.stem != current_id
        )
        return all_ids

    def mark_relational_scanned(self, session_id: str) -> None:
        """Marque une session comme scannee pour la memoire relationnelle."""
        scanned = self._load_scan_index()
        scanned.add(session_id)
        self._save_scan_index(scanned)
        logger.debug("ConversationStore — session marquee scannee : %s", session_id)

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    @staticmethod
    def _read_preview(path: Path) -> str:
        """Lit la premiere ligne user du fichier et retourne un extrait de 80 chars."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if entry.get("role") == "user":
                        text = entry.get("content", "")
                        return text[:80] + ("…" if len(text) > 80 else "")
        except Exception:
            pass
        return "(conversation vide)"

    @staticmethod
    def _id_to_ts(session_id: str) -> str:
        """Convertit '2026-05-05_20-03-12' en '05/05/2026 20:03'."""
        try:
            dt = datetime.strptime(session_id, "%Y-%m-%d_%H-%M-%S")
            return dt.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return session_id
