"""
bio_activation.py — Injection contextuelle ciblee de la biographie auteur

Workflow par message :
    1er message de session → TOUS les groupes (portrait de depart complet)
    Messages suivants      → Archiviste selectionne 0-3 groupes pertinents

Signaux :
    injection_ready(str)  → texte formate a injecter via engine.inject_context_note()
                            Chaine vide si rien a injecter.

Usage :
    bio = BioActivation(archiviste_config, bio_path, author_name)
    bio.injection_ready.connect(on_injection)
    bio.activate(user_message)   # a appeler avant engine.send()
    # en debut de session :
    bio.reset_session()
"""

import json
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from openai import OpenAI

logger = logging.getLogger(__name__)

_BIO_FILE = "author_bio_compiled.json"

_SYSTEM_SELECTION = (
    "Tu es un archiviste memoire. Selectionne les groupes biographiques "
    "pertinents pour le message fourni, et detecte si le message contient "
    "une information sur l'auteur a memoriser. "
    "Reponds UNIQUEMENT en JSON strict, sans texte avant ni apres."
)

_USER_SELECTION = """\
Message de l'auteur : "{message}"

Catalogue des groupes disponibles :
{catalog}

Selectionne 0 a 3 groupes biographiques pertinents pour ce message.
Detecte aussi si le message contient une information sur l'AUTEUR LUI-MEME a memoriser.

Regles groupes :
- Message neutre, salutation, remerciement, ponctuation seule -> 0 groupe
- Message ou l'auteur parle de lui-meme, de ses habitudes, gouts -> 1-2 groupes
- Message impliquant une personne reelle, un lieu ou un evenement connu -> 1-2 groupes
- Jamais plus de 3 groupes

Regles memorisation (champ mem) :
- null si rien a memoriser (question sur le roman, instruction de redaction, phrase neutre)
- Formuler en 1 phrase concise si l'auteur revele une habitude, preference, fait biographique, ou mentionne une personne/lieu reel
- NE PAS memoriser ce qui concerne les personnages fictifs, l'intrigue, ou le roman

Format JSON strict :
{{"groups": ["GROUPE1"], "reasoning": "justification courte", "mem": null}}
ou si memorisation pertinente :
{{"groups": [], "reasoning": "...", "mem": "L'auteur prefere les dialogues courts"}}"""


# ─── Worker ───────────────────────────────────────────────────────────────────

class _BioSelectionWorker(QThread):
    """Thread : selectionne les groupes et retourne le texte d'injection formate."""

    injection_ready = pyqtSignal(str)
    mem_detected    = pyqtSignal(str)   # contenu a memoriser (chaine non vide si detecte)

    def __init__(
        self,
        message: str,
        bio_path: Path,
        client: OpenAI,
        model: str,
        is_first: bool,
        author_name: str,
    ):
        super().__init__()
        self._message     = message
        self._bio_path    = bio_path
        self._client      = client
        self._model       = model
        self._is_first    = is_first
        self._author_name = author_name

    def run(self) -> None:
        if not self._bio_path.exists():
            logger.debug("BioSelectionWorker — bio_compiled absent, skip")
            self.injection_ready.emit("")
            return

        try:
            with open(self._bio_path, "r", encoding="utf-8") as f:
                bio_data = json.load(f)
        except Exception as exc:
            logger.warning("BioSelectionWorker — lecture echouee : %s", exc)
            self.injection_ready.emit("")
            return

        groups = bio_data.get("groups", {})
        if not groups:
            self.injection_ready.emit("")
            return

        if self._is_first:
            selected = list(groups.keys())
            logger.info("[BIO:SELECT] premier message -> tous les groupes (%d) : %s",
                        len(selected), selected)
        else:
            selected, mem_content = self._select_via_archiviste(groups)
            if selected:
                logger.info("[BIO:SELECT] Archiviste -> groupes retenus : %s", selected)
            else:
                logger.debug("[BIO:SELECT] Archiviste -> 0 groupe (message neutre)")
            if mem_content:
                logger.info("[MEM:LIVE] information auteur detectee : %s", mem_content[:80])
                self.mem_detected.emit(mem_content)

        injection = self._format_injection(groups, selected)
        self.injection_ready.emit(injection)

    # ── Selection via Archiviste ───────────────────────────────────────────────

    def _select_via_archiviste(self, groups: dict) -> tuple[list[str], str | None]:
        """Retourne (groupes_selectionnes, contenu_a_memoriser_ou_None).
        [MODIFIE] Utilise desormais une selection locale par mots-cles (rapide)
        au lieu d'un appel API, pour eliminer la latence UX.
        """
        import re
        message_lower = self._message.lower()
        words = set(re.findall(r'\w+', message_lower))
        
        scores = {}
        for name, data in groups.items():
            score = 0
            keywords = data.get("keywords", [])
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in words:
                    score += 2
                elif kw_lower in message_lower:
                    score += 1
            if score > 0:
                scores[name] = score
                
        # Trier par score decroissant, limiter a 3
        sorted_groups = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = [g for g, s in sorted_groups[:3]]
        
        logger.debug("BioSelectionWorker — selection locale rapide : %s", selected)
        return selected, None

    # ── Formatage ─────────────────────────────────────────────────────────────

    def _format_injection(self, groups: dict, selected: list[str]) -> str:
        if not selected:
            return ""

        parts: list[str] = []
        seen:  set[str]  = set()

        for gname in selected:
            gdata = groups.get(gname)
            if not gdata:
                continue
            lines = []
            for fact in gdata.get("facts", []):
                content = fact.get("content", "")
                if content and content not in seen:
                    seen.add(content)
                    lines.append(f"- {content}")
            if lines:
                parts.append(f"[{gname}]\n" + "\n".join(lines))

        if not parts:
            return ""

        result = (
            f"[VOIX DE L'ARCHIVISTE - MÉMOIRE RELATIONNELLE]\n"
            f"Voici ce que nous savons sur l'auteur ({self._author_name}) dans le monde réel (hors fiction) :\n"
            + "\n".join(parts)
            + "\n(Utilise ces informations pour nuancer ta réponse si pertinent, mais ne les cite pas artificiellement.)\n"
        )
        logger.info(
            "[BIO:INJECT] %d groupe(s) injecte(s) (%d faits, ~%d tokens) : %s",
            len(selected), len(seen), len(result) // 4, selected,
        )
        return result


