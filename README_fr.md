# EUGENIA

*Lire ce document en [English](README.md)*

**EUGENIA** est un assistant d'écriture IA avancé et doté d'une mémoire cognitive profonde, conçu spécifiquement pour les auteurs, écrivains et créateurs. Grâce à une architecture cognitive évoluée, EUGENIA apprend au fil de vos interactions, se souvient de vos sessions passées et vous apporte une aide à l'écriture hautement personnalisée avec une continuité de contexte exceptionnelle.

## Fonctionnalités Clés

* **🧠 Mémoire Cognitive Profonde :** Eugenia se rappelle qui vous êtes et ce dont vous avez parlé. Elle combine une base de données relationnelle, un système de document persistant ("Bibles") et une recherche vectorielle sémantique (FAISS) pour retrouver vos sessions passées de façon naturelle.
* **📚 Le Système Archiviste :** Un module sophistiqué de lecture et d'écriture interne qui analyse vos textes, synthétise l'information et injecte le contexte utile dans la discussion sans surcharger la mémoire de travail de l'IA.
* **🎭 Ego & Personnalité Dynamiques :** EUGENIA adapte son ton et son comportement grâce à l' "Ego Manager", qui compile dynamiquement ses instructions système en fonction de règles établies et des interactions passées.
* **🎨 Interface Moderne et Thémable :** Une interface graphique premium développée en PySide6, entièrement personnalisable avec des modes clair, sombre et des thèmes spéciaux (comme le Glassmorphism), optimisant les contrastes et le confort de lecture.
* **🔒 Confidentialité et Sécurité :** Conçu pour respecter votre vie privée. Les données personnelles, clés API et journaux d'activité (logs) internes sont gérés de manière sécurisée.

## Démarrage Rapide (Windows)

L'installation d'EUGENIA est optimisée pour être simple et directe sur Windows.

1. **Cloner le dépôt :**
   ```bash
   git clone https://github.com/kidshadow79/Eugenia.git
   cd Eugenia
   ```

2. **Installation :**
   Double-cliquez simplement sur le raccourci `Installer_EUGENIA`, ou lancez `install.bat` depuis votre terminal.
   Le script créera automatiquement un environnement virtuel Python isolé (`venv`) et y installera toutes les dépendances requises listées dans `requirements.txt`.

3. **Lancement d'EUGENIA :**
   Une fois installé, double-cliquez sur le raccourci `Demarrer_EUGENIA`, ou exécutez `run.bat`. Le script activera l'environnement virtuel et démarrera l'application principale.

## Prérequis
- Python 3.10+
- Les dépendances sont gérées automatiquement lors de l'installation.

## Aperçu de l'Architecture
- **UI/UX (`ui/`)** : Contient la fenêtre principale de l'application, les styles, thèmes et les boîtes de dialogue de configuration.
- **Moteur Principal (`core/`)** : Contient le moteur IA, le cache de contexte, la gestion de l'Ego, l'indexation vectorielle sémantique (FAISS) et les interfaces d'API.

## Licence
*Tous droits réservés.*
