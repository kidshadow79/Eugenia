# EUGENIA — Travail en cours

*Mise à jour : 1er mai 2026*

---

## État de l'implémentation

| Étape | Statut | Fichiers produits |
|-------|--------|-------------------|
| 1 — Scaffold | ✅ Validé | `main.py`, `run.bat`, `requirements.txt`, structure dossiers |
| 2 — Layout 4 colonnes | ✅ Validé | `ui/icon_bar.py`, `ui/context_panel.py`, `ui/editor_zone.py`, `ui/ai_panel.py`, `ui/main_window.py` |
| 3 — Écran démarrage | ✅ Validé | `ui/startup_dialog.py`, `core/session_manager.py` |
| 4 — Moteur IA | ✅ Validé | `core/ai_engine.py`, `core/config_manager.py` |
| 5 — Clipboard Monitor | ✅ Validé | `core/clipboard_monitor.py`, `ui/clipboard_notification.py` |
| 6 — Bible + Archiviste | 🔄 En cours de conception | — |
| 7 — Ingest document Word | ⬜ À venir | — |

---

## Étape 6 — Ce qu'on s'apprête à construire

### Le système bi-céphale — architecture corrigée

EUGENIA a une architecture **bi-céphale** (reprise d'OGMA) :

- **Cerveau chaud** = `AIEngine` (déjà codé, étape 4)
  - Température ~0.7
  - C'est le **visage conversationnel** — il parle à l'auteur, rien d'autre
  - Il ne gère pas la mémoire, ne fait pas d'analyse technique
  - Il reçoit un briefing préparé par l'Archiviste avant chaque réponse

- **Archiviste** = subconscient (à coder, étape 6)
  - Température ~0.2
  - Travaille **en sous-marin**, l'auteur ne lui parle jamais directement
  - Deux modes de fonctionnement distincts :
    - **Mode lecture** (avant chaque réponse de l'IA principale) : consulte la Bible, sélectionne les souvenirs pertinents, produit une note de contexte injectée silencieusement dans le prompt
    - **Mode écriture** (après chaque ingest/clipboard) : analyse le texte reçu, extrait personnages/lieux/événements, met à jour la Bible (SQLite)

### Flux complet — échange conversationnel normal

```
Auteur écrit un message dans le chat
         ↓
[ARCHIVISTE — mode lecture]
    analyse le message + historique récent
    consulte la Bible SQLite
    sélectionne les souvenirs pertinents
    produit une "note de contexte" :
      "L'auteur est susceptible sur ce sujet"
      "Rappel : Éleanor est morte au chapitre 2"
      "Ton dernier message était trop directif"
         ↓
Note injectée dans le prompt (role=system) de l'IA principale
         ↓
[IA PRINCIPALE — cerveau chaud]
    répond à l'auteur, informée, sans avoir cherché elle-même
```

### Flux complet — injection clipboard/ingest

```
Clipboard copy (50+ chars) → popup → [Envoyer]
         ↓
        ├──→ [IA PRINCIPALE] inject() → réponse créative dans le chat
        │
        └──→ [ARCHIVISTE — mode écriture]
                 analyse le texte
                 extrait : personnages, lieux, événements, décisions
                 met à jour Bible SQLite
                 si contradiction détectée → ajoute dans table contradictions
```

### Décisions architecturales validées (1er mai 2026)

**Q1 — Bible vide** : skip le mode lecture. Pas d'appel API inutile au départ.

**Q2 — Contradictions** : Option B — écriture dans table `contradictions` + l'Archiviste recommande à l'IA principale de le mentionner à l'auteur. Les contradictions sont signalées immédiatement dans le chat.

**Q3 — Sources de mémorisation** : Deux mémoires distinctes (voir ci-dessous).

**Q4 — Portée de la Bible** : Par projet (`data/projects/{slug}/memory_work/`). Possibilité de ponts inter-projets à envisager plus tard.

---

## Architecture mémoire — Deux mémoires distinctes

### Mémoire de travail (= la Bible du roman)

Ce qui concerne le **contenu de l'œuvre** : personnages, lieux, chronologie, décisions, contradictions.

| Source | Mode | Déclencheur |
|--------|------|-------------|
| Clipboard | Autonome | Texte envoyé via popup |
| Ingest (.docx) | Autonome | Import du fichier |
| Chat | **Manuel uniquement** | Phrase trigger : `mémorise ça : xxx` ou `/MEM xxx` |

**Chunking obligatoire** pour les textes longs (chapitre entier, document complet) :
- Découper en chunks de taille raisonnable (à définir — ~500 tokens ?)
- À chaque réinjection : **détecter uniquement les zones modifiées** (hash par chunk) → ne re-scanner que le delta
- Permet un suivi de l'évolution du texte sur la durée du projet

### Mémoire relationnelle (= profil de l'auteur)

Ce qui concerne la **relation EUGENIA ↔ auteur** : personnalité, sensibilités, préférences stylistiques, historique de la relation.

| Source | Mode | Déclencheur |
|--------|------|-------------|
| Chat | **Autonome à chaque message** | L'Archiviste analyse silencieusement |
| Ingest (biographie) | Autonome | Import d'un doc biographique dédié |

Exemple de ce que mémorise la mémoire relationnelle :
> *"L'auteur a dit que son personnage est timide et qu'il ne sait pas comment l'exprimer → EUGENIA mémorise pour adapter son aide stylistique."*

**Chunking** aussi si biographie longue — mêmes règles que mémoire de travail.

### Différence clé résumée

```
Auteur tape dans le chat :
"Mon personnage principal est timide, je ne sais pas comment le montrer"
    → Mémoire RELATIONNELLE : autonome (Archiviste analyse + stocke le besoin de l'auteur)
    → Mémoire de TRAVAIL : rien (pas de trigger /MEM)

Auteur tape dans le chat :
"/MEM Jean Vautrin — 45 ans, yeux noirs, père absent"
    → Mémoire de TRAVAIL : ajout fiche personnage Jean Vautrin
    → Mémoire RELATIONNELLE : rien de spécial

Auteur colle un chapitre via clipboard :
    → Mémoire de TRAVAIL : chunking + extraction automatique
    → Mémoire RELATIONNELLE : rien (ce n'est pas de la relation)
```

### Stockage

```
data/projects/{slug}/memory_work/
    bible.db          ← mémoire de travail (SQLite)
    chunks.json       ← index des chunks + leurs hashes (pour détection delta)

data/authors/{slug}/
    relational.db     ← mémoire relationnelle (SQLite, par auteur — pas par projet)
```

Note : la mémoire relationnelle est **par auteur**, pas par projet — EUGENIA connaît l'auteur peu importe le roman sur lequel on travaille.

---

## Système de chunking — Pattern validé (OGMA project_rag)

OGMA a déjà un système complet dans `extensions/project_rag/`. On le réutilise.

### Pattern Parent Document Retrieval (project_chunker.py)

Deux niveaux de chunks pour chaque texte ingéré :

| Niveau | Taille cible | Usage |
|--------|-------------|-------|
| **Petit chunk** | ~200 tokens | Recherche FAISS — précision maximale |
| **Chunk parent** | ~800 tokens | Injection LLM — contexte riche |

Logique : on cherche avec le petit chunk (signal concentré), mais on injecte le chunk parent (contexte suffisant pour l'IA).

### Détection delta (réinjection d'un texte modifié)

- Chaque chunk a un `hash` (sha256 du texte)
- Stocké dans SQLite avec `file_id` + `chunk_index`
- À la réinjection : on compare hash par hash
  - Hash identique → skip (pas de re-scan)
  - Hash différent ou chunk absent → re-scanner ce chunk uniquement
- Résultat : si l'auteur modifie 3 paragraphes sur 40 → 3 appels Archiviste, pas 40

### Schéma SQLite chunks (inspiré de project_manager.py)

```sql
CREATE TABLE files (
    id TEXT PRIMARY KEY,          -- hash du chemin fichier
    filename TEXT,
    file_type TEXT,               -- 'docx', 'clipboard', 'odt'
    chunk_count INTEGER,
    last_ingested_at TEXT
);

CREATE TABLE chunks (
    id TEXT PRIMARY KEY,          -- uuid
    file_id TEXT,
    chunk_index INTEGER,
    text_small TEXT,              -- ~200 tokens, pour FAISS
    text_parent TEXT,             -- ~800 tokens, pour injection LLM
    chunk_hash TEXT,              -- sha256(text_small) — détection delta
    embedding_json TEXT,          -- vecteur FAISS
    faiss_position INTEGER,
    created_at TEXT,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);
```

---

## Mémoire relationnelle — déclenchement validé

**PAS** à chaque message. Le déclenchement se fait :
1. Lors de la **résumation de conversation** (tous les N messages) — l'Archiviste profite du contexte qu'il acquiert pendant la résumation pour extraire de la matière relationnelle si elle existe
2. Lors de l'**ingest d'un doc biographique** — traitement autonome complet

**Déduplication** : avant d'écrire une nouvelle entrée relationnelle, vérification que l'info n'est pas déjà présente (hash de contenu + similarité sémantique). Pattern repris d'OGMA `injection_deduplicator.py`.

---

## RÈGLE MAJEURE : Ultra-modularité obligatoire

OGMA a atteint 9000+ lignes dans `core_logic.py` — on évite absolument ça dans EUGENIA.

**Règle** : chaque fichier a **une responsabilité unique**. Dès qu'un fichier dépasse ~200 lignes, se poser la question de le découper.

Structure cible :
```
core/
    ai_engine.py          ← cerveau chaud (déjà fait)
    archiviste.py         ← orchestrateur Archiviste (dispatch vers sous-modules)
    archiviste_writer.py  ← mode écriture (extraction + stockage Bible)
    archiviste_reader.py  ← mode lecture (consultation Bible + note de contexte)
    archiviste_relational.py ← mémoire relationnelle (résumation + extraction)
    bible_db.py           ← CRUD SQLite Bible (mémoire de travail)
    relational_db.py      ← CRUD SQLite relationnelle (mémoire auteur)
    chunk_manager.py      ← chunking + delta detection (réutilise project_rag)
    config_manager.py     ← déjà fait
    session_manager.py    ← déjà fait
    clipboard_monitor.py  ← déjà fait
ui/
    bible_panel.py        ← 5 onglets Bible
    bible_characters.py   ← widget onglet Personnages
    bible_places.py       ← widget onglet Lieux
    bible_timeline.py     ← widget onglet Chronologie
    bible_decisions.py    ← widget onglet Décisions
    bible_contradictions.py ← widget onglet Contradictions
    ... (reste déjà fait)
```

### Fichiers à créer

```
core/archiviste.py          ← Cerveau froid (QThread, prompt analytique, SQLite)
core/bible_db.py            ← Couche accès SQLite (CRUD fiches)
ui/bible_panel.py           ← 5 onglets: Personnages, Lieux, Chronologie, Décisions, Contradictions
```

### Modifications à faire

```
ui/main_window.py           ← après injection → déclenche aussi l'Archiviste
ui/context_panel.py         ← remplace placeholder "bible" par BiblePanel
```

### Schéma SQLite (prévu)

```sql
-- Personnages
CREATE TABLE characters (
    id INTEGER PRIMARY KEY,
    project_slug TEXT,
    name TEXT,
    description TEXT,
    first_seen TEXT,         -- extrait de texte source
    updated_at TEXT
);

-- Lieux
CREATE TABLE places (
    id INTEGER PRIMARY KEY,
    project_slug TEXT,
    name TEXT,
    description TEXT,
    updated_at TEXT
);

-- Événements chronologiques
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    project_slug TEXT,
    label TEXT,
    date_narrative TEXT,     -- date dans le récit (ex: "Jour 3", "Été 1943")
    description TEXT,
    updated_at TEXT
);

-- Décisions narratives
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY,
    project_slug TEXT,
    decision TEXT,
    context TEXT,
    updated_at TEXT
);

-- Contradictions détectées
CREATE TABLE contradictions (
    id INTEGER PRIMARY KEY,
    project_slug TEXT,
    description TEXT,
    source_text TEXT,
    resolved INTEGER DEFAULT 0,
    detected_at TEXT
);
```

---

## Rappels techniques

- **Config API** : `data/config/app_config.json` — `{"api_key": "sk-...", "base_url": null, "model": "gpt-4o-mini"}`
- **Slugs projets** : `data/projects/{slug}/` — le `slug` vient de `SessionManager._slugify(name)`
- **Bible DB** : `data/projects/{slug}/memory_work/bible.db`
- **Encodage** : toujours `encoding='utf-8'` explicite en Python, jamais PowerShell Get-Content/Set-Content sur fichiers avec accents
- **Pattern QThread** : voir `AICallWorker` dans `core/ai_engine.py` — l'Archiviste utilise le même pattern

---

## Règles de travail rappel (non négociables)

- **Aucun code sans feu vert de Auteur**
- **Pas de fallbacks** — si ça plante, ça doit planter visiblement, pas être masqué
- **OGMA est la source** — auditer avant de concevoir, pas d'invention instinctive
- **Équipe** — pas de décision solo, tout se discute

## Audit OGMA obligatoire avant de coder l'Archiviste

Lire dans cet ordre avant d'écrire la moindre ligne :

1. `CODETXT/06_archiviste_optimizer.txt` — logique complète de l'Archiviste
2. `CODETXT/04_memory_manager.txt` — mémoire hybride SQLite+FAISS
3. `CODETXT/09_conversation_summarizer.txt` — résumé de conversation (utile pour le mode lecture)
4. `CODETXT/11_temporal_injector.txt` — injection dans le prompt (pattern pour le briefing)
5. `archiviste_memory_optimizer.py` — implémentation concrète
6. `memory_manager.py` — implémentation SQLite+FAISS
