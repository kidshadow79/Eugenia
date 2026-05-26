# Règles de design UI — EUGENIA

> Document de référence pour l'homogénéité visuelle du projet.
> À consulter avant tout ajout ou modification d'un composant d'interface.

---

## 1. Technologie d'icônes — règle centrale

### ✅ Méthode validée : QtAwesome (`qtawesome`)

Les icônes de l'interface EUGENIA utilisent **exclusivement la bibliothèque `qtawesome`**,
qui donne accès aux polices vectorielles Font Awesome 5 (préfixe `fa5s.`, `fa5r.`, `fa5b.`).

```python
import qtawesome as qta

btn = QPushButton()
btn.setIcon(qta.icon("fa5s.book", color="#858585", color_active="#ffffff"))
btn.setIconSize(QSize(18, 18))
btn.setText("")   # bouton icône seul : pas de texte
```

**Avantages** :
- Rendu vectoriel propre à toutes les résolutions / DPI
- Couleur contrôlée par le code (adaptable au thème clair/sombre)
- Cohérence visuelle totale — même famille de formes partout
- Professionnel : même approche que VS Code, JetBrains, Figma

### ❌ À bannir : les émojis Unicode comme labels de boutons

Les boutons `QPushButton("📎")`, `QPushButton("🔍")`, `QPushButton("👁")`, etc.
sont **interdits dans les nouveaux composants**. Raisons :

- Rendu dépendant de la police système (Windows/macOS donnent des résultats différents)
- Taille non contrôlable via QSS
- Aspect non professionnel, trop « app mobile »
- Incohérence visuelle avec les icônes de la sidebar

**Migration progressive** : les boutons emoji actuels (voir §6) seront remplacés au fur et à mesure.

---

## 2. Catalogue d'icônes utilisées

| Élément UI | Icône FA | Identifiant |
|---|---|---|
| Bible | `fa5s.book` | sidebar |
| Historique | `fa5s.history` | sidebar |
| Sources | `fa5s.folder-open` | sidebar |
| Profil de style | `fa5s.pen-nib` | sidebar |
| Mémoire | `fa5s.brain` | sidebar |
| Statistiques | `fa5s.chart-bar` | sidebar |
| Paramètres | `fa5s.cog` | sidebar bas |
| Joindre un fichier | `fa5s.paperclip` | ai_panel |
| Scanner (Ghost Writer) | `fa5s.search` | ai_panel |
| Afficher/masquer badges | `fa5s.eye` / `fa5s.eye-slash` | ai_panel |
| Capture éditeur | `fa5s.camera` | ai_panel |
| Analyser mémoire | `fa5s.search` | memory_panel |
| Sourdine source | `fa5s.volume-mute` | sources_panel |
| Supprimer | `fa5s.trash-alt` | partout |
| Modifier / éditer | `fa5s.pen` | partout |
| Fermer / retirer | `fa5s.times` | pill, modals |
| Nouvelle conversation | `fa5s.plus` | history_panel |
| Reprendre | `fa5s.undo` | history_panel |
| Réinitialiser | `fa5s.redo` | settings_panel |

> Pour chercher une icône : https://fontawesome.com/v5/search (filtre "Free")
> Syntaxe qtawesome : `"fa5s."` + nom sans préfixe (`fa5s.trash-alt`, pas `fa5s.fa-trash-alt`)

---

## 3. Tailles d'icônes

| Contexte | `setIconSize` | Notes |
|---|---|---|
| Sidebar (IconBar) | `QSize(22, 22)` | Boutons 48×48 |
| Boutons de la barre d'outils chat (bottom_row) | `QSize(16, 16)` | Boutons compacts |
| Boutons dans les panneaux (memory, sources…) | `QSize(14, 14)` | Intégrés dans des lignes de texte |
| Boutons de dialog / modal | `QSize(16, 16)` | — |

---

## 4. Couleurs d'icônes

Les couleurs sont toujours lues depuis le dictionnaire de thème (`get_colors(theme)`),
**jamais hardcodées** dans les composants — sauf pour le fallback initial de la sidebar
en attendant le premier `apply_theme()`.

| Clé thème | Usage |
|---|---|
| `icon_color` | Icône inactive / repos |
| `icon_active` | Icône active (sidebar checked) |
| `text_muted` | Icône désactivée (setEnabled(False)) |
| `accent` | Icône d'action principale (ex: envoyer) |

---

## 5. Typographie des boutons

### Boutons texte (avec label)
- Police : héritée du thème (`font_family`, `font_size`)
- Pas de majuscules forcées (pas de `text-transform: uppercase`)
- Labels : français, minuscules, concis — ex: `"Envoyer"`, `"Sauvegarder"`, `"Analyser"`

