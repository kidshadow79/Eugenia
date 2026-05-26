"""
bible_db.py — Mémoire de travail SQLite par projet (Bible)

Gère les 5 tables narratives :
    - characters    (personnages)
    - places        (lieux)
    - events        (événements / chronologie)
    - decisions     (décisions d'auteur)
    - contradictions (contradictions détectées)

Chaque table a la même structure de base :
    id, label, content, source_chunk_id, created_at, updated_at

Sécurité : backup automatique avant toute écriture (rotation 4 fichiers).
Chemin : data/projects/{slug}/memory_work/bible.db

Usage :
    db = BibleDB(project_dir)
    db.upsert("characters", "Elara", "Elfe de 300 ans, cicatrice sur l'œil gauche", "chunk-uuid")
    rows = db.get_all("characters")
    db.close()
"""

import json
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
import re

# Nombre maximal de backups conservés en rotation
_MAX_BACKUPS = 4

# Tables par défaut (rétrocompatibilité avec les projets anciens)
TABLES = ("characters", "places", "events", "decisions", "contradictions")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    label        TEXT NOT NULL,
    content      TEXT NOT NULL,
    source_chunk TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{table}_label ON {table}(label);
"""


class BibleDB:
    """Accès SQLite à la Bible d'un projet. Thread-safety : utiliser une instance par thread."""

    def __init__(self, project_dir: Path,
                 tables: tuple[str, ...] | None = None):
        """
        Args:
            project_dir : dossier du projet, ex: data/projects/mon-roman/
                          La base sera dans project_dir/memory_work/bible.db
            tables      : tuple des noms de tables à gérer.
                          Si None → lit project.json pour récupérer "categories".
                          Fallback sur TABLES si project.json est absent.
        """
        self._work_dir = project_dir / "memory_work"
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._work_dir / "bible.db"
        self._conn: Optional[sqlite3.Connection] = None

        if tables is not None:
            raw_tables = tuple(tables)
        else:
            raw_tables = self._load_tables_from_project(project_dir)

        valid_tables = []
        for t in raw_tables:
            if not re.match(r"^[a-zA-Z0-9_]+$", t):
                raise ValueError(f"Nom de table invalide (SQL injection guard) : {t}")
            valid_tables.append(t)
        self._tables = tuple(valid_tables)

        self._init_db()

    @staticmethod
    def _load_tables_from_project(project_dir: Path) -> tuple[str, ...]:
        """Lit les catégories dans project.json. Fallback sur TABLES."""
        json_path = project_dir / "project.json"
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cats = data.get("categories")
                if cats and isinstance(cats, list):
                    return tuple(cats)
            except (json.JSONDecodeError, OSError):
                pass
        return TABLES

    # ─── Initialisation ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Crée toutes les tables si elles n'existent pas."""
        conn = self._get_conn()
        for table in self._tables:
            sql = _CREATE_TABLE_SQL.format(table=table)
            conn.executescript(sql)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Retourne la connexion persistante (crée si nécessaire)."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=5.0)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    # ─── Backup ────────────────────────────────────────────────────────────────

    def _backup(self) -> None:
        """
        Sauvegarde la base avant une écriture.
        Rotation : on garde les 4 derniers backups.
        Nommage : bible.db.bak1 (le plus récent) → bible.db.bak4 (le plus vieux)
        """
        if not self._db_path.exists():
            return

        # Rotation : bak3→bak4, bak2→bak3, bak1→bak2
        for i in range(_MAX_BACKUPS - 1, 0, -1):
            src = self._work_dir / f"bible.db.bak{i}"
            dst = self._work_dir / f"bible.db.bak{i + 1}"
            if src.exists():
                shutil.copy2(src, dst)

        # Copier la base courante → bak1 via VACUUM INTO pour eviter les corruptions
        bak1_path = self._work_dir / "bible.db.bak1"
        if bak1_path.exists():
            bak1_path.unlink()
        try:
            conn = self._get_conn()
            conn.execute(f"VACUUM INTO '{bak1_path}'")
        except Exception:
            if self._db_path.exists():
                shutil.copy2(self._db_path, bak1_path)

    # ─── CRUD ──────────────────────────────────────────────────────────────────

    def upsert(self, table: str, label: str, content: str,
               source_chunk: Optional[str] = None) -> int:
        """
        Insère ou met à jour une entrée (clé = label).
        Si un enregistrement avec le même label existe → UPDATE content + updated_at.
        Sinon → INSERT.

        Returns:
            id de la ligne insérée ou mise à jour.
        """
        if table not in self._tables:
            raise ValueError(f"Table inconnue : {table!r}. Tables valides : {self._tables}")

        self._backup()
        conn = self._get_conn()
        now = datetime.now().isoformat()

        # Normalisation du label pour la recherche d'existence (insensible à la casse)
        existing = conn.execute(
            f"SELECT id FROM {table} WHERE lower(trim(label)) = lower(trim(?))", (label,)
        ).fetchone()

        if existing:
            conn.execute(
                f"UPDATE {table} SET content=?, source_chunk=?, updated_at=? WHERE id=?",
                (content, source_chunk, now, existing["id"]),
            )
            conn.commit()
            return existing["id"]
        else:
            cursor = conn.execute(
                f"INSERT INTO {table} (label, content, source_chunk, created_at, updated_at) "
                f"VALUES (?, ?, ?, ?, ?)",
                (label, content, source_chunk, now, now),
            )
            conn.commit()
            return cursor.lastrowid

    def get_all(self, table: str) -> list[dict]:
        """Retourne toutes les entrées d'une table, triées par label."""
        if table not in self._tables:
            raise ValueError(f"Table inconnue : {table!r}")
        conn = self._get_conn()
        rows = conn.execute(
            f"SELECT * FROM {table} ORDER BY label COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_label(self, table: str, label: str) -> Optional[dict]:
        """Retourne une entrée par son label exact (insensible à la casse)."""
        if table not in self._tables:
            raise ValueError(f"Table inconnue : {table!r}")
        conn = self._get_conn()
        row = conn.execute(
            f"SELECT * FROM {table} WHERE label = ? COLLATE NOCASE", (label,)
        ).fetchone()
        return dict(row) if row else None

    def search(self, table: str, query: str) -> list[dict]:
        """Recherche par texte (label OU content) — LIKE insensible à la casse."""
        if table not in self._tables:
            raise ValueError(f"Table inconnue : {table!r}")
        conn = self._get_conn()
        pattern = f"%{query}%"
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE label LIKE ? OR content LIKE ? "
            f"ORDER BY label COLLATE NOCASE",
            (pattern, pattern),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, table: str, label: str) -> bool:
        """Supprime une entrée par son label. Retourne True si supprimée."""
        if table not in self._tables:
            raise ValueError(f"Table inconnue : {table!r}")
        self._backup()
        conn = self._get_conn()
        cursor = conn.execute(f"DELETE FROM {table} WHERE label = ? COLLATE NOCASE", (label,))
        conn.commit()
        return cursor.rowcount > 0

    def get_all_tables(self) -> list[dict]:
        """
        Retourne toutes les entrees de toutes les tables, chacune enrichie
        du champ 'table' indiquant sa provenance.

        Usage : pour vectoriser la Bible entiere dans FAISS.
        """
        all_entries = []
        for table in self._tables:
            for row in self.get_all(table):
                entry = dict(row)
                entry["table"] = table
                all_entries.append(entry)
        return all_entries

    def get_labels_for_source_chunks(self, chunk_ids: list[str]) -> set[str]:
        """
        Retourne l'ensemble des labels (Bible) issus des chunk_ids fournis.
        Utilise pour filtrer les hits FAISS Bible quand une source est en sourdine.
        """
        if not chunk_ids:
            return set()
        conn = self._get_conn()
        labels: set[str] = set()
        
        for i in range(0, len(chunk_ids), 999):
            batch = chunk_ids[i:i+999]
            placeholders = ",".join("?" * len(batch))
            for table in self._tables:
                cursor = conn.execute(
                    f"SELECT label FROM {table} WHERE source_chunk IN ({placeholders})",
                    batch,
                )
                labels.update(row[0] for row in cursor.fetchall())
        return labels

    def delete_by_source_chunks(self, chunk_ids: list[str]) -> int:
        """
        Supprime toutes les entrees de toutes les tables dont source_chunk
        est dans la liste fournie.

        Args:
            chunk_ids: liste de valeurs source_chunk (ex: ['chunk-0', 'chunk-1', ...])

        Returns:
            Nombre total de lignes supprimees.
        """
        if not chunk_ids:
            return 0
        self._backup()
        conn = self._get_conn()
        total = 0
        for i in range(0, len(chunk_ids), 999):
            batch = chunk_ids[i:i+999]
            placeholders = ",".join("?" * len(batch))
            for table in self._tables:
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE source_chunk IN ({placeholders})",
                    batch,
                )
                total += cursor.rowcount
        conn.commit()
        return total

    def count(self, table: str) -> int:
        """Nombre d'entrées dans une table."""
        if table not in self._tables:
            raise ValueError(f"Table inconnue : {table!r}")
        conn = self._get_conn()
        row = conn.execute(f"SELECT COUNT(*) as n FROM {table}").fetchone()
        return row["n"]

    def is_empty(self) -> bool:
        """True si toutes les tables sont vides (aucune Bible construite)."""
        return all(self.count(t) == 0 for t in self._tables)

    # ─── Cycle de vie ──────────────────────────────────────────────────────────

    def close(self) -> None:
        """Ferme la connexion SQLite."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __repr__(self) -> str:
        counts = {t: self.count(t) for t in self._tables}
        return f"BibleDB({self._db_path}, {counts})"
