"""
archiviste_writer.py — Mode écriture de l'Archiviste

Responsabilité unique : à partir d'un chunk de texte romanesque,
extraire les entités narratives et les écrire dans la Bible SQLite.

Entités extraites :
    - characters   : personnages (nom, description physique/psychologique)
    - places       : lieux (nom, ambiance, localisation)
    - events       : événements (titre court, description)
    - decisions    : décisions d'auteur (ex: "Elara parle elfique")
    - contradictions : incohérences détectées vs Bible existante

L'appel API tourne dans un QThread (pattern AICallWorker).
L'Archiviste communique avec l'UI uniquement via des signaux Qt.

Signaux émis :
    extraction_done(dict)      : entités extraites pour 1 chunk (pour log)
    bible_updated(str, int)    : (table, nb_entrées_totales) après écriture
    contradiction_found(str)   : description de la contradiction détectée
    error_occurred(str)        : erreur API ou JSON

Usage (depuis ArchivisteOrchestrator) :
    writer = ArchivisteWriter(config, bible_db)
    writer.contradiction_found.connect(main_window.on_contradiction)
    writer.process_chunk(chunk_result)
"""

import json
import re
import logging
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from openai import OpenAI

from core.bible_db import BibleDB
from core.chunk_manager import ChunkResult
from core.project_types import DEFAULT_CATEGORIES, build_writer_prompt

logger = logging.getLogger(__name__)

_USER_PROMPT_WRITER = """Analyse cet extrait et extrais UNIQUEMENT les faits qui y sont EXPLICITEMENT écrits.

Règle absolue : si une information n'est pas textuellement présente dans l'extrait ci-dessous,
ne l'inclus PAS. Aucune inférence, aucune interprétation, aucune supposition.

{bible_context}

Extrait à analyser :
---
{chunk_text}
---
"""


# Nombre maximum de chunks traités simultanément (appels API parallèles)
# I/O-bound pur : les workers ne font qu'un appel HTTP, les écritures DB
# restent sur le thread principal via signaux Qt → sans risque de race condition.
_MAX_CONCURRENT = 3


def _parse_json_tolerant(s: str) -> dict:
    """
    Tente de parser le JSON. Si la réponse est tronquée (max_tokens dépassé),
    essaie de récupérer ce qui est valide plutôt que de tout perdre.
    """
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Tentative 1 : truncation propre sur la dernière liste/objet complet
    # On cherche la dernière virgule + fermeture possible
    for end in range(len(s) - 1, 0, -1):
        candidate = s[:end]
        # Fermer les tableaux/objets ouverts
        opens = candidate.count('{') - candidate.count('}')
        arrays = candidate.count('[') - candidate.count(']')
        closing = (']' * arrays) + ('}' * opens)
        try:
            return json.loads(candidate + closing)
        except json.JSONDecodeError:
            continue
        if end < len(s) - 500:   # on ne cherche pas trop loin
            break

    logger.warning("_parse_json_tolerant — JSON irrécupérable, retour vide")
    return {}


