# EUGENIA — Audit OGMA
*Réalisé le 1er mai 2026 — Source : `c:\APP\SOURCE_IDEES_PROTOS\OGMA\`*

> Ce document recense ce qu'OGMA a déjà résolu, ce qui est directement réutilisable pour EUGENIA, et ce qui est à adapter. Il doit être consulté avant toute décision d'architecture.

---

## 1. Philosophie fondatrice OGMA (à conserver intacte dans EUGENIA)

Tirée de `CODETXT/02_ARCHITECTURE.md` — ce sont les piliers qui ont guidé toutes les décisions techniques :

| Pilier | Ce que ça signifie concrètement |
|--------|--------------------------------|
| **Transparence totale** | Aucune action cachée. Les erreurs s'affichent, jamais masquées. **Pas de fallback silencieux.** |
| **Authenticité vs Fiabilité mécanique** | Une vraie réponse imparfaite vaut mieux qu'une fausse réponse parfaite. L'IA dit "je ne sais pas" plutôt que de fabriquer. |
| **Intelligence proto-consciente** | L'IA est traitée comme une entité en développement, pas un outil. Identité stable, mémoire persistante, conscience du contexte. |
| **Croissance organique** | Le système évolue naturellement avec l'usage. Pas de programmation explicite des comportements — ils émergent. |

**Pour EUGENIA** : Ces 4 piliers s'appliquent tel quel, avec une nuance — l'identité n'est plus celle d'une IA généraliste mais d'une **compagne créative spécialisée pour l'auteur**.

---

## 2. Le système bi-céphale — Architecture validée

### Définition formelle (OGMA `02_ARCHITECTURE.md`)

> **Dual-IA Architecture** : Deux cerveaux IA distincts avec rôles séparés.

| | IA Principale (cerveau chaud) | Archiviste (subconscient) |
|---|---|---|
| Température | 0.7 | 0.3 (on utilisera 0.2 pour EUGENIA) |
| Rôle | Interface chaleureuse, conversationnelle | Analyse, extraction, enrichissement mémoire |
| Visibilité | Parle à l'utilisateur | Invisible — travaille en sous-marin |
| Format sortie | Prose naturelle | JSON structuré |
| Mémoire propre | Non — reçoit un briefing | Oui — consulte et écrit dans SQLite |

### Pourquoi deux cerveaux (OGMA l'explique) :
> *"Séparer la chaleur humaine (IA principale) de l'analyse froide (Archiviste) pour une expérience optimale."*

L'IA principale ne gère jamais la mémoire elle-même — ça la garderait dans son rôle conversationnel pur.

---

## 3. L'Archiviste — Deux modes de fonctionnement

### Mode lecture (avant chaque réponse)

Implémenté dans OGMA via `archiviste_memory_optimizer.py`. Le flux exact :

```
Message utilisateur
    ↓
[ARCHIVISTE — analyse intention]
    Analyse sémantique organique (PAS mécanique)
    Génère 8-10 "queries SMART" (pas des mots-clés, des phrases ciblées)
    Ex: "Jean caractère physique" + "Jean relations famille" + "tension chapitre 3"
    ↓
[RECHERCHE BATCH FAISS]
    1 seul appel batch (pas 8 appels séquentiels)
    80 candidats (8 queries × 10 résultats)
    Déduplication cascading (ID puis sémantique)
    ↓
[SYNTHÈSE]
    L'Archiviste produit 1 note de contexte unifiée (~300 tokens max)
    Injectée silencieusement dans le prompt de l'IA principale
