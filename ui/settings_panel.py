"""
settings_panel.py — Panneau de configuration des IA (colonne 2)

3 sections indépendantes :
    - IA Principale   (cerveau chaud — parle à l'auteur)
    - IA Archiviste   (cerveau froid — analytique, silencieux)
    - IA Embed        (vectorisation — futur FAISS)

Chaque section :
    Provider  [dropdown]
    Clé API   [champ masqué] [afficher/masquer]
    Modèle    [dropdown — peuplé selon le provider]

Sauvegarde via le bouton en bas → émet config_saved(dict).
MainWindow écoute ce signal pour recharger les engines.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QComboBox, QLineEdit, QPushButton, QFrame, QTextEdit,
    QTabWidget, QButtonGroup, QRadioButton, QCheckBox, QDoubleSpinBox,
    QSizePolicy, QSlider, QSpinBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QCursor
import logging
import qtawesome as qta

logger = logging.getLogger(__name__)

from core.i18n import tr
from core.providers import (
    get_provider_labels, get_chat_models, get_embed_models,
    PROVIDERS, PROVIDER_ORDER,
)
from core.config_manager import load_config, save_config
from core.config_manager import load_prompts, save_prompts, reset_prompt
from core.config_manager import _PROMPT_DEFAULTS as _PROMPT_DEFS
from core.model_fetcher import ModelFetchWorker
from core.profile_manager import load_profile, save_profile
from core.web_search import WEB_PROVIDERS, WEB_PROVIDER_ORDER, WebKeyTestWorker
from ui.font_config import FONT_FAMILIES

# ─── Styles ───────────────────────────────────────────────────────────────────

# ─── Styles ───────────────────────────────────────────────────────────────────
# Les styles de SettingsPanel sont gérés globalement par themes.py.
# Pas de setStyleSheet local nécessaire.

# Zones de couleurs exposables à l'utilisateur (clé palette, libellé)
_COLOR_ZONES = [
    ("item_select",  tr("Sélection")),
    ("accent",       tr("Accent / boutons")),
    ("bg_window",    tr("Fond principal")),
    ("bg_panel",     tr("Fond panneaux")),
    ("icon_bar_bg",  tr("Fond barre onglets")),
    ("text_primary", tr("Texte principal")),
    ("icon_color",   tr("Icônes (barre)")),
    ("icon_active",  tr("Icônes actives")),
    ("notif_bg",     tr("Notification — fond")),
    ("notif_text",   tr("Notification — texte")),
    ("badge_bg",     tr("Annotation — fond encadré")),
    ("badge_text",   tr("Annotation — texte encadré")),
]


# ─── Section Recherche Web ────────────────────────────────────────────────────

class _WebSearchSection(QWidget):
    """
    Section de configuration de la recherche web (/web).
    Provider + cle API + nombre max de resultats.
    """

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        self._test_worker: WebKeyTestWorker | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(6)

        title = QLabel(tr("Recherche Web (/web)"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        desc = QLabel(
            tr("Tapez <code>/web [recherche]</code> dans le chat pour interroger "
            "le web avant qu'EUGENIA reponde.")
        )
        desc.setWordWrap(True)
        desc.setObjectName("FieldLabel")
        layout.addWidget(desc)

        # Provider
        row_prov = QHBoxLayout()
        row_prov.setSpacing(8)
        lbl_prov = QLabel(tr("Provider"))
        lbl_prov.setObjectName("FieldLabel")
        row_prov.addWidget(lbl_prov)
        self._combo_provider = QComboBox()
        for pid in WEB_PROVIDER_ORDER:
            self._combo_provider.addItem(WEB_PROVIDERS[pid]["label"], userData=pid)
        self._combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        row_prov.addWidget(self._combo_provider)
        layout.addLayout(row_prov)

        # Cle API (dans un QWidget pour pouvoir masquer toute la ligne)
        self._key_widget = QWidget()
        row_key = QHBoxLayout(self._key_widget)
        row_key.setContentsMargins(0, 0, 0, 0)
        row_key.setSpacing(8)
        lbl_key = QLabel(tr("Cle API"))
        lbl_key.setObjectName("FieldLabel")
        row_key.addWidget(lbl_key)
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("...")
        self._key_edit.textChanged.connect(self._reset_test_status)
        row_key.addWidget(self._key_edit)
        self._toggle_btn = QPushButton("o")
        self._toggle_btn.setObjectName("ToggleBtn")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.toggled.connect(
            lambda checked: self._key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        row_key.addWidget(self._toggle_btn)
        layout.addWidget(self._key_widget)

        # Lien "Obtenir une cle"
        self._key_url_lbl = QLabel("")
        self._key_url_lbl.setObjectName("FieldLabel")
        self._key_url_lbl.setOpenExternalLinks(True)
        layout.addWidget(self._key_url_lbl)

        # Max resultats
        row_max = QHBoxLayout()
        row_max.setSpacing(8)
        lbl_max = QLabel(tr("Resultats max"))
        lbl_max.setObjectName("FieldLabel")
        from PyQt6.QtWidgets import QSpinBox
        self._spin_max = QSpinBox()
        self._spin_max.setRange(3, 10)
        self._spin_max.setValue(5)
        self._spin_max.setMaximumWidth(70)
        row_max.addWidget(lbl_max)
        row_max.addStretch()
        row_max.addWidget(self._spin_max)
        layout.addLayout(row_max)

        # Bouton test + indicateur statut
        self._test_widget = QWidget()
        row_test = QHBoxLayout(self._test_widget)
        row_test.setContentsMargins(0, 0, 0, 0)
        row_test.setSpacing(8)
        self._test_btn = QPushButton(qta.icon("fa5s.vial", color="#888"), tr("Tester la cle"))
        self._test_btn.setObjectName("SecondaryBtn")
        self._test_btn.clicked.connect(self._on_test_key)
        row_test.addWidget(self._test_btn)
        self._test_status_lbl = QLabel("")
        self._test_status_lbl.setObjectName("FieldLabel")
        self._test_status_lbl.setWordWrap(True)
        row_test.addWidget(self._test_status_lbl, stretch=1)
        layout.addWidget(self._test_widget)

        # Init etat initial
        self._on_provider_changed(0)

    def _on_provider_changed(self, _index: int) -> None:
        pid = self._combo_provider.currentData()
        meta = WEB_PROVIDERS.get(pid, {})
        needs_key = meta.get("needs_key", True)
        self._key_widget.setVisible(needs_key)
        self._test_widget.setVisible(needs_key)
        self._reset_test_status()
        key_url = meta.get("key_url", "")
        if key_url and needs_key:
            self._key_url_lbl.setText(tr('<a href="{}">Obtenir une cle API</a>').format(key_url))
            self._key_url_lbl.setVisible(True)
        else:
            self._key_url_lbl.setVisible(False)

    def _reset_test_status(self) -> None:
        self._test_status_lbl.setText("")
        self._test_status_lbl.setStyleSheet("")

    def _on_test_key(self) -> None:
        pid     = self._combo_provider.currentData()
        api_key = self._key_edit.text().strip()
        if not api_key:
            self._test_status_lbl.setText(tr("Entrez une cle API d'abord"))
            self._test_status_lbl.setStyleSheet("color: #ff9800;")
            return
        self._test_btn.setEnabled(False)
        self._test_status_lbl.setText(tr("Test en cours…"))
        self._test_status_lbl.setStyleSheet("")
        self._test_worker = WebKeyTestWorker(pid, api_key)
        self._test_worker.test_ok.connect(self._on_key_test_ok)
        self._test_worker.test_error.connect(self._on_key_test_error)
        self._test_worker.start()

    def _on_key_test_ok(self) -> None:
        self._test_status_lbl.setText(tr("Cle valide"))
        self._test_status_lbl.setStyleSheet("color: #4caf50; font-weight: bold;")
        self._test_btn.setEnabled(True)

    def _on_key_test_error(self, msg: str) -> None:
        short = msg[:100] if len(msg) > 100 else msg
        self._test_status_lbl.setText(tr("Erreur : {}").format(short))
        self._test_status_lbl.setStyleSheet("color: #e53935; font-weight: bold;")
        self._test_btn.setEnabled(True)

    # ── API publique ──────────────────────────────────────────────────────────

    def get_values(self) -> dict:
        return {
            "provider":    self._combo_provider.currentData(),
            "api_key":     self._key_edit.text().strip(),
            "max_results": self._spin_max.value(),
        }

    def set_values(self, cfg: dict) -> None:
        provider = cfg.get("provider", "duckduckgo")
        idx = self._combo_provider.findData(provider)
        if idx >= 0:
            self._combo_provider.setCurrentIndex(idx)
        self._key_edit.setText(cfg.get("api_key", ""))
        try:
            self._spin_max.setValue(int(cfg.get("max_results", 5)))
        except (ValueError, TypeError):
            self._spin_max.setValue(5)


# ─── Widget section (1 IA) ───────────────────────────────────────────────────

class _IASection(QWidget):
    """
    Bloc de configuration pour une IA (principale, archiviste ou embed).
    Gère l'interaction provider → modèles.
    """

    def __init__(self, title: str, embed_mode: bool = False):
        """
        Args:
            title:      titre affiché ("IA Principale", etc.)
            embed_mode: si True, liste les modèles embed au lieu des modèles chat
        """
        super().__init__()
        self._embed_mode = embed_mode
        self._fetch_worker: ModelFetchWorker | None = None
        self._setup_ui(title)

    def _setup_ui(self, title: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(6)

        # Titre de section
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        layout.addWidget(title_label)

        # Provider
        row_provider = QHBoxLayout()
        row_provider.setSpacing(8)
        lbl_prov = QLabel(tr("Provider"))
        lbl_prov.setObjectName("FieldLabel")
        row_provider.addWidget(lbl_prov)
        self._combo_provider = QComboBox()
        for pid, plabel in get_provider_labels():
            if self._embed_mode and not PROVIDERS[pid]["embed_models"]:
                continue   # Masquer les providers sans embed
            self._combo_provider.addItem(plabel, userData=pid)
        self._combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        row_provider.addWidget(self._combo_provider)
        layout.addLayout(row_provider)

        # Clé API
        row_key = QHBoxLayout()
        row_key.setSpacing(8)
        lbl_key = QLabel(tr("Cle API"))
        lbl_key.setObjectName("FieldLabel")
        row_key.addWidget(lbl_key)
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("sk-...")
        row_key.addWidget(self._key_edit)
        self._toggle_btn = QPushButton("o")
        self._toggle_btn.setObjectName("ToggleBtn")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setToolTip(tr("Afficher/masquer la clé"))
        self._toggle_btn.clicked.connect(self._on_toggle_key)
        row_key.addWidget(self._toggle_btn)
        layout.addLayout(row_key)

        # Modèle
        row_model = QHBoxLayout()
        row_model.setSpacing(8)
        lbl_model = QLabel(tr("Modele"))
        lbl_model.setObjectName("FieldLabel")
        row_model.addWidget(lbl_model)
        self._combo_model = QComboBox()
        self._combo_model.setMinimumContentsLength(20)
        row_model.addWidget(self._combo_model)
        self._refresh_btn = QPushButton("~")
        self._refresh_btn.setObjectName("RefreshBtn")
        self._refresh_btn.setToolTip(tr("Récupérer les modèles via API"))
        self._refresh_btn.clicked.connect(self._on_refresh_models)
        row_model.addWidget(self._refresh_btn)
        layout.addLayout(row_model)

        # Hint clé API
        self._hint_label = QLabel("")
        self._hint_label.setObjectName("HintLabel")
        layout.addWidget(self._hint_label)

        # Peupler les modèles pour le provider initial
        self._on_provider_changed(0)

    # ─── Interactions ─────────────────────────────────────────────────────────

    def _on_provider_changed(self, _index: int):
        provider_id = self._combo_provider.currentData()
        if not provider_id:
            return

        # Mettre à jour le hint de format de clé
        hint = PROVIDERS[provider_id].get("key_hint", "")
        key_url = PROVIDERS[provider_id].get("key_url", "")
        self._hint_label.setText(tr("format: {}  |  {}").format(hint, key_url) if hint else "")
        self._key_edit.setPlaceholderText(hint or "...")

        # Peupler les modèles
        models = (
            get_embed_models(provider_id)
            if self._embed_mode
            else get_chat_models(provider_id)
        )
        self._combo_model.clear()
        for m in models:
            self._combo_model.addItem(m)

    def _on_toggle_key(self, checked: bool):
        if checked:
            self._key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_btn.setText("*")
        else:
            self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_btn.setText("o")

    def _on_refresh_models(self):
        """Lance la récupération live des modèles via API."""
        api_key = self._key_edit.text().strip()
        if not api_key:
            self._hint_label.setText(tr("[!] Entrez la clé API avant d'actualiser."))
            return

        provider_id = self._combo_provider.currentData()
        if not provider_id:
            return

        # Désactiver pendant le chargement
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText(".")
        self._hint_label.setText(tr("Chargement..."))

        self._fetch_worker = ModelFetchWorker(
            provider_id=provider_id,
            api_key=api_key,
            embed_mode=self._embed_mode,
        )
        self._fetch_worker.models_ready.connect(self._on_models_fetched)
        self._fetch_worker.fetch_error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    def _on_models_fetched(self, models: list):
        """Récupération réussie — repeupler le combo."""
        current = self._combo_model.currentText()
        self._combo_model.clear()
        for m in models:
            self._combo_model.addItem(m)
        # Restaurer la sélection si elle existe encore
        idx = self._combo_model.findText(current)
        if idx >= 0:
            self._combo_model.setCurrentIndex(idx)
        hint = PROVIDERS.get(self._combo_provider.currentData() or "", {}).get("key_hint", "")
        self._hint_label.setText(tr("{} modèles chargés").format(len(models)))
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("~")

    def _on_fetch_error(self, msg: str):
        """Erreur de récupération — afficher sans planter."""
        self._hint_label.setText(tr("[!] {}").format(msg))
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("~")

    # ─── Données ──────────────────────────────────────────────────────────────

    def get_values(self) -> dict:
        """Retourne la config de cette section."""
        return {
            "backend":  "api",
            "provider": self._combo_provider.currentData() or "openai",
            "api_key":  self._key_edit.text().strip(),
            "model":    self._combo_model.currentText().strip(),
        }

    def set_values(self, cfg: dict):
        """Applique une config sauvegardée à cette section."""
        # Provider
        provider = cfg.get("provider", "openai")
        for i in range(self._combo_provider.count()):
            if self._combo_provider.itemData(i) == provider:
                self._combo_provider.setCurrentIndex(i)
                break

        # Clé API
        self._key_edit.setText(cfg.get("api_key", ""))

        # Modèle (après que le combo soit peuplé via _on_provider_changed)
        model = cfg.get("model", "")
        idx = self._combo_model.findText(model)
        if idx >= 0:
            self._combo_model.setCurrentIndex(idx)
        elif model:
            # Modèle personnalisé non dans la liste → ajouter en tête
            self._combo_model.insertItem(0, model)
            self._combo_model.setCurrentIndex(0)


# ─── Section prompts ─────────────────────────────────────────────────────────

# Labels affichés dans l'UI pour chaque clé de prompt
# (label, tooltip)
_PROMPT_LABELS = {
    "ia_principale": (
        tr("Prompt IA Principale"),
        tr("Instruction systeme envoyee au debut de chaque conversation.\n"
        "Definit le role, le ton et les regles de conduite de l'IA compagnon.\n"
        "Toujours presente en tete des messages envoyes a l'API."),
    ),
    "archiviste_writer": (
        tr("Prompt Archiviste \u2014 extraction"),
        tr("Instruction utilisee lorsque l'Archiviste analyse un passage du manuscrit\n"
        "pour en extraire des faits (personnages, lieux, evenements, relations).\n"
        "Active a chaque envoi de message contenant du texte a analyser."),
    ),
    "archiviste_reader": (
        tr("Prompt Archiviste \u2014 contexte"),
        tr("Instruction utilisee lorsque l'Archiviste resume les informations pertinentes\n"
        "de la Bible pour repondre a une question de l'auteur.\n"
        "Injecte le contexte biblique dans la reponse de l'IA principale."),
    ),
    "archiviste_relational": (
        tr("Prompt Archiviste \u2014 profil auteur"),
        tr("Instruction pour construire et mettre a jour le profil relationnel de l'auteur :\n"
        "ses preferences, ses habitudes d'ecriture, ses retours recurrents.\n"
        "Alimente la base relationnelle (relational.db)."),
    ),
    "session_summarizer": (
        tr("Prompt Resumation de session"),
        tr("Instruction utilisee en fin de session (a la fermeture de l'app) pour\n"
        "produire un resume compact de la conversation.\n"
        "Ce resume est reinjete en contexte au demarrage de la session suivante."),
    ),
    "style_profiler": (
        tr("Prompt Profil de style"),
        tr("Instruction utilisee pour analyser un echantillon du manuscrit et\n"
        "produire un profil stylistique de l'auteur (rythme, registre, ton...).\n"
        "Le profil genere est injecte dans chaque conversation pour que l'IA\n"
        "respecte le style de l'auteur dans ses suggestions."),
    ),
}


# ─── Section Ego ────────────────────────────────────────────────────────────────────

class _EgoSection(QWidget):
    """
    Section 'Instructions personnalisees EUGENIA' dans l'onglet Instructions.

    Affiche l'instruction ego en cours (lecture seule) et propose
    un bouton pour lancer le scan manuellement.
    """

    scan_requested = pyqtSignal()
    heartbeat_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(8)

        # Separateur
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("Separator")
        layout.addWidget(sep)

        # Titre
        title = QLabel(tr("Instructions personnalisees EUGENIA"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            tr("EUGENIA analyse vos echanges et formule ses propres instructions "
            "comportementales pour mieux vous accompagner. "
            "L'analyse se declenche automatiquement apres quelques minutes "
            "d'inactivite et a la fermeture de l'application.")
        )
        desc.setWordWrap(True)
        desc.setObjectName("FieldLabel")
        layout.addWidget(desc)

        # Zone editable (autorise les corrections par l'utilisateur)
        self._instruction_view = QTextEdit()
        self._instruction_view.setObjectName("PromptEdit")
        self._instruction_view.setReadOnly(False)
        self._instruction_view.setMinimumHeight(80)
        self._instruction_view.setMaximumHeight(160)
        self._instruction_view.setPlaceholderText(
            tr("Aucune instruction generee pour l'instant. Vous pouvez ecrire la votre ici.")
        )
        layout.addWidget(self._instruction_view)


        # Ligne : Delai Heartbeat
        hb_row = QHBoxLayout()
        hb_row.setSpacing(8)
        hb_lbl = QLabel(tr("Délai d'inactivité avant scan (minutes) :"))
        hb_lbl.setObjectName("FieldLabel")
        self._hb_spin = QSpinBox()
        self._hb_spin.setRange(1, 60)
        self._hb_spin.setValue(3)
        self._hb_spin.valueChanged.connect(self.heartbeat_changed.emit)
        hb_row.addWidget(hb_lbl)
        hb_row.addWidget(self._hb_spin)
        hb_row.addStretch()
        layout.addLayout(hb_row)

        # Ligne : statut + bouton Scanner

        row = QHBoxLayout()
        row.setSpacing(8)
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("FieldLabel")
        row.addWidget(self._status_lbl)
        row.addStretch()
        self._scan_btn = QPushButton(tr("Scanner maintenant"))
        self._scan_btn.setObjectName("ResetPromptBtn")
        self._scan_btn.setIcon(qta.icon("fa5s.sync", color="#a0a0a0"))
        self._scan_btn.setIconSize(QSize(14, 14))
        self._scan_btn.setToolTip(
            tr("Lance une analyse de la session courante pour mettre a jour "
            "les instructions comportementales d'EUGENIA.")
        )
        self._scan_btn.clicked.connect(self.scan_requested)
        row.addWidget(self._scan_btn)
        layout.addLayout(row)

    # ── API publique ──────────────────────────────────────────────────────────────

    def set_ego_data(
        self,
        instruction: str,
        scan_count: int,
        last_scanned_at: str,
    ) -> None:
        """Met a jour l'affichage de l'instruction et du statut."""
        self._instruction_view.setPlainText(instruction)
        if scan_count:
            date_str = last_scanned_at[:16].replace("T", " ") if last_scanned_at else "?"
            self._status_lbl.setText(
                tr("Derniere analyse : {}  |  {} analyse(s)").format(date_str, scan_count)
            )
        else:
            self._status_lbl.setText(tr("Aucune analyse effectuee."))

    def set_scanning(self, scanning: bool) -> None:
        """Desactive/reactivie le bouton et met a jour l'icone."""
        self._scan_btn.setEnabled(not scanning)
        icon_name = "fa5s.spinner" if scanning else "fa5s.sync"
        self._scan_btn.setIcon(qta.icon(icon_name, color="#a0a0a0"))
        self._scan_btn.setText(tr("Analyse en cours...") if scanning else tr("Scanner maintenant"))

    def get_instruction(self) -> str:
        """Retourne le texte de l'instruction Ego."""
        return self._instruction_view.toPlainText()

    def set_heartbeat(self, minutes: int) -> None:
        self._hb_spin.blockSignals(True)
        self._hb_spin.setValue(minutes)
        self._hb_spin.blockSignals(False)

    def get_heartbeat(self) -> int:
        return self._hb_spin.value()