class _WriterCallWorker(QThread):
    """Thread d'appel API pour l'extraction d'entités (ne pas utiliser directement)."""

    extraction_done = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, client: OpenAI, model: str,
                 chunk: ChunkResult, bible_context: str, system_prompt: str):
        super().__init__()
        self._client = client
        self._model = model
        self._chunk = chunk
        self._bible_context = bible_context
        self._system_prompt = system_prompt

    def run(self):
        logger.info("[ARCHIVISTE:APPEL] writer chunk=%s model=%s (%d chars)",
                    self._chunk.chunk_index, self._model, len(self._chunk.text_parent))
        user_content = _USER_PROMPT_WRITER.format(
            bible_context=self._bible_context,
            chunk_text=self._chunk.text_parent,
        )
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user",   "content": user_content},
        ]
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.0,    # Extraction = zéro créativité, 100% fidèle au texte
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            # Extraire le JSON même si le modèle ajoute du texte autour
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                self.error_occurred.emit(
                    f"[Archiviste] JSON introuvable dans la réponse : {raw[:120]}"
                )
                return
            json_str = match.group(0)
            result = _parse_json_tolerant(json_str)
            result["_chunk_index"] = self._chunk.chunk_index
            if not result:
                self.error_occurred.emit(
                    f"[Archiviste] JSON irrécupérable pour chunk {self._chunk.chunk_index}"
                )
                return
            n = sum(len(result.get(k, [])) for k in result if k != "_chunk_index" and isinstance(result.get(k), list))
            logger.info("[ARCHIVISTE:RETOUR] writer chunk=%s -> %d entités extraites",
                        self._chunk.chunk_index, n)
            self.extraction_done.emit(result)
        except json.JSONDecodeError as e:
            logger.error("WriterWorker — JSON invalide (non récupéré) : %s", e)
            self.error_occurred.emit(f"[Archiviste] JSON invalide : {e}")
        except Exception as e:
            logger.error("WriterWorker — erreur API : %s", e)
            self.error_occurred.emit(f"[Archiviste] Erreur API : {e}")