```

**Gain validé dans OGMA** : -30% d'appels API, +300% de précision vs une recherche directe.

**Leçon clé** : Ne pas embedder la requête COMPLÈTE de l'utilisateur dans FAISS — c'est de la dilution sémantique. L'Archiviste extrait d'abord les concepts-clés, PUIS cherche.

### Mode écriture (après injection de texte)

Déclenché sur clipboard/ingest. L'Archiviste reçoit le texte brut et produit du JSON structuré pour mise à jour SQLite.

---

## 4. Le système de mémoire hybride (SQLite + FAISS + FTS5)

### Architecture dans OGMA (`memory_manager.py`)

**Trois couches complémentaires :**

| Couche | Technologie | Usage | Vitesse |
|--------|-------------|-------|---------|
| Exacte | SQLite FTS5 | Recherche par mot-clé exact | ~1ms |
| Sémantique | FAISS (CPU) | Recherche par sens/contexte | ~5-10ms |
| Structurée | SQLite classique | CRUD fiches (personnages, lieux...) | ~1ms |

**Pourquoi FAISS CPU et pas GPU ?**
- Application desktop, pas de serveur
- faiss-cpu est déjà dans nos requirements
- Suffisant pour les volumes d'un roman (quelques milliers de fragments max)

### Nettoyage sémantique avant embedding (`memory_manager.py`)

OGMA a résolu un problème subtil : si on embedde "tu te souviens du nom de mon chat ?", le vecteur est pollué par "tu te souviens", "du", "mon" — des mots qui n'ont aucune valeur sémantique.

Solution : **nettoyer la requête avant embedding** — ne garder que le signal pur.

```
"tu te souviens du nom de mon chat ?" → "nom mon chat"
"qu'est-ce que t'évoque la légende des 2 phares ?" → "légende 2 phares"
```

**Pour EUGENIA** : Même logique pour les recherches dans la Bible — "qui est le personnage qui a les yeux bleus ?" → "personnage yeux bleus".

### Score de matching hybride

OGMA combine deux scores pour classer les résultats :
1. Score FAISS (cosine similarity — sémantique)
2. Score keyword matching (% des mots de la requête trouvés dans le souvenir)

Le score final est une combinaison pondérée. Pas de score = pas de résultat retourné. Pas de fallback.

---

## 5. Le système Ego (identité persistante de l'IA)

### Principe (`modules/logic/ego_activation.py`)

L'IA principale ne reçoit pas son "caractère" sous forme d'un gros prompt système fixe. C'est trop coûteux en tokens (~1700 tokens pour tous les groupes).

À la place : **injection dynamique et ciblée par l'Archiviste**.

```
Données ego stockées par "groupes" (PHOBIES, ETHIQUE, RELATIONS_USER, INTIMITE...)
    ↓
Pour chaque message, l'Archiviste lit le catalogue des groupes (noms + descriptions)
    ↓
Sélectionne 0-3 groupes pertinents pour CE message
    ↓
