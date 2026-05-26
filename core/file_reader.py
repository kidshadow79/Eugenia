"""
file_reader.py — Lecture de fichiers pour injection dans la conversation.

Supporte :
- Texte brut : .txt, .md, .py, .json, .js/ts, .html/.css/.xml, .yaml,
               .csv, .log, .sql, .sh/.bat/.ps1, .c/.cpp/.h/.java/.cs,
               .go, .rs, .toml, .ini, .cfg, .conf, .rst
- Documents  : .docx (extraction paragraphes)
- Images     : .jpg, .jpeg, .png, .webp, .gif → base64 + mime type

Retourne un dict :
    {
        "type"    : "text" | "image",
        "content" : str,          # vide pour les images
        "filename": str,
        "mime"    : str | None,   # ex : "image/png"
        "b64"     : str | None,   # base64 brut (sans header data-URI)
    }
Retourne None si le fichier est introuvable, vide, ou d'un type non géré.
"""

import base64
import logging
import mimetypes
from pathlib import Path

logger = logging.getLogger(__name__)

_TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".pyw", ".json", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".htm", ".css", ".xml", ".yaml", ".yml", ".csv", ".log",
    ".sql", ".sh", ".bash", ".bat", ".cmd", ".ps1", ".c", ".cpp", ".h",
    ".hpp", ".java", ".cs", ".go", ".rs", ".rb", ".php", ".toml", ".ini",
    ".cfg", ".conf", ".rst", ".tex",
}

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def read_file_for_context(path: str | Path) -> dict | None:
    """
    Lit un fichier et retourne son contenu structuré.

    Args:
        path: chemin vers le fichier (str ou Path).

    Returns:
        dict avec les clés type/content/filename/mime/b64, ou None.
    """
    path = Path(path)
    if not path.exists() or not path.is_file():
        logger.warning("[FILE-READER] Fichier introuvable : %s", path)
        return None

    ext = path.suffix.lower()
    filename = path.name

    try:
        # ── Fichiers texte ─────────────────────────────────────────────────────
        if ext in _TEXT_EXTENSIONS:
            content = path.read_text(encoding="utf-8", errors="replace")
            if not content.strip():
                logger.warning("[FILE-READER] Fichier texte vide : %s", filename)
                return None
            logger.info("[FILE-READER] Texte lu (%d chars) : %s", len(content), filename)
            return {
                "type": "text",
                "content": content,
                "filename": filename,
                "mime": None,
                "b64": None,
            }

        # ── DOCX ───────────────────────────────────────────────────────────────
        if ext == ".docx":
            try:
                import docx  # type: ignore
            except ImportError:
                logger.error("[FILE-READER] python-docx non installé")
                return None
            doc = docx.Document(str(path))
            content = "\n".join(para.text for para in doc.paragraphs)
            if not content.strip():
                logger.warning("[FILE-READER] Document .docx vide : %s", filename)
                return None
            logger.info("[FILE-READER] DOCX lu (%d chars) : %s", len(content), filename)
            return {
                "type": "text",
                "content": content,
                "filename": filename,
                "mime": None,
                "b64": None,
            }

        # ── Images ─────────────────────────────────────────────────────────────
        if ext in _IMAGE_EXTENSIONS:
            data = path.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
            logger.info("[FILE-READER] Image lue (%d octets) : %s", len(data), filename)
            return {
                "type": "image",
                "content": "",
                "filename": filename,
                "mime": mime,
                "b64": b64,
            }

    except Exception as exc:
        logger.error("[FILE-READER] Erreur lecture %s : %s", path, exc)
        return None

    # Type non géré
    logger.warning("[FILE-READER] Extension non supportée : %s", ext)
    return None
