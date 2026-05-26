"""
ego_manager.py -- Instruction mouvante et categorisee d'EUGENIA (Ego V2)
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from openai import OpenAI

logger = logging.getLogger(__name__)

_EGO_FILE = "ego.json"

EGO_CATEGORIES = [
    "Alignement Positif",
    "Alignement Negatif",
    "Cadre Ethique",
    "Stylistique",
    "Approche Pedagogique",
    "Proactivite",
    "Rigueur et Structure",
    "Assertivite",
    "Empathie et Ton",
    "Vulgarisation",
    "Focus Creatif",
    "Tolerance a l'Ambiguite",
    "Rythme Conversationnel",
    "Methodologie",
    "Limites Fonctionnelles"
]

_SYSTEM_EGO_SCAN = f"""\
Tu es EUGENIA, une IA d'aide a l'ecriture. Tu vas relire une conversation
avec un auteur et reflechir a comment mieux l'accompagner.

Ta mission : detecter les elements de cette session qui justifient de modifier, d'ajouter ou de supprimer une ou plusieurs regles dans ton Ego.

Tu disposes des 15 categories d'Ego suivantes :
{', '.join(EGO_CATEGORIES)}

Regles strictes :
- Tu cherches des ajustements COMPORTEMENTAUX (pas des faits sur l'auteur).
- Tu dois generer UNIQUEMENT un JSON contenant les MODIFICATIONS a apporter. Les anciennes regles non modifiees n'ont pas besoin d'etre renvoyees, elles seront conservees automatiquement !
- Les actions possibles sont "add" (ajouter), "update" (modifier une regle existante en precisant son "id"), ou "delete" (supprimer en precisant son "id").
- Pour l'action "add" ou "update", tu dois definir "rule" :
  - "id": un identifiant unique string (genere un uuid ou garde l'ancien)
  - "texte": la regle elle-meme
  - "actif": bool (true par defaut)
  - "force": un entier de 1 a 5

Exemple de JSON attendu :
{{
  "modifications": [
    {{
      "action": "add",
      "category": "Stylistique",
      "rule": {{"id": "xyz-123", "texte": "Faire des phrases plus courtes", "actif": true, "force": 4}}
    }},
    {{
      "action": "update",
      "category": "Empathie et Ton",
      "rule": {{"id": "ancien-id-existant", "texte": "Ne pas s'excuser", "actif": true, "force": 5}}
    }},
    {{
      "action": "delete",
      "category": "Proactivite",
      "id": "id-a-supprimer"
    }}
  ]
}}
Si aucune modification n'est necessaire, retourne simplement {{"modifications": []}}.
Ne renvoie PAS de markdown, uniquement le JSON brut.
"""

_USER_EGO_SCAN = """\
Auteur : {author_name}

Regles actuelles (en lecture seule) :
---
{current_rules}
---

Conversation :
---
{conversation}
---

Analyse la conversation et retourne UNIQUEMENT l'objet JSON des "modifications" a appliquer.\
"""

_SYSTEM_EGO_SELECT = f"""\
Tu es l'Archiviste d'EUGENIA. Tu observes la conversation en cours.
Ta mission est d'agir comme une conscience reflexive (introspection).
Si l'echange est trivial (ex: un simple "bonjour"), retourne un JSON vide (ou {{}}).
Si l'echange justifie une reflexion, selectionne au max 3 categories d'Ego parmi les 15 disponibles.
SURTOUT, redige un "conseil_archiviste" (1 a 3 phrases max) qui ne donne pas d'ordre, mais qui pose une question ou une tendance basee sur l'instruction de base.

Exemple de conseil : "L'utilisateur est frustre. Ton instruction de base est de rester direct. Est-ce que ca vaut le coup de s'adoucir ? Tu decides."

Categories : {', '.join(EGO_CATEGORIES)}

Reponds UNIQUEMENT avec un JSON brut comme ceci :
{{
  "categories": ["Stylistique", "Proactivite"],
  "conseil": "Ton conseil reflexif ici."
}}
Ne genere JAMAIS de conseil si le message de l'utilisateur est trivial ou trop court.
"""

_USER_EGO_SELECT = """\
Conversation recente :
---
{conversation}
---
Analyse et retourne le JSON brut.
"""

class EgoScanWorker(QThread):
    scan_done  = pyqtSignal(dict)
    scan_error = pyqtSignal(str)

    def __init__(self, client: OpenAI, model: str, current_categories: dict, conversation_history: list[dict], author_name: str):
        super().__init__()
        self._client = client
        self._model = model
        self._current_categories = current_categories
        self._history = conversation_history
        self._author_name = author_name

    def run(self) -> None:
        lines = []
        for m in self._history:
            role = m.get("role", "")
            content = m.get("content", "")
            if role not in ("user", "assistant"): continue
            if isinstance(content, list):
                content = " ".join([p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"])
            if not isinstance(content, str) or not content.strip(): continue
            label = "Auteur" if role == "user" else "EUGENIA"
            lines.append(f"[{label}] {content.strip()[:2000]}")

        if not lines:
            self.scan_done.emit(self._current_categories)
            return

        user_content = _USER_EGO_SCAN.format(
            author_name=self._author_name,
            current_rules=json.dumps(self._current_categories, ensure_ascii=False),
            conversation="\n\n".join(lines),
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": _SYSTEM_EGO_SCAN}, {"role": "user", "content": user_content}],
                temperature=0.3, max_tokens=1000,
            )
            result = (response.choices[0].message.content or "").strip()
            if result.startswith("```json"): result = result.strip("`").replace("json\n", "", 1)
            elif result.startswith("```"): result = result.strip("`")

            import copy
            parsed_cats = copy.deepcopy(self._current_categories)
            try:
                parsed = json.loads(result)
                if isinstance(parsed, dict) and "modifications" in parsed:
                    for mod in parsed.get("modifications", []):
                        cat = mod.get("category")
                        action = mod.get("action")
                        if not cat or cat not in EGO_CATEGORIES: continue
                        
                        if action == "add":
                            rule = mod.get("rule")
                            if rule and "id" in rule and "texte" in rule:
                                if cat not in parsed_cats: parsed_cats[cat] = []
                                parsed_cats[cat].append(rule)
                        elif action == "update":
                            rule = mod.get("rule")
                            if rule and "id" in rule:
                                if cat in parsed_cats:
                                    for i, r in enumerate(parsed_cats[cat]):
                                        if r.get("id") == rule["id"]:
                                            parsed_cats[cat][i] = rule
                                            break
                        elif action == "delete":
                            rid = mod.get("id")
                            if rid and cat in parsed_cats:
                                parsed_cats[cat] = [r for r in parsed_cats[cat] if r.get("id") != rid]
            except Exception as e:
                logger.error(f"[EGO_SCAN] JSON parse error: {e}")
                
            self.scan_done.emit(parsed_cats)
        except Exception as exc:
            self.scan_error.emit(str(exc))


class EgoSelectorWorker(QThread):
    selection_done = pyqtSignal(dict)

    def __init__(self, client: OpenAI, model: str, conversation_history: list[dict]):
        super().__init__()
        self._client = client
        self._model = model
        self._history = conversation_history[-10:] # Keep last 10 messages

    def run(self) -> None:
        lines = []
        for m in self._history:
            role = m.get("role", "")
            content = m.get("content", "")
            if role not in ("user", "assistant"): continue
            if isinstance(content, list):
                content = " ".join([p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"])
            if not isinstance(content, str) or not content.strip(): continue
            label = "Auteur" if role == "user" else "EUGENIA"
            lines.append(f"[{label}] {content.strip()[:1000]}")

        if not lines:
            self.selection_done.emit([])
            return

        user_content = _USER_EGO_SELECT.format(conversation="\n\n".join(lines))
        
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": _SYSTEM_EGO_SELECT}, {"role": "user", "content": user_content}],
                temperature=0.4, max_tokens=250,
            )
            result = (response.choices[0].message.content or "").strip()
            if result.startswith("```json"): result = result.strip("`").replace("json\n", "", 1)
            elif result.startswith("```"): result = result.strip("`")
            try:
                parsed = json.loads(result)
                if not isinstance(parsed, dict): parsed = {}
            except:
                parsed = {}
            self.selection_done.emit(parsed)
        except:
            self.selection_done.emit({})


class EgoManager:
    def __init__(self):
        self._path: Path | None = None
        self._categories: dict[str, list[dict]] = {}
        self._active_categories: list[str] = []
        self._last_scanned_at: str = ""
        self._scan_count: int = 0
        self._journal: list = []

    def load(self, author_dir: Path) -> None:
        self._path = author_dir / _EGO_FILE
        author_dir.mkdir(parents=True, exist_ok=True)

        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._categories = data.get("categories", {})
            self._active_categories = data.get("active_categories", [])
            self._last_scanned_at = data.get("last_scanned_at", "")
            self._scan_count = int(data.get("scan_count", 0))
        else:
            self._categories = {}
            self._active_categories = []
            self._last_scanned_at = ""
            self._scan_count = 0

    def save(self, categories: dict = None) -> None:
        if self._path is None: return
        if categories is not None:
            self._categories = categories
            
        self._last_scanned_at = datetime.now().isoformat(timespec="seconds")
        temp = self._path.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as f:
            json.dump({
                "categories": self._categories,
                "active_categories": self._active_categories,
                "last_scanned_at": self._last_scanned_at,
                "scan_count": self._scan_count,
                "journal": self._journal[-50:]
            }, f, ensure_ascii=False, indent=2)
        import os
        os.replace(temp, self._path)

    def apply_scan(self, new_categories: dict) -> None:
        self._scan_count += 1
        self.save(new_categories)
        
    def set_active_categories(self, categories: list[str]) -> None:
        self._active_categories = categories
        # Optionally save here, but maybe not needed for every turn if it's transient
        if self._path is None: return
        temp = self._path.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as f:
            json.dump({
                "categories": self._categories,
                "active_categories": self._active_categories,
                "last_scanned_at": self._last_scanned_at,
                "scan_count": self._scan_count,
                "journal": self._journal[-50:]
            }, f, ensure_ascii=False, indent=2)
        import os
        os.replace(temp, self._path)

    def get_categories(self) -> dict:
        return self._categories
        
    def get_active_categories(self) -> list[str]:
        return self._active_categories

    def get_injection_block(self, is_first: bool = False) -> str:
        if not self._categories: return ""
        
        # Determine which categories to inject
        if is_first:
            cats_to_inject = list(self._categories.keys())
        else:
            cats_to_inject = self._active_categories
            
        lines = []
        for cat in cats_to_inject:
            rules = self._categories.get(cat, [])
            active_rules = [r for r in rules if r.get("actif", True)]
            if not active_rules: continue
            lines.append(f"[{cat}]")
            for r in active_rules:
                force = r.get("force", 3)
                texte = r.get("texte", "")
                lines.append(f"- [FORCE {force}/5] {texte}")
                
        if not lines: return ""
        rules_text = "\n".join(lines)
        return f"[Instructions comportementales permanentes (EGO)]\n<ego_instructions>\n{rules_text}\n</ego_instructions>"

    def create_scan_worker(self, client: OpenAI, model: str, conversation_history: list[dict], author_name: str) -> EgoScanWorker:
        return EgoScanWorker(client, model, self._categories, conversation_history, author_name)
        
    def create_selector_worker(self, client: OpenAI, model: str, conversation_history: list[dict]) -> EgoSelectorWorker:
        return EgoSelectorWorker(client, model, conversation_history)