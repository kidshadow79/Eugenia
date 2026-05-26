# EUGENIA

*Read this in [Français](README_fr.md)*

**EUGENIA** is an advanced, memory-augmented AI writing assistant designed specifically for novelists, authors, and creators. Far more than a simple text editor, EUGENIA is engineered as a cognitive companion that adapts to your creative voice, remembers your lore, and integrates seamlessly with your existing writing tools.

---

## Key Pillars

### 1. Dual-Core ("Bicephalous") Memory System
EUGENIA separates knowledge into two distinct cognitive hemispheres to ensure she never confuses the creator with the creation:
* **Relational Memory (The Creator's Sphere):** Remembers details about *you*, the author. It tracks your writing rules, stylistic preferences, vocabulary habits, feedback, and personal background. This makes interactions feel deeply personalized and continuous.
* **Project Memory (The Novel's Sphere):** Stores the lore, characters, timeline, and plot of your project. This is managed via dynamic SQLite databases and custom-built **Bibles** containing structured world-building information.

### 2. Adaptive Ego Engine
The **Ego Manager** acts as the AI's internal behavioral filter. Instead of relying on static system prompts, EUGENIA dynamically compiles a set of behavioral rules based on your ongoing interactions. She adapts her tone, suggestions, and critique styles to match your creative needs.

### 3. Native Third-Party Companion Integration
While EUGENIA includes its own editing environment, it is designed to run alongside and augment your favorite writing software (e.g., **Scrivener, MS Word, Google Docs, or text editors**):
* **OCR & Graphic Screen Capture:** Instantly grab screenshots of your active writing software to let EUGENIA analyze your current paragraphs.
* **Active Window Monitoring & Overlay:** Hook into other application windows to read text, annotate, or provide overlays directly on top of your workspace.
* **Smart Clipboard Tracking:** Read and update your system clipboard to speed up copy-paste iteration loops.

### 4. Semantic Text Chunking & Bibles
To handle massive manuscript lengths without exceeding LLM context windows:
* Long texts are split into semantic chunks, vectorized, and stored using a **FAISS** database.
* The system pulls only the most relevant context chunks related to your current cursor position or search query.
* Easily compile, index, and query specialized Bibles (character sheets, geography logs, magic systems).

---

## 🛠️ Configuration & Model Selection

EUGENIA allows you to configure your preferred Large Language Models (LLMs) and embedding providers using API keys.

### ⚠️ Critical Embedding Advice
* **Recommended Model:** We highly recommend using **`mistral-embed`** for text vectorization.
* **CRITICAL WARNING:** Do **NOT** change your embedding model once a project has started. Changing the embedding model (e.g., switching from OpenAI's `text-embedding-3-small` to `mistral-embed`) will corrupt vector compatibility. You will be forced to re-index all your project text and Bibles from scratch.

---

## 👥 Multi-Profile & Multi-Project
EUGENIA supports managing multiple authors (profiles) and multiple universes/novels (projects) on the same machine. Each project maintains its own isolated database, vector store, and configuration.

---

## 🚀 Getting Started (Windows)

### Prerequisites & Build Tools
To compile and run native libraries (like `faiss-cpu` or `numpy`) smoothly, please ensure you have the following installed on your Windows machine:
1. **Python 3.10 or 3.11** (Ensure it is added to your system `PATH`).
2. **Microsoft C++ Build Tools:**
   * Download and install the [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).
   * During installation, check the **"Desktop development with C++"** workload. This is required to compile Python C-extensions if pre-built wheels are not available.
3. **Microsoft Visual C++ Redistributable** installed.

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/kidshadow79/Eugenia.git
   cd Eugenia
   ```

2. **Run Installer:**
   Double-click the `Installer_EUGENIA` shortcut (or run `install.bat`). 
   This setup script configures an isolated python Virtual Environment (`venv`) and installs the dependencies from `requirements.txt`.

3. **Launch:**
   Double-click the `Demarrer_EUGENIA` shortcut (or run `run.bat`).