# ─── Section Prompts ─────────────────────────────────────────────────────────────────

class _PromptsSection(QWidget):
    """
    4 éditeurs de texte, un par prompt système.
    Bouton « Réinitialiser » par prompt → restaure _PROMPT_DEFAULTS.
    """

    def __init__(self):
        super().__init__()
        self._editors: dict[str, QTextEdit] = {}
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(10)

        title = QLabel(tr("Prompts systeme"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        for key, (label, tooltip) in _PROMPT_LABELS.items():
            # Titre + bouton reset sur une ligne
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setObjectName("FieldLabel")
            lbl.setToolTip(tooltip)
            row.addWidget(lbl)
            row.addStretch()
            reset_btn = QPushButton(tr("Reinitialiser"))
            reset_btn.setObjectName("ResetPromptBtn")
            reset_btn.clicked.connect(lambda checked, k=key: self._on_reset(k))
            row.addWidget(reset_btn)
            layout.addLayout(row)

            # Zone de texte
            editor = QTextEdit()
            editor.setObjectName("PromptEdit")
            editor.setMinimumHeight(90)
            editor.setMaximumHeight(150)
            editor.setToolTip(tooltip)
            layout.addWidget(editor)
            self._editors[key] = editor

    def _load(self):
        prompts = load_prompts()
        for key, editor in self._editors.items():
            editor.setPlainText(prompts.get(key, ""))

    def _on_reset(self, key: str):
        default = _PROMPT_DEFS.get(key, "")
        self._editors[key].setPlainText(default)

    def get_values(self) -> dict[str, str]:
        return {k: e.toPlainText() for k, e in self._editors.items()}

    def set_values(self, data: dict[str, str]) -> None:
        """Peuple les éditeurs depuis un dict (ex. chargement backup)."""
        for key, editor in self._editors.items():
            if key in data:
                editor.setPlainText(data[key])


# ─── Section Interface ────────────────────────────────────────────────────────

class _InterfaceSection(QWidget):
    """Preferences visuelles : theme clair / sombre + taille police."""

    color_overrides_live_changed = pyqtSignal()  # couleurs modifiées en direct (hors save)

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(12)

        # Theme
        title = QLabel(tr("Apparence"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(16)
        lbl = QLabel(tr("Theme"))
        lbl.setObjectName("FieldLabel")
        lbl.setToolTip(
            tr("Choix du theme de l'interface.\n"
            "Le changement est applique immediatement a la sauvegarde.")
        )
        row.addWidget(lbl)

        self._theme_combo = QComboBox()
        self._theme_combo.addItem(tr("Glassmorphism (Sombre)"), "glass")
        self._theme_combo.addItem(tr("Glassmorphism (Clair)"), "glass_light")
        self._theme_combo.addItem(tr("Flat macOS (Sombre)"), "flat_mac")
        self._theme_combo.addItem(tr("Flat macOS (Clair)"), "flat_mac_light")
        self._theme_combo.addItem(tr("Cyber Pro"), "cyber")
        self._theme_combo.addItem(tr("Classique Sombre"), "dark")
        self._theme_combo.addItem(tr("Classique Clair"), "light")
        self._theme_combo.setFixedWidth(200)
        
        row.addWidget(self._theme_combo)
        row.addStretch()
        layout.addLayout(row)

        # Taille de police
        row_font = QHBoxLayout()
        row_font.setSpacing(12)
        lbl_font = QLabel(tr("Taille de police"))
        lbl_font.setObjectName("FieldLabel")
        lbl_font.setToolTip(tr("Taille de la police de l'interface (12 a 16 px)."))
        row_font.addWidget(lbl_font)

        self._font_slider = QSlider(Qt.Orientation.Horizontal)
        self._font_slider.setMinimum(12)
        self._font_slider.setMaximum(16)
        self._font_slider.setValue(13)
        self._font_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._font_slider.setTickInterval(1)
        self._font_slider.setSingleStep(1)
        self._font_slider.setFixedWidth(120)
        row_font.addWidget(self._font_slider)

        self._font_value_lbl = QLabel(tr("13 px"))
        self._font_value_lbl.setObjectName("FieldLabel")
        self._font_value_lbl.setFixedWidth(36)
        row_font.addWidget(self._font_value_lbl)
        row_font.addStretch()

        self._font_slider.valueChanged.connect(
            lambda v: self._font_value_lbl.setText(tr("{} px").format(v))
        )

        layout.addLayout(row_font)

        # Famille de police
        row_family = QHBoxLayout()
        row_family.setSpacing(12)
        lbl_family = QLabel(tr("Police"))
        lbl_family.setObjectName("FieldLabel")
        lbl_family.setToolTip(tr("Police de l'interface."))
        row_family.addWidget(lbl_family)

        self._font_family_combo = QComboBox()
        for fam in FONT_FAMILIES:
            self._font_family_combo.addItem(fam)
        self._font_family_combo.setFixedWidth(160)
        row_family.addWidget(self._font_family_combo)
        row_family.addStretch()
        layout.addLayout(row_family)

        # Interligne chat
        row_lh = QHBoxLayout()
        row_lh.setSpacing(12)
        lbl_lh = QLabel(tr("Interligne chat"))
        lbl_lh.setObjectName("FieldLabel")
        lbl_lh.setToolTip(tr("Interligne des bulles de conversation (1.2 a 2.2)."))
        row_lh.addWidget(lbl_lh)

        self._chat_lh_slider = QSlider(Qt.Orientation.Horizontal)
        self._chat_lh_slider.setMinimum(10)
        self._chat_lh_slider.setMaximum(22)
        self._chat_lh_slider.setValue(16)   # 1.6 par defaut
        self._chat_lh_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._chat_lh_slider.setTickInterval(2)
        self._chat_lh_slider.setSingleStep(1)
        self._chat_lh_slider.setFixedWidth(120)
        row_lh.addWidget(self._chat_lh_slider)

        self._chat_lh_lbl = QLabel("1.6")
        self._chat_lh_lbl.setObjectName("FieldLabel")
        self._chat_lh_lbl.setFixedWidth(36)
        row_lh.addWidget(self._chat_lh_lbl)
        row_lh.addStretch()

        self._chat_lh_slider.valueChanged.connect(
            lambda v: self._chat_lh_lbl.setText(f"{v / 10:.1f}")
        )
        layout.addLayout(row_lh)

        # Opacité notification
        row_op = QHBoxLayout()
        row_op.setSpacing(12)
        lbl_op = QLabel(tr("Opacité annotations"))
        lbl_op.setObjectName("FieldLabel")
        lbl_op.setToolTip(tr("Transparence des encadrés d'annotations Ghost Writer (30 à 100 %)."))
        row_op.addWidget(lbl_op)

        self._notif_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._notif_opacity_slider.setMinimum(30)
        self._notif_opacity_slider.setMaximum(100)
        self._notif_opacity_slider.setValue(85)  # 85 % par défaut
        self._notif_opacity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._notif_opacity_slider.setTickInterval(10)
        self._notif_opacity_slider.setSingleStep(5)
        self._notif_opacity_slider.setFixedWidth(120)
        row_op.addWidget(self._notif_opacity_slider)

        self._notif_opacity_lbl = QLabel("85 %")
        self._notif_opacity_lbl.setObjectName("FieldLabel")
        self._notif_opacity_lbl.setFixedWidth(40)
        row_op.addWidget(self._notif_opacity_lbl)
        row_op.addStretch()

        self._notif_opacity_slider.valueChanged.connect(
            lambda v: self._notif_opacity_lbl.setText(f"{v} %")
        )
        layout.addLayout(row_op)


        self._color_btns: dict[str, QPushButton] = {}
        for key, label_text in _COLOR_ZONES:
            row_c = QHBoxLayout()
            row_c.setSpacing(8)
            lbl_c = QLabel(label_text)
            lbl_c.setObjectName("FieldLabel")
            lbl_c.setFixedWidth(130)
            row_c.addWidget(lbl_c)

            btn_c = QPushButton()
            btn_c.setFixedSize(28, 20)
            btn_c.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_c.setToolTip(tr("Cliquer pour changer '{}'").format(label_text))
            btn_c.clicked.connect(lambda checked, k=key: self._pick_color(k))
            self._color_btns[key] = btn_c
            row_c.addWidget(btn_c)

            btn_reset_c = QPushButton("↺")
            btn_reset_c.setFixedSize(22, 20)
            btn_reset_c.setObjectName("ResetPromptBtn")
            btn_reset_c.setToolTip(tr("Réinitialiser"))
            btn_reset_c.clicked.connect(lambda checked, k=key: self._reset_color(k))
            row_c.addWidget(btn_reset_c)
            row_c.addStretch()
            layout.addLayout(row_c)

        btn_reset_all = QPushButton(tr("Réinitialiser toutes les couleurs"))
        btn_reset_all.setObjectName("ResetPromptBtn")
        btn_reset_all.clicked.connect(self._reset_all_colors)
        layout.addWidget(btn_reset_all)

        # ── Avancé ───────────────────────────────────────────────────────────────────
        sep_adv = QFrame()
        sep_adv.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep_adv)

        title_adv = QLabel(tr("Avancé"))
        title_adv.setObjectName("SectionTitle")
        layout.addWidget(title_adv)

        row_scroll = QHBoxLayout()
        row_scroll.setSpacing(12)
        lbl_scroll = QLabel(tr("Vitesse synchro scroll"))
        lbl_scroll.setObjectName("FieldLabel")
        lbl_scroll.setToolTip(
            tr("Sensibilité du suivi scroll des annotations Ghost Writer.\n"
            "1 = très lent, 5 = normal, 10 = très rapide.")
        )
        row_scroll.addWidget(lbl_scroll)

        self._scroll_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._scroll_speed_slider.setMinimum(1)
        self._scroll_speed_slider.setMaximum(10)
        self._scroll_speed_slider.setValue(5)
        self._scroll_speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._scroll_speed_slider.setTickInterval(1)
        self._scroll_speed_slider.setSingleStep(1)
        self._scroll_speed_slider.setFixedWidth(120)
        row_scroll.addWidget(self._scroll_speed_slider)

        self._scroll_speed_lbl = QLabel("5")
        self._scroll_speed_lbl.setObjectName("FieldLabel")
        self._scroll_speed_lbl.setFixedWidth(24)
        row_scroll.addWidget(self._scroll_speed_lbl)
        row_scroll.addStretch()

        self._scroll_speed_slider.valueChanged.connect(
            lambda v: self._scroll_speed_lbl.setText(str(v))
        )
        layout.addLayout(row_scroll)

        row_margin = QHBoxLayout()
        row_margin.setSpacing(12)
        lbl_margin = QLabel(tr("Marge droite annotations"))
        lbl_margin.setObjectName("FieldLabel")
        lbl_margin.setToolTip(tr("Distance entre les annotations Ghost Writer et le bord droit (px)."))
        row_margin.addWidget(lbl_margin)

        self._badge_margin_r_slider = QSlider(Qt.Orientation.Horizontal)
        self._badge_margin_r_slider.setMinimum(0)
        self._badge_margin_r_slider.setMaximum(200)
        self._badge_margin_r_slider.setValue(30)
        self._badge_margin_r_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._badge_margin_r_slider.setTickInterval(10)
        self._badge_margin_r_slider.setSingleStep(1)
        self._badge_margin_r_slider.setFixedWidth(120)
        row_margin.addWidget(self._badge_margin_r_slider)

        self._badge_margin_r_lbl = QLabel("30 px")
        self._badge_margin_r_lbl.setObjectName("FieldLabel")
        self._badge_margin_r_lbl.setFixedWidth(40)
        row_margin.addWidget(self._badge_margin_r_lbl)
        row_margin.addStretch()

        self._badge_margin_r_slider.valueChanged.connect(
            lambda v: self._badge_margin_r_lbl.setText(f"{v} px")
        )
        layout.addLayout(row_margin)

        row_ocr = QHBoxLayout()
        row_ocr.setSpacing(12)
        lbl_ocr = QLabel(tr("Moteur OCR"))
        lbl_ocr.setObjectName("FieldLabel")
        lbl_ocr.setToolTip(
            tr("Windows OCR : rapide (~0.1s), natif Windows 10/11.\n"
            "EasyOCR : précis mais lent (3–8s, nécessite PyTorch).")
        )
        row_ocr.addWidget(lbl_ocr)

        self._ocr_combo = QComboBox()
        self._ocr_combo.addItem(tr("Windows OCR (rapide)"), "winrt")
        self._ocr_combo.addItem(tr("EasyOCR (précis, lent)"), "easyocr")
        self._ocr_combo.setFixedWidth(200)
        row_ocr.addWidget(self._ocr_combo)
        row_ocr.addStretch()
        layout.addLayout(row_ocr)

        layout.addStretch()

        # Actualiser les swatches quand le thème bascule
        self._theme_combo.currentIndexChanged.connect(self._refresh_color_buttons)
        self._refresh_color_buttons()

    def get_theme(self) -> str:
        return self._theme_combo.currentData()

    def set_theme(self, theme: str):
        idx = self._theme_combo.findData(theme)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        else:
            self._theme_combo.setCurrentIndex(0) # Default to glass

    def get_font_size(self) -> int:
        return self._font_slider.value()

    def set_font_size(self, size: int):
        self._font_slider.setValue(max(12, min(16, size)))
        self._font_value_lbl.setText(f"{self._font_slider.value()} px")

    def get_font_family(self) -> str:
        return self._font_family_combo.currentText()

    def set_font_family(self, family: str):
        idx = self._font_family_combo.findText(family)
        if idx >= 0:
            self._font_family_combo.setCurrentIndex(idx)

    def get_chat_lh(self) -> float:
        return self._chat_lh_slider.value() / 10.0

    def set_chat_lh(self, lh: float):
        v = max(10, min(22, round(lh * 10)))
        self._chat_lh_slider.setValue(v)
        self._chat_lh_lbl.setText(f"{v / 10:.1f}")

    def get_badge_opacity(self) -> float:
        """Retourne l'opacité des badges en float 0.0–1.0."""
        return self._notif_opacity_slider.value() / 100.0

    def set_badge_opacity(self, pct: int) -> None:
        """Charge l'opacité des badges (0–100)."""
        v = max(30, min(100, pct))
        self._notif_opacity_slider.setValue(v)
        self._notif_opacity_lbl.setText(f"{v} %")

    def get_scroll_speed(self) -> int:
        return self._scroll_speed_slider.value()

    def set_scroll_speed(self, speed: int) -> None:
        v = max(1, min(10, speed))
        self._scroll_speed_slider.setValue(v)
        self._scroll_speed_lbl.setText(str(v))

    def get_badge_margin_r(self) -> int:
        return self._badge_margin_r_slider.value()

    def set_badge_margin_r(self, margin: int) -> None:
        v = max(0, min(200, margin))
        self._badge_margin_r_slider.setValue(v)
        self._badge_margin_r_lbl.setText(tr("{} px").format(v))









    def get_ocr_engine(self) -> str:
        """Retourne l'identifiant du backend OCR sélectionné."""
        return self._ocr_combo.currentData()

    def set_ocr_engine(self, backend: str) -> None:
        """Sélectionne le backend OCR dans la combo."""
        idx = self._ocr_combo.findData(backend)
        if idx >= 0:
            self._ocr_combo.setCurrentIndex(idx)

    def _get_current_theme(self) -> str:
        return self.get_theme()

    def _refresh_color_buttons(self) -> None:
        from ui.theme_config import ThemeConfig
        from ui.themes import get_colors
        theme = self._get_current_theme()
        palette = get_colors(theme)
        overrides = ThemeConfig.instance().get_overrides(theme)
        merged = {**palette, **overrides}
        for key, btn in self._color_btns.items():
            color = merged.get(key, "#888888")
            border = "2px solid #4ec9b0" if key in overrides else "1px solid #666"
            btn.setStyleSheet(
                f"background-color: {color}; border: {border}; border-radius: 2px;"
            )

    def _pick_color(self, key: str) -> None:
        from PyQt6.QtWidgets import QColorDialog, QApplication
        from PyQt6.QtGui import QColor
        from ui.theme_config import ThemeConfig
        from ui.themes import get_colors, build_stylesheet
        from ui.font_config import FontConfig
        theme = self._get_current_theme()
        palette = get_colors(theme)
        overrides = ThemeConfig.instance().get_overrides(theme)
        current = overrides.get(key, palette.get(key, "#888888"))
        color = QColorDialog.getColor(QColor(current), self, tr("Couleur — {}").format(key))
        if color.isValid():
            ThemeConfig.instance().set_override(theme, key, color.name())
            self._refresh_color_buttons()
            QApplication.instance().setStyleSheet(
                build_stylesheet(theme, FontConfig.instance())
            )
            self._autosave_color_overrides()

    def _reset_color(self, key: str) -> None:
        from PyQt6.QtWidgets import QApplication
        from ui.theme_config import ThemeConfig
        from ui.themes import build_stylesheet
        from ui.font_config import FontConfig
        theme = self._get_current_theme()
        ThemeConfig.instance().reset_override(theme, key)
        self._refresh_color_buttons()
        QApplication.instance().setStyleSheet(
            build_stylesheet(theme, FontConfig.instance())
        )
        self._autosave_color_overrides()

    def _reset_all_colors(self) -> None:
        from PyQt6.QtWidgets import QApplication
        from ui.theme_config import ThemeConfig
        from ui.themes import build_stylesheet
        from ui.font_config import FontConfig
        theme = self._get_current_theme()
        ThemeConfig.instance().reset_all(theme)
        self._refresh_color_buttons()
        QApplication.instance().setStyleSheet(
            build_stylesheet(theme, FontConfig.instance())
        )
        self._autosave_color_overrides()

    def get_color_overrides(self) -> dict:
        from ui.theme_config import ThemeConfig
        return ThemeConfig.instance().dump()

    def _autosave_color_overrides(self) -> None:
        """Persiste immédiatement les color_overrides dans app_config.json."""
        from ui.theme_config import ThemeConfig
        from core.config_manager import load_config, save_config
        cfg = load_config()
        cfg["color_overrides"] = ThemeConfig.instance().dump()
        save_config(cfg)
        self.color_overrides_live_changed.emit()

    def set_color_overrides(self, data: dict) -> None:
        from ui.theme_config import ThemeConfig
        ThemeConfig.instance().load(data)
        self._refresh_color_buttons()


# ─── Profil auteur ───────────────────────────────────────────────────────────

class _ProfileSection(QWidget):
    """
    Formulaire de profil auteur — transversal a tous les projets.
    Sauvegarde independante du bouton global (profil != config IA).
    """

    saved = pyqtSignal()   # emis apres sauvegarde reussie

    def __init__(self, author_slug: str, author_name: str, parent=None):
        super().__init__(parent)
        self._author_slug = author_slug
        self._author_name = author_name
        self._setup_ui()
        if author_slug:
            self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        def _field(label_text: str, placeholder: str, min_h: int = 60) -> QTextEdit:
            lbl = QLabel(label_text)
            lbl.setObjectName("FieldLabel")
            layout.addWidget(lbl)
            field = QTextEdit()
            field.setPlaceholderText(placeholder)
            field.setMinimumHeight(min_h)
            field.setMaximumHeight(min_h + 40)
            layout.addWidget(field)
            return field

        intro = QLabel(
            tr("Profil de <b>{}</b> — ces informations sont injectees en contexte systeme de l'IA principale pour chaque session, quel que soit le projet ouvert.").format(self._author_name)
        )
        intro.setWordWrap(True)
        intro.setObjectName("GuideIntro")
        layout.addWidget(intro)

        self._bio   = _field(tr("Qui es-tu ?"),
            tr("Auteur de science-fiction, j'ecris des romans hard SF explorant la conscience artificielle."),
            70)
        self._prefs = _field(tr("Ce que tu attends d'EUGENIA"),
            tr("Suggestions courtes et directes. Pas de reformulations creuses. Poser des questions plutot que proposer du texte tout fait."),
            70)
        self._tone  = _field(tr("Ton souhaite"),
            tr("Tutoiement, direct, sans condescendance."),
            45)
        self._topics = _field(tr("Genres et themes d'ecriture"),
            tr("science-fiction, hard SF, fantasy sombre, philosophie"),
            45)

        self._status = QLabel("")
        self._status.setObjectName("StatusLabel")
        layout.addWidget(self._status)

        btn = QPushButton(tr("Sauvegarder le profil"))
        btn.setObjectName("SaveBtn")
        btn.clicked.connect(self._save)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addStretch()

    def _load(self):
        p = load_profile(self._author_slug)
        self._bio.setPlainText(p.get("bio", ""))
        self._prefs.setPlainText(p.get("preferences", ""))
        self._tone.setPlainText(p.get("tone", ""))
        self._topics.setPlainText(p.get("topics", ""))

    def _save(self):
        if not self._author_slug:
            return
        save_profile(self._author_slug, {
            "bio":         self._bio.toPlainText().strip(),
            "preferences": self._prefs.toPlainText().strip(),
            "tone":        self._tone.toPlainText().strip(),
            "topics":      self._topics.toPlainText().strip(),
        })
        from datetime import datetime
        self._status.setText(tr("Profil sauvegarde a {}").format(datetime.now().strftime('%H:%M:%S')))
        self.saved.emit()


# ─── Guide ────────────────────────────────────────────────────────────────────

_GUIDE_HTML = tr("""
<style>
  body  { margin: 0; padding: 0; }
  h2    { font-size: 13px; font-weight: bold; margin: 14px 0 4px 0; }
  h3    { font-size: 12px; font-weight: bold; margin: 10px 0 2px 0; }
  p     { font-size: 12px; margin: 2px 0 6px 0; line-height: 1.5; }
  code  { font-family: Consolas, monospace; font-size: 12px;
          background: rgba(128,128,128,0.15); border-radius: 3px;
          padding: 1px 4px; }
  .cmd  { font-family: Consolas, monospace; font-size: 12px; font-weight: bold; }
  hr    { border: none; border-top: 1px solid rgba(128,128,128,0.3);
          margin: 10px 0; }
</style>

<h2>Commandes speciales</h2>
<p>Certains prefixes en debut de message activent des comportements etendus.</p>

<hr/>

<h3><span class="cmd">/web</span> &mdash; Recherche en ligne</h3>
<p>Prefixe un message pour qu'EUGENIA interroge le Web avant de repondre.
   Utile pour verifier une information recente, trouver une reference ou
   completer un passage qui demande de la factualite.<br/>
   <b>Exemple :</b> <code>/web influences du romantisme allemand sur Victor Hugo</code></p>

<hr/>

<h3><span class="cmd">/mem</span> &mdash; Recherche en memoire</h3>
<p>Force une recherche dans la memoire du projet (notes, personnages, lieux,
   scenes deja travaillees) avant de repondre. A utiliser quand vous cherchez
   une information que vous avez deja fournie a EUGENIA.<br/>
   <b>Exemple :</b> <code>/mem couleur des yeux d'Alma</code></p>

<hr/>

<h3><span class="cmd">/edit</span> &mdash; Mode edition co-auteur</h3>
<p>Ouvre un nouveau document en mode edition. EUGENIA devient co-autrice :
   ses reponses modifient directement le document. Utilisez la barre de
   micro-commandes de l'editeur pour des instructions rapides (raccourcir,
   rendre plus lyrique, corriger, developper).<br/>
   <b>Exemple :</b> <code>/edit Prologue du roman</code></p>

<hr/>

<h3><span class="cmd">/edition</span> &mdash; Rouvrir un document edite</h3>
<p>Recharge en mode edition un document deja existant, identifie par son titre
   exact. La liste des documents edites is also accessible dans le panneau
   Sources (double-clic pour rouvrir).<br/>
   <b>Exemple :</b> <code>/edition Prologue du roman</code></p>

<hr/>

<h3><span class="cmd">/stat</span> &mdash; Statistique personnalisee</h3>
<p>Demande a EUGENIA de generer une statistique personnalisee a partir des informations
   que vous lui fournissez dans le message ou le contexte de la conversation.
   Le resultat est sauvegarde dans le panneau <b>Statistiques</b> (barre gauche)
   et affichable en graphique (double-clic sur l'entree).<br/>
   EUGENIA choisit automatiquement le type de graphique le plus adapte :
   camembert pour des proportions, barres pour des comparaisons, courbe pour des
   evolutions dans le temps.<br/>
   <b>Exemples :</b><br/>
   <code>/stat fais un camembert des categories sociales de ma famille : 40% paysans, 30% nobles, 20% artisans, 10% clerge</code><br/>
   <code>/stat compare les ventes de mes trois romans : roman A 1200 ex., roman B 850 ex., roman C 2100 ex.</code></p>

  <hr/>

  <h2>Mémorisation Naturelle</h2>
  <p>EUGENIA dispose désormais d'une mémoire autonome. Si vous lui dites "mémorise ça" ou "retiens cette information", elle utilisera une balise interne secrète pour archiver définitivement la donnée dans sa mémoire relationnelle.</p>
  <p>Vous n'avez rien de spécial à faire : lorsqu'elle déclenche cette action, une bulle discrète <b>Information mémorisée : ...</b> apparaîtra en gris dans la conversation pour vous confirmer que c'est bien gravé.</p>

  <hr/>
  
  <p><i>D'autres commandes seront ajoutees ici au fil des developpements.</i></p>
""")


class _GuideSection(QWidget):
    """Contenu statique de l'onglet Guide."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        label = QLabel(_GUIDE_HTML)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setOpenExternalLinks(False)
        layout.addWidget(label)


# ─── Section Sauvegardes ─────────────────────────────────────────────────────

class _BackupSection(QWidget):
    """
    Export / restauration de la configuration (clés API et/ou instructions).
    Émet des signaux ; c'est SettingsPanel qui gère la lecture/écriture réelle.
    """

    save_requested = pyqtSignal(bool, bool, str)  # include_api, include_instructions, path
    load_requested = pyqtSignal(str)              # path du fichier à charger

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(8)

        title = QLabel(tr("Sauvegardes de configuration"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        desc = QLabel(
            tr("Exportez vos clés API et/ou instructions dans un fichier JSON, "
            "et restaurez-les sur un autre poste ou après réinstallation.")
        )
        desc.setWordWrap(True)
        desc.setObjectName("FieldLabel")
        layout.addWidget(desc)

        # Choix du contenu à sauvegarder
        lbl_what = QLabel(tr("Contenu à exporter :"))
        lbl_what.setObjectName("FieldLabel")
        layout.addWidget(lbl_what)

        btn_group = QButtonGroup(self)
        self._rb_api   = QRadioButton(tr("API uniquement  (clés, providers, modèles)"))
        self._rb_instr = QRadioButton(tr("Instructions uniquement  (prompts système)"))
        self._rb_both  = QRadioButton(tr("API + Instructions"))
        self._rb_both.setChecked(True)
        for rb in (self._rb_api, self._rb_instr, self._rb_both):
            btn_group.addButton(rb)
            layout.addWidget(rb)

        # Boutons Exporter / Restaurer
        row = QHBoxLayout()
        row.setSpacing(8)

        self._save_btn = QPushButton(
            qta.icon("fa5s.file-export", color="#888"), tr("Exporter…")
        )
        self._save_btn.setObjectName("SecondaryBtn")
        self._save_btn.clicked.connect(self._on_save)
        row.addWidget(self._save_btn)

        self._load_btn = QPushButton(
            qta.icon("fa5s.file-import", color="#888"), tr("Restaurer…")
        )
        self._load_btn.setObjectName("SecondaryBtn")
        self._load_btn.clicked.connect(self._on_load)
        row.addWidget(self._load_btn)

        row.addStretch()
        layout.addLayout(row)

        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("FieldLabel")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

    # ── Slots internes ────────────────────────────────────────────────────────

    def _on_save(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Exporter la configuration EUGENIA"),
            "eugenia_config_backup.json",
            tr("Sauvegarde EUGENIA (*.json)"),
        )
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        include_api  = self._rb_api.isChecked()  or self._rb_both.isChecked()
        include_instr = self._rb_instr.isChecked() or self._rb_both.isChecked()
        self.save_requested.emit(include_api, include_instr, path)

    def _on_load(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Restaurer une configuration EUGENIA"),
            "",
            tr("Sauvegarde EUGENIA (*.json)"),
        )
        if path:
            self.load_requested.emit(path)

    # ── API publique ─────────────────────────────────────────────────────────

    def set_status(self, msg: str, ok: bool = True) -> None:
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(
            f"color: {'#4caf50' if ok else '#e53935'}; font-style: italic;"
        )


# ─── Section Mémoire ─────────────────────────────────────────────────────────

class _MemorySection(QWidget):
    """Paramètres de la mémoire sémantique (déduplication FAISS)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── Titre ──────────────────────────────────────────────────────────
        title = QLabel(tr("Déduplication sémantique"))
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        # ── Description ────────────────────────────────────────────────────
        desc = QLabel(
            tr("Avant d'ingérer un nouveau document, chaque chunk est comparé "
            "sémantiquement aux chunks déjà indexés. Si la similarité dépasse "
            "le seuil, le chunk est ignoré (doublon quasi-identique).")
        )
        desc.setWordWrap(True)
        desc.setObjectName("FieldLabel")
        layout.addWidget(desc)

        # ── Activation ─────────────────────────────────────────────────────
        self._chk_enabled = QCheckBox(tr("Activer la déduplication sémantique"))
        self._chk_enabled.setChecked(True)
        self._chk_enabled.setToolTip(
            tr("Si décoché, les chunks sont ingérés sans vérification FAISS.\n"
            "Utile pour forcer la ré-ingestion d'un document modifié.")
        )
        layout.addWidget(self._chk_enabled)

        # ── Seuil ──────────────────────────────────────────────────────────
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel(tr("Seuil de similarité cosinus"))
        lbl.setObjectName("FieldLabel")

        # Icône info avec tooltip complet
        tip_icon = QLabel("ℹ")
        tip_icon.setObjectName("InfoTip")
        tip_icon.setToolTip(
            tr("Seuil cosinus [0.50 – 0.99] au-dessus duquel un chunk est\n"
            "considéré comme un doublon sémantique et ignoré lors de l'ingest.\n\n"
            "Exemples de valeurs :\n"
            "  0.93 (défaut) — quasi-identique (même texte légèrement reformulé)\n"
            "  0.85          — variantes stylistiques d'un même passage\n"
            "  0.70          — thèmes similaires (risque de faux positifs)\n\n"
            "↓ Réduire = filtrage plus agressif (exclut davantage)\n"
            "↑ Augmenter = filtrage plus strict (tolère plus de variantes)")
        )
        tip_icon.setCursor(QCursor(Qt.CursorShape.WhatsThisCursor))

        self._spin_threshold = QDoubleSpinBox()
        self._spin_threshold.setRange(0.50, 0.99)
        self._spin_threshold.setSingleStep(0.01)
        self._spin_threshold.setDecimals(2)
        self._spin_threshold.setValue(0.93)
        self._spin_threshold.setMinimumWidth(80)
        self._spin_threshold.setMaximumWidth(110)
        self._spin_threshold.setToolTip(
            tr("Seuil cosinus de déduplication (0.50 – 0.99).\n"
            "Défaut recommandé : 0.93")
        )

        row.addWidget(lbl)
        row.addWidget(tip_icon)
        row.addStretch()
        row.addWidget(self._spin_threshold)
        layout.addLayout(row)

        # ── Infobulle contextuelle ─────────────────────────────────────────
        info = QLabel(
            tr("💡 Astuce : augmentez le seuil (0.95–0.98) si des passages "
            "similaires mais distincts sont filtrés à tort. Réduisez-le "
            "(0.85–0.90) pour éliminer les reformulations proches.")
        )
        info.setObjectName("InfoTip")
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Séparateur ─────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("Separator")
        layout.addWidget(sep)

        # Connecter le toggle pour griser le spinbox
        self._chk_enabled.toggled.connect(self._spin_threshold.setEnabled)

        layout.addStretch()

    # ── API publique ───────────────────────────────────────────────────────
    def get_config(self) -> dict:
        return {
            "faiss_dedup_enabled":   self._chk_enabled.isChecked(),
            "faiss_dedup_threshold": self._spin_threshold.value(),
        }

    def load_config(self, cfg: dict) -> None:
        enabled = cfg.get("faiss_dedup_enabled", True)
        threshold = cfg.get("faiss_dedup_threshold", 0.93)
        self._chk_enabled.setChecked(bool(enabled))
        self._spin_threshold.setValue(float(threshold))
        self._spin_threshold.setEnabled(bool(enabled))


# ─── Panneau principal ────────────────────────────────────────────────────────

class SettingsPanel(QWidget):
    """
    Panneau de configuration organise en onglets :
      - Modeles IA    : 3 sections provider/cle/modele
      - Instructions  : 6 prompts editables
      - Interface     : theme clair/sombre
    """

    config_saved   = pyqtSignal(dict)   # config IA complete apres save
    theme_changed  = pyqtSignal(str)    # "dark" ou "light" apres save
    font_size_changed = pyqtSignal(int) # taille police (12-16) apres save
    font_family_changed = pyqtSignal(str)   # famille police apres save
    chat_lh_changed = pyqtSignal(float)     # interligne chat apres save
    notif_opacity_changed = pyqtSignal(float)  # conservé pour compatibilité
    badge_opacity_changed = pyqtSignal(float)  # opacité annotations (0.0–1.0)
    scroll_speed_changed  = pyqtSignal(int)     # vitesse synchro scroll (1–10)
    badge_margin_r_changed = pyqtSignal(int)    # marge droite annotations (px)
    color_overrides_changed   = pyqtSignal()     # couleur annotation changée en direct
    ego_scan_requested = pyqtSignal()           # bouton Scanner dans Instructions
    ego_instruction_saved = pyqtSignal(str)     # instruction Ego éditée manuellement
    ego_heartbeat_changed = pyqtSignal(int)     # Délai du heartbeat ego

    def __init__(self, author_slug: str = "", author_name: str = ""):
        super().__init__()
        self.setObjectName("SettingsPanel")
        self._author_slug = author_slug
        self._author_name = author_name
        self._setup_ui()
        self._load_current_config()

    # ------------------------------------------------------------------ #
    # Construction                                                         #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Onglets ───────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs)

        # ── Onglet 1 : Modeles IA ─────────────────────────────────────────────
        tab_models = QWidget()
        tab_models.setObjectName("ScrollContent")
        self._tabs.addTab(self._make_scroll(tab_models), tr("Modeles IA"))

        ml = QVBoxLayout(tab_models)
        ml.setContentsMargins(12, 8, 12, 12)
        ml.setSpacing(0)

        self._sec_principale = _IASection(tr("IA Principale"), embed_mode=False)
        self._sec_archiviste = _IASection(tr("IA Archiviste"), embed_mode=False)
        self._sec_embed      = _IASection(tr("IA Embed"),      embed_mode=True)

        ml.addWidget(self._sec_principale)
        ml.addWidget(self._separator())
        ml.addWidget(self._sec_archiviste)
        ml.addWidget(self._separator())
        ml.addWidget(self._sec_embed)
        ml.addWidget(self._separator())
        self._sec_web_search = _WebSearchSection()
        ml.addWidget(self._sec_web_search)
        ml.addWidget(self._separator())
        self._sec_backup = _BackupSection()
        self._sec_backup.save_requested.connect(self._on_backup_save)
        self._sec_backup.load_requested.connect(self._on_backup_load)
        ml.addWidget(self._sec_backup)
        ml.addStretch()

        # ── Onglet 2 : Instructions ───────────────────────────────────────────
        tab_prompts = QWidget()
        tab_prompts.setObjectName("ScrollContent")
        self._tabs.addTab(self._make_scroll(tab_prompts), tr("Instructions"))

        pl = QVBoxLayout(tab_prompts)
        pl.setContentsMargins(12, 8, 12, 12)
        pl.setSpacing(0)

        self._sec_prompts = _PromptsSection()
        pl.addWidget(self._sec_prompts)

        self._sec_ego = _EgoSection()
        self._sec_ego.scan_requested.connect(self.ego_scan_requested)
        self._sec_ego.heartbeat_changed.connect(self.ego_heartbeat_changed.emit)
        pl.addWidget(self._sec_ego)

        pl.addStretch()

        # ── Onglet 3 : Interface ──────────────────────────────────────────────
        tab_interface = QWidget()
        tab_interface.setObjectName("ScrollContent")
        self._tabs.addTab(self._make_scroll(tab_interface), tr("Interface"))

        il = QVBoxLayout(tab_interface)
        il.setContentsMargins(12, 8, 12, 12)
        il.setSpacing(0)

        self._sec_interface = _InterfaceSection()
        self._sec_interface.color_overrides_live_changed.connect(self.color_overrides_changed)
        il.addWidget(self._sec_interface)
        il.addStretch()

        # ── Onglet 4 : Mémoire ────────────────────────────────────────────────
        tab_memory = QWidget()
        tab_memory.setObjectName("ScrollContent")
        self._tabs.addTab(self._make_scroll(tab_memory), tr("Mémoire"))

        ml = QVBoxLayout(tab_memory)
        ml.setContentsMargins(12, 8, 12, 12)
        ml.setSpacing(0)

        self._sec_memory = _MemorySection()
        ml.addWidget(self._sec_memory)
        ml.addStretch()

        # ── Onglet 5 : Profil auteur ──────────────────────────────────────────
        tab_profile = QWidget()
        tab_profile.setObjectName("ScrollContent")
        self._tabs.addTab(self._make_scroll(tab_profile), tr("Profil"))

        pp = QVBoxLayout(tab_profile)
        pp.setContentsMargins(12, 8, 12, 12)
        pp.setSpacing(0)

        self._sec_profile = _ProfileSection(
            author_slug=self._author_slug,
            author_name=self._author_name,
        )
        pp.addWidget(self._sec_profile)
        pp.addStretch()

        # ── Onglet 5 : Guide ──────────────────────────────────────────────────
        tab_guide = QWidget()
        tab_guide.setObjectName("ScrollContent")
        self._tabs.addTab(self._make_scroll(tab_guide), tr("Guide"))

        gl = QVBoxLayout(tab_guide)
        gl.setContentsMargins(12, 8, 12, 12)
        gl.setSpacing(0)

        self._guide_view = _GuideSection()
        gl.addWidget(self._guide_view)
        gl.addStretch()

        # ── Barre de sauvegarde (sous les onglets) ────────────────────────────
        footer = QWidget()
        footer.setObjectName("ScrollContent")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 6, 12, 8)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        fl.addWidget(self._status_label)
        fl.addStretch()

        self._save_btn = QPushButton(tr("Sauvegarder"))
        self._save_btn.setObjectName("SaveBtn")
        self._save_btn.clicked.connect(self._on_save)
        fl.addWidget(self._save_btn)

        root.addWidget(footer)

    @staticmethod
    def _make_scroll(content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setObjectName("Separator")
        line.setFrameShape(QFrame.Shape.HLine)
        return line

    # ------------------------------------------------------------------ #
    # Donnees                                                              #
    # ------------------------------------------------------------------ #

    def _load_current_config(self):
        cfg = load_config()
        self._sec_principale.set_values(cfg.get("ia_principale", {}))
        self._sec_archiviste.set_values(cfg.get("ia_archiviste", {}))
        self._sec_embed.set_values(cfg.get("ia_embed", {}))
        self._sec_web_search.set_values(cfg.get("web_search", {}))
        self._sec_interface.set_theme(cfg.get("theme", "dark"))
        self._sec_interface.set_font_size(cfg.get("font_size", 13))
        self._sec_interface.set_font_family(cfg.get("font_family", "Segoe UI"))
        self._sec_interface.set_chat_lh(cfg.get("chat_lh", 1.6))
        self._sec_interface.set_badge_opacity(int(cfg.get("badge_opacity", 85)))
        self._sec_interface.set_scroll_speed(int(cfg.get("scroll_speed", 5)))
        self._sec_interface.set_badge_margin_r(int(cfg.get("badge_margin_r", 30)))
        self._sec_interface.set_ocr_engine(cfg.get("ocr_engine", "winrt"))
        self._sec_interface.set_color_overrides(cfg.get("color_overrides", {"dark": {}, "light": {}}))
        self._sec_memory.load_config(cfg.get("memory", {}))

    def _on_save(self):
        # Config IA → app_config.json (gitignored)
        theme = self._sec_interface.get_theme()
        font_size = self._sec_interface.get_font_size()
        font_family = self._sec_interface.get_font_family()
        chat_lh = self._sec_interface.get_chat_lh()
        notif_opacity_pct = round(self._sec_interface.get_badge_opacity() * 100)
        scroll_speed = self._sec_interface.get_scroll_speed()
        badge_margin_r = self._sec_interface.get_badge_margin_r()
        ocr_engine = self._sec_interface.get_ocr_engine()
        config = {
            "ia_principale": self._sec_principale.get_values(),
            "ia_archiviste": self._sec_archiviste.get_values(),
            "ia_embed":      self._sec_embed.get_values(),
            "web_search":    self._sec_web_search.get_values(),
            "theme":         theme,
            "font_size":     font_size,
            "font_family":   font_family,
            "chat_lh":       chat_lh,
            "badge_opacity": notif_opacity_pct,
            "scroll_speed":  scroll_speed,
            "badge_margin_r": badge_margin_r,
            "ocr_engine":    ocr_engine,
            "ego_heartbeat_minutes": self._sec_ego.get_heartbeat(),
            "color_overrides": self._sec_interface.get_color_overrides(),
            "memory":        self._sec_memory.get_config(),
        }
        save_config(config)

        # Prompts → prompts.json (versionnable)
        save_prompts(self._sec_prompts.get_values())

        logger.info(
            "SettingsPanel \u2014 sauvegarde OK (principale=%s archi=%s embed=%s theme=%s)",
            config["ia_principale"].get("model"),
            config["ia_archiviste"].get("model"),
            config["ia_embed"].get("model"),
            theme,
        )

        from datetime import datetime
        self._status_label.setText(tr("Sauvegarde a {}").format(datetime.now().strftime('%H:%M:%S')))

        self.ego_instruction_saved.emit(self._sec_ego.get_instruction())
        self.config_saved.emit(config)
        self.theme_changed.emit(theme)
        self.font_size_changed.emit(font_size)
        self.font_family_changed.emit(font_family)
        self.chat_lh_changed.emit(chat_lh)
        self.badge_opacity_changed.emit(notif_opacity_pct / 100.0)
        self.scroll_speed_changed.emit(scroll_speed)
        self.badge_margin_r_changed.emit(badge_margin_r)

    # ------------------------------------------------------------------ #
    # Backup / Restauration                                                #
    # ------------------------------------------------------------------ #

    def _on_backup_save(self, include_api: bool, include_instr: bool, path: str) -> None:
        from core.config_manager import save_settings_backup
        from pathlib import Path

        api_data    = None
        instr_data  = None
        if include_api:
            api_data = {
                "ia_principale": self._sec_principale.get_values(),
                "ia_archiviste": self._sec_archiviste.get_values(),
                "ia_embed":      self._sec_embed.get_values(),
                "web_search":    self._sec_web_search.get_values(),
            }
        if include_instr:
            instr_data = self._sec_prompts.get_values()

        try:
            save_settings_backup(path, api_data, instr_data)
            parts = []
            if include_api:   parts.append("API")
            if include_instr: parts.append("Instructions")
            self._sec_backup.set_status(
                tr("Exporté ({}) → {}").format(' + '.join(parts), Path(path).name),
                ok=True,
            )
            logger.info("SettingsPanel — backup exporté : %s", path)
        except Exception as exc:
            self._sec_backup.set_status(tr("Erreur export : {}").format(exc), ok=False)
            logger.error("SettingsPanel — backup save error : %s", exc)

    def _on_backup_load(self, path: str) -> None:
        from core.config_manager import load_settings_backup

        try:
            data = load_settings_backup(path)
        except Exception as exc:
            self._sec_backup.set_status(tr("Erreur lecture : {}").format(exc), ok=False)
            logger.error("SettingsPanel — backup load error : %s", exc)
            return

        parts: list[str] = []

        if "api" in data:
            api = data["api"]
            self._sec_principale.set_values(api.get("ia_principale", {}))
            self._sec_archiviste.set_values(api.get("ia_archiviste", {}))
            self._sec_embed.set_values(api.get("ia_embed", {}))
            self._sec_web_search.set_values(api.get("web_search", {}))
            parts.append("API")

        if "instructions" in data:
            self._sec_prompts.set_values(data["instructions"])
            parts.append("Instructions")

        date_str = data.get("_date", "?")
        self._sec_backup.set_status(
            tr("Restauré ({}) du {} — cliquez sur Sauvegarder pour appliquer.").format(' + '.join(parts), date_str),
            ok=True,
        )
        logger.info("SettingsPanel — backup restauré depuis %s (%s)", path, parts)