### Boutons icône seul (sans texte)
- `btn.setText("")` — aucun texte
- `btn.setToolTip("Description de l'action")` — **obligatoire** pour l'accessibilité
- `btn.setCursor(Qt.CursorShape.PointingHandCursor)` — **obligatoire**

### Boutons mixtes (icône + texte)
- Icône à gauche, texte à droite : `btn.setLayoutDirection(Qt.LeftToRight)` (défaut)
- Espacement : géré par le style QSS via `padding` et `spacing`
- Exemple : `"Analyser"` avec `fa5s.search` à gauche

---

## 6. Inventaire des boutons emoji à migrer (dette technique)

Ces boutons utilisent encore des émojis Unicode et doivent être remplacés progressivement
par des icônes qtawesome lors des prochains cycles de travail sur ces composants.

| Fichier | Bouton | Emoji actuel | Icône FA cible |
|---|---|---|---|
| `ui/ai_panel.py` | `_attach_btn` | 📎 | `fa5s.paperclip` |
| `ui/ai_panel.py` | `_ghost_scan_btn` | 🔍 | `fa5s.search` |
| `ui/ai_panel.py` | `_ghost_hide_btn` | 👁 | `fa5s.eye` / `fa5s.eye-slash` |
| `ui/ai_panel.py` | `_screenshot_btn` | 📷 | `fa5s.camera` |
| `ui/ai_panel.py` | `_pill_close_btn` | ✕ | `fa5s.times` (ou garder ✕ — acceptable pour les fermetures) |
| `ui/ai_panel.py` | `_insert_btn` | ↓ texte | `fa5s.arrow-down` + texte |
| `ui/memory_panel.py` | `_scan_btn` | 🔍 texte | `fa5s.search` + texte |
| `ui/sources_panel.py` | `_mute_btn` | 🔇 texte | `fa5s.volume-mute` + texte |
| `ui/ingest_dialog.py` | `_btn_yes_bible` | 📖 texte | `fa5s.book` + texte |
| `ui/ingest_dialog.py` | `_btn_no_bible` | 🗂 texte | `fa5s.folder` + texte |
| `ui/approval_gate.py` | `_accept_btn` | ✓ texte | `fa5s.check` + texte |

> **Priorité de migration** : ai_panel (visible en permanence) > memory_panel > le reste.

---

## 7. Structure des panneaux

### Principe général : colonnes VS Code

```
[ IconBar 48px ] [ ContextPanel collapsible ] [ EditorZone flex ] [ AIPanel collapsible ]
```

- Colonnes 2, 3, 4 dans un `QSplitter` horizontal
- Col 3 absorbe l'espace libre quand un panneau se ferme
- Pas de bordures entre panneaux — séparation par couleur de fond

### Couleurs de fond par zone

| Zone | Clé thème | Dark par défaut |
|---|---|---|
| IconBar | `bg_sidebar` | `#333333` |
| ContextPanel | `bg_panel` | `#252526` |
| EditorZone | transparent (app tierce) | — |
| AIPanel | `bg_panel` | `#252526` |
| InputArea (zone saisie) | `bg_input_area` | `#2d2d2d` |
| ChatHistory | `bg_chat` | `#1e1e1e` |

### Séparateurs

- Entre sections d'un panneau : `QFrame` ligne horizontale (`HLine`), objectName `"Separator"`
- Pas de séparateurs verticaux décoratifs visibles

---

## 8. Règles de layout dans les panneaux

- Marges internes standard : `8px` sur les 4 côtés
- Espacement entre widgets : `6px` (rowspacing) ou `4px` (tight)
- Les étiquettes de section (titres) : `objectName="SectionTitle"`, uppercase, `letter-spacing: 1px`, taille `xs`
- Les labels de champ : `objectName="FieldLabel"`, couleur `text_muted`
- Pas de `QGroupBox` — les sections sont délimitées par des `SectionTitle` + `Separator`

---

## 9. Pills et badges

Les pills (pièces jointes, annotations) suivent ce pattern :
- Fond légèrement contrasté par rapport au panneau parent
- Bordure 1px `border_input`
- Border-radius `4px`
- Icône (qtawesome) + texte tronqué + bouton fermer `fa5s.times` à droite
- **Ne jamais mettre un bouton icône à droite d'un texte dans un `ui.row` avec `items-center`** — rogné sur certains DPI

---

## 10. Ce qu'on ne fait pas

| Pratique | Raison |
|---|---|
| Émojis Unicode comme icônes de boutons | Rendu non contrôlable, aspect non professionnel |
| `QGroupBox` pour délimiter les sections | Visuellement lourd, difficile à thématiser |
| Couleurs hardcodées dans les composants | Impossible à thématiser |
| Boutons sans tooltip | Inaccessible pour les boutons icône seuls |
| Labels tronqués sans tooltip | L'utilisateur ne peut pas lire le contenu complet |
| `QPushButton` stylé comme lien | Utiliser un vrai label cliquable si nécessaire |
