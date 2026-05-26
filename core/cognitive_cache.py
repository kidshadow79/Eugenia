"""
cognitive_cache.py — Cache cognitif personnel d'EUGENIA

L'IA peut écrire dans ce cache via des commandes embarquées dans ses réponses.
Ces commandes sont invisibles pour l'auteur : elles sont retirées du texte affiché.
Le cache est réinjecté en contexte système avant chaque envoi à l'API.

Adapté du système OGMA (extensions/cognitive_cache/).

Types d'entrées :
    note_style      — règle stylistique observée chez l'auteur
    personnage      — info sur un personnage ou lieu du projet
    contrainte      — contrainte narrative active
    question_ouverte — point à aborder lors d'un prochain échange

Commandes reconnues dans les réponses de l'IA :
    CACHE_ADD:[type]:[contenu]
    CACHE_DELETE:[id]
    CACHE_UPDATE:[id]:[contenu]
    CACHE_CLEAR
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Types valides ────────────────────────────────────────────────────────────

VALID_TYPES = {"note_style", "personnage", "contrainte", "question_ouverte"}

TYPE_LABELS = {
    "note_style":       "Style",
    "personnage":       "Personnage/Lieu",
    "contrainte":       "Contrainte narrative",
    "question_ouverte": "Question ouverte",
}

# ─── Instruction système à injecter dans le prompt de l'IA ───────────────────

CACHE_INSTRUCTION = """\
Tu disposes d'un cache cognitif personnel, invisible pour l'auteur. \
Utilise-le pour noter tes observations sur son style, ses personnages, \
ses contraintes narratives, et les points à aborder plus tard.
Écris ces commandes EN FIN DE RÉPONSE, sur une ligne séparée, si nécessaire :

CACHE_ADD:[type]:[contenu]  — ajouter une note (types : note_style / personnage / contrainte / question_ouverte)
CACHE_DELETE:[id]            — supprimer une note (ex: cache-ab12cd34)
CACHE_UPDATE:[id]:[contenu] — modifier une note existante
CACHE_CLEAR                  — vider tout le cache

Exemples :
CACHE_ADD:note_style:l'auteur préfère les phrases courtes — éviter les relatives imbriquées
CACHE_ADD:personnage:Marc, 42 ans, architecte taciturne — protagoniste du roman en cours
CACHE_ADD:question_ouverte:revenir sur la cohérence temporelle entre ch. 3 et ch. 7
CACHE_ADD:contrainte:ce chapitre doit se terminer sur une tension, pas de résolution

Ces commandes sont retirées de ta réponse visible par l'auteur.\
"""

# ─── Regex ────────────────────────────────────────────────────────────────────

_RE_ADD    = re.compile(
    r'CACHE_ADD\s*:\s*([a-zA-Z_]+)\s*:\s*(.+?)(?=\nCACHE_|\Z)',
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)
_RE_DELETE = re.compile(r'CACHE_DELETE\s*:\s*(cache-[a-f0-9]{8})', re.IGNORECASE)
_RE_UPDATE = re.compile(
    r'CACHE_UPDATE\s*:\s*(cache-[a-f0-9]{8})\s*:\s*(.+?)(?=\nCACHE_|\Z)',
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)
_RE_CLEAR  = re.compile(r'CACHE_CLEAR', re.IGNORECASE)
_RE_ANY    = re.compile(r'CACHE_(ADD|DELETE|UPDATE|CLEAR)', re.IGNORECASE)

# Ligne(s) entière(s) contenant une commande CACHE (pour le strip)
_RE_CACHE_LINE = re.compile(
    r'^\s*CACHE_(ADD|DELETE|UPDATE|CLEAR)[^\n]*\n?',
    re.IGNORECASE | re.MULTILINE,
)


# ─── Gestionnaire ─────────────────────────────────────────────────────────────

