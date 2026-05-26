"""
relational_db.py — Mémoire relationnelle SQLite par auteur

Stocke ce que l'Archiviste apprend SUR l'auteur (pas sur le roman).
Peuplée uniquement lors des résumations de conversation.

Tables :
    - author_notes    : faits généraux sur l'auteur (style, habitudes, préférences)
    - author_entities : personnes réelles, lieux, événements mentionnés par l'auteur

Chaque entrée a un hash de contenu (déduplication simple sans LLM).

Chemin : data/authors/{slug}/memory_relational/relational.db

Usage :
    db = RelationalDB(author_dir)
    added = db.upsert_note("style", "Préfère les phrases courtes et percutantes")
    added = db.upsert_entity("person", "Marthe", "Sa mère, décédée en 2019")
    notes = db.get_all_notes()
    db.close()
"""

import hashlib
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_BACKUPS = 4

# Types d'entités supportés
ENTITY_TYPES = ("person", "place", "event", "other")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS author_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,
    content     TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_category ON author_notes(category);

CREATE TABLE IF NOT EXISTS author_entities (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type  TEXT NOT NULL,
    label        TEXT NOT NULL,
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_type  ON author_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_label ON author_entities(label);
"""


class RelationalDB:
    """Mémoire relationnelle de l'auteur (persistante entre projets)."""

    def __init__(self, author_dir: Path):
        """
        Initialise la base de donnees relationnelle.
        Args:
            author_dir: dossier de l'auteur, ex: data/authors/auteur_1/
                        La base sera dans author_dir/memory_relational/relational.db
        """
        self._rel_dir = author_dir / "memory_relational"
        self._rel_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._rel_dir / "relational.db"
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ─── Init ──────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    # ─── Backup ────────────────────────────────────────────────────────────────

    def _backup(self) -> None:
        if not self._db_path.exists():
            return
        for i in range(_MAX_BACKUPS - 1, 0, -1):
            src = self._rel_dir / f"relational.db.bak{i}"
            dst = self._rel_dir / f"relational.db.bak{i + 1}"
            if src.exists():
                shutil.copy2(src, dst)
        shutil.copy2(self._db_path, self._rel_dir / "relational.db.bak1")

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()

    # ─── Notes ─────────────────────────────────────────────────────────────────

    def upsert_note(self, category: str, content: str) -> bool:
        """
        Ajoute une note sur l'auteur si elle n'existe pas déjà (déduplication par hash).

        Args:
            category: ex "style", "habitudes", "preferences", "contexte"
            content:  texte de la note

        Returns:
            True si ajoutée, False si déjà présente (doublon)
        """
        h = self._hash(content)
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT id FROM author_notes WHERE content_hash = ?", (h,)
        ).fetchone()
        if existing:
            return False

        self._backup()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO author_notes (category, content, content_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (category, content.strip(), h, now, now),
        )
        conn.commit()
        logger.info("[MEM:WRITE] note ajoutee (cat=%s) : %s", category, content[:80])
        return True

    def get_all_notes(self, category: Optional[str] = None) -> list[dict]:
        """
        Retourne toutes les notes, optionnellement filtrées par catégorie.
        Triées par created_at décroissant (les plus récentes d'abord).
        """
        conn = self._get_conn()
        if category:
            rows = conn.execute(
                "SELECT * FROM author_notes WHERE category = ? ORDER BY created_at DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM author_notes ORDER BY category, created_at DESC"
            ).fetchall()
        logger.debug("[MEM:READ] get_all_notes(cat=%s) -> %d entree(s)", category or "*", len(rows))
        return [dict(r) for r in rows]

    def delete_note(self, note_id: int) -> bool:
        """Supprime une note via son ID. Retourne True si une suppression a eu lieu."""
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM author_notes WHERE id = ?", (note_id,))
        conn.commit()
        if cur.rowcount > 0:
            logger.info("[MEM:DELETE] note supprimee (id=%d)", note_id)
            return True
        return False

    # ─── Entités ───────────────────────────────────────────────────────────────

    def upsert_entity(self, entity_type: str, label: str, content: str) -> bool:
        """
        Ajoute une entité réelle (personne, lieu, événement) ou la met a jour si elle existe deja.

        Args:
            entity_type: "person", "place", "event" ou "other"
            label:       nom de l'entité (ex: "Marthe")
            content:     description (ex: "Sa mère, décédée en 2019")

        Returns:
            True si ajoutée ou mise a jour, False si doublon exact
        """
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT id, content FROM author_entities WHERE lower(trim(entity_type)) = lower(trim(?)) AND lower(trim(label)) = lower(trim(?))",
            (entity_type, label)
        ).fetchone()

        now = datetime.now().isoformat()
        
        if existing:
            old_content = existing["content"]
            if content.lower().strip() not in old_content.lower():
                new_content = old_content + " | " + content.strip()
                h = self._hash(f"{entity_type}:{label}:{new_content}")
                self._backup()
                conn.execute(
                    "UPDATE author_entities SET content = ?, content_hash = ?, updated_at = ? WHERE id = ?",
                    (new_content, h, now, existing["id"])
                )
                conn.commit()
                logger.info("[MEM:WRITE] entite mise a jour (type=%s label=%s) : %s", entity_type, label, new_content[:80])
                return True
            return False

        h = self._hash(f"{entity_type}:{label}:{content}")
        self._backup()
        conn.execute(
            "INSERT INTO author_entities (entity_type, label, content, content_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (entity_type, label.strip(), content.strip(), h, now, now),
        )
        conn.commit()
        logger.info("[MEM:WRITE] entite ajoutee (type=%s label=%s) : %s", entity_type, label, content[:80])
        return True

    def get_all_entities(self, entity_type: Optional[str] = None) -> list[dict]:
        """Retourne toutes les entités, optionnellement filtrées par type."""
        conn = self._get_conn()
        if entity_type:
            rows = conn.execute(
                "SELECT * FROM author_entities WHERE entity_type = ? ORDER BY label COLLATE NOCASE",
                (entity_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM author_entities ORDER BY entity_type, label COLLATE NOCASE"
            ).fetchall()
        logger.debug("[MEM:READ] get_all_entities(type=%s) -> %d entree(s)", entity_type or "*", len(rows))
        return [dict(r) for r in rows]

    def delete_entity(self, entity_id: int) -> bool:
        """Supprime une entite via son ID. Retourne True si une suppression a eu lieu."""
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM author_entities WHERE id = ?", (entity_id,))
        conn.commit()
        if cur.rowcount > 0:
            logger.info("[MEM:DELETE] entite supprimee (id=%d)", entity_id)
            return True
        return False

    def is_empty(self) -> bool:
        conn = self._get_conn()
        n_notes = conn.execute("SELECT COUNT(*) as n FROM author_notes").fetchone()["n"]
        n_ent = conn.execute("SELECT COUNT(*) as n FROM author_entities").fetchone()["n"]
        empty = n_notes == 0 and n_ent == 0
        logger.debug("[MEM:READ] is_empty -> %s (notes=%d, entites=%d)", empty, n_notes, n_ent)
        return empty

    # ─── Cycle de vie ──────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __repr__(self) -> str:
        conn = self._get_conn()
        n_notes = conn.execute("SELECT COUNT(*) as n FROM author_notes").fetchone()["n"]
        n_ent = conn.execute("SELECT COUNT(*) as n FROM author_entities").fetchone()["n"]
        return f"RelationalDB({self._db_path}, notes={n_notes}, entities={n_ent})"
