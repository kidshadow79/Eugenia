# EUGENIA

*Read this in [Français](README_fr.md)*

**EUGENIA** is an advanced, memory-augmented AI writing assistant designed specifically for authors, writers, and creators. By utilizing a deep cognitive architecture, EUGENIA learns from your interactions, remembers your past sessions, and provides highly personalized assistance with an unparalleled continuity of context.

## Key Features

* **🧠 Deep Cognitive Memory:** Eugenia remembers who you are and what you've discussed. She leverages a combination of a Relational Database, a persistent "Bible" document system, and Semantic Vector Search (FAISS) to recall past sessions naturally.
* **📚 The Archivist System:** A sophisticated internal reading and writing system that analyzes texts, synthesizes information, and injects relevant context seamlessly into the conversation flow without cluttering the working memory.
* **🎭 Dynamic Ego & Personality:** EUGENIA adapts her tone and behavior through the "Ego Manager," dynamically compiling system prompts based on established rules and past interactions.
* **🎨 Modern & Themed Interface:** A premium, fully customizable PySide6 GUI featuring light, dark, and specialized themes (e.g., Glassmorphism) with high contrast and readability.
* **🔒 Privacy & Security First:** Designed to run with your privacy in mind. Personal data, API keys, and internal logs are handled securely.

## Getting Started (Windows)

EUGENIA is built for an effortless setup experience on Windows.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/kidshadow79/Eugenia.git
   cd Eugenia
   ```

2. **Installation:**
   Simply double-click the `Installer_EUGENIA` shortcut, or run `install.bat` from the terminal. 
   This will automatically create an isolated Python Virtual Environment (`venv`) and install all required dependencies listed in `requirements.txt`.

3. **Running EUGENIA:**
   Once installed, double-click the `Demarrer_EUGENIA` shortcut, or run `run.bat`. The script will activate the environment and launch the main application.

## Requirements
- Python 3.10+
- Dependencies are managed automatically via `requirements.txt`.

## Architecture Overview
- **UI/UX (`ui/`)**: Houses the main application window, custom themes, and setting dialogs.
- **Core Engine (`core/`)**: Contains the AI Engine, Cognitive Cache, Ego Manager, Vector Indexing (FAISS), and API Providers.

## License
*All rights reserved.*
