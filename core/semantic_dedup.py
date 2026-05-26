import json
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from openai import OpenAI
from core.relational_db import RelationalDB

logger = logging.getLogger(__name__)

_SYSTEM_EGO_DEDUP = """\
Tu es l'Archiviste d'EUGENIA. Tu vas recevoir un tableau JSON contenant les règles de comportement (Ego) actuelles pour une catégorie donnée.
Ta mission est d'identifier les règles SÉMANTIQUEMENT REDONDANTES (celles qui expriment exactement la même idée ou contrainte avec des mots différents).

Règles de déduplication :
1. Si plusieurs règles expriment la même idée, conserve uniquement la plus forte (force la plus élevée) ou la mieux formulée, et supprime les autres.
2. Si une règle est unique, conserve-la telle quelle.
3. Ne crée AUCUNE nouvelle règle. Ne fais que supprimer les doublons.
4. Retourne UNIQUEMENT un tableau JSON (sans markdown, sans blabla) avec la liste finale épurée. Ne renvoie PAS d'objet, mais bien une liste: `[ { "id": "...", "texte": "...", "actif": true, "force": 3 }, ... ]`
"""

class EgoDedupWorker(QThread):
    """
    Parcourt chaque catégorie d'Ego et demande au LLM de supprimer les redondances sémantiques.
    """
    dedup_done = pyqtSignal(dict)
    dedup_error = pyqtSignal(str)

    def __init__(self, client: OpenAI, model: str, current_categories: dict):
        super().__init__()
        self._client = client
        self._model = model
        self._current_categories = current_categories

    def run(self) -> None:
        import copy
        new_categories = copy.deepcopy(self._current_categories)
        dedup_count = 0

        for cat, rules in self._current_categories.items():
            if len(rules) <= 1:
                continue

            user_content = json.dumps(rules, ensure_ascii=False, indent=2)

            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_EGO_DEDUP},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.0,
                )
                result = (response.choices[0].message.content or "").strip()
                if result.startswith("```json"): result = result.strip("`").replace("json\n", "", 1)
                elif result.startswith("```"): result = result.strip("`")

                parsed = json.loads(result)
                if isinstance(parsed, list):
                    if len(parsed) < len(rules):
                        dedup_count += (len(rules) - len(parsed))
                        new_categories[cat] = parsed
            except Exception as e:
                logger.error("[EGO:DEDUP] echec sur la categorie %s : %s", cat, e)
                continue
                
        if dedup_count > 0:
            logger.info("[EGO:DEDUP] termine : %d doublon(s) supprime(s)", dedup_count)
            self.dedup_done.emit(new_categories)
        else:
            # Ne pas emettre de signal si rien n'a change pour eviter des I/O inutiles
            logger.debug("[EGO:DEDUP] aucun doublon detecte")


_SYSTEM_REL_DEDUP = """\
Tu es l'Archiviste d'EUGENIA. Tu vas recevoir un tableau JSON contenant des faits sur l'auteur extraits de la mémoire.
Chaque fait possède un "id" et un "content".
Ta mission est d'identifier les faits SÉMANTIQUEMENT REDONDANTES (ceux qui racontent exactement la même chose).

Règles de déduplication :
1. Si plusieurs faits expriment exactement la même idée, garde un seul "id" et place les autres "id" dans une liste d'IDs à supprimer.
2. S'ils se complètent, ne les supprime pas.
3. Retourne UNIQUEMENT un objet JSON contenant la liste des IDs à supprimer.
Exemple attendu :
{
  "ids_to_delete": [4, 12, 45]
}
"""

class RelationalDedupWorker(QThread):
    """
    Parcourt les notes relationnelles et supprime les doublons sémantiques.
    """
    dedup_done = pyqtSignal()

    def __init__(self, client: OpenAI, model: str, relational_db: RelationalDB):
        super().__init__()
        self._client = client
        self._model = model
        self._db = relational_db

    def run(self) -> None:
        all_notes = self._db.get_all_notes()
        if len(all_notes) <= 1:
            return

        # On groupe par catégorie pour éviter au LLM de tout comparer d'un coup
        notes_by_cat = {}
        for n in all_notes:
            notes_by_cat.setdefault(n["category"], []).append({"id": n["id"], "content": n["content"]})

        total_deleted = 0

        for cat, notes in notes_by_cat.items():
            if len(notes) <= 1:
                continue

            user_content = json.dumps(notes, ensure_ascii=False, indent=2)

            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_REL_DEDUP},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.0,
                )
                result = (response.choices[0].message.content or "").strip()
                if result.startswith("```json"): result = result.strip("`").replace("json\n", "", 1)
                elif result.startswith("```"): result = result.strip("`")

                parsed = json.loads(result)
                if isinstance(parsed, dict) and "ids_to_delete" in parsed:
                    ids = parsed.get("ids_to_delete", [])
                    for i in ids:
                        if self._db.delete_note(int(i)):
                            total_deleted += 1
            except Exception as e:
                logger.error("[MEM:DEDUP] echec sur la categorie %s : %s", cat, e)
                continue
                
        if total_deleted > 0:
            logger.info("[MEM:DEDUP] termine : %d doublon(s) supprime(s)", total_deleted)
            self.dedup_done.emit()
        else:
            logger.debug("[MEM:DEDUP] aucun doublon relationnel detecte")