Injecte uniquement les flags de ces groupes (~50-150 tokens vs 1700)
```

**Premier message d'une session** : Injection complète (tous les groupes) pour établir les "rails" de personnalité.
**Messages suivants** : Sélection ciblée — économie massive de tokens.

### Pour EUGENIA

Équivalent du système Ego = le **profil de l'auteur** :
- Voix narrative (ton, style, longueur de phrase)
- Préférences (EUGENIA évite de proposer des finales, l'auteur aime décider lui-même)
- Susceptibilités (sujets sensibles dans le projet)
- Historique relationnel (comment ça s'est passé entre l'auteur et EUGENIA)

Ce profil doit être injecté de façon dynamique et ciblée, pas en bloc.

---

## 6. La gestion des conversations longues (ConversationSummarizer)

### Problème résolu (`CODETXT/09_conversation_summarizer.txt`)

Une conversation de 50+ messages coûte des milliers de tokens à chaque appel (tout l'historique est renvoyé). OGMA a résolu ça avec un système de résumé progressif :

- Tous les 10 messages → l'Archiviste génère un résumé (~300 tokens pour 10 messages)
- Déclenchement automatique quand 30+ messages non résumés
- L'interface utilisateur voit l'historique complet
- Le backend n'envoie que : résumés compressés + 20 derniers messages en clair
- Persistance : résumés sauvés dans le JSON de conversation (pas de perte au rechargement)

**Pour EUGENIA** : Même mécanique — une session de travail sur un roman peut durer des heures. Sans résumé progressif, les coûts API explosent et le contexte dépasse la fenêtre du modèle.

---

## 7. Le déduplicateur d'injections (InjectionDeduplicator)

### Problème résolu (`injection_deduplicator.py`)

L'Archiviste peut injecter le même souvenir plusieurs fois si la conversation y revient. OGMA a quantifié le problème : triple redondance possible = 3500 à 4500 tokens gaspillés par requête.

Solution : tracking des IDs de souvenirs déjà injectés dans la session courante, avec un système de **cooldown** (un souvenir ne peut être ré-injecté qu'après N messages).

```python
cooldown_threshold = 3  # 3 messages entre deux injections du même souvenir
```

**Pour EUGENIA** : Même logique — l'Archiviste ne doit pas injecter "Éleanor est morte au chapitre 2" à chaque réponse si ça a déjà été dit deux messages auparavant.

---

## 8. Le TemporalInjector (conscience temporelle)

### État dans OGMA (`temporal_injector.py`)

Module actuellement **désactivé** dans OGMA (en attente d'une extension `temporal_guardian`). Le principe reste valide :

- Injecter l'heure et la date dans le prompt au **début de session** seulement
- Pas à chaque message (trop coûteux)
- 10 tokens suffisent pour une "conscience temporelle qualitative"

**Pour EUGENIA** : Utile pour que l'IA sache qu'on est en mai 2026, que la session a commencé il y a 2 heures, etc. À implémenter simplement — pas besoin du module complet d'OGMA.

---

## 9. L'IdentityManager (multi-profils)

### Ce qu'il fait (`identity_manager.py`)

OGMA supporte plusieurs utilisateurs sur la même machine, chacun avec son profil :
- `user_name`, `ai_name`, `ai_description`
- `relationship_type` (professional, collaborative, intimate)
- `relationship_context` — phrase décrivant la relation, avec `{user_name}` comme placeholder

**Pour EUGENIA** : Déjà partiellement implémenté via `SessionManager` (auteur + projet). À enrichir avec :
- Le profil de style de l'auteur (voix narrative)
- L'historique de relation EUGENIA ↔ auteur (ton de la relation évolue avec le temps)

---

## 10. Ce qu'OGMA N'a PAS (à créer pour EUGENIA)

Ces besoins sont spécifiques à EUGENIA — OGMA ne les a pas résolus :

| Besoin | Pourquoi absent d'OGMA | Approche envisagée |
|--------|------------------------|-------------------|
| **Bible du roman** | OGMA mémorise des événements de vie, pas une fiction | SQLite dédié par projet — 5 tables (personnages, lieux, chronologie, décisions, contradictions) |
| **Extraction d'entités narratives** | OGMA extrait des souvenirs biographiques | Prompt Archiviste spécialisé pour fiction — JSON avec types narratifs |
| **Détection de contradictions** | OGMA ne compare pas le passé et le présent d'une fiction | Avant d'écrire une fiche, l'Archiviste compare avec l'existant dans SQLite |
| **Ingest Word/ODT** | OGMA reçoit du texte conversationnel | `python-docx` + `win32com` (déjà dans requirements) |
| **Synchronisation éditeur tiers** | OGMA est une interface autonome | `win32gui` pour repositionner la fenêtre Word/LibreOffice |

---

## 11. Ce qu'OGMA a résolu que nous N'implémenterons PAS (hors scope EUGENIA)

Pour ne pas sur-ingéniérer :

| Fonctionnalité OGMA | Pourquoi pas dans EUGENIA |
|---------------------|--------------------------|
| Perception webcam (moondream) | Pas pertinent pour un auteur |
| Génération d'images (DALL-E, SD) | Hors scope |
| Support multi-providers (Google, Anthropic, GROK, Ollama, GGUF...) | On supporte OpenAI-compatible seulement (simplifie massivement) |
| Streaming tokens | Confort UX non critique pour l'étape actuelle |
| Dream Engine (consolidation pendant inactivité) | Étape future possible — pas maintenant |
| STT/TTS audio | Pas prévu |
| Extension Web Navigator (recherche web) | Pas pertinent |

---

## 12. Ordre d'implémentation recommandé pour EUGENIA (tiré de l'audit)

### Étape 6 — Bible + Archiviste

Composants à créer dans cet ordre (chaque brique dépend de la précédente) :

1. **`core/bible_db.py`** — Couche SQLite CRUD (5 tables)
   - S'inspire de `MemoryStructure` dans `core_logic.py` : backup auto, rotation, protection contre corruption

2. **`core/archiviste.py`** — Mode écriture (extraction + stockage)
   - Pattern QThread identique à `AICallWorker` dans `core/ai_engine.py`
   - Prompt spécialisé fiction, JSON structuré, temperature 0.2
   - S'inspire de `ArchivisteMemoryOptimizer._analyze_user_intent()`

3. **`ui/bible_panel.py`** — Affichage des 5 onglets
   - Lecture seule sur les données SQLite
   - Bouton "Actualiser"

4. **Branchement mode lecture** — Archiviste brief l'IA principale
   - Avant chaque `AIEngine.send()`, l'Archiviste consulte la Bible
   - Produit une note injectée comme `role=system`
   - S'inspire du pattern `get_optimized_context()` → injection dans historique

### Étape 7 — Ingest

5. **`core/ingest.py`** — Lecture .docx via `python-docx`
6. Branchement sur le bouton [Synchroniser]

---

## 13. Règles techniques apprises d'OGMA à respecter dans EUGENIA

- **Pas de fallback silencieux** — règle fondatrice d'OGMA, pilier 1
- **Nettoyage sémantique avant FAISS** — toujours filtrer les stopwords conversationnels
- **Déduplication par cooldown** — ne pas ré-injecter le même souvenir trop souvent
- **Résumé progressif** — pour les sessions longues (toutes les 10-30 interactions)
- **JSON compilé pour l'ego** (profil auteur) — pas d'un seul bloc, injection ciblée par groupe
- **Backup automatique SQLite** — avant chaque écriture, copie horodatée + rotation 4 backups max
- **FTS5 + FAISS combinés** — pas l'un ou l'autre, les deux se complètent