class ArchivisteWriter(QObject):
    """
    Pilote l'extraction d'entités et l'écriture dans la Bible.

    Instancier une fois par projet. Thread-safe pour les lectures,
    mais process_chunk() ne doit pas être appelé en parallèle
    (les appels sont séquentiels — un chunk à la fois).
    """

    # ─── Signaux publics ──────────────────────────────────────────────────────
    extraction_done    = pyqtSignal(dict)    # données brutes extraites (pour log/debug)
    bible_updated      = pyqtSignal(str, int)# (table_name, new_total)
    contradiction_found = pyqtSignal(str)    # description de la contradiction
    error_occurred     = pyqtSignal(str)     # erreur bloquante
    all_chunks_done    = pyqtSignal()        # fin du traitement d'une liste de chunks
    chunk_processed    = pyqtSignal(int, int)# (done, total) — progression

    def __init__(self, config: dict, bible_db: BibleDB,
                 categories: list[str] | None = None, parent=None):
        """
        Args:
            config:     dict avec keys "api_key", "base_url" (ou None), "model"
            bible_db:   instance BibleDB du projet courant
            categories: catégories Bible du projet (ex: ["characters", "places"])
                        Si None → utilise les catégories de bible_db._tables.
        """
        super().__init__(parent)
        self._bible_db = bible_db
        self._model = config.get("model", "gpt-4o-mini")
        self._categories: list[str] = list(
            categories if categories is not None
            else getattr(bible_db, '_tables', None) or DEFAULT_CATEGORIES
        )
        self._system_prompt = build_writer_prompt(self._categories)
        api_key_val = config.get("api_key", "")
        self._client = OpenAI(
            api_key=api_key_val.strip() if api_key_val else "",
            base_url=config.get("base_url") or None,
            default_headers=config.get("extra_headers") or None,
        )
        self._worker: _WriterCallWorker | None = None

    # ─── API publique ─────────────────────────────────────────────────────────

    def process_chunk(self, chunk: ChunkResult) -> None:
        """
        Lance l'extraction pour un chunk.

        L'appel est asynchrone (QThread). Les résultats arrivent via les signaux.
        Ne pas appeler pendant qu'un traitement est déjà en cours.
        """
        if self._worker and self._worker.isRunning():
            logger.warning("ArchivisteWriter — traitement déjà en cours, chunk ignoré")
            self.error_occurred.emit(
                "[Archiviste] Traitement déjà en cours — chunk ignoré"
            )
            return

        logger.debug("ArchivisteWriter — process_chunk index=%s", chunk.chunk_index)
        self._current_chunk = chunk   # nécessaire pour stocker text_index dans _on_extraction_done
        bible_context = self._build_bible_context()
        self._worker = _WriterCallWorker(
            self._client, self._model, chunk, bible_context, self._system_prompt
        )
        self._worker.extraction_done.connect(self._on_extraction_done)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.start()

    def process_chunks(self, chunks: list[ChunkResult],
                        on_chunk_saved: callable = None) -> None:
        """
        Traite une liste de chunks avec _MAX_CONCURRENT appels LLM en parallèle.
        Émet all_chunks_done quand tout est terminé.

        Args:
            chunks:         liste des chunks à traiter
            on_chunk_saved: callback(chunk) appelé après chaque chunk OK
                            (utilisé pour save_chunk_hash en temps réel)
        """
        if not chunks:
            self.all_chunks_done.emit()
            return
        self._pending_chunks   = list(chunks)
        self._chunks_total     = len(chunks)
        self._chunks_done      = 0
        self._on_chunk_saved   = on_chunk_saved
        self._active_workers:  list[_WriterCallWorker] = []
        # Lookup chunk_index → ChunkResult pour stocker text_index au retour
        self._chunk_map: dict[int, ChunkResult] = {c.chunk_index: c for c in chunks}
        logger.info(
            "[WRITER:START] %d chunks à traiter (concurrence=%d)",
            len(chunks), _MAX_CONCURRENT,
        )
        for _ in range(min(_MAX_CONCURRENT, len(chunks))):
            self._launch_next_parallel()

    # ─── Interne ──────────────────────────────────────────────────────────────

    def _launch_next_parallel(self) -> None:
        """Lance le prochain worker en attente, si le quota de concurrence le permet."""
        if not self._pending_chunks:
            return
        chunk = self._pending_chunks.pop(0)
        bible_context = self._build_bible_context()
        worker = _WriterCallWorker(
            self._client, self._model, chunk, bible_context, self._system_prompt
        )
        worker.extraction_done.connect(self._on_parallel_done)
        worker.error_occurred.connect(self._on_parallel_error)
        self._active_workers.append(worker)  # garde la référence (évite GC)
        worker.start()

    def _on_parallel_done(self, data: dict) -> None:
        """Réception résultat d'un worker parallèle — s'exécute sur le thread principal."""
        # Restaurer le bon chunk courant pour _on_extraction_done (text_index)
        chunk_idx = data.get("_chunk_index")
        self._current_chunk = self._chunk_map.get(chunk_idx)

        self._on_extraction_done(data)
        self._chunks_done += 1
        if self._on_chunk_saved and self._current_chunk:
            self._on_chunk_saved(self._current_chunk)
        self.chunk_processed.emit(self._chunks_done, self._chunks_total)

        sender = self.sender()
        if sender in self._active_workers:
            self._active_workers.remove(sender)

        if self._pending_chunks:
            self._launch_next_parallel()
        elif not self._active_workers:
            logger.info("[WRITER:DONE] %d chunks traités", self._chunks_done)
            self.all_chunks_done.emit()

    def _on_parallel_error(self, msg: str) -> None:
        """Un chunk a échoué — on logge et on continue les suivants."""
        self.error_occurred.emit(msg)
        self._chunks_done += 1
        self.chunk_processed.emit(self._chunks_done, self._chunks_total)

        sender = self.sender()
        if sender in self._active_workers:
            self._active_workers.remove(sender)

        if self._pending_chunks:
            self._launch_next_parallel()
        elif not self._active_workers:
            logger.info("[WRITER:DONE] %d chunks traités (avec erreurs)", self._chunks_done)
            self.all_chunks_done.emit()

    def _process_next_chunk(self) -> None:
        if not self._pending_chunks:
            self.all_chunks_done.emit()
            return
        self._current_chunk = self._pending_chunks.pop(0)
        bible_context = self._build_bible_context()
        worker = _WriterCallWorker(
            self._client, self._model, self._current_chunk, bible_context, self._system_prompt
        )
        worker.extraction_done.connect(self._on_sequential_done)
        worker.error_occurred.connect(self._on_sequential_error)
        worker.start()
        # Garder une référence pour éviter le GC
        self._worker = worker

    def _on_sequential_done(self, data: dict) -> None:
        self._on_extraction_done(data)
        self._chunks_done += 1
        # Sauvegarde progressive du hash de ce chunk
        if self._on_chunk_saved and self._current_chunk:
            self._on_chunk_saved(self._current_chunk)
        self.chunk_processed.emit(self._chunks_done, self._chunks_total)
        self._process_next_chunk()

    def _on_sequential_error(self, msg: str) -> None:
        self.error_occurred.emit(msg)
        self._chunks_done += 1
        self.chunk_processed.emit(self._chunks_done, self._chunks_total)
        # On continue sur le prochain chunk malgré l'erreur
        self._process_next_chunk()

    def _on_extraction_done(self, data: dict) -> None:
        """Reçoit le JSON extrait par le thread et écrit dans la Bible."""
        self.extraction_done.emit(data)

        # Stocker le résumé factuel dans le chunk courant (utilisé par VectorIndex)
        resume = (data.get("resume") or "").strip()
        if resume and hasattr(self, "_current_chunk") and self._current_chunk is not None:
            self._current_chunk.text_index = resume
            logger.debug("[WRITER:RESUME] chunk=%s resume=%d chars",
                         self._current_chunk.chunk_index, len(resume))

        chunk_id = f"chunk-{data.get('_chunk_index', '?')}"
        total_written = 0

        tables_to_write = [c for c in self._categories if c != "contradictions"]
        for table in tables_to_write:
            entries = data.get(table, [])
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                label = (entry.get("label") or "").strip()
                content = (entry.get("content") or "").strip()
                if not label or not content:
                    continue
                self._bible_db.upsert(table, label, content, chunk_id)
                total = self._bible_db.count(table)
                self.bible_updated.emit(table, total)
                total_written += 1

        # Contradictions → écriture + signal spécial (si catégorie active)
        if "contradictions" not in self._categories:
            return
        contradictions = data.get("contradictions", [])
        if not isinstance(contradictions, list):
            return
        for entry in contradictions:
            if not isinstance(entry, dict):
                continue
            label = (entry.get("label") or "").strip()
            content = (entry.get("content") or "").strip()
            if not label or not content:
                continue
            self._bible_db.upsert("contradictions", label, content, chunk_id)
            total = self._bible_db.count("contradictions")
            self.bible_updated.emit("contradictions", total)
            self.contradiction_found.emit(f"{label} — {content}")
            logger.warning("Contradiction détectée : %s", label)

        if total_written:
            logger.info("[BIBLE:WRITE] %d entrée(s) persistées (chunk=%s)", total_written, chunk_id)
        else:
            logger.debug("[BIBLE:WRITE] 0 entrée nouvelle (tout déjà connu, chunk=%s)", chunk_id)

    def _build_bible_context(self) -> str:
        """
        Construit un résumé compact de la Bible existante à passer en contexte.
        Permet à l'Archiviste de détecter les contradictions.
        Retourne une chaîne vide si la Bible est vide.
        """
        if self._bible_db.is_empty():
            return ""

        lines = ["Bible du projet (contexte existant) :"]
        context_tables = [c for c in self._categories
                          if c not in ("contradictions", "events")]
        for table in context_tables[:3]:  # max 3 tables en contexte
            rows = self._bible_db.get_all(table)
            if rows:
                lines.append(f"\n[{table.upper()}]")
                for r in rows[:10]:  # limite à 10 entrées par table
                    lines.append(f"  • {r['label']} : {r['content'][:120]}")

        return "\n".join(lines)

    def update_config(self, config: dict) -> None:
        """Met à jour la config API (appelé si l'utilisateur change les paramètres)."""
        self._model = config.get("model", "gpt-4o-mini")
        api_key_val = config.get("api_key", "")
        self._client = OpenAI(
            api_key=api_key_val.strip() if api_key_val else "",
            base_url=config.get("base_url") or None,
            default_headers=config.get("extra_headers") or None,
        )
