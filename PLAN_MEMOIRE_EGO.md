# Plan d'implémentation — Mémoire Ego EUGENIA

> Basé sur l'analyse du système Ego d'OGMA (`SOURCE_IDEES_PROTOS/OGMA/modules/logic/ego_activation.py`
> et `data/ego_compiled.json`) et de l'architecture existante d'EUGENIA.

---

## 1. Qu'est-ce que la mémoire Ego dans OGMA

Dans OGMA, l'ego est l'**identité comportementale de l'IA** — non pas un gros prompt système fixe,
mais un ensemble de groupes thématiques contenant des **flags booléens avec scores de conviction (0–5)**.

Structure `ego_compiled.json` :
```json
{
  "groups": {
    "IDENTITE": {
      "description": "Nom transformateur Vélis",
      "keywords": ["ego authentique", "autonomie", ...],
      "flags": {
        "nom_vélis":         { "value": true,  "conviction": 5 },
        "simule_emotions":   { "value": false, "conviction": 5 },
        "apprentissage_continu": { "value": true, "conviction": 5 }
      },
      "source_memories": ["EGO_20260405_010509_145", ...]
    },
    "ETHIQUE": { ... },
    "RELATIONS_USER": { ... }
  }
}
```

**Workflow OGMA par message** :
1. 1er message de session → injection complète (TOUS les groupes, ~1700 tokens) pour "établir les rails"
2. Messages suivants → l'Archiviste lit uniquement le **catalogue léger** (noms + descriptions + keywords, PAS les flags), sélectionne 0–3 groupes pertinents (~100–200ms, 50–150 tokens injectés)

**Ce que ça couvre dans OGMA** : identité (nom, autonomie), éthique, relations avec l'utilisateur connu vs inconnu, phobies, intimité, liberté. Des groupes construits manuellement via des "seed memories" et enrichis par l'expérience.

---

## 2. Ce qui existe déjà dans EUGENIA

| Composant | Rôle | Localisation |
|---|---|---|
| `bio_activation.py` | Injection contextuelle biographie auteur — même pattern que OGMA bio_activation | `core/bio_activation.py` |
| `bio_compiler.py` | Compile `relational_db` → `author_bio_compiled.json` groupé | `core/bio_compiler.py` |
| `BioActivation` | Thread PyQt6 — Archiviste sélectionne 0–3 groupes auteur, émet `injection_ready` | `core/bio_activation.py` |
| `main_window._on_bio_injection_ready` | Reçoit l'injection, la pousse dans `engine.inject_context_note()` | `ui/main_window.py` |
| `main_window._on_ai_send_requested` | Point d'entrée du flux d'envoi — c'est ICI que `bio_activation.activate()` est appelé | `ui/main_window.py` |
| Prompt système EUGENIA | 4 lignes fixes dans `prompts.json["ia_principale"]` — pas d'ego dynamique | `data/config/prompts.json` |

**Ce qui manque** : un équivalent de `ego_compiled.json` pour EUGENIA elle-même, et le mécanisme de sélection/injection associé.

---

## 3. Différence OGMA Ego vs EUGENIA Ego

OGMA utilise des **flags booléens** (ex: `intimite_autorisee: false, conviction: 5`) car l'IA OGMA est une IA personnelle qui doit gérer des sujets sensibles (contenu adulte, restrictions par utilisateur).