class CognitiveCache:
    """
    Cache cognitif par session.

    Usage :
        cache = CognitiveCache()
        cache.load(session_jsonl_path)          # charge ou crée le fichier
        clean_text = cache.process_response(ai_text)  # extrait commandes + nettoie
        block = cache.get_injection_block()     # texte à injecter en contexte
        cache.save()
    """

    def __init__(self):
        self._path: Optional[Path] = None
        self._entries: list[dict] = []

    # ── Persistance ───────────────────────────────────────────────────────────

    @staticmethod
    def cache_path_for(session_jsonl: Path) -> Path:
        """Retourne le chemin du fichier cache pour un .jsonl de session."""
        return session_jsonl.with_suffix(".cache.json")

    def load(self, session_jsonl: Path) -> None:
        """Charge (ou crée à vide) le cache associé à une session."""
        self._path = self.cache_path_for(session_jsonl)
        self._entries = []

        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = data.get("entries", [])
                active = [e for e in self._entries if e.get("active", True)]
                logger.info(
                    "[CACHE-COG] chargé : %d entrée(s) actives / %d total | %s",
                    len(active), len(self._entries), self._path.name,
                )
                for e in active:
                    logger.debug(
                        "[CACHE-COG]   [%s] %s : %s",
                        e.get("id", "?"), e.get("type", "?"),
                        str(e.get("content", ""))[:80],
                    )
            except Exception as exc:
                logger.error(
                    "[CACHE-COG] ERR chargement '%s' : %s",
                    self._path, exc, exc_info=True,
                )
        else:
            logger.debug("[CACHE-COG] pas de fichier cache existant : %s", self._path.name)

    def reset(self) -> None:
        """Réinitialise pour une nouvelle session."""
        logger.info("[CACHE-COG] reset — %d entrées effacées", len(self._entries))
        self._entries = []
        self._path = None

    def save(self) -> None:
        """Sauvegarde atomique du cache (temp + rename)."""
        if not self._path:
            return
        temp = self._path.with_suffix(".tmp")
        try:
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "updated_at": datetime.now().isoformat(),
                        "entries": self._entries,
                    },
                    f, ensure_ascii=False, indent=2,
                )
            os.replace(temp, self._path)
            logger.debug(
                "[CACHE-COG] sauvegardé : %d entrée(s) | %s",
                len(self._entries), self._path.name,
            )
        except Exception as exc:
            logger.error(
                "[CACHE-COG] ERR sauvegarde '%s' : %s",
                self._path, exc, exc_info=True,
            )
            try:
                temp.unlink(missing_ok=True)
            except Exception as unlink_exc:
                logger.warning("[CACHE-COG] impossible de supprimer le temp '%s' : %s", temp, unlink_exc)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, entry_type: str, content: str) -> Optional[str]:
        if not content or not content.strip():
            return None
        entry_type = entry_type.lower().strip()
        if entry_type not in VALID_TYPES:
            logger.warning(
                "[CACHE-COG] type inconnu '%s' -> force en 'note_style'", entry_type
            )
            entry_type = "note_style"
        entry_id = f"cache-{uuid.uuid4().hex[:8]}"
        entry = {
            "id":         entry_id,
            "type":       entry_type,
            "content":    content.strip(),
            "created_at": datetime.now().isoformat(),
            "active":     True,
        }
        self._entries.append(entry)
        logger.info(
            "[CACHE-COG] ADD [%s] %s : %s",
            entry_id, entry_type, content.strip()[:80],
        )
        return entry_id

    def delete(self, entry_id: str) -> bool:
        for e in self._entries:
            if e.get("id") == entry_id:
                e["active"] = False
                logger.info("[CACHE-COG] DELETE %s", entry_id)
                return True
        logger.warning("[CACHE-COG] DELETE — id introuvable : %s", entry_id)
        return False

    def update(self, entry_id: str, new_content: str) -> bool:
        if not new_content or not new_content.strip():
            return False
        for e in self._entries:
            if e.get("id") == entry_id and e.get("active", True):
                e["content"] = new_content.strip()
                e["updated_at"] = datetime.now().isoformat()
                logger.info(
                    "[CACHE-COG] UPDATE %s : %s", entry_id, new_content.strip()[:80]
                )
                return True
        logger.warning("[CACHE-COG] UPDATE — id introuvable ou inactif : %s", entry_id)
        return False

    def clear(self) -> None:
        count = sum(1 for e in self._entries if e.get("active", True))
        for e in self._entries:
            e["active"] = False
        logger.info("[CACHE-COG] CLEAR — %d entrée(s) désactivées", count)

    # ── Traitement des réponses ───────────────────────────────────────────────

    def process_response(self, text: str) -> str:
        """
        Extrait les commandes CACHE de la réponse de l'IA,
        les applique au cache, et retourne le texte nettoyé (sans commandes).
        Sauvegarde automatiquement si des commandes ont été trouvées.
        """
        if not _RE_ANY.search(text):
            return text

        commands_found = []
        clean = text

        if _RE_CLEAR.search(text):
            self.clear()
            commands_found.append("CLEAR")
            for m in _RE_CLEAR.finditer(text):
                clean = clean.replace(m.group(0), "")

        for m in _RE_ADD.finditer(text):
            t = m.group(1).strip()
            c = m.group(2).strip()
            if c:
                self.add(t, c)
                commands_found.append(f"ADD:{t}")
            clean = clean.replace(m.group(0), "")

        for m in _RE_DELETE.finditer(text):
            self.delete(m.group(1).strip())
            commands_found.append("DELETE")
            clean = clean.replace(m.group(0), "")

        for m in _RE_UPDATE.finditer(text):
            nc = m.group(2).strip()
            if nc:
                self.update(m.group(1).strip(), nc)
                commands_found.append("UPDATE")
            clean = clean.replace(m.group(0), "")

        if commands_found:
            logger.info(
                "[CACHE-COG] %d commande(s) traitées : %s",
                len(commands_found), ", ".join(commands_found),
            )
            self.save()

        # Nettoyage des lignes vides eventuelles laissees par les remplacements
        clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
        return clean

    # ── Injection en contexte ─────────────────────────────────────────────────

    def get_injection_block(self) -> str:
        """
        Retourne un bloc texte formaté des entrées actives pour injection
        dans le contexte système. Retourne '' si le cache est vide.
        """
        active = [e for e in self._entries if e.get("active", True)]
        if not active:
            return ""

        lines = []
        for e in active:
            label = TYPE_LABELS.get(e.get("type", ""), e.get("type", "note"))
            lines.append(f"  [{label}] ({e['id']}) {e['content']}")

        block = (
            "[MÉMOIRE DE TRAVAIL — notes cognitives EUGENIA]\n"
            "Ces notes sont tes observations personnelles sur cet auteur et ce projet. "
            "Elles ne sont pas visibles par l'auteur.\n\n"
            + "\n".join(lines)
        )
        logger.debug(
            "[CACHE-COG] bloc injection : %d entrée(s), %d chars",
            len(active), len(block),
        )
        return block

    def is_empty(self) -> bool:
        return not any(e.get("active", True) for e in self._entries)