# ─── Gestionnaire public ──────────────────────────────────────────────────────

class BioActivation(QObject):
    """
    Gestionnaire d'activation biographique contextuelle.

    Instancier avec la config Archiviste (api_key, base_url, model).
    Appeler activate(message) avant engine.send() pour obtenir l'injection.
    Appeler reset_session() au debut d'une nouvelle session.

    Signal injection_ready(str) emis des que l'injection est prete.
    Chaine vide = rien a injecter.
    """

    injection_ready  = pyqtSignal(str)
    memorize_detected = pyqtSignal(str)   # information auteur a memoriser (non vide)

    def __init__(
        self,
        config: dict,
        bio_path: Path,
        author_name: str,
        parent=None,
    ):
        super().__init__(parent)
        api_key_val = config.get("api_key", "")
        self._client = OpenAI(
            api_key=api_key_val.strip() if api_key_val else "",
            base_url=config.get("base_url") or None,
            default_headers=config.get("extra_headers") or None,
        )
        self._model       = config.get("model", "gpt-4o-mini")
        self._bio_path    = bio_path
        self._author_name = author_name
        self._is_first    = True
        self._worker: _BioSelectionWorker | None = None

    def activate(self, message: str) -> None:
        """Lance la selection asynchrone des groupes bio pour ce message."""
        if self._worker and self._worker.isRunning():
            logger.debug("BioActivation — worker occupe, rien injecte")
            self.injection_ready.emit("")
            return

        self._worker = _BioSelectionWorker(
            message=message,
            bio_path=self._bio_path,
            client=self._client,
            model=self._model,
            is_first=self._is_first,
            author_name=self._author_name,
        )
        self._worker.injection_ready.connect(self._on_worker_done)
        self._worker.mem_detected.connect(self.memorize_detected)
        self._worker.start()

    def reset_session(self) -> None:
        """Remet le flag premier-message a True (nouvelle session)."""
        self._is_first = True

    def update_config(self, config: dict) -> None:
        """Met a jour la config API (apres sauvegarde Parametres)."""
        self._model = config.get("model", "gpt-4o-mini")
        api_key_val = config.get("api_key", "")
        self._client = OpenAI(
            api_key=api_key_val.strip() if api_key_val else "",
            base_url=config.get("base_url") or None,
            default_headers=config.get("extra_headers") or None,
        )

    def _on_worker_done(self, injection: str) -> None:
        self._is_first = False
        self.injection_ready.emit(injection)
