# Création de l'installeur universel EUGENIA

> **Objectif :** Permettre à n'importe quel utilisateur Windows — sans Python, sans outils de développement, sans connaissances techniques — d'installer et de lancer EUGENIA en un double-clic.

---

## Stack technique utilisée

| Outil | Version | Rôle |
|---|---|---|
| Python (conda) | 3.13.5 | Environnement de développement |
| PyInstaller | 6.20.0 | Compilation de l'exe autonome |
| Inno Setup | 6 | Génération de l'installeur `.exe` |
| PyQt6 | 6.11.0 | Framework UI |
| rapidfuzz | 3.14.5 | Matching flou (fuzzy matching) |
| faiss | - | Index vectoriel local |

L'environnement de build est isolé dans `C:\APP\EUGENIA\build_venv\` (venv dédié, séparé de conda).

---

## Problème 1 — `ModuleNotFoundError: No module named 'email'` (et `http`, `html`)

### Symptôme

Au lancement de `EUGENIA.exe` sur un PC cible (sans Python installé), crash immédiat :

```
ModuleNotFoundError: No module named 'email'
```

Même chose pour `http` et `html`.

### Cause racine

Python 3.13 a **gelé** (frozen) plusieurs modules de la bibliothèque standard (`email`, `http`, `html`, etc.). Ces modules sont intégrés directement dans l'interpréteur C et non plus fournis comme fichiers `.py`.

