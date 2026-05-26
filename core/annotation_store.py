"""
annotation_store.py — Persistance des annotations Ghost Writer

Une annotation = un badge visible dans le calque transparent par-dessus l'éditeur tiers.
Elle est ancrée dans le texte via une suite de mots (n-gramme) extraite du document.

Chemin de la base : data/projects/{slug}/memory_work/annotations.db

Structure d'une annotation :
    id          — identifiant unique
    document    — chemin ou nom du fichier annoté (ex: "chapitre_1.docx")
    anchor      — suite de 6-8 mots du texte, sert de clé de localisation OCR
    label       — texte court affiché dans le badge (marge du calque)
    note        — texte complet affiché dans le tooltip au survol
    created_at  — horodatage ISO

Usage :
    store = AnnotationStore(project_dir)
    store.add("chapitre_1.docx", "le soir tomba sur la colline sombre", "⚠ Jacques", "Yeux bleus au chap.1, verts ici")
    annotations = store.get_for_document("chapitre_1.docx")
    store.delete(annotation_id)
    store.close()
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS annotations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document    TEXT    NOT NULL,
    anchor      TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    note        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_annotations_document ON annotations(document);
"""


class Annotation(NamedTuple):
    id: int
    document: str
    anchor: str
    label: str
    note: str
    created_at: str


class AnnotationStore:
    """
    Accès SQLite aux annotations Ghost Writer d'un projet.
    Une instance par projet — ouvrir/fermer autour de la session.
    """

    def __init__(self, project_dir: Path) -> None:
        """
        Args:
            project_dir : dossier racine du projet, ex: data/projects/mon-roman/
                          La base sera dans project_dir/memory_work/annotations.db
        """
        work_dir = project_dir / "memory_work"
        work_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = work_dir / "annotations.db"
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    # ─── Connexion ─────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        self._get_conn().executescript(_CREATE_SQL)
        self._get_conn().commit()

    # ─── Écriture ──────────────────────────────────────────────────────────────

    def add(self, document: str, anchor: str, label: str, note: str) -> Annotation:
        """
        Crée une nouvelle annotation et la persiste.

        Args:
            document : nom ou chemin du fichier annoté
            anchor   : suite de mots du texte (6-8 mots recommandés)
            label    : texte court pour le badge (ex: "⚠ Jacques")
            note     : texte complet du tooltip

        Returns:
            L'annotation créée avec son id.

        Raises:
            ValueError : si anchor, label ou note est vide.
        """
        if not anchor.strip():
            raise ValueError("AnnotationStore.add : anchor ne peut pas être vide")
        if not label.strip():
            raise ValueError("AnnotationStore.add : label ne peut pas être vide")
        if not note.strip():
            raise ValueError("AnnotationStore.add : note ne peut pas être vide")
        if not document.strip():
            raise ValueError("AnnotationStore.add : document ne peut pas être vide")

        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO annotations (document, anchor, label, note, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (document.strip(), anchor.strip(), label.strip(), note.strip(), now),
        )
        conn.commit()
        return Annotation(
            id=cur.lastrowid,
            document=document.strip(),
            anchor=anchor.strip(),
            label=label.strip(),
            note=note.strip(),
            created_at=now,
        )

    def update_note(self, annotation_id: int, label: str, note: str) -> None:
        """
        Met à jour le label et la note d'une annotation existante.

        Raises:
            KeyError : si l'id n'existe pas.
        """
        if not label.strip():
            raise ValueError("AnnotationStore.update_note : label ne peut pas être vide")
        if not note.strip():
            raise ValueError("AnnotationStore.update_note : note ne peut pas être vide")

        conn = self._get_conn()
        cur = conn.execute(
            "UPDATE annotations SET label = ?, note = ? WHERE id = ?",
            (label.strip(), note.strip(), annotation_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise KeyError(f"AnnotationStore.update_note : id {annotation_id} introuvable")

    def delete(self, annotation_id: int) -> None:
        """
        Supprime une annotation par son id.

        Raises:
            KeyError : si l'id n'existe pas.
        """
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise KeyError(f"AnnotationStore.delete : id {annotation_id} introuvable")

    def delete_for_document(self, document: str) -> int:
        """
        Supprime toutes les annotations d'un document.

        Returns:
            Nombre d'annotations supprimées.
        """
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM annotations WHERE document = ?", (document,))
        conn.commit()
        return cur.rowcount

    # ─── Lecture ───────────────────────────────────────────────────────────────

    def get(self, annotation_id: int) -> Annotation:
        """
        Retourne une annotation par son id.

        Raises:
            KeyError : si l'id n'existe pas.
        """
        row = self._get_conn().execute(
            "SELECT * FROM annotations WHERE id = ?", (annotation_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"AnnotationStore.get : id {annotation_id} introuvable")
        return Annotation(**dict(row))

    def get_for_document(self, document: str) -> list[Annotation]:
        """
        Retourne toutes les annotations d'un document, triées par created_at.
        Retourne une liste vide si aucune annotation n'existe pour ce document.
        """
        rows = self._get_conn().execute(
            "SELECT * FROM annotations WHERE document = ? ORDER BY created_at",
            (document,),
        ).fetchall()
        return [Annotation(**dict(r)) for r in rows]

    def get_all(self) -> list[Annotation]:
        """Retourne toutes les annotations du projet, tous documents confondus."""
        rows = self._get_conn().execute(
            "SELECT * FROM annotations ORDER BY document, created_at"
        ).fetchall()
        return [Annotation(**dict(r)) for r in rows]

    # ─── Fermeture ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Ferme la connexion SQLite proprement."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