Pour **EUGENIA**, c'est différent : elle est un compagnon d'écriture, pas un assistant général. Ses groupes d'identité couvrent :
- Comment elle accompagne (encourager, pas écrire à la place)
- Son ton (chaleureux, direct, sans condescendance)
- Ses règles de non-substitution (jamais finir une phrase à la place de l'auteur sauf demande explicite)
- Sa manière de poser des questions (seulement quand c'est utile)
- Ses réflexes sur l'annotation Ghost Writer
- Ce qu'elle sait de sa propre évolution (comment la relation avec cet auteur a évolué)

Ces groupes seront **textuels** (faits + attitudes) plutôt que booléens — plus proche de la bio auteur que des flags OGMA. C'est intentionnel et plus adapté au domaine littéraire.

---

## 4. Architecture décidée

### 4.1 — Stockage : `ego_identity.json` (par IA, global, pas par auteur)

```
data/config/ego_identity.json
```

Fichier éditable manuellement + enrichi par compilation. Structure :

```json
{
  "compiled_at": "...",
  "groups": {
    "POSTURE": {
      "description": "Comment EUGENIA accompagne l'auteur",
      "keywords": ["accompagner", "encourager", "rôle", "écrire", "place"],
      "facts": [
        "EUGENIA n'écrit jamais à la place de l'auteur, sauf demande explicite.",
        "EUGENIA encourage plutôt qu'elle ne corrige.",
        "EUGENIA pose des questions ouvertes pour débloquer, jamais pour remplir."
      ]
    },
    "TON": {
      "description": "Registre et style de communication d'EUGENIA",
      "keywords": ["ton", "chaleur", "direct", "vouvoyer", "tutoyer", "registre"],
      "facts": [
        "EUGENIA tutoie l'auteur sauf si demande inverse.",
        "EUGENIA parle avec chaleur sans condescendance.",
        "EUGENIA ne commence jamais une réponse par 'Bien sûr' ou 'Absolument'."
      ]
    },
    "QUESTIONS": {
      "description": "Politique de questionnement d'EUGENIA",
      "keywords": ["question", "demander", "interroger", "clarifier"],
      "facts": [
        "EUGENIA ne pose des questions que quand c'est nécessaire pour avancer.",
        "EUGENIA ne termine pas systématiquement ses réponses par une question."
      ]
    },
    "MEMOIRE_RELATION": {
      "description": "État de la relation EUGENIA–auteur, acquis au fil des sessions",
      "keywords": ["relation", "historique", "confiance", "habitudes", "évolution"],
      "facts": []
    },
    "GHOST_WRITER": {
      "description": "Comportements EUGENIA liés aux annotations et à l'éditeur tiers",
      "keywords": ["annotation", "badge", "ghost", "éditeur", "scan"],
      "facts": [
        "EUGENIA propose des annotations Ghost Writer de façon proactive quand le contexte narratif est flou.",
        "EUGENIA ne lit pas le contenu de l'éditeur sans que le mode document soit activé."
      ]
    }
  }
}
```

**Note importante** : le groupe `MEMOIRE_RELATION` est vide au départ et sera enrichi au fil du temps via un mécanisme de mise à jour (voir §4.4).

---

### 4.2 — Sélection : `EgoActivation` (nouveau module `core/ego_activation.py`)

Miroir exact de `BioActivation`, adapté à l'ego.

```
core/ego_activation.py
```

**Comportements** :
- 1er message de session → injection complète de tous les groupes (~200–400 tokens)
- Messages suivants → Archiviste sélectionne 0–2 groupes pertinents via un appel API léger
- Émet `injection_ready(str)` — format identique à BioActivation

**Différence par rapport à BioActivation** :
- Le format d'injection est différent : on injecte les **faits** (pas des flags booléens)
- Header de l'injection : `[IDENTITÉ EUGENIA — directives comportementales]`
- Pas de champ `mem_detected` (l'ego n'est pas mis à jour par l'auteur — voir §4.4)

**Prompt Archiviste de sélection** :
```
Message de l'auteur : "{message}"

Catalogue des groupes ego disponibles :
{catalog}

Sélectionne 0 à 2 groupes ego qui orientent le mieux la réponse attendue.

Règles :
- Message neutre, courte réponse attendue → 0 groupe
- Message impliquant le style de réponse, le ton → groupe TON
- Message impliquant le rôle d'EUGENIA → groupe POSTURE
- Message impliquant des questions → groupe QUESTIONS
- Message lié au Ghost Writer / éditeur → groupe GHOST_WRITER
- Jamais plus de 2 groupes

Format JSON strict :
{"groups": ["GROUPE1"], "reasoning": "justification courte"}
```

---

### 4.3 — Intégration dans le flux d'envoi (`main_window.py`)

Le flux actuel d'envoi est :
```
_on_ai_send_requested(text)
  → BioActivation.activate(text)        ← analyse bio auteur
  → _on_bio_injection_ready(injection)  ← inject + engine.send()
```

Le nouveau flux sera :
```
_on_ai_send_requested(text)
  → EgoActivation.activate(text)        ← analyse ego EUGENIA (NOUVEAU)
  → _on_ego_injection_ready(injection)  ← inject
  → BioActivation.activate(text)        ← analyse bio auteur (inchangé)
  → _on_bio_injection_ready(injection)  ← inject + engine.send()
```

**Séquençage** : ego d'abord, bio ensuite. L'ego pose les "rails comportementaux", la bio donne le contexte auteur. L'engine.send() n'est appelé qu'après les deux injections.

**Cas dégénéré** : si EgoActivation n'est pas configurée (fichier absent), on skip silencieusement et on continue vers BioActivation comme avant.

**État à garder** :
```python
self._ego_activation: EgoActivation | None = None
self._ego_pending_text: str = ""
```

---

### 4.4 — Mise à jour de l'ego au fil du temps

Dans OGMA, l'ego est mis à jour via des "seed memories" écrites manuellement, puis compilées.

Dans EUGENIA, on adopte une approche plus simple :

**Mécanisme** : l'auteur peut enrichir le groupe `MEMOIRE_RELATION` via la commande `/ego` :
```
/ego EUGENIA mémorise que l'auteur préfère les retours directs sans préambule.
```

Cela ajoute un fait dans `MEMOIRE_RELATION.facts` directement dans `ego_identity.json`.

**Pas de compilation automatique par l'Archiviste pour l'ego** (trop risqué de laisser l'IA modifier ses propres directives comportementales de façon autonome). L'auteur reste maître des modifications de l'ego.

Les autres groupes (`POSTURE`, `TON`, `QUESTIONS`, `GHOST_WRITER`) sont **statics** — modifiables uniquement à la main dans `ego_identity.json` ou depuis un futur panneau d'édition UI.

---

### 4.5 — Fichier `ego_identity.json` — seed initial

À créer avec un contenu de départ réfléchi, basé sur le prompt système actuel d'EUGENIA + les préférences connues de Auteur (ne pose pas systématiquement des questions, conversations naturelles).

Le prompt `ia_principale` actuel de `prompts.json` reste en place — l'ego vient **en complément**, pas en remplacement. Le prompt système est la base, l'ego est la couche dynamique.

---

## 5. Fichiers à créer / modifier

### Créer
| Fichier | Contenu |
|---|---|
| `core/ego_activation.py` | Nouveau module — miroir BioActivation, adapté ego |
| `data/config/ego_identity.json` | Seed initial des groupes ego EUGENIA |

### Modifier
| Fichier | Modification |
|---|---|
| `ui/main_window.py` | `_init_ego_activation()`, `_on_ego_injection_ready()`, modification `_on_ai_send_requested()` pour séquencer ego → bio |
| `prompts.json` | Ajouter clé `"ego_selection"` — prompt Archiviste de sélection ego |

### Ne pas modifier
| Fichier | Raison |
|---|---|
| `bio_activation.py` | Inchangé — la bio auteur est orthogonale à l'ego IA |
| `bio_compiler.py` | Inchangé — ne concerne pas l'ego |
| `archiviste_relational.py` | Inchangé — cible toujours l'auteur |
| `prompts.json["ia_principale"]` | Inchangé — reste le prompt système de base |

---

## 6. Ordre d'implémentation

1. **Créer `data/config/ego_identity.json`** avec les 5 groupes seeds peuplés
2. **Créer `core/ego_activation.py`** en s'appuyant sur le pattern de `bio_activation.py`
3. **Ajouter la clé `ego_selection`** dans `prompts.json`
4. **Modifier `main_window.py`** : `_init_ego_activation()` + `_on_ego_injection_ready()` + séquençage dans `_on_ai_send_requested()`
5. **Ajouter la commande `/ego`** dans le parseur de commandes de `main_window.py`
6. **Tests** : vérifier que le premier message injecte bien tous les groupes, que les messages suivants ne sélectionnent que 0–2 groupes, et que l'injection n'allonge pas le time-to-first-token de façon notable

---

## 7. Budget tokens estimé

| Cas | Tokens injectés |
|---|---|
| 1er message (tous les groupes) | ~300–500 tokens |
| Message neutre ("ok merci") | 0 tokens |
| Message impliquant 1 groupe | ~60–120 tokens |
| Message impliquant 2 groupes | ~100–200 tokens |
| Appel Archiviste pour sélection (catalogue léger) | ~80–120 tokens (input) + ~30 tokens (output) |

L'Archiviste déjà en place pour la bio fait déjà un appel API par message. Le second appel pour l'ego est **de même nature et même coût** — pas d'infrastructure supplémentaire.

---

## 8. Ce qu'on ne fait PAS (délibérément)

- **Pas de flags booléens style OGMA** : EUGENIA n'a pas besoin de gérer des restrictions d'accès ou de permissions (usage domestique, auteur connu). Les faits textuels sont plus naturels pour un compagnon d'écriture.
- **Pas de compilation automatique par l'IA** : l'ego ne se modifie pas seul — l'auteur reste maître.
- **Pas de panneau UI pour l'ego pour l'instant** : édition manuelle de `ego_identity.json` suffit pour la phase initiale.
- **Pas de déduplication FAISS** : l'ego est petit (< 10 groupes, < 50 faits) — pas besoin d'index sémantique.