PyInstaller détecte ces modules comme `excluded` (déjà dans l'interpréteur) et ne les emballe pas dans le bundle. Or, sur une machine sans Python, il n'y a **aucun fichier Python** pour les fournir.

Sur la machine de développement (avec conda), l'application fonctionnait car Python trouvait ces modules dans l'environnement conda. Sur la machine cible : crash.

### Solution appliquée

Copie forcée des sources `.py` depuis `miniconda3/Lib/` directement dans le répertoire `_internal/` du bundle PyInstaller, via le fichier `EUGENIA.spec` :

```python
# EUGENIA.spec — stdlib Python 3.13 : copie forcée depuis conda
_conda_lib = Path(sys.base_prefix) / 'Lib'
if not (_conda_lib / 'email' / '__init__.py').exists():
    _conda_lib = Path(r'C:\Users\utilisateur\miniconda3\Lib')

_excluded_stdlib_pkgs = ['email', 'http', 'html']
stdlib_force_datas = []
for _pkg in _excluded_stdlib_pkgs:
    _pkg_path = _conda_lib / _pkg
    if _pkg_path.exists():
        stdlib_force_datas.append((str(_pkg_path), _pkg))
```

Ces datas sont ensuite ajoutées à `all_datas` dans la configuration `Analysis`.

---

## Problème 2 — `ModuleNotFoundError: No module named 'rapidfuzz'`

### Symptôme

Même scénario : l'exe fonctionnait parfaitement sur la machine de dev, mais crashait sur le PC cible :

```
ModuleNotFoundError: No module named 'rapidfuzz'
```

L'import incriminé se trouvait dans `core/ghost_matcher.py` :

```python
from rapidfuzz import fuzz
```

### Cause racine (en deux couches)

**Couche 1 — `rapidfuzz` absent du `build_venv`**

`rapidfuzz` n'était pas dans `requirements.txt` et donc pas installé dans l'environnement de build isolé. PyInstaller ne pouvait pas le trouver du tout.

**Couche 2 — `collect_all('rapidfuzz')` manquant dans le spec**

Même après avoir installé `rapidfuzz` dans `build_venv`, PyInstaller ne trouvait que les fichiers `.pyd` (extensions C compilées, détectées automatiquement) mais **pas les fichiers Python** (`__init__.py`, `fuzz.py`, `process.py`, etc.) qui sont nécessaires au runtime.

Sans `collect_all('rapidfuzz')`, PyInstaller n'emballait pas les sources Python du package dans le PYZ. Sur la machine de dev, conda fournissait ces fichiers en fallback. Sur la machine cible : aucun fallback → crash.

### Pourquoi ce comportement est trompeur

C'est le piège classique des packages hybrides Python/C :
- PyInstaller détecte les `.pyd` (C extensions) → les inclut dans `binaries`
- Il NE détecte PAS automatiquement les `.py` du même package si le hook PyInstaller n'est pas invoqué
- Sur la machine de dev, le conda env masque le problème en fournissant les `.py` manquants
- Sur une machine vierge : `ModuleNotFoundError` au premier `import rapidfuzz`

### Solution appliquée

**Étape 1** — Installation dans `build_venv` :

```powershell
& "C:\APP\EUGENIA\build_venv\Scripts\pip.exe" install rapidfuzz
```

**Étape 2** — Ajout dans `requirements.txt` :

```
rapidfuzz>=3.0.0
```

**Étape 3** — Ajout de `collect_all` dans `EUGENIA.spec` :

```python
rf_datas, rf_bins, rf_hiddens = collect_all('rapidfuzz')

all_datas    = (...) + rf_datas    + (...)
all_binaries = (...) + rf_bins
all_hiddens  = (...) + rf_hiddens  + (...)
```

`collect_all` force PyInstaller à embarquer **tout** le contenu du package : sources Python, extensions C (`.pyd`), ressources, et les hooks internes (`rapidfuzz.__pyinstaller`).

---

## Problème 3 — Faux positif lors du test de l'exe

### Symptôme

Lors des premiers tests en PowerShell avec `Start-Process`, la commande ne levait aucune erreur même pour un chemin d'exe inexistant — `$p.HasExited` retournait `True` immédiatement.

### Cause

`Start-Process` dans PowerShell ne lève pas d'exception si l'exe n'existe pas dans certaines configurations. La vérification `$p.HasExited` était donc trompeuse.

### Solution

Utilisation de `cmd /c "EUGENIA.exe 2>&1"` avec capture de la sortie console, qui reflète fidèlement la sortie réelle de l'exe.

---

## Configuration finale du spec

Le fichier `EUGENIA.spec` final gère tous les packages tiers de manière robuste :

```python
from PyInstaller.utils.hooks import collect_all

# Packages avec ressources dynamiques ou architecture hybride
qt_datas,    qt_bins,    qt_hiddens    = collect_all('PyQt6')
qta_datas,   qta_bins,   qta_hiddens   = collect_all('qtawesome')
mpl_datas,   mpl_bins,   mpl_hiddens   = collect_all('matplotlib')
faiss_datas, faiss_bins, faiss_hiddens = collect_all('faiss')
rf_datas,    rf_bins,    rf_hiddens    = collect_all('rapidfuzz')

# numpy et PIL sont gérés par les hooks intégrés PyInstaller
# (hook-numpy.py, hook-PIL.py, etc.) — pas besoin de collect_all manuel
```

### Tableau récapitulatif des packages

| Package | Méthode | Raison |
|---|---|---|
| `PyQt6` | `collect_all` | Ressources Qt (DLLs, plugins, traductions, QML...) |
| `qtawesome` | `collect_all` | Fichiers de polices d'icônes (.ttf, .json) |
| `matplotlib` | `collect_all` | Backends, polices, données mpl-data |
| `faiss` | `collect_all` | Extensions C avec variantes AVX2 |
| `rapidfuzz` | `collect_all` | Sources Python + extensions C (fuzz.py, etc.) |
| `numpy` | Hook auto PyInstaller | Hook `hook-numpy.py` intégré |
| `PIL` / Pillow | Hook auto PyInstaller | Hooks `hook-PIL.py`, `hook-PIL.Image.py` |
| `pywin32` | Hook auto contrib | `win32api`, `win32gui`, `win32clipboard`... |
| `email`, `http`, `html` | Copie forcée source | Modules gelés en Python 3.13 |

---

## Commandes de build

### Rebuild complet PyInstaller

```powershell
Remove-Item -Recurse -Force "C:\APP\EUGENIA\dist", "C:\APP\EUGENIA\build" -ErrorAction SilentlyContinue
& "C:\APP\EUGENIA\build_venv\Scripts\pyinstaller.exe" "C:\APP\EUGENIA\EUGENIA.spec" `
    --noconfirm `
    --distpath "C:\APP\EUGENIA\dist" `
    --workpath "C:\APP\EUGENIA\build" `
    2>&1 | Tee-Object -FilePath "C:\APP\EUGENIA\build_venv_log.txt"
Write-Host "=== EXIT CODE: $LASTEXITCODE ==="
```

### Génération de l'installeur Inno Setup

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "C:\APP\EUGENIA\installer\EUGENIA_setup.iss"
```

L'installeur généré : `C:\APP\EUGENIA\dist\installer\EUGENIA_Setup_0.1.0.exe`

---

## Test de validation

```powershell
cd "C:\APP\EUGENIA\dist\EUGENIA"
cmd /c "EUGENIA.exe 2>&1" | Select-Object -First 15
```

Sortie attendue (succès) :

```
[INFO] core.logger — Logging initialisé
[INFO] faiss.loader — Loading faiss with AVX2 support.
[INFO] faiss.loader — Successfully loaded faiss with AVX2 support.
[INFO] __main__ — === Démarrage EUGENIA v0.1.0 ===
```

---

## Règles à retenir pour les futurs packages

> Si un nouveau `ModuleNotFoundError` apparaît sur la machine cible mais PAS sur la machine de dev, appliquer systématiquement ce protocole :

1. Vérifier que le package est dans `requirements.txt`
2. L'installer dans `build_venv` : `build_venv\Scripts\pip.exe install <package>`
3. Si le package est hybride Python+C (contient à la fois des `.py` et des `.pyd`) → ajouter `collect_all('<package>')` dans le spec
4. Si c'est un module stdlib qui crashe → vérifier s'il est gelé en Python 3.13 et appliquer le pattern `stdlib_force_datas`
5. Rebuilder et tester avec `cmd /c "EUGENIA.exe 2>&1"`

---

## Résultat final

L'installeur `EUGENIA_Setup_0.1.0.exe` :
- Ne requiert **aucune installation préalable** (pas de Python, pas de Visual C++, pas de redistribuables manuels)
- Fonctionne sur tout Windows 10/11 x64
- Se lance par double-clic, installe EUGENIA dans `Program Files`, crée un raccourci bureau et menu démarrer
- Embarque l'intégralité du runtime Python 3.13 et de toutes les dépendances
