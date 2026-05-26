# EUGENIA

<p align="center">
  <img src="assets/logo.png" alt="EUGENIA Logo" width="200"/>
</p>

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
While EUGENIA includes its own editing environment, it is designed to run alongside, attach to, and augment your favorite third-party software—including web browsers like **Chrome** and **Firefox**, word processors like **Microsoft Word**, **LibreOffice**, **Scrivener**, or **Google Docs**, and text or code editors:
* **OCR & Graphic Screen Capture:** Instantly grab screenshots of your active writing software to let EUGENIA analyze your current paragraphs.
* **Active Window Monitoring & Overlay:** Hook into other application windows to read text, annotate, or provide overlays directly on top of your workspace.
* **Smart Clipboard Tracking:** Read and update your system clipboard to speed up copy-paste iteration loops.

<p align="center">
  <img src="assets/capture.png" alt="EUGENIA Main Interface" width="800"/>
  <br/>
  <em>EUGENIA Main Interface</em>
</p>

<p align="center">
  <img src="assets/capture_firefox.png" alt="EUGENIA Companion Overlay (Firefox Integration)" width="800"/>
  <br/>
  <em>EUGENIA Companion Overlay attached to Firefox</em>
</p>

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

### Prerequisites & Installation Ease
* **Python 3.10+:** Required. If you do not have Python installed, EUGENIA's installer (`install.bat`) will **automatically attempt to install it for you** using the Windows Package Manager (`winget`).
* **C++ Build Tools:** **NOT required** for typical installations! Libraries like `faiss-cpu` and `numpy` install directly using precompiled binary packages (wheels) from PyPI. 
* *Note: The only common Windows component required is the standard Microsoft Visual C++ Redistributable, which is already installed on almost all modern Windows systems.*

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
