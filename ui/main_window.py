"""
MainWindow — Fenêtre principale EUGENIA

Layout 4 colonnes (inspiré VS Code) :
  Col 1 : IconBar (fixe, 48px) — hors splitter
  Col 2 : ContextPanel (collapsible) — contenu dépend de l'icône active
  Col 3 : EditorZone — zone neutre pour l'éditeur tiers
  Col 4 : AIPanel (collapsible) — conversation avec EUGENIA

Les colonnes 2, 3, 4 sont dans un QSplitter horizontal : chaque séparateur
est draggable. La col 3 absorbe l'espace libre quand un panneau se ferme.
"""

import json as _json
import re
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget
from PyQt6.QtCore import Qt, QSettings, QByteArray, QTimer, pyqtSignal, QPoint
from PyQt6.QtGui import QIcon
from ui.edit_panel import EditPanel
from ui.title_bar import CustomTitleBar
from core.edit_document import EditDocStore, EditDocument
from core.stats_engine import StatsStore, count_words_docx
from ui.sidebar_splitter import SidebarSplitter
from PyQt6.QtWidgets import QApplication
import logging
from ui.icon_bar import IconBar
from ui.context_panel import ContextPanel
from ui.editor_zone import EditorZone
from ui.ai_panel import AIPanel
from ui.clipboard_notification import ClipboardNotification
from ui.bible_panel import BiblePanel
from ui.ingest_dialog import IngestDialog
from core.ai_engine import AIEngine
from core.config_manager import load_config, load_prompt
from core.providers import resolve_engine_config
from core.clipboard_monitor import ClipboardMonitor
from core.archiviste import Archiviste
from core.archiviste_relational import ArchivisteRelational
from core.annotation_generator import AnnotationGenerator
from core.conversation_store import ConversationStore
from core.relational_scanner import RelationalScanner
from core.bio_compiler import compile_bio
from core.bio_activation import BioActivation
from core.source_store import SourceStore
from core.vector_index import VectorIndex
from core.session_summarizer import SessionSummarizer
from core.rolling_summarizer import RollingSummarizer
from core.cognitive_cache import CognitiveCache, CACHE_INSTRUCTION
from core.style_profiler import StyleProfiler
from core.session_manager import PROJECTS_DIR
from core.ego_manager import EgoManager, EgoScanWorker
from core.semantic_dedup import EgoDedupWorker, RelationalDedupWorker
from core.web_search import WebSearchWorker
from core.document_controller import DocumentController
from ui.approval_gate import ApprovalGate
from ui.themes import build_stylesheet, get_colors
from ui.ghost_overlay import GhostOverlay
from core.annotation_store import AnnotationStore
from core.ghost_scanner import GhostScanner
from core.scroll_tracker import ScrollTracker
from core.ghost_matcher import match_annotations
from core.i18n import tr

logger = logging.getLogger(__name__)

# Tailles par défaut des colonnes (en pixels)
DEFAULT_COL2 = 280   # panneau contextuel
DEFAULT_COL3 = 700   # zone éditeur (valeur indicative, prend le reste)
DEFAULT_COL4 = 350   # panneau IA

# Instruction injectee quand le mode edition est actif
_EDIT_MODE_INSTRUCTION = """\
[MODE EDITION ACTIF — DOCUMENT : "{title}"]
Tu co-edites un document avec l'auteur. Contenu actuel du document :
---
{content}
---
REGLE ABSOLUE : Utilise impérativement les balises <edit> et <comment> pour répondre.
<edit>
Le contenu COMPLET du document en markdown (N'utilise pas cette balise si tu ne modifies rien).
</edit>
<comment>
Ton message court pour l'auteur dans le chat (N'utilise pas cette balise si tu n'as rien à dire).
</comment>

Ne fournis le contenu COMPLET dans <edit> QUE si tu modifies le document.
"""

DARK_THEME = ""  # conserve pour compatibilite — styles dans ui/themes.py
LIGHT_THEME = ""  # idem


class MainWindow(QMainWindow):
    _memorize_signal = pyqtSignal(str)
    def __init__(self, session: dict):
        super().__init__()
        self._session = session
        author = session["author"]["name"]
        project = session["project"]["name"]
        self.setWindowTitle(tr("EUGENIA — {}  ({})").format(project, author))
        self.setWindowIcon(QIcon("assets/logo.png"))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMinimumSize(1200, 700)
        self.resize(1400, 800)
        # Appliquer le theme depuis la config (defaut dark)
        cfg = load_config()
        from ui.theme_config import ThemeConfig
        ThemeConfig.instance().load(cfg.get("color_overrides", {"dark": {}, "light": {}}))
        self._startup_cfg = cfg
        self._badge_opacity: float = int(cfg.get("badge_opacity", 85)) / 100.0
        self._scroll_speed: int = int(cfg.get("scroll_speed", 5))
        self._badge_x_offset: int = int(cfg.get("badge_x_offset", 0))
        self._badge_margin_r: int = int(cfg.get("badge_margin_r", 30))
        self._setup_ui()
        self.apply_theme(
            cfg.get("theme", "dark"),
            cfg.get("font_size", 13),
            cfg.get("font_family", None),
            cfg.get("chat_lh", None),
        )



    def _restore_layout(self) -> None:
        """Restaure la geometrie de la fenetre et les tailles du splitter depuis QSettings."""
        s = QSettings("EUGENIA", "Layout")
        geometry: QByteArray = s.value("window/geometry")  # type: ignore[assignment]
        splitter_state: QByteArray = s.value("splitter/state")  # type: ignore[assignment]
        if geometry and not geometry.isEmpty():
            self.restoreGeometry(geometry)
        if splitter_state and not splitter_state.isEmpty():
            self.splitter.restoreState(splitter_state)
        ai_saved = s.value("ai_panel/saved_width")
        if ai_saved is not None:
            try:
                self._ai_saved_width = int(ai_saved)
            except (ValueError, TypeError):
                pass
        ctx_saved = s.value("ctx_panel/saved_width")
        if ctx_saved is not None:
            try:
                self._ctx_saved_width = int(ctx_saved)
            except (ValueError, TypeError):
                pass
        logger.debug("MainWindow — layout restaure (geometry=%s splitter=%s)",
                     bool(geometry), bool(splitter_state))

    def _save_layout(self) -> None:
        """Sauvegarde la geometrie de la fenetre et les tailles du splitter dans QSettings."""
        s = QSettings("EUGENIA", "Layout")
        s.setValue("window/geometry", self.saveGeometry())
        # Ne pas sauvegarder l'etat splitter quand AIPanel est replie (fixedWidth=24)
        # pour ne pas ecraser les tailles reelles
        if not self._ai_collapsed:
            s.setValue("splitter/state", self.splitter.saveState())
        s.setValue("ai_panel/saved_width", self._ai_saved_width)
        s.setValue("ctx_panel/saved_width", self._ctx_saved_width)
        logger.debug("MainWindow — layout sauvegarde")

    def apply_theme(self, theme: str, font_size: int = 13,
                    font_family: str | None = None,
                    chat_lh: float | None = None) -> None:
        """Applique le theme dark ou light sur toute l'application."""
        from PyQt6.QtGui import QFont
        from ui.font_config import FontConfig
        fc = FontConfig.instance()
        fc.update(size=font_size, family=font_family, chat_lh=chat_lh)
        self._current_theme = theme
        app = QApplication.instance()
        app.setStyleSheet(build_stylesheet(theme, fc))
        # Actualiser les icônes qtawesome de la barre latérale
        if hasattr(self, "icon_bar"):
            self.icon_bar.apply_theme(theme)
        if hasattr(self, "context_panel"):
            self.context_panel.apply_theme(theme)
        if hasattr(self, "ai_panel"):
            self.ai_panel.apply_theme(theme)
        # setFont() atteint tous les widgets sans font-size explicite dans leur QSS
        font = QFont(fc.family, fc.size)
        app.setFont(font)
        # Propager aux panneaux avec stylesheets locaux
        if hasattr(self, "context_panel"):
            self.context_panel.bible_panel.apply_font_config(fc)
        if hasattr(self, "ai_panel"):
            self.ai_panel.apply_font_config(fc)
        if hasattr(self, "context_panel"):
            cp = self.context_panel
            if hasattr(cp, "history_panel"):
                cp.history_panel.apply_font_config(fc)
            if hasattr(cp, "style_panel"):
                cp.style_panel.apply_font_config(fc)
            if hasattr(cp, "sources_panel"):
                cp.sources_panel.apply_font_config(fc)
        logger.debug("MainWindow — theme applique : %s  font_size=%d", theme, font_size)
        if hasattr(self, '_ghost_overlay'):
            self._apply_badge_colors()

    def _apply_badge_colors(self) -> None:
        """Lit badge_bg/badge_text/badge_opacity depuis le thème et les applique aux badges."""
        from ui.theme_config import ThemeConfig
        from ui.themes import get_colors
        theme = getattr(self, '_current_theme', 'dark')
        c = {**get_colors(theme), **ThemeConfig.instance().get_overrides(theme)}
        self._ghost_overlay.update_badge_colors(
            bg_hex   = c.get("badge_bg",   "#1e1e3a"),
            text_hex = c.get("badge_text", "#e0e0e0"),
            opacity  = self._badge_opacity,
        )

    def _setup_ui(self):
        # Widget central contenant toute l'interface
        central = QWidget()
        central.setObjectName("MainWindowCentral")
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.title_bar = CustomTitleBar(self.windowTitle())
        self.title_bar.close_requested.connect(self.close)
        self.title_bar.maximize_requested.connect(self._toggle_maximize)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        main_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        root_layout = QHBoxLayout(content_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Colonne 1 : barre d'icônes (fixe, hors splitter) ---
        self.icon_bar = IconBar()
        self.icon_bar.icon_clicked.connect(self._on_icon_clicked)
        root_layout.addWidget(self.icon_bar)

        # --- Colonnes 2, 3, 4 : splitter horizontal ---
        self.splitter = SidebarSplitter()

        self.context_panel = ContextPanel(
            author_slug=self._session["author"]["slug"],
            author_name=self._session["author"]["name"],
        )
        self.editor_zone = EditorZone()
        self.ai_panel = AIPanel()

        # Mode Edition : store + panneau (substitue a l'EditorZone dans le splitter)
        _proj_slug = self._session["project"]["slug"]
        self._edit_store = EditDocStore(PROJECTS_DIR / _proj_slug)
        self._edit_panel = EditPanel(self._edit_store)
        self._current_edit_doc: EditDocument | None = None

        # Stats — store de persistance
        self._stats_store = StatsStore(PROJECTS_DIR / _proj_slug)
        self._pending_stat_mode: bool = False

        # Col 3 : QStackedWidget — index 0 = EditorZone, index 1 = EditPanel
        self._center_stack = QStackedWidget()
        self._center_stack.addWidget(self.editor_zone)   # index 0
        self._center_stack.addWidget(self._edit_panel)   # index 1

        self.splitter.addWidget(self.context_panel)    # index 0
        self.splitter.addWidget(self._center_stack)    # index 1
        self.splitter.addWidget(self.ai_panel)         # index 2

        # Col 3 (éditeur) est élastique : elle prend l'espace libre
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        self.splitter.setSizes([DEFAULT_COL2, DEFAULT_COL3, DEFAULT_COL4])

        root_layout.addWidget(self.splitter)
        main_layout.addWidget(content_widget)

        # Raccourci vers le BiblePanel (logé dans ContextPanel)
        self._bible_panel = self.context_panel.bible_panel

        # Créer et brancher le moteur IA
        self._init_ai_engine()

        # Brancher la base relationnelle sur le MemoryPanel (relational_db cree dans _init_ai_engine)
        self.context_panel.set_memory_db(self._relational_db)
        # Bouton "Analyser" du MemoryPanel → lancer le scanner
        self.context_panel.memory_panel.scan_requested.connect(self._on_memory_scan_requested)

        # BioActivation — initialise apres relational_db, avant Archiviste
        self._bio_activation: BioActivation | None = None
        self._bio_pending_text: str = ""
        self._web_search_worker = None

        # Pré-déclarations nécessaires avant _init_conversation_store
        self._rolling_summarizer: RollingSummarizer | None = None
        self._cognitive_cache: CognitiveCache = CognitiveCache()

        # Créer et brancher l'Archiviste (après engine pour avoir la config)
        self._init_archiviste()

        # Initialiser le store de conversations
        self._init_conversation_store()

        # Brancher l'index FAISS sur l'Archiviste (filtre semantique a l'ingest)
        if self._archiviste is not None:
            self._archiviste.set_vector_index(self._vector_index)

        # Connecter le panneau Paramètres → rechargement des engines
        self.context_panel.settings_panel.config_saved.connect(self._on_config_saved)
        self.context_panel.settings_panel.theme_changed.connect(
            lambda theme: self.apply_theme(theme, self.context_panel.settings_panel._sec_interface.get_font_size())
        )
        self.context_panel.settings_panel.font_size_changed.connect(
            lambda size: self.apply_theme(
                self.context_panel.settings_panel._sec_interface.get_theme(), size,
                self.context_panel.settings_panel._sec_interface.get_font_family(),
                self.context_panel.settings_panel._sec_interface.get_chat_lh(),
            )
        )
        self.context_panel.settings_panel.font_family_changed.connect(
            lambda fam: self.apply_theme(
                self.context_panel.settings_panel._sec_interface.get_theme(),
                self.context_panel.settings_panel._sec_interface.get_font_size(),
                fam,
                self.context_panel.settings_panel._sec_interface.get_chat_lh(),
            )
        )
        self.context_panel.settings_panel.chat_lh_changed.connect(
            lambda lh: self.apply_theme(
                self.context_panel.settings_panel._sec_interface.get_theme(),
                self.context_panel.settings_panel._sec_interface.get_font_size(),
                self.context_panel.settings_panel._sec_interface.get_font_family(),
                lh,
            )
        )
        self.context_panel.settings_panel.notif_opacity_changed.connect(
            lambda v: setattr(self, "_notif_opacity_compat", v)   # signal conservé mais inutilisé
        )
        self.context_panel.settings_panel.badge_opacity_changed.connect(
            self._on_badge_opacity_changed
        )
        self.context_panel.settings_panel.scroll_speed_changed.connect(
            self._on_scroll_speed_changed
        )
        self.context_panel.settings_panel.badge_margin_r_changed.connect(
            self._on_badge_margin_r_changed
        )
        self.context_panel.settings_panel.color_overrides_changed.connect(
            self._apply_badge_colors
        )
        self.context_panel.settings_panel.ego_scan_requested.connect(
            self._run_ego_scan
        )
        self.context_panel.settings_panel.ego_instruction_saved.connect(
            self._save_ego_instruction
        )
        
        # Restaurer la geometrie et les tailles de colonnes de la session precedente
        self._restore_layout()

        # Sauvegarde en temps reel au moindre deplacement du splitter principal
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        # Connecter le footer AIPanel ↔ EditorZone (embed Win32)
        self.ai_panel.attach_editor_requested.connect(self.editor_zone.attach_editor)
        self.ai_panel.detach_editor_requested.connect(self.editor_zone.detach_editor)
        self.editor_zone.editor_attached.connect(lambda: self.ai_panel.set_editor_attached(True))
        self.editor_zone.editor_detached.connect(lambda: self.ai_panel.set_editor_attached(False))

        # Mode Edition : signaux EditPanel
        self._edit_panel.closed.connect(self._exit_edit_mode)
        self._edit_panel.save_requested.connect(self._on_edit_save)
        self._edit_panel.ai_command_requested.connect(self._on_edit_ai_command)
        # SourcesPanel -> ouvrir un doc edite par double-clic
        self.context_panel.sources_panel.edit_open_requested.connect(self._on_edit_doc_open)
        self.context_panel.sources_panel.delete_edit_doc_requested.connect(self._on_edit_doc_delete)
        # Peupler la liste des docs edites des l'ouverture du projet
        self.context_panel.sources_panel.refresh_edit_docs(self._edit_store.list_docs())

        # StatsPanel — signaux
        _sp = self.context_panel.stats_panel
        _sp.doc_dropped.connect(self._on_stat_doc_dropped)
        _sp.refresh_requested.connect(self._on_stat_refresh)
        _sp.chart_requested.connect(self._on_stat_chart_requested)
        _sp.delete_requested.connect(self._on_stat_delete)
        # Peupler les listes des l'ouverture du projet
        _sp.refresh_display(
            self._stats_store.list_doc_stats(),
            self._stats_store.list_custom_stats(),
        )

        # DocumentController + ApprovalGate
        self._doc_ctrl = DocumentController(parent=self)
        self._approval_gate = ApprovalGate(parent=self)
        self._doc_mode: bool = False
        self.editor_zone.hwnd_changed.connect(self._doc_ctrl.set_hwnd)
        self._doc_ctrl.operation_done.connect(
            lambda msg: logger.info("[DOC:CTRL] %s", msg)
        )
        self._doc_ctrl.operation_failed.connect(
            lambda msg: logger.warning("[DOC:CTRL] ECHEC : %s", msg)
        )
        # Brancher le bouton 'Insérer dans l'éditeur' du panneau IA
        self.ai_panel.insert_in_editor_requested.connect(self._on_insert_in_editor)
        # Mode document
        self.ai_panel.document_mode_changed.connect(self._on_doc_mode_changed)

        # ── Ghost Writer ──────────────────────────────────────────────────────
        project_slug = self._session["project"]["slug"]
        self._annotation_store = AnnotationStore(PROJECTS_DIR / project_slug)
        self._ghost_overlay = GhostOverlay(parent=self)
        self._ghost_overlay.set_x_offset(self._badge_x_offset)
        self._ghost_overlay.set_margin_r(self._badge_margin_r)
        self._ghost_overlay.x_offset_changed.connect(self._on_badge_x_offset_changed)
        self._x_offset_save_timer = QTimer(self)
        self._x_offset_save_timer.setSingleShot(True)
        self._x_offset_save_timer.setInterval(500)
        self._x_offset_save_timer.timeout.connect(self._persist_badge_x_offset)
        self._ghost_scanner: GhostScanner | None = None
        self._scroll_tracker = ScrollTracker(parent=self)
        self._scroll_tracker.set_speed(self._scroll_speed)
        self._scroll_tracker.scroll_delta.connect(self._on_scroll_delta)
        self._scroll_tracker.rescan_requested.connect(self._on_scroll_rescan_requested)
        self.editor_zone.editor_attached.connect(
            lambda: self._ghost_overlay.attach(self.editor_zone)
        )
        self.editor_zone.editor_attached.connect(self._on_ghost_editor_attached)
        self.editor_zone.editor_detached.connect(self._ghost_overlay.detach)
        self.editor_zone.editor_detached.connect(self._ghost_overlay.clear_badges)
        self.editor_zone.editor_detached.connect(self._scroll_tracker.detach)
        self._ghost_overlay.scan_requested.connect(self._on_ghost_scan_requested)
        self._ghost_overlay.annotation_deleted.connect(self._on_ghost_annotation_deleted)
        self._ghost_overlay.annotation_edited.connect(self._on_ghost_annotation_edited)
        self.ai_panel.ghost_scan_requested.connect(self._on_ghost_scan_requested)
        self.ai_panel.ghost_toggle_requested.connect(self._on_ghost_toggle_overlay)
        self.ai_panel.screenshot_requested.connect(self._on_screenshot_requested)
        self.ai_panel.edit_requested.connect(lambda: self._enter_edit_mode())

        # Repli/deploi du panneau IA via clic sur le titre EUGENIA
        self._ai_collapsed: bool = False
        self._ai_saved_width: int = DEFAULT_COL4
        self.ai_panel.toggle_requested.connect(self._on_ai_panel_toggle)

        # Suivi de l'etat replié du panneau contextuel gauche
        self._ctx_collapsed: bool = False
        self._ctx_saved_width: int = DEFAULT_COL2

        # Démarrer la surveillance du presse-papier
        self._clipboard_monitor = ClipboardMonitor()
        self._clipboard_monitor.text_detected.connect(self._on_clipboard_text)
        self._clipboard_monitor.start()

        # Dernier extrait explicitement partagé dans le contexte IA (via la notification)
        self._last_shared_clip: str = ""

        # Garde une référence à la notification active pour éviter les doublons
        self._active_notif: ClipboardNotification | None = None

        # Initialiser les grips de redimensionnement transparents
        self._init_resize_grips()

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _master_preprocessor(self, text: str) -> str:
        """
        Appelé dans le thread worker par AIEngine avant de stocker la réponse.
        Filtre le CACHE_ADD et [MEMORISER].
        """
        # 1. Filtre du cache cognitif
        text = self._cognitive_cache.process_response(text)
        
        # 2. Filtre de [MEMORISER]
        import re
        pattern = r'\[MEMORISER\](.*?)(?=\[|$)'
        matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
        
        extracted_texts = []
        for m in matches:
            extracted = m.group(1).strip()
            if extracted:
                extracted_texts.append(extracted)
                
        # Supprimer les balises du texte final
        cleaned_text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL).strip()
        
        # Emettre les signaux pour traiter de facon thread-safe
        for ext in extracted_texts:
            self._memorize_signal.emit(ext)
            
        return cleaned_text

    def _on_memorize_signal(self, text_to_memorize: str) -> None:
        """
        Exécuté dans le Main Thread, appelé par _memorize_signal.
        Déclenche la mémorisation relationnelle et affiche la notification.
        """
        if self._archiviste:
            self._archiviste.relational().memorize_direct(text_to_memorize)
            self.ai_panel.append_injected(
                tr("Archiviste"), 
                tr("Information mémorisée : {}...").format(text_to_memorize[:80])
            )
            logger.info("[MEM:WRITE] Auto-mémorisation déclenchée par EUGENIA : %s", text_to_memorize[:60])

    def _init_ai_engine(self):
        """Charge la config API et branche le moteur sur le panneau IA."""
        from core.profile_manager import build_profile_injection
        from core.relational_db import RelationalDB
        from core.session_manager import AUTHORS_DIR
        cfg = load_config()
        engine_cfg = resolve_engine_config(cfg["ia_principale"])
        base_prompt = load_prompt("ia_principale")
        # Instancier la memoire relationnelle de l'auteur (transversale aux projets)
        author_slug = self._session["author"]["slug"]
        author_name = self._session["author"]["name"]
        author_dir  = AUTHORS_DIR / author_slug

        # Injecter le nom de l'auteur directement dans le prompt système de base
        base_prompt += f"\n\n[INFO SYSTÈME] : L'auteur avec qui tu interagis s'appelle {author_name}."

        # Pas d'injection statique : la bio est activee dynamiquement par message
        engine_cfg["system_prompt"] = base_prompt
        self._relational_db = RelationalDB(author_dir)
        self._engine = None
        if engine_cfg.get("api_key"):
            self._engine = AIEngine(
                config=engine_cfg,
                on_response=self._on_ai_response,
                on_error=self.ai_panel.on_ai_error,
            )
            self.ai_panel.set_engine(self._engine)
            logger.info("MainWindow — AIEngine initialisé (model=%s)", engine_cfg.get("model"))
        else:
            logger.warning("MainWindow — AIEngine non initialisé : clé API manquante")
        # Connecter le signal d'envoi (orchestre Archiviste avant engine.send)
        self.ai_panel.send_requested.connect(self._on_ai_send_requested)

    def _init_archiviste(self):
        """Instancie l'Archiviste et branche la BiblePanel."""
        cfg = load_config()
        archiviste_cfg = resolve_engine_config(cfg["ia_archiviste"])
        self._archiviste: Archiviste | None = None
        self._pending_send_text: str = ""
        self._ingesting: bool = False

        if not archiviste_cfg.get("api_key"):
            logger.warning("MainWindow — Archiviste non initialisé : clé API manquante")
            return

        self._archiviste = Archiviste(
            config=archiviste_cfg,
            session={
                "author":       self._session["author"]["name"],
                "author_slug":  self._session["author"]["slug"],
                "project":      self._session["project"]["name"],
                "project_slug": self._session["project"]["slug"],
            },
        )

        # Signaux Archiviste → UI
        self._archiviste.contradiction_found.connect(self._on_contradiction)
        self._archiviste.bible_updated.connect(self._bible_panel.on_bible_updated)
        self._archiviste.error_occurred.connect(self._on_archiviste_error)

        # Contexte note prête → injecter puis appeler engine.send
        self._archiviste.context_note_ready.connect(self._on_context_note_ready)

        # Brancher la Bible UI
        self._bible_panel.set_bible_db(self._archiviste.bible_db)
        self._bible_panel.bible_manually_changed.connect(self._on_memorize_bible_requested)
        # Debounce : re-vectorise 3 s après le dernier bible_updated (ingest, /mem_bible...)
        # _ingesting est initialisé dans __init__ de _init_archiviste (plus haut)
        self._bible_sync_timer = QTimer(self)
        self._bible_sync_timer.setSingleShot(True)
        self._bible_sync_timer.setInterval(3000)
        self._bible_sync_timer.timeout.connect(self._on_memorize_bible_requested)
        self._archiviste.bible_updated.connect(
            lambda *_: None if self._ingesting else self._bible_sync_timer.start()
        )

    def _init_relational_scanner(self) -> None:
        """Instancie le RelationalScanner si l'Archiviste est disponible."""
        if not hasattr(self, "_archiviste") or self._archiviste is None:
            logger.warning("MainWindow — RelationalScanner non init : Archiviste absent")
            return
        cfg = load_config()
        archiviste_cfg = resolve_engine_config(cfg["ia_archiviste"])
        if not archiviste_cfg.get("api_key"):
            return
        relational = ArchivisteRelational(
            config=archiviste_cfg,
            relational_db=self._relational_db,
        )
        self._relational_scanner = RelationalScanner(
            conv_store=self._conv_store,
            archiviste=relational,
        )
        self._relational_scanner.scan_complete.connect(self._on_relational_scan_complete)
        self._relational_scanner.scan_error.connect(
            lambda msg: logger.warning("RelationalScanner — %s", msg)
        )
        logger.info("MainWindow — RelationalScanner initialise")

    def _init_ego(self) -> None:
        """Charge le fichier ego.json de l'auteur courant."""
        from core.session_manager import AUTHORS_DIR
        author_slug = self._session["author"]["slug"]
        author_dir  = AUTHORS_DIR / author_slug
        self._ego_manager.load(author_dir)
        # Mettre a jour la vue dans le panneau Parametres (si deja affiche)
        self._refresh_ego_ui()


    def _on_ego_heartbeat_changed(self, minutes: int) -> None:
        if hasattr(self, "_ego_heartbeat_timer"):
            self._ego_heartbeat_timer.setInterval(minutes * 60 * 1000)
            if self._ego_heartbeat_timer.isActive():
                self._ego_heartbeat_timer.start()
            logger.info("[EGO] Intervalle heartbeat mis à %d minutes", minutes)
            # Sauvegarder dynamiquement
            self.context_panel.settings_panel._on_save()

    def _init_ego_heartbeat_timer(self) -> None:
        """Demarre le timer heartbeat ego."""
        cfg = load_config()
        minutes = cfg.get("ego_heartbeat_minutes", 3)
        self._ego_heartbeat_timer = QTimer(self)
        self._ego_heartbeat_timer.setSingleShot(True)
        self._ego_heartbeat_timer.setInterval(minutes * 60 * 1000)
        self._ego_heartbeat_timer.timeout.connect(self._on_ego_heartbeat)
        # Ne demarrer que si l'engine est disponible
        if self._engine is not None:
            self._ego_heartbeat_timer.start()
            logger.info("[EGO:HEARTBEAT] timer demarre (3 min)")

    def _on_ego_heartbeat(self) -> None:
        """Declenche les scans de fond (ego, relationnel) apres inactivite."""
        if self._engine is None:
            return
        logger.info("[HEARTBEAT] inactivite detectee -- lancement des scans de fond")
        
        # 1. Scan Ego (conversation courante)
        self._run_ego_scan()
        
        # 2. Scan Relationnel (conversations non-scannees + courante)
        if self._relational_scanner is not None:
            self._relational_scanner.run_pending()
            
        # 3. Scan Travail (forcons un check sur la session courante)
        if self._rolling_summarizer is not None and self._conv_store is not None:
            try:
                all_msgs = self._conv_store.load_session(
                    self._conv_store.current_path.stem
                )
                self._rolling_summarizer.maybe_summarize(all_msgs)
            except Exception as exc:
                logger.debug("[HEARTBEAT:ROLLING] check ignore : %s", exc)
                
        # 4. Déduplication sémantique
        self._run_deduplication()

    def _run_deduplication(self) -> None:
        """Lance la déduplication de l'Ego et de la mémoire relationnelle."""
        if self._engine is None:
            return
            
        logger.info("[DEDUP] Lancement de la deduplication semantique en arriere-plan")
        
        # Ego Dedup
        self._ego_dedup_worker = EgoDedupWorker(
            client=self._engine._client,
            model=self._engine._model,
            current_categories=self._ego_manager.get_categories()
        )
        self._ego_dedup_worker.dedup_done.connect(self._on_ego_dedup_done)
        self._ego_dedup_worker.start()
        
        # Relational Dedup
        if hasattr(self, "_relational_db") and self._relational_db:
            self._rel_dedup_worker = RelationalDedupWorker(
                client=self._engine._client,
                model=self._engine._model,
                relational_db=self._relational_db
            )
            self._rel_dedup_worker.dedup_done.connect(self._on_rel_dedup_done)
            self._rel_dedup_worker.start()

    def _on_ego_dedup_done(self, new_categories: dict) -> None:
        self._ego_manager.save(new_categories)
        self._refresh_ego_ui()

    def _on_rel_dedup_done(self) -> None:
        if self.context_panel.memory_panel:
            self.context_panel.memory_panel._refresh_tables()

    def _run_ego_selector(self) -> None:
        if self._engine is None or self._conv_store is None:
            return
        if not self._conv_store.current_path:
            return
        try:
            history = self._conv_store.load_session(self._conv_store.current_path.stem)
        except Exception:
            return
        if not history:
            return
            
        logger.info("[EGO:SELECT] Selection des categories asynchrone...")
        worker = self._ego_manager.create_selector_worker(
            client=self._engine.client,
            model=self._engine.model,
            conversation_history=history
        )
        worker.selection_done.connect(self._on_ego_selector_done)
        
        # We need to keep a reference to the worker so it doesn't get garbage collected
        if not hasattr(self, "_ego_selector_workers"):
            self._ego_selector_workers = []
        self._ego_selector_workers.append(worker)
        worker.finished.connect(lambda: self._ego_selector_workers.remove(worker) if worker in self._ego_selector_workers else None)
        worker.start()
        
    def _on_ego_selector_done(self, active_categories: dict) -> None:
        logger.info(f"[EGO:SELECT] Categories selectionnees: {active_categories}")
        self._ego_manager.set_active_categories(active_categories)

    def _reset_ego_heartbeat(self) -> None:
        """Remet le timer a zero : a appeler apres chaque echange avec l'IA."""
        if self._engine is not None and hasattr(self, "_ego_heartbeat_timer"):
            self._ego_heartbeat_timer.start()

    def _save_ego_instruction(self, instruction: list[str]) -> None:
        """Sauvegarde l'instruction ego modifiee manuellement."""
        if self._ego_manager:
            self._ego_manager.save(instruction)
            logger.info("[EGO] instruction mise a jour manuellement via Parametres")

    def _run_ego_scan(self, on_done: object = None) -> None:
        """
        Lance le scan ego en background.

        :param on_done: callable optionnel() appele quand le scan se termine
                        (qu'il y ait eu changement ou non).
        """
        if self._engine is None:
            if callable(on_done):
                on_done()
            return
        if self._ego_scan_worker is not None and self._ego_scan_worker.isRunning():
            logger.debug("[EGO] scan deja en cours -- ignore")
            if callable(on_done):
                on_done()
            return

        # Construire l'historique de conversation
        history: list[dict] = []
        if self._conv_store is not None and self._conv_store.has_active_session:
            try:
                history = self._conv_store.load_session(
                    self._conv_store.current_path.stem
                )
            except Exception as exc:
                logger.error("[EGO] impossible de lire la session : %s", exc)

        valid_history = [m for m in history if m.get("role") in ("user", "assistant")]
        last_scanned = getattr(self._rolling_summarizer, "last_ego_scanned", 0)
        new_history = valid_history[last_scanned:]

        if not new_history:
            logger.info("[EGO] pas de nouveaux messages a analyser -- scan annule")
            if callable(on_done):
                on_done()
            return

        self._ego_pending_on_done = on_done
        self._ego_pending_scan_count = len(valid_history)

        worker = self._ego_manager.create_scan_worker(
            client=self._engine.client,
            model=self._engine.model,
            conversation_history=new_history,
            author_name=self._session["author"]["name"],
        )
        self._ego_scan_worker = worker
        worker.scan_done.connect(self._on_ego_scan_done)
        worker.scan_error.connect(self._on_ego_scan_error)
        worker.start()
        # Mettre a jour le bouton dans les Parametres
        self._set_ego_scanning(True)

    def _on_ego_scan_done(self, new_rules: dict) -> None:
        """Recoit le resultat du scan ego."""
        self._set_ego_scanning(False)
        if new_rules:
            self._ego_manager.save(new_rules)
            logger.info(
                "[EGO] regles mises a jour (%d regles)", len(new_rules)
            )
        else:
            logger.info("[EGO] pas de changement d'instruction")
        self._refresh_ego_ui()
        # Rappeler le callback de fermeture si present
        cb = self._ego_pending_on_done
        self._ego_pending_on_done = None
        if callable(cb):
            cb()
        # Relancer le heartbeat si on n'est pas en cours de fermeture
        if not getattr(self, "_closing", False):
            self._reset_ego_heartbeat()
        self._run_ego_selector()

    def _on_ego_scan_error(self, msg: str) -> None:
        """Erreur du scan ego."""
        logger.error("[EGO] erreur scan : %s", msg)
        self._set_ego_scanning(False)
        cb = self._ego_pending_on_done
        self._ego_pending_on_done = None
        if callable(cb):
            cb()
        if not getattr(self, "_closing", False):
            self._reset_ego_heartbeat()
        self._run_ego_selector()

    def _refresh_ego_ui(self) -> None:
        """Met a jour la section ego dans le panneau Parametres."""
        try:
            sec = self.context_panel.settings_panel._sec_ego
            sec.set_ego_data(
                instruction="\n".join(self._ego_manager.get_rules()),
                scan_count=self._ego_manager.scan_count,
                last_scanned_at=self._ego_manager.last_scanned_at,
            )
        except AttributeError:
            pass   # panneau pas encore construit

    def _set_ego_scanning(self, scanning: bool) -> None:
        """Active/desactive l'indicateur de scan dans le panneau Parametres."""
        try:
            self.context_panel.settings_panel._sec_ego.set_scanning(scanning)
        except AttributeError:
            pass

    def _init_bio_activation(self) -> None:
        """Compile la bio et instancie BioActivation si l'Archiviste est configure."""
        from core.session_manager import AUTHORS_DIR
        cfg = load_config()
        archiviste_cfg = resolve_engine_config(cfg["ia_archiviste"])
        if not archiviste_cfg.get("api_key"):
            logger.warning("MainWindow — BioActivation non init : cle API Archiviste manquante")
            return
        author_slug = self._session["author"]["slug"]
        author_dir  = AUTHORS_DIR / author_slug
        # Compiler la bio depuis le SQLite (operation sync rapide, pas d'API)
        bio_path = compile_bio(author_dir, self._relational_db)
        self._bio_activation = BioActivation(
            config=archiviste_cfg,
            bio_path=bio_path,
            author_name=self._session["author"]["name"],
        )
        self._bio_activation.injection_ready.connect(self._on_bio_injection_ready)
        self._bio_activation.memorize_detected.connect(self._on_live_memorize)
        logger.info("MainWindow — BioActivation initialise")

    def _on_relational_scan_complete(self, added: int) -> None:
        if added:
            logger.info("RelationalScanner — scan complet : %d entree(s) ajoutee(s)", added)
            self.context_panel.memory_panel.refresh()
            self._recompile_bio()
        # Remettre le bouton Analyser dans son état normal dans tous les cas
        self.context_panel.memory_panel.set_scanning(False)

    # ── Ghost Writer ──────────────────────────────────────────────────────────

    def _on_ghost_editor_attached(self) -> None:
        """
        L'éditeur tiers vient d'être attaché.
        Lance un scan auto après 800ms pour recharger les badges immédiatement.
        """
        self.ai_panel.ghost_scan_finished()   # réinitialise l'état du bouton
        QTimer.singleShot(800, self._on_ghost_scan_requested)

    def _on_ghost_toggle_overlay(self) -> None:
        """Bascule l'activation du système Ghost Writer (overlay + scroll tracker + scan)."""
        if self._ghost_overlay.isVisible():
            # Désactivation : masquer + arrêter le tracker
            self._ghost_overlay.hide()
            self._scroll_tracker.detach()
            self.ai_panel.set_ghost_active(False)
        else:
            # Réactivation : afficher + rebrancher le tracker
            self._ghost_overlay.show()
            hwnd = self.editor_zone.embedded_hwnd
            if hwnd is not None:
                self._scroll_tracker.attach(hwnd, self.editor_zone.height())
            self.ai_panel.set_ghost_active(True)

    def _on_badge_opacity_changed(self, opacity: float) -> None:
        """Mise à jour immédiate de l'opacité des badges sans redémarrage."""
        self._badge_opacity = opacity
        self._apply_badge_colors()

    def _on_scroll_speed_changed(self, speed: int) -> None:
        """Mise à jour immédiate de la vitesse de synchro scroll."""
        self._scroll_speed = speed
        self._scroll_tracker.set_speed(speed)

    def _on_badge_margin_r_changed(self, margin: int) -> None:
        """Mise à jour immédiate de la marge droite des badges."""
        self._badge_margin_r = margin
        self._ghost_overlay.set_margin_r(margin)




    def _on_badge_x_offset_changed(self, offset: int) -> None:
        """Mise à jour en mémoire immédiate, sauvegarde disque débouncée (500ms)."""
        self._badge_x_offset = offset
        self._x_offset_save_timer.start()

    def _persist_badge_x_offset(self) -> None:
        """Sauvegarde effective de badge_x_offset dans app_config.json."""
        from core.config_manager import load_config, save_config
        cfg = load_config()
        cfg["badge_x_offset"] = self._badge_x_offset
        save_config(cfg)

    def _ghost_current_anchor(self) -> str:
        """
        Retourne l'ancre pour une annotation Ghost Writer.
        Priorité : dernier extrait partagé dans le contexte IA,
        sinon dernier texte du presse-papier système.
        Lève ValueError si aucune ancre utilisable.
        """
        # 1. Extrait partagé explicitement vers l'IA (via notification clipboard)
        if len(self._last_shared_clip.strip()) >= 10:
            return self._last_shared_clip.strip()
        # 2. Fallback : presse-papier système
        anchor = self._clipboard_monitor._last_text.strip()
        if len(anchor) < 10:
            raise ValueError(
                "Aucun extrait partagé disponible comme ancre. "
                "Copiez d'abord le passage à annoter, puis cliquez 'Envoyer' "
                "dans la notification pour l'ajouter au contexte."
            )
        return anchor

    def _ghost_create_annotation(self, note: str) -> None:
        """
        Crée une annotation Ghost Writer depuis la commande /annotation ou un trigger naturel.
        Ancre = dernier texte du presse-papier. Document = titre Win32 de la fenêtre attachée.
        """
        if not note:
            self.ai_panel.append_injected(
                tr("Ghost Writer"), tr("(/annotation) Note vide — format : /annotation [texte de la note]")
            )
            return

        try:
            anchor = self._ghost_current_anchor()
        except ValueError as exc:
            self.ai_panel.append_injected(tr("Ghost Writer"), tr(str(exc)))
            return

        document = self._ghost_document_name()
        label    = note[:30].rstrip() + ("…" if len(note) > 30 else "")

        ann = self._annotation_store.add(document, anchor, label, note)
        self.ai_panel.append_injected(
            tr("Ghost Writer"),
            tr("🟡 Annotation créée sur \u00ab {}… \u00bb — \u00ab {} \u00bb").format(anchor[:50], label),
        )
        logger.info(
            "GhostWriter — annotation %d créée pour document '%s' : %r",
            ann.id, document, note[:60],
        )


    # ── Détection triggers naturels ───────────────────────────────────────────────────

    # Mots-clés racines : si l'un d'eux est présent dans le message normalisé
    # → considéré comme une demande d'annotation.
    # On utilise des fragments courts pour couvrir impératif, infinitif, interrogatif.
    _ANNOTATION_TRIGGERS = (
        # fragment "annotation" + verbe d'action
        "faire une annotation",
        "fais une annotation",
        "fais moi une annotation",
        "cree une annotation",
        "creer une annotation",
        "ecris une annotation",
        "redige une annotation",
        "mets une annotation",
        "mets en annotation",
        "ajoute une annotation",
        "pose une annotation",
        # fragment "note" + verbe d'action
        "faire une note",
        "fais une note",
        "fais moi une note",
        "ecris une note",
        "ajoute une note",
        "mets une note",
        "redige une note",
        # formes courtes directes
        "annote ca",
        "note ca",
        # interrogatif : "tu peux faire une annotation", "peux-tu faire une note"
        "peux faire une annotation",
        "peux faire une note",
        "peux tu faire une annotation",
        "peux tu faire une note",
        # formulation "je voudrais / j'aimerais une annotation"
        "voudrais une annotation",
        "aimerais une annotation",
        "voudrais que tu fasses une annotation",
        "aimerais que tu fasses une annotation",
    )

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Minuscules + suppression des accents pour comparaison souple."""
        import unicodedata
        nfd = unicodedata.normalize("NFD", text.lower())
        return "".join(c for c in nfd if unicodedata.category(c) != "Mn")

    def _detect_annotation_trigger(self, text: str) -> str | None:
        """
        Détecte les phrases naturelles d'annotation dans le message utilisateur.
        La comparaison est insensible à la casse ET aux accents.

        Retourne la note extraite si un trigger est trouvé, None sinon.
        Si le message ne contient pas de texte de note après le trigger, la note
        vaut le texte complet du message (EUGENIA rédige elle-même la note).
        """
        normalized = self._normalize_text(text)
        for trigger in self._ANNOTATION_TRIGGERS:
            if trigger in normalized:
                idx = normalized.index(trigger) + len(trigger)
                remainder = text[idx:].lstrip(" :\u202f")
                return remainder if remainder else text
        return None

    # ─────────────────────────────────────────────────────────────────────────

    def _ghost_request_annotation_from_ai(self, user_request: str) -> None:
        """
        Lance l'Archiviste pour générer une annotation intelligente.
        L'Archiviste reçoit la demande + le dernier extrait partagé comme contexte.
        """
        from core.config_manager import load_config
        from core.providers import resolve_engine_config
        from core.annotation_generator import AnnotationGenerator

        cfg = load_config()
        archiviste_cfg = resolve_engine_config(cfg["ia_archiviste"])
        if not archiviste_cfg.get("api_key"):
            self.ai_panel.append_injected(
                tr("Ghost Writer"), tr("⚠️ Archiviste non configuré — impossible de générer l'annotation.")
            )
            return

        self.ai_panel.append_injected(tr("Ghost Writer"), tr("⏳ Rédaction de l'annotation en cours…"))

        worker = AnnotationGenerator(
            config=archiviste_cfg,
            user_request=user_request,
            context_clip=self._last_shared_clip,
        )
        worker.annotation_ready.connect(self._on_annotation_generated)
        worker.error_occurred.connect(
            lambda msg: self.ai_panel.append_injected(tr("Ghost Writer"), tr("❌ {}").format(msg))
        )
        self._annotation_worker = worker
        worker.start()

    def _on_annotation_generated(self, label: str, note: str) -> None:
        """Reçoit label + note depuis l'Archiviste, crée le badge."""
        try:
            anchor = self._ghost_current_anchor()
        except ValueError as exc:
            self.ai_panel.append_injected(tr("Ghost Writer"), tr(str(exc)))
            return

        document = self._ghost_document_name()
        ann = self._annotation_store.add(document, anchor, label, note)

        if self._ghost_overlay.isVisible():
            self._ghost_overlay.scan_requested.emit()

        self.ai_panel.append_injected(
            tr("Ghost Writer"),
            tr("🟡 Annotation créée : **{}**\n{}").format(label, note),
        )
        logger.info(
            "GhostWriter — annotation %d générée par Archiviste pour document '%s' : %r",
            ann.id, document, note[:60],
        )

    def _ghost_document_name(self) -> str:
        """
        Nom du document actuellement attaché dans EditorZone.
        Utilise le titre Win32 de la fenêtre, ou "__default__" si indisponible.
        """
        hwnd = self.editor_zone._embedded_hwnd
        if hwnd is not None:
            import win32gui
            title = win32gui.GetWindowText(hwnd)
            if title:
                return title
        return "__default__"

    def _on_screenshot_requested(self) -> None:
        """
        Capture la fenêtre de l'éditeur embarqué et l'attache comme pièce jointe
        QPixmap de la fenêtre Win32, puis l'encode en PNG base64.
        """
        import base64
        from PyQt6.QtCore import QBuffer, QByteArray
        from PyQt6.QtCore import QIODeviceBase
        hwnd = self.editor_zone.embedded_hwnd
        if hwnd is None:
            logger.warning("[SCREENSHOT] aucun éditeur attaché")
            return
        screen = QApplication.primaryScreen()
        pixmap = screen.grabWindow(hwnd)
        if pixmap.isNull():
            logger.warning("[SCREENSHOT] grabWindow a échoué pour hwnd=%d", hwnd)
            return
        buf = QBuffer()
        buf.open(QIODeviceBase.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        png_bytes = bytes(buf.data())
        b64 = base64.b64encode(png_bytes).decode("ascii")
        file_data = {
            "type":     "image",
            "filename": "capture_editeur.png",
            "content":  "",
            "mime":     "image/png",
            "b64":      b64,
        }
        self.ai_panel.set_screenshot(file_data)
        logger.info("[SCREENSHOT] capture éditeur encodée (%d bytes PNG)", len(png_bytes))

    def _on_ghost_scan_requested(self) -> None:
        """Bouton Scanner cliqué — lance le thread OCR."""
        if self._ghost_scanner is not None and self._ghost_scanner.isRunning():
            logger.warning("GhostWriter — scan déjà en cours, ignoré")
            self._ghost_overlay.scan_finished()
            self.ai_panel.ghost_scan_finished()
            return

        ocr_backend = self._startup_cfg.get("ocr_engine", "winrt")
        self._ghost_scanner = GhostScanner(self.editor_zone, backend=ocr_backend, parent=self)
        self._ghost_scanner.scan_done.connect(self._on_ghost_scan_done)
        self._ghost_scanner.scan_error.connect(self._on_ghost_scan_error)
        self._ghost_scanner.start()
        logger.info("GhostWriter — scan OCR lancé")

    def _on_ghost_scan_done(self, blocks: list) -> None:
        """Résultats OCR reçus — matcher les ancres et placer les badges."""
        self._ghost_overlay.scan_finished()
        self.ai_panel.ghost_scan_finished()
        document    = self._ghost_document_name()
        annotations = self._annotation_store.get_for_document(document)
        results     = match_annotations(annotations, blocks)

        self._ghost_overlay.clear_badges()
        for r in results:
            self._ghost_overlay.place_badge(r.annotation_id, r.label, r.note, r.center_y)


        # (Re)calibrer le tracker scroll après chaque scan
        hwnd = self.editor_zone.embedded_hwnd
        if hwnd is not None:
            attached = self._scroll_tracker.attach(hwnd, self.editor_zone.height())
            if not attached:
                # Fallback : recalibration si déjà actif
                self._scroll_tracker.recalibrate(self.editor_zone.height())

        logger.info(
            "GhostWriter — scan terminé : %d blocs OCR, %d annotations, %d matchées",
            len(blocks), len(annotations), len(results),
        )

    def _on_ghost_scan_error(self, message: str) -> None:
        """Erreur OCR — réactive le bouton et affiche une notification à l'utilisateur."""
        self._ghost_overlay.scan_finished()
        self.ai_panel.ghost_scan_finished()
        logger.error("GhostWriter — erreur scan : %s", message)

        screen = self.screen()
        notif = ClipboardNotification(
            text=tr("⚠ Erreur OCR Ghost Writer\n{}").format(message),
            screen=screen,
        )
        notif.show()

    def _on_scroll_delta(self, delta_px: int) -> None:
        """Scroll détecté — déplace les badges immédiatement (estimation)."""
        self._ghost_overlay.shift_badges_by(delta_px)

    def _on_scroll_rescan_requested(self) -> None:
        """L'utilisateur a cessé de scroller — relancer un scan précis."""
        if not self._ghost_overlay.isVisible():
            return   # Ghost Writer désactivé, on ne scanne pas
        if self._ghost_scanner is not None and self._ghost_scanner.isRunning():
            return   # scan déjà en cours, on attend
        self._on_ghost_scan_requested()

    def _on_ghost_annotation_deleted(self, annotation_id: int) -> None:
        """Badge supprimé depuis le calque — efface l'annotation du store."""
        self._annotation_store.delete(annotation_id)
        self._ghost_overlay.remove_badge(annotation_id)
        logger.info("GhostWriter — annotation %d supprimée", annotation_id)


    def _on_ghost_annotation_edited(self, annotation_id: int, new_label: str, new_note: str) -> None:
        """Badge édité depuis le popup — met à jour le store."""
        self._annotation_store.update_note(annotation_id, new_label, new_note)
        logger.info("GhostWriter — annotation %d mise à jour : %r", annotation_id, new_note[:40])

    # ─────────────────────────────────────────────────────────────────────────

    def _on_memory_scan_requested(self) -> None:
        """Bouton 'Analyser' du MemoryPanel : lance un scan relationnel immédiat."""
        if self._relational_scanner is None:
            self.context_panel.memory_panel.set_scanning(False)
            logger.warning("MainWindow — scan demande mais RelationalScanner non init")
            return
        logger.info("MainWindow — scan memoire relationnelle demande par l'utilisateur")
        self._relational_scanner.run_pending()
        self._run_ego_scan()

    def _recompile_bio(self) -> None:
        """Recompile author_bio_compiled.json apres toute nouvelle memorisation."""
        if self._bio_activation is None:
            return
        from core.session_manager import AUTHORS_DIR
        author_slug = self._session["author"]["slug"]
        author_dir  = AUTHORS_DIR / author_slug
        compile_bio(author_dir, self._relational_db)
        logger.debug("MainWindow — bio recompilee")

    def _init_summarizer(self, project_dir):
        """Initialise le SessionSummarizer et injecte le résumé de la session precedente."""
        cfg = load_config()
        engine_cfg = resolve_engine_config(cfg["ia_principale"])
        if not engine_cfg.get("api_key"):
            logger.warning("MainWindow — SessionSummarizer non initialise : cle API manquante")
            return
        self._summarizer = SessionSummarizer(project_dir, engine_cfg)
        last = self._summarizer.load_last_summary()
        if last and self._engine:
            self._engine.inject_system_prompt(
                "[MÉMOIRE DE TRAVAIL — session précédente]\n"
                "Voici un résumé de ta dernière session avec l'auteur. "
                "Utilise-le pour assurer la continuité.\n\n"
                + last
            )
            logger.info("MainWindow — résumé session précédente injecté en contexte")

    def _init_rolling_summarizer(self) -> None:
        """Initialise le RollingSummarizer pour la session active."""
        cfg = load_config()
        engine_cfg = resolve_engine_config(cfg["ia_principale"])
        if not engine_cfg.get("api_key"):
            logger.warning("MainWindow — RollingSummarizer non init : clé API manquante")
            return
        if self._conv_store is None or self._conv_store.current_path is None:
            return
        from core.rolling_summarizer import RollingSummarizer
        meta = RollingSummarizer.meta_path_for(self._conv_store.current_path)
        self._rolling_summarizer = RollingSummarizer(engine_cfg, meta, parent=self)
        self._rolling_summarizer.summary_ready.connect(
            lambda: logger.info("[ROLLING] résumé glissant créé et persisté")
        )
        logger.info("MainWindow — RollingSummarizer initialisé")

    def _init_style_profiler(self, project_dir):
        """Initialise le StyleProfiler, charge le profil existant et le branche sur l'UI."""
        cfg = load_config()
        engine_cfg = resolve_engine_config(cfg["ia_principale"])
        if not engine_cfg.get("api_key"):
            logger.warning("MainWindow — StyleProfiler non initialise : cle API manquante")
            return
        self._style_profiler = StyleProfiler(project_dir, engine_cfg)
        # Charger et afficher le profil existant
        existing = self._style_profiler.load_profile()
        if existing:
            self.context_panel.style_panel.show_profile(existing)
            if self._engine:
                self._engine.inject_context_note(
                    f"[PROFIL DE STYLE DE L'AUTEUR]\n{existing}"
                )
            logger.info("MainWindow — profil de style charge et injecté")
        # Brancher les signaux
        self._style_profiler.profile_ready.connect(self._on_style_profile_ready)
        self.context_panel.style_panel.analyze_requested.connect(self._on_style_analyze_requested)

    def _on_style_analyze_requested(self):
        """Lance l'analyse de style a partir des chunks FAISS."""
        if self._style_profiler is None:
            return
        if self._vector_index.is_empty():
            logger.warning("MainWindow — style_analyze : index FAISS vide, aucun chunk disponible")
            return
        # Prend les 20 premiers chunks de l'index comme echantillon representatif
        hits = self._vector_index.search(
            "style ecriture narration description personnages", k=20
        )
        sample = "\n\n".join(h["text_parent"] for h in hits)
        source_ids = list({h["source_id"] for h in hits})
        self._style_profiler.analyze(sample, source_ids)

    def _on_style_profile_ready(self, profile_text: str):
        """Recu apres analyse : affiche + injecte en contexte."""
        self.context_panel.style_panel.show_profile(profile_text)
        if self._engine:
            self._engine.inject_context_note(
                f"Profil de style de l'auteur :\n{profile_text}"
            )
        logger.info("MainWindow — profil de style mis a jour")

    def _init_conversation_store(self):
        """Cree le store JSONL et demarre une nouvelle session de conversation."""
        project_slug = self._session["project"]["slug"]
        self._conv_store = ConversationStore(project_slug)
        self._conv_store.start_session()
        self.context_panel.history_panel.set_store(self._conv_store)
        self.context_panel.history_panel.resume_requested.connect(self._on_resume_session)
        self.context_panel.history_panel.new_requested.connect(self._on_new_session)
        self.context_panel.history_panel.scan_requested.connect(self._on_scan_history_requested)
        self.context_panel.history_panel.session_deleted.connect(self._on_session_deleted)
        logger.info("MainWindow — ConversationStore initialise (projet=%s)", project_slug)

        # Initialiser le RollingSummarizer pour cette session
        self._init_rolling_summarizer()

        # Charger le cache cognitif pour cette session
        if self._conv_store.current_path:
            self._cognitive_cache.load(self._conv_store.current_path)
        # Brancher le preprocesseur sur l'engine (strip des commandes CACHE)
        if self._engine:
            self._engine.set_response_preprocessor(self._master_preprocessor)
            # Injecter l'instruction système (une seule fois, permanente dans l'historique)
            self._engine.inject_system_prompt(
                f"[INSTRUCTION — cache cognitif]\n{CACHE_INSTRUCTION}"
            )
            logger.info("[CACHE-COG] instruction système injectée dans l'engine")

        # Initialiser le store de sources
        project_dir = PROJECTS_DIR / project_slug
        self._source_store = SourceStore(project_dir)
        sp = self.context_panel.sources_panel
        sp.set_store(self._source_store)
        sp.reingest_requested.connect(self._on_reingest_requested)
        sp.import_requested.connect(self._open_ingest_dialog)
        sp.import_path_requested.connect(self._open_ingest_dialog)
        sp.remove_requested.connect(self._on_remove_requested)
        sp.mute_requested.connect(self._on_mute_requested)

        # Initialiser l'index vectoriel FAISS
        self._vector_index = VectorIndex(project_dir)
        logger.info("MainWindow — VectorIndex initialise (vide=%s)", self._vector_index.is_empty())
        # Appliquer la config de deduplication et le modele embed depuis app_config.json
        _cfg = load_config()
        _mem_cfg = _cfg.get("memory", {})
        self._vector_index.set_dedup_config(
            enabled=_mem_cfg.get("faiss_dedup_enabled", True),
            threshold=_mem_cfg.get("faiss_dedup_threshold", 0.93),
        )
        self._vector_index.set_embed_config(
            resolve_engine_config(_cfg.get("ia_embed", {}))
        )

        # Initialiser le summarizer de session (résumé à la fermeture)
        self._summarizer: SessionSummarizer | None = None
        self._init_summarizer(project_dir)

        # Résumé glissant en cours de session (RollingSummarizer)
        # (pré-déclaré dans _setup_ui avant _init_conversation_store)

        # Cache cognitif (mémoire de travail de l'IA, invisible pour l'auteur)
        # (pré-déclaré dans _setup_ui avant _init_conversation_store)

        # Initialiser le profiler de style
        self._style_profiler: StyleProfiler | None = None
        self._init_style_profiler(project_dir)

        # Initialiser le scanner de memoire relationnelle
        self._relational_scanner: RelationalScanner | None = None
        self._init_relational_scanner()
        self._init_bio_activation()
        # Instruction mouvante ego
        self._ego_manager: EgoManager = EgoManager()
        self._ego_scan_worker: EgoScanWorker | None = None
        self._ego_pending_on_done: object = None   # callable | None
        self._init_ego() 
        # Lancer un dedup a l'ouverture
        QTimer.singleShot(5000, self._run_deduplication)
        self.context_panel.set_ego_manager(self._ego_manager)
        self._init_ego_heartbeat_timer()

    # ------------------------------------------------------------------ #
    # Clipboard Monitor                                                    #
    # ------------------------------------------------------------------ #

    def _on_clipboard_text(self, text: str):
        """Appelé quand le monitor détecte un texte copié significatif."""
        # Une seule notification à la fois
        if self._active_notif and not self._active_notif.isHidden():
            self._active_notif.close()

        screen = self.screen()
        notif = ClipboardNotification(text=text, screen=screen)
        notif.send_requested.connect(self._on_clipboard_send)
        self._active_notif = notif
        notif.show()

    def _on_clipboard_send(self, text: str):
        """L'auteur a cliqué 'Envoyer' sur la notification."""
        # Mémoriser l'extrait comme ancre potentielle pour Ghost Writer
        self._last_shared_clip = text
        # Injection dans le moteur IA (cerveau chaud)
        if self._engine:
            self._engine.inject(text, label="Extrait partagé via presse-papier")
        # Affichage dans le panneau conversation
        self.ai_panel.append_injected(tr("Extrait"), text)
        # Archiviste : analyse et stockage dans la Bible (async)
        if self._archiviste:
            self._archiviste.ingest_text(text, source_id="clipboard")

    # ------------------------------------------------------------------ #
    # Orchestration Archiviste + envoi IA principale                       #
    # ------------------------------------------------------------------ #

    def _on_ai_send_requested(self, text: str):
        """
        Intercepté avant engine.send().
        - /web [recherche] : recherche web puis injection des resultats
        - /mem [element] : memorisation directe via l'Archiviste (routage auto)
        - Sinon : lance l'Archiviste en mode lecture, puis engine.send()
        """
        stripped = text.strip()

        # ── Commande /edit ─────────────────────────────────────────────────────
        if stripped.lower().startswith("/edit"):
            parts = stripped.split(None, 1)
            title = parts[1].strip() if len(parts) > 1 else "Sans titre"
            self._enter_edit_mode(title=title)
            if len(parts) == 1:
                # Ouverture simple sans prompt -> on s'arrete
                self.ai_panel.set_busy(False)
                return
            
            # Sinon on a une requete a traiter. On redefinit text sans le '/edit'
            # pour que l'IA comprenne bien l'instruction.
            text = title
            stripped = text.strip()
            # On ne return pas ! Le flux normal va s'en charger (Archiviste -> engine.send)

        # ── Commande /edition ──────────────────────────────────────────────────
        if stripped.lower().startswith("/edition "):
            title = stripped[9:].strip()
            if not title:
                self.ai_panel.append_injected(
                    tr("EUGENIA"), tr("(/edition) Precisez le titre du document apres /edition.")
                )
                self.ai_panel.set_busy(False)
                return
            doc = self._edit_store.find_by_title(title)
            if doc is None:
                self.ai_panel.append_injected(
                    tr("EUGENIA"), tr("(/edition) Document introuvable : {}.").format(title)
                )
                self.ai_panel.set_busy(False)
                return
            self._enter_edit_mode(doc=doc)
            self.ai_panel.set_busy(False)
            return

        # ── Commande /web ──────────────────────────────────────────────────────
        if stripped.lower().startswith("/web "):
            query = stripped[5:].strip()
            if not query:
                self.ai_panel.append_injected(
                    tr("EUGENIA"), tr("(/web) Precisez votre recherche apres /web.")
                )
                self.ai_panel.set_busy(False)
                return
            if self._engine is None:
                self.ai_panel.append_injected(
                    tr("EUGENIA"), tr("(/web) Moteur IA non configure.")
                )
                self.ai_panel.set_busy(False)
                return
            cfg = load_config().get("web_search", {})
            provider    = cfg.get("provider", "duckduckgo")
            api_key     = cfg.get("api_key", "")
            max_results = int(cfg.get("max_results", 5))
            logger.info("[WEB] commande /web -- provider=%s | query=%s", provider, query[:60])
            self.ai_panel.append_injected(
                tr("EUGENIA"), tr("Recherche web ({}) : {}…").format(provider, query)
            )
            worker = WebSearchWorker(provider, api_key, query, max_results)
            self._web_search_worker = worker
            worker.results_ready.connect(
                lambda block, q=query: self._on_web_search_ready(block, q)
            )
            worker.search_error.connect(
                lambda err, q=query: self._on_web_search_error(err, q)
            )
            worker.start()
            return

        # ── Commande /mem ──────────────────────────────────────────────────────
        if stripped.lower().startswith("/mem "):
            mem_text = stripped[5:].strip()
            if mem_text and self._relational_scanner is not None:
                archiviste = self._relational_scanner._archiviste

                def _on_mem_added(n, t=mem_text):
                    self._on_mem_memorized(t, "relationnelle", n)
                    self._recompile_bio()

                def _on_mem_work(content):
                    self._on_mem_memorized(content, "travail", 1)
                    # Persistance dans la Bible via ingest
                    if self._archiviste:
                        self._archiviste.ingest_text(content, source_id="mem_direct")
                        logger.info("[MEM:WRITE] /mem work persiste dans la Bible : %s", content[:60])

                archiviste.entries_added.connect(_on_mem_added)
                archiviste.mem_routed_to_work.connect(_on_mem_work)
                archiviste.nothing_found.connect(
                    lambda t=mem_text: self._on_mem_memorized(t, "doublon", 0)
                )
                archiviste.memorize_direct(mem_text)
                self._relational_scanner.run_pending()
            else:
                self.ai_panel.append_injected(
                    tr("EUGENIA"), tr("(/mem) Aucun contenu a memoriser ou systeme non configure.)")
                )
            self.ai_panel.set_busy(False)
            return

        # ── Commande /bible ───────────────────────────────────────────────────
        if stripped.lower() == "/journal ego":
            journal = self._ego_manager.get_journal()
            if not journal:
                self.ai_panel.append_injected(tr("EUGENIA"), tr("(/journal ego) Le journal d'introspection est vide."))
                self.ai_panel.set_busy(False)
                return
            
            lines = []
            for entry in journal:
                lines.append(f"[{entry['time']}] {entry['conseil']}")
                
            dump = "\n".join(lines)
            # Inject into system prompt
            self._engine.inject_context_note(f"Journal d'Introspection Recent :\n{dump}")
            self.ai_panel.append_injected(tr("Archiviste"), tr("(/journal ego) Journal injecte dans le contexte de l'IA."))
            self.ai_panel.set_busy(False)
            return

        if stripped.lower() == "/bible":
            if self._archiviste is None:
                self.ai_panel.append_injected(
                    tr("EUGENIA"), tr("(/bible) Archiviste non configure.")
                )
                self.ai_panel.set_busy(False)
                return
            all_entries = self._archiviste.bible_db.get_all_tables()
            if not all_entries:
                self.ai_panel.append_injected(
                    tr("EUGENIA"), tr("(/bible) La Bible est vide.")
                )
                self.ai_panel.set_busy(False)
                return
            lines = []
            current_table = None
            for e in all_entries:
                if e["table"] != current_table:
                    current_table = e["table"]
                    lines.append(f"\n[{current_table.upper()}]")
                lines.append(f"  • {e['label']} : {e['content'][:300]}")
            dump = "\n".join(lines).strip()
            self._engine.inject_context_note(
                f"Bible complete du projet :\n{dump}"
            )
            self.ai_panel.append_injected(
                tr("Archiviste"),
                tr("Bible injectee ({} entrees) dans le prochain message.").format(len(all_entries)),
            )
            logger.info("[BIBLE:INJECT] dump complet : %d entrees", len(all_entries))
            self.ai_panel.set_busy(False)
            return

        # ── Commande /mem_bible ────────────────────────────────────────────────
        if stripped.lower().startswith("/mem_bible "):
            mem_text = stripped[11:].strip()
            if mem_text and self._archiviste:
                self._archiviste.ingest_text(mem_text, source_id="mem_bible")
                self.ai_panel.append_injected(
                    tr("Archiviste"), tr("Envoye a la Bible : {}").format(mem_text[:80])
                )
                logger.info("[MEM:WRITE] /mem_bible -> Bible : %s", mem_text[:60])
            else:
                self.ai_panel.append_injected(
                    tr("EUGENIA"), tr("(/mem_bible) Aucun contenu ou Archiviste non configure.")
                )
            self.ai_panel.set_busy(False)
            return

        # ── Commande /annotation ──────────────────────────────────────────────
        if stripped.lower().startswith("/annotation "):
            note = stripped[12:].strip()
            self._ghost_create_annotation(note)
            self.ai_panel.set_busy(False)  # débloquer — aucune réponse IA attendue
            return

        # ── Commande /stat ────────────────────────────────────────────────────
        if stripped.lower().startswith("/stat "):
            stat_request = stripped[6:].strip()
            if not stat_request:
                self.ai_panel.append_injected(
                    tr("EUGENIA"),
                    tr("(/stat) Décris la statistique souhaitée après /stat.\n"
                    "Exemple : /stat fais un camembert des catégories sociales de ma famille"),
                )
                self.ai_panel.set_busy(False)
                return
            self._pending_stat_mode = True

            _stats_panel = self.context_panel.stats_panel
            _use_docs  = _stats_panel.use_docs
            _use_bible = _stats_panel.use_bible

            from core.docx_reader import read_docx as _read_docx
            from pathlib import Path as _Path_stat
            _docs_injected = 0

            # ── Docs importés ──────────────────────────────────────────────
            if _use_docs:
                tracked_docs = self._stats_store.list_doc_stats()
                for _doc_entry in tracked_docs:
                    _doc_path = _Path_stat(_doc_entry.path)
                    if _doc_path.exists() and _doc_path.suffix.lower() == ".docx":
                        try:
                            _content = _read_docx(_doc_path)
                            if self._engine:
                                self._engine.inject_context_note(
                                    f"[DOCUMENT SUIVI — {_doc_entry.title} "
                                    f"({_doc_entry.latest_word_count or '?'} mots)]\n"
                                    f"Contenu complet :\n\n"
                                    f"{_content}"
                                )
                            _docs_injected += 1
                            logger.info("[STATS:/stat] doc injecte : %s (%d chars)", _doc_entry.title, len(_content))
                        except Exception as _exc:
                            logger.warning("[STATS:/stat] impossible de lire '%s' : %s", _doc_entry.path, _exc)

            # ── Bible complète ─────────────────────────────────────────────
            _bible_injected = False
            if _use_bible and self._archiviste is not None:
                try:
                    _all_entries = self._archiviste.bible_db.get_all_tables()
                    if _all_entries:
                        _lines = []
                        for _e in _all_entries:
                            _lines.append(f"[{_e.get('table','?').upper()}] {_e.get('label','?')}\n{_e.get('content','')}")
                        if self._engine:
                            self._engine.inject_context_note(
                                f"[BIBLE DU PROJET — {len(_all_entries)} entrées]\n\n"
                                + "\n\n---\n\n".join(_lines)
                            )
                        _bible_injected = True
                        logger.info("[STATS:/stat] Bible injectée (%d entrées)", len(_all_entries))
                except Exception as _exc:
                    logger.warning("[STATS:/stat] impossible d'injecter la Bible : %s", _exc)

            _sources_desc = []
            if _docs_injected > 0:
                _sources_desc.append(f"{_docs_injected} document(s) suivi(s)")
            if _bible_injected:
                _sources_desc.append("la Bible du projet")
            _sources_str = " et ".join(_sources_desc) if _sources_desc else None

            _STAT_JSON_PROMPT = (
                "Tu es l'archiviste statisticien d'EUGENIA. L'utilisateur demande une statistique personnalisée.\n"
                + (
                    f"Le contenu de {_sources_str} a été injecté ci-dessus dans le contexte. "
                    "Analyse-le directement pour produire la statistique demandée. "
                    "NE PAS demander des données qui se trouvent déjà dans ces sources.\n"
                    if _sources_str
                    else ""
                )
                + "Si tu as TOUTES les données nécessaires dans le contexte, réponds UNIQUEMENT avec ce JSON strict "
                "(aucun texte avant ou après) :\n"
                '{"stat_name": "...", "chart_type": "pie|bar|line", '
                '"data": {"labels": [...], "values": [...]}, "description": "..."}\n'
                "Si et SEULEMENT si des données sont absolument introuvables dans le contexte, réponds :\n"
                '{"needs_data": true, "questions": ["question 1"]}\n'
                "Règle graphique : 'pie' pour proportions/pourcentages (values doit totaliser 100), "
                "'bar' pour comparaisons, 'line' pour évolutions temporelles. "
                "Extrais les données des sources fournies — ne demande JAMAIS ce qui est lisible dans le contexte."
            )
            if self._engine:
                self._engine.inject_context_note(_STAT_JSON_PROMPT)
            # Rebind : on envoie la requête propre (sans le préfixe /stat)
            # Le flux normal ci-dessous traitera l'éventuelle pièce jointe et appellera engine.send()
            text = stat_request
            stripped = stat_request

        # ── Triggers naturels Ghost Writer ────────────────────────────────────
        annotation_note = self._detect_annotation_trigger(stripped)
        if annotation_note is not None:
            logger.info("[GHOST] trigger d'annotation détecté — request=%r", stripped[:60])
            self._ghost_request_annotation_from_ai(stripped)
            self.ai_panel.set_busy(False)  # aucune réponse IA principale attendue
            return

        # ── Flux normal ────────────────────────────────────────────────────────
        # ── Mode document : injection du contenu de l'éditeur ─────────────────
        if self._doc_mode and self._doc_ctrl.is_connected() and self._engine:
            doc_text = self._doc_ctrl.read_visible_text()
            if doc_text.strip():
                _DOC_MAX = 12_000
                truncated = len(doc_text) > _DOC_MAX
                snippet = doc_text[:_DOC_MAX]
                logger.info(
                    "[DOC:MODE] contenu lu (%d chars%s) — aperçu : %.150r",
                    len(doc_text), ", tronqué" if truncated else "", doc_text[:150],
                )
                note = (
                    f"[DOCUMENT OUVERT DANS L'ÉDITEUR TIERS — SOURCE PRIMAIRE ACTUELLE]\n"
                    f"IMPORTANT : Ce contenu est lu EN TEMPS RÉEL depuis l'écran de l'utilisateur. "
                    f"C'est la source d'information principale pour répondre à sa prochaine question. "
                    f"Ne pas confondre avec les sessions précédentes ou la mémoire personnelle.\n"
                    f"Contenu ({'tronqué' if truncated else 'complet'}) :\n\n"
                    f"{snippet}"
                    + ("\n[... suite du document non transmise ...]" if truncated else "")
                )
                self._engine.inject_context_note(note)
                logger.info(
                    "[DOC:MODE] contenu injecté (%d chars%s)",
                    len(doc_text), ", tronqué" if truncated else "",
                )

        # ── Pièce jointe ──────────────────────────────────────────────────────
        attachment = self.ai_panel.pop_attachment()
        if attachment and self._engine:
            if attachment["type"] == "text":
                content_preview = attachment["content"][:8000]
                self._engine.inject_context_note(
                    f"[FICHIER JOINT : {attachment['filename']}]\n{content_preview}"
                )
                self.ai_panel.append_injected(
                    tr("Fichier joint"),
                    attachment["filename"],
                )
                logger.info(
                    "[ATTACH:TEXT] '%s' injecte (%d chars)",
                    attachment["filename"], len(attachment["content"]),
                )
            elif attachment["type"] == "image":
                self._engine.queue_image(attachment["b64"], attachment["mime"])
                self.ai_panel.append_injected(
                    tr("Image jointe"),
                    attachment["filename"],
                )
                logger.info(
                    "[ATTACH:IMAGE] '%s' mise en file (%s)",
                    attachment["filename"], attachment["mime"],
                )

        # --- Trigger Naturel : Rappel d'anciennes sessions ---
        import re
        if re.search(r"\b(souviens|rappelle|conversation(s)? passée(s)?|dernière(s)? conversation(s)?|dernière(s)? session(s)?|hier)\b", stripped, re.IGNORECASE):
            if self._summarizer:
                recents = self._summarizer.load_recent_summaries(limit=3)
                if recents:
                    context_lines = []
                    for idx, r in enumerate(recents):
                        context_lines.append(f"--- Archive {idx+1} ---\n{r}")
                    full_context = "\n".join(context_lines)
                    self._engine.inject_context_note(
                        f"[ARCHIVES DE SESSIONS (Récupérées suite à ta demande)]\n"
                        f"Voici les résumés des dernières sessions. Sers-t-en pour te rafraîchir la mémoire et assurer la continuité de la conversation :\n\n"
                        f"{full_context}"
                    )
                    self.ai_panel.append_injected(tr("Mémoire"), tr("Archives des {} dernières sessions injectées.").format(len(recents)))
                    logger.info("[SESSION:RECALL] %d archives injectées suite au trigger naturel.", len(recents))

        self._pending_send_text = text
        # Recherche FAISS en amont : partitionne Bible memorisee / manuscrit
        bible_context = ""
        self._pending_manuscript_hits = []
        if not self._vector_index.is_empty():
            from core.query_cleaner import clean_query
            all_hits = self._vector_index.search(clean_query(text), k=8)
            # ── Filtre sourdine ────────────────────────────────────────────────
            muted = self._source_store.get_muted() if self._source_store else set()
            if muted:
                # Filtrer les chunks manuscrit des sources muées
                all_hits = [
                    h for h in all_hits
                    if h["source_id"] == "bible" or h["source_id"] not in muted
                ]
                # Filtrer les hits Bible issus des sources muées (via labels)
                chunk_mgr = self._archiviste._chunk_mgr if self._archiviste else None
                bible_db  = self._archiviste.bible_db if self._archiviste else None
                if chunk_mgr and bible_db:
                    excluded_labels: set[str] = set()
                    for sid in muted:
                        if self._source_store.is_bible_source(sid):
                            chunk_ids = chunk_mgr.get_chunk_ids_for_source(sid)
                            excluded_labels |= bible_db.get_labels_for_source_chunks(chunk_ids)
                    if excluded_labels:
                        all_hits = [
                            h for h in all_hits
                            if h["source_id"] != "bible"
                            or h.get("bible_label", "") not in excluded_labels
                        ]
                        logger.info(
                            "[MUTE] %d labels Bible exclus (%d sources en sourdine)",
                            len(excluded_labels), len(muted),
                        )
            # ── Partition Bible / manuscrit ────────────────────────────────────
            bible_hits = [h for h in all_hits if h["source_id"] == "bible"]
            self._pending_manuscript_hits = [
                h for h in all_hits if h["source_id"] != "bible"
            ]
            if bible_hits:
                lines = []
                for h in bible_hits:
                    lines.append(h["text_parent"])
                bible_context = "\n".join(lines)
                logger.info(
                    "[FAISS:BIBLE] %d entree(s) Bible pertinente(s) transmises au Reader",
                    len(bible_hits),
                )
            if self._pending_manuscript_hits:
                logger.info(
                    "[FAISS:MANUSCRIT] %d chunk(s) manuscrit pertinent(s)",
                    len(self._pending_manuscript_hits),
                )
        if self._conv_store.has_active_session:
            self._conv_store.append("user", text)
        if self._archiviste:
            self._archiviste.build_context_note(text, bible_context=bible_context)
        else:
            if self._engine:
                self._engine.send(text)

    def _on_mem_memorized(self, text: str, target: str, added: int) -> None:
        """Feedback visible dans le chat apres une commande /mem."""
        if target == "doublon":
            msg = tr("(deja en memoire : {})").format(text[:80])
        elif target == "travail":
            msg = tr("Memorise dans la memoire de travail : {}").format(text[:80])
        else:
            if added:
                msg = tr("Memorise (memoire relationnelle) : {}").format(text[:80])
            else:
                msg = tr("(deja en memoire relationnelle : {})").format(text[:80])
        self.ai_panel.append_injected(tr("Archiviste"), msg)

    def _on_context_note_ready(self, note: str):
        """
        Recoit la note de l'Archiviste.
        Injecte en system (si non vide) puis declenche l'envoi.
        Enrichit aussi avec les chunks FAISS les plus proches.
        """
        if not self._pending_send_text:
            return
        text = self._pending_send_text
        self._pending_send_text = ""

        if self._engine:
            if note:
                logger.info("[ARCHIVISTE:NOTE] note lecteur injectee (%d chars)", len(note))
                self._engine.inject_context_note(note)
            else:
                logger.debug("[ARCHIVISTE:NOTE] note lecteur vide, pas d'injection")
            # Injection de l'instruction ego (si definie)
            ego_block = self._ego_manager.get_injection_block()
            if ego_block:
                self._engine.inject_context_note(ego_block)
                logger.info("[EGO] bloc instruction injecte (%d chars)", len(ego_block))
            # Injection du cache cognitif courant (si non vide)
            cache_block = self._cognitive_cache.get_injection_block()
            if cache_block:
                self._engine.inject_context_note(cache_block)
                logger.info("[CACHE-COG] bloc cache injecté avant envoi (%d chars)", len(cache_block))
            # Mode edition : injecter instruction + contenu courant du document
            if self._current_edit_doc is not None:
                self._inject_edit_mode_context()
            # Injection des chunks manuscrit (pre-calcules avant le Reader)
            hits = getattr(self, "_pending_manuscript_hits", [])
            self._pending_manuscript_hits = []
            if hits:
                logger.info("[FAISS:SEARCH] %d chunk(s) manuscrit injectes", len(hits))
                excerpts = "\n---\n".join(h["text_parent"] for h in hits)
                self._engine.inject_context_note(
                    f"[EXTRAITS DU MANUSCRIT — passages pertinents pour cette question]\n"
                    f"Ces extraits proviennent du texte en cours de rédaction.\n\n"
                    f"{excerpts}"
                )
            # Activation bio : selecte les groupes pertinents puis declenche send
            if self._bio_activation is not None:
                logger.info("[BIO:ACTIVÉ] activation bio pour : %s", text[:60])
                self._bio_pending_text = text
                self._bio_activation.activate(text)
            else:
                logger.info("[ENVOI:IA] message envoye (sans bio, %d chars)", len(text))
                self._engine.send(text, optimized_history=self._build_optimized_history())

    def _build_optimized_history(self) -> list[dict] | None:
        """
        Construit l'historique compressé (résumés + messages récents) si le
        RollingSummarizer est disponible, sinon retourne None (historique complet).

        Les injections contextuelles éphémères de l'engine (doc, bible, bio…)
        sont préservées en les insérant avant les messages récents.
        """
        if self._rolling_summarizer is None or self._conv_store is None:
            logger.debug("[ROLLING] _build_optimized_history — summarizer absent, historique complet")
            return None
        try:
            all_msgs = self._conv_store.load_session(
                self._conv_store.current_path.stem
            )
        except Exception as exc:
            logger.error("[ROLLING] _build_optimized_history — échec load_session : %s", exc)
            return None
        try:
            base = self._rolling_summarizer.build_optimized_history(
                self._engine.system_prompt, all_msgs
            )
            # Récupérer les injections éphémères présentes dans l'engine
            # (messages system ajoutés après le message system initial)
            ephemeral_raw = [
                m for m in self._engine._history
                if m["role"] == "system" and m["content"] != self._engine.system_prompt
            ]
            # Dédupliquer par en-tête (première ligne) : ne garder que la plus récente
            # de chaque type. Cela évite que les anciennes injections doc/cache/bio
            # restent dans le contexte quand le contenu a changé (ex: changement de page).
            # On normalise les variantes d'en-tête doc pour éviter les doublons
            # entre ancienne et nouvelle formulation.
            _DOC_HEADERS = (
                "[DOCUMENT OUVERT DANS L'ÉDITEUR TIERS",  # préfixe commun aux deux variantes
            )
            def _normalize_header(h: str) -> str:
                for prefix in _DOC_HEADERS:
                    if h.startswith(prefix):
                        return prefix
                return h
            seen: dict[str, dict] = {}
            for m in ephemeral_raw:
                header = (m["content"].splitlines()[0] if m["content"] else "").strip()
                key = _normalize_header(header)
                seen[key] = m  # écrase les anciennes, garde la dernière
            ephemeral = list(seen.values())
            if ephemeral:
                logger.info(
                    "[ROLLING] %d injection(s) éphémère(s) préservée(s) dans l'historique optimisé",
                    len(ephemeral),
                )
                for i, e in enumerate(ephemeral):
                    first = e["content"].splitlines()[0] if e["content"] else ""
                    logger.debug("[ROLLING]   éphémère[%d] : %s", i, first[:80])
                # Insérer avant les messages récents (après le bloc résumés)
                last_sys = next(
                    (i for i in range(len(base) - 1, -1, -1)
                     if base[i]["role"] == "system"), 0
                )
                return base[:last_sys + 1] + ephemeral + base[last_sys + 1:]
            return base
        except Exception as exc:
            logger.error("[ROLLING] _build_optimized_history — erreur : %s", exc, exc_info=True)
            return None

    def _on_bio_injection_ready(self, injection: str) -> None:
        """Recoit l'injection bio, l'injecte si non vide, puis envoie le message."""
        text = self._bio_pending_text
        self._bio_pending_text = ""
        if not text or not self._engine:
            logger.debug("[BIO:ACTIVÉ] injection_ready recue mais texte vide ou engine absent")
            return
        if injection:
            logger.info("[BIO:INJECT] bio injectee (%d chars) avant envoi", len(injection))
            self._engine.inject_context_note(injection)
        else:
            logger.debug("[BIO:INJECT] bio vide (0 groupe pertinent)")

        logger.info("[ENVOI:IA] message envoye (%d chars)", len(text))
        self._engine.send(text, optimized_history=self._build_optimized_history())

    def _on_live_memorize(self, content: str) -> None:
        """
        Recu depuis BioActivation quand le modele detecte une info auteur a memoriser.
        Appelle memorize_direct (routage automatique relational/work).
        """
        if not content or not self._relational_scanner:
            return
        archiviste = self._relational_scanner._archiviste
        logger.info("[MEM:LIVE] memorisation automatique declenchee : %s", content[:80])

        def _on_added(n):
            logger.info("[MEM:LIVE] %d entree(s) ajoutee(s) en memoire relationnelle", n)
            self._recompile_bio()
            archiviste.entries_added.disconnect(_on_added)
            archiviste.nothing_found.disconnect(_on_nothing)
            archiviste.mem_routed_to_work.disconnect(_on_work)

        def _on_nothing():
            logger.debug("[MEM:LIVE] info deja en memoire (doublon ignore)")
            archiviste.entries_added.disconnect(_on_added)
            archiviste.nothing_found.disconnect(_on_nothing)
            archiviste.mem_routed_to_work.disconnect(_on_work)

        def _on_work(work_content):
            logger.info("[MEM:LIVE] route vers Bible : %s", work_content[:60])
            if self._archiviste:
                self._archiviste.ingest_text(work_content, source_id="mem_direct")
            archiviste.entries_added.disconnect(_on_added)
            archiviste.nothing_found.disconnect(_on_nothing)
            archiviste.mem_routed_to_work.disconnect(_on_work)

        archiviste.entries_added.connect(_on_added)
        archiviste.nothing_found.connect(_on_nothing)
        archiviste.mem_routed_to_work.connect(_on_work)
        archiviste.memorize_direct(content)

    def _record_ai_response(self, text: str):
        """Enregistre la reponse IA dans le store et rafraichit l'historique."""
        if self._conv_store.has_active_session:
            self._conv_store.append("assistant", text)
        self.context_panel.history_panel.refresh()

    def _on_ai_response(self, text: str):
        """Recu de l'AIEngine : affiche dans le panneau et enregistre."""
        if self._current_edit_doc is not None:
            self._route_edit_response(text)
            return
        if self._pending_stat_mode:
            self._pending_stat_mode = False
            self._route_stat_response(text)
            return
        self.ai_panel.on_ai_response(text)
        self._record_ai_response(text)
        # Chaque reponse IA = activite : relancer le heartbeat ego
        self._reset_ego_heartbeat()
        self._run_ego_selector()
        # L'insertion en Mode doc n'est déclenchée QUE par le bouton
        # "Insérer dans l'éditeur" — pas automatiquement après chaque réponse.

        # Déclencher éventuellement un résumé glissant
        if self._rolling_summarizer is not None and self._conv_store is not None:
            try:
                all_msgs = self._conv_store.load_session(
                    self._conv_store.current_path.stem
                )
                self._rolling_summarizer.maybe_summarize(all_msgs)
            except Exception as exc:
                logger.debug("[ROLLING] maybe_summarize ignoré : %s", exc)

    def _on_web_search_ready(self, block: str, query: str) -> None:
        """Resultats web recus : injecter puis envoyer la question a l'IA."""
        if self._engine is None:
            return
        if block:
            self._engine.inject_context_note(block)
            logger.info("[WEB] bloc resultat injecte (%d chars)", len(block))
        else:
            self.ai_panel.append_injected(tr("EUGENIA"), tr("(Aucun resultat web trouve.)"))
        self._engine.send(query, optimized_history=self._build_optimized_history())

    def _on_web_search_error(self, err: str, query: str) -> None:
        """Erreur de recherche web : avertir l'utilisateur et envoyer quand meme."""
        logger.error("[WEB] erreur recherche : %s", err)
        self.ai_panel.append_injected(
            tr("EUGENIA"), tr("(Recherche web echouee : {})").format(err)
        )
        if self._engine is not None:
            self._engine.send(query, optimized_history=self._build_optimized_history())

    # ── Mode Edition ──────────────────────────────────────────────────────────

    def _enter_edit_mode(
        self,
        title: str = "Sans titre",
        doc: "EditDocument | None" = None,
    ) -> None:
        """Ouvre le mode edition (substitue EditPanel a l'EditorZone)."""
        if doc is None:
            doc = self._edit_store.create_doc(title)
        self._current_edit_doc = doc
        self._edit_panel.load_document(doc)
        self._center_stack.setCurrentIndex(1)
        self.ai_panel.append_injected(
            tr("Edition"),
            tr("Mode edition ouvert — {}. Ecrivez vos instructions dans le chat.").format(doc.title),
        )
        logger.info("[EDIT] mode edition ouvert — id=%s titre=%s", doc.doc_id, doc.title)

    def _exit_edit_mode(self) -> None:
        """Ferme le mode edition et revient a l'EditorZone."""
        if self._current_edit_doc is not None:
            self._edit_store.save_doc(self._current_edit_doc)
            logger.info("[EDIT] mode edition ferme — id=%s", self._current_edit_doc.doc_id)
        self._current_edit_doc = None
        self._center_stack.setCurrentIndex(0)
        # Mettre a jour la liste dans SourcesPanel
        self.context_panel.sources_panel.refresh_edit_docs(
            self._edit_store.list_docs()
        )
        self.ai_panel.append_injected(tr("Edition"), tr("Mode edition ferme."))

    def _inject_edit_mode_context(self) -> None:
        """Injecte l'instruction mode edition + contenu courant avant engine.send()."""
        if self._engine is None or self._current_edit_doc is None:
            return
        instruction = _EDIT_MODE_INSTRUCTION.format(
            title   = self._current_edit_doc.title,
            content = self._current_edit_doc.content or "(document vide — commence a ecrire)",
        )
        self._engine.inject_context_note(instruction)

    def _route_edit_response(self, text: str) -> None:
        """
        Parseur de balises XML mode edition.
        L'IA repond : <edit>...</edit> <comment>...</comment>
          edit    -> met a jour EditPanel (avec backup prealable)
          comment -> envoye dans le chat
        En cas d'echec de parsing, envoie la reponse brute au chat.
        """
        import re
        edit_content = None
        comment = None
        
        edit_match = re.search(r"<edit>(.*?)</edit>", text, re.DOTALL | re.IGNORECASE)
        if edit_match:
            edit_content = edit_match.group(1).strip()
            
        comment_match = re.search(r"<comment>(.*?)</comment>", text, re.DOTALL | re.IGNORECASE)
        if comment_match:
            comment = comment_match.group(1).strip()
            
        # Si on ne trouve pas de balises bien formees, on cherche des balises ouvertes non fermees (reponse tronquee)
        if not edit_content and not comment:
            edit_open_match = re.search(r"<edit>(.*)", text, re.DOTALL | re.IGNORECASE)
            if edit_open_match:
                edit_content = edit_open_match.group(1).strip()
                logger.warning("[EDIT] reponse tronquee (sans </edit>) — extraction de force")
            else:
                comment_open_match = re.search(r"<comment>(.*)", text, re.DOTALL | re.IGNORECASE)
                if comment_open_match:
                    comment = comment_open_match.group(1).strip()
                    logger.warning("[EDIT] reponse tronquee (sans </comment>) — extraction de force")
            
        if not edit_match and not comment_match:
            # Fallback : le modele a-t-il ignore la consigne et repondu en JSON a cause de son historique ?
            clean = text.strip()
            start_idx = clean.find('{')
            end_idx = clean.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                try:
                    data = _json.loads(clean[start_idx:end_idx+1])
                    edit_content = data.get("edit")
                    comment = data.get("comment") or ""
                except Exception:
                    pass
                    
            # Si toujours rien (ni XML ni JSON valide)
            if not edit_content and not comment:
                logger.warning("[EDIT] reponse sans balises en mode edition — renvoi au chat")
                self.ai_panel.on_ai_response(text)
                self._record_ai_response(text)
                self._reset_ego_heartbeat()
                self._run_ego_selector()
                return

        if edit_content:
            self._edit_store.push_backup(self._current_edit_doc)
            self._current_edit_doc.content = edit_content
            self._edit_store.save_doc(self._current_edit_doc)
            self._edit_panel.set_content(edit_content)
            logger.info("[EDIT] document mis a jour (%d chars)", len(edit_content))

        if comment:
            self.ai_panel.on_ai_response(comment)
            self._record_ai_response(comment)
        elif edit_content:
            self.ai_panel.append_injected(tr("Edition"), tr("(Document mis a jour)"))
            self.ai_panel.set_busy(False)

        self._reset_ego_heartbeat()
        self._run_ego_selector()

    def _on_edit_save(self, path: str) -> None:
        """Export du document vers un fichier disque (demande depuis EditPanel)."""
        if self._current_edit_doc is None:
            return
        from pathlib import Path as _Path
        self._edit_store.export_to_file(self._current_edit_doc, _Path(path))
        self.ai_panel.append_injected(tr("Edition"), tr("Document exporte : {}").format(path))
        logger.info("[EDIT] export -> %s", path)

    def _on_edit_ai_command(self, cmd: str, selection: str) -> None:
        """Micro-commande IA depuis EditPanel : injecte le contexte et envoie."""
        if self._engine is None or self._current_edit_doc is None:
            return
        prompt = (
            f"{cmd}\n\n"
            f"Passage cible :\n---\n{selection}\n---"
        )
        self.ai_panel.append_injected(tr("Edition"), tr("Commande rapide : {}").format(cmd))
        self._inject_edit_mode_context()
        self._engine.send(prompt, optimized_history=self._build_optimized_history())

    def _on_edit_doc_open(self, doc_id: str) -> None:
        """Ouvre un document edite existant depuis le SourcesPanel."""
        doc = self._edit_store.get_doc(doc_id)
        if doc is None:
            self.ai_panel.append_injected(tr("Edition"), tr("Document introuvable (id={})").format(doc_id))
            return
        self._enter_edit_mode(doc=doc)

    def _on_edit_doc_delete(self, doc_id: str) -> None:
        """Supprime un document edite (demande depuis SourcesPanel)."""
        # Si le doc est actuellement ouvert en edition, fermer d'abord
        if self._current_edit_doc is not None and self._current_edit_doc.doc_id == doc_id:
            self._current_edit_doc = None
            self._center_stack.setCurrentIndex(0)
        self._edit_store.delete_doc(doc_id)
        self.context_panel.sources_panel.refresh_edit_docs(self._edit_store.list_docs())
        logger.info("[EDIT] document supprime — id=%s", doc_id)

    # ------------------------------------------------------------------ #
    # Stats                                                                #
    # ------------------------------------------------------------------ #

    def _on_stat_doc_dropped(self, path: str) -> None:
        """Fichier .docx déposé dans le StatsPanel — comptage + persistance."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QSpinBox, QDialogButtonBox
        try:
            wc = count_words_docx(path)
        except Exception as exc:
            logger.error("[STATS] erreur comptage mots '%s' : %s", path, exc)
            self.ai_panel.append_injected(tr("EUGENIA"), tr("Impossible de lire ce fichier : {}").format(exc))
            return

        existing = self._stats_store.get_doc_stat_by_path(path)
        baseline_wpd: int | None = None

        if existing is None:
            # Première injection : proposer une baseline
            dlg = QDialog(self)
            dlg.setWindowTitle(tr("Première analyse"))
            dlg.setModal(True)
            dlg.setFixedWidth(380)
            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(20, 16, 20, 12)
            layout.setSpacing(10)
            layout.addWidget(QLabel(
                f"<b>{path.split('/')[-1].split(chr(92))[-1]}</b><br>"
                f"<span style='color:#888'>{wc:,} mots détectés.</span>"
            ))
            layout.addWidget(QLabel(
                tr("Connaissez-vous votre objectif de mots par jour ?\n"
                "(Laissez 0 si inconnu — vous pourrez le définir plus tard.)")
            ))
            spin = QSpinBox()
            spin.setRange(0, 50000)
            spin.setSingleStep(100)
            spin.setValue(0)
            spin.setSuffix(tr(" mots/jour"))
            layout.addWidget(spin)
            btns = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            layout.addWidget(btns)
            if dlg.exec() == QDialog.DialogCode.Rejected:
                return
            val = spin.value()
            baseline_wpd = val if val > 0 else None

        entry = self._stats_store.add_doc_injection(path, wc, baseline_wpd=baseline_wpd)
        self.context_panel.stats_panel.refresh_display(
            self._stats_store.list_doc_stats(),
            self._stats_store.list_custom_stats(),
        )
        logger.info("[STATS] injection doc '%s' — %d mots", path, wc)

        # Feedback dans le chat
        title = entry.title
        delta = entry.word_count_delta
        if delta is not None:
            sign = "+" if delta >= 0 else ""
            msg = tr("Statistiques mises à jour pour « {} » : {} mots ({}{} depuis la dernière session).").format(title, wc, sign, delta)
        else:
            msg = tr("Statistiques initialisées pour « {} » : {} mots.").format(title, wc)
        self.ai_panel.append_injected(tr("Archiviste"), msg)

    def _on_stat_refresh(self) -> None:
        """Rafraîchit l'affichage du StatsPanel depuis le store."""
        self.context_panel.stats_panel.refresh_display(
            self._stats_store.list_doc_stats(),
            self._stats_store.list_custom_stats(),
        )

    def _on_stat_chart_requested(self, kind: str, item_id: str) -> None:
        """Ouvre le StatsChartOverlay pour un item donné."""
        from ui.stats_chart_overlay import StatsChartOverlay
        overlay = StatsChartOverlay(parent=self)
        if kind == "doc":
            entry = self._stats_store.get_doc_stat(item_id)
            if entry is None:
                logger.warning("[STATS] doc_id inconnu pour chart : %s", item_id)
                return
            overlay.show_doc_evolution(entry)
        elif kind == "custom":
            entries = {e.stat_id: e for e in self._stats_store.list_custom_stats()}
            if item_id not in entries:
                logger.warning("[STATS] stat_id inconnu pour chart : %s", item_id)
                return
            overlay.show_custom_stat(entries[item_id])
        overlay.exec()

    def _on_stat_delete(self, kind: str, item_id: str) -> None:
        """Supprime un doc stat ou une stat custom."""
        from PyQt6.QtWidgets import QMessageBox
        if kind == "doc":
            entry = self._stats_store.get_doc_stat(item_id)
            name = entry.title if entry else item_id
        else:
            entries = {e.stat_id: e for e in self._stats_store.list_custom_stats()}
            entry = entries.get(item_id)
            name = entry.name if entry else item_id

        reply = QMessageBox.question(
            self, tr("Supprimer"),
            tr("Supprimer « {} » et toutes ses statistiques ?").format(name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if kind == "doc":
            self._stats_store.delete_doc_stat(item_id)
            logger.info("[STATS] doc stat supprime — id=%s", item_id)
        else:
            self._stats_store.delete_custom_stat(item_id)
            logger.info("[STATS] custom stat supprimee — id=%s", item_id)

        self.context_panel.stats_panel.refresh_display(
            self._stats_store.list_doc_stats(),
            self._stats_store.list_custom_stats(),
        )

    def _route_stat_response(self, text: str) -> None:
        """Parse la réponse JSON de l'IA pour une commande /stat."""
        import json as _json_stat
        raw = text.strip()
        # Tenter d'extraire le JSON si l'IA a ajouté du texte autour
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            raw_json = raw[start:end]
            data = _json_stat.loads(raw_json)
        except (ValueError, _json_stat.JSONDecodeError) as exc:
            logger.warning("[STATS] reponse non-JSON de l'IA : %s — affichage normal", exc)
            self.ai_panel.on_ai_response(text)
            self._record_ai_response(text)
            return

        # Cas : l'IA a besoin de données supplémentaires
        if data.get("needs_data"):
            questions = data.get("questions", [])
            msg = "Pour générer cette statistique, j'ai besoin de quelques informations :\n"
            msg += "\n".join(f"• {q}" for q in questions)
            self.ai_panel.on_ai_response(msg)
            # Relancer en mode stat pour la prochaine réponse
            self._pending_stat_mode = True
            return

        # Cas : stat complète
        stat_name = data.get("stat_name", "Stat personnalisée")
        chart_type = data.get("chart_type", "bar")
        stat_data = data.get("data", {})
        description = data.get("description", "")

        if not stat_data.get("labels") or not stat_data.get("values"):
            logger.warning("[STATS] JSON stat incomplet : %s", data)
            self.ai_panel.on_ai_response(text)
            self._record_ai_response(text)
            return

        entry = self._stats_store.add_custom_stat(stat_name, chart_type, stat_data, description)
        self.context_panel.stats_panel.refresh_display(
            self._stats_store.list_doc_stats(),
            self._stats_store.list_custom_stats(),
        )
        self.ai_panel.on_ai_response(
            f"Statistique « {stat_name} » créée et ajoutée au panneau Statistiques.\n"
            f"{description}"
        )
        self._record_ai_response(text)
        logger.info("[STATS] stat custom creee — name=%s chart=%s", stat_name, chart_type)

    def _on_new_session(self) -> None:
        """
        Démarre une nouvelle conversation :
        - La session courante est conservée dans le store (déjà persistée)
        - On démarre une nouvelle session vide
        - L'historique de l'engine est réinitialisé
        - Le chat est vidé, le cache cognitif est réinitialisé
        """
        if self._engine is None or self._conv_store is None:
            return

        # Démarrer la nouvelle session dans le store
        self._conv_store.start_session()
        logger.info("[NEW-SESSION] nouvelle session démarrée : %s", self._conv_store.current_path)

        # Réinitialiser l'engine (repart du system prompt uniquement)
        self._engine.reset_history()

        # Réinitialiser et charger le cache cognitif pour la nouvelle session
        self._cognitive_cache.reset()
        if self._conv_store.current_path:
            self._cognitive_cache.load(self._conv_store.current_path)

        # Réinitialiser le RollingSummarizer
        if self._rolling_summarizer is not None and self._conv_store.current_path:
            from core.rolling_summarizer import RollingSummarizer
            meta = RollingSummarizer.meta_path_for(self._conv_store.current_path)
            self._rolling_summarizer.load_for_session(meta)

        # Vider le panneau de chat
        self.ai_panel.clear_chat()

        # Rafraîchir l'historique (la session précédente apparaît maintenant)
        self.context_panel.history_panel.refresh()

        logger.info("[NEW-SESSION] conversation réinitialisée")


    def _on_session_deleted(self, sid: str) -> None:
        """Nettoie le résumé Markdown et l'index FAISS lors de la suppression d'une session."""
        try:
            if self._summarizer:
                sum_path = self._summarizer._dir / f"{sid}.md"
                if sum_path.exists():
                    sum_path.unlink()
            if self._vector_index:
                self._vector_index.remove_source(f"session_summary_{sid}")
            logger.info("MainWindow — suppression FAISS/Résumé pour session %s", sid)
        except Exception as e:
            logger.error("MainWindow — erreur lors du nettoyage de la session %s : %s", sid, e)

    def _on_scan_history_requested(self):
        """Parcourt tous les fichiers .md des sessions passées et les indexe dans FAISS."""
        if not self._vector_index or not self._summarizer:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, tr("Erreur"), tr("FAISS ou Summarizer non initialisé."))
            return

        sum_dir = self._summarizer._dir
        if not sum_dir.exists():
            return
            
        try:
            from core.chunk_manager import ChunkResult
            import hashlib
            indexed = 0
            for sum_file in sum_dir.glob("*.md"):
                session_id = sum_file.stem
                with open(sum_file, "r", encoding="utf-8") as f:
                    content = f.read()
                cr = ChunkResult(
                    chunk_index=0,
                    text_small=content[:800],
                    text_parent=content,
                    hash=hashlib.sha256(content.encode()).hexdigest(),
                    text_index=""
                )
                self._vector_index.add_chunks(f"session_summary_{session_id}", [cr])
                indexed += 1
            
            logger.info("MainWindow — scan manuel des historiques terminé : %d sessions indexées", indexed)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, 
                tr("Scan Terminé"), 
                tr("{} session(s) passée(s) ajoutée(s) à la mémoire de recherche.").format(indexed)
            )
        except Exception as e:
            logger.error("MainWindow — erreur lors du scan de l'historique : %s", e)

    def _on_resume_session(self, session_id: str) -> None:
        """
        Reprend une conversation passée :
        1. Bascule le ConversationStore sur la session existante
        2. Recharge l'historique dans le moteur IA (contexte)
        3. Affiche les messages dans l'AIPanel
        """
        if self._engine is None or self._conv_store is None:
            return
        try:
            messages = self._conv_store.resume_session(session_id)
        except FileNotFoundError as exc:
            logger.error("MainWindow._on_resume_session — %s", exc)
            return

        # Reconstruire l'historique dans l'engine (sans le message system initial)
        # On repart du system prompt existant et on réinjecte les échanges
        self._engine.reset_history()
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant"):
                self._engine.push_history(role, content)

        # Charger les résumés glissants de la session reprise
        if self._rolling_summarizer is not None and self._conv_store.current_path:
            from core.rolling_summarizer import RollingSummarizer
            meta = RollingSummarizer.meta_path_for(self._conv_store.current_path)
            self._rolling_summarizer.load_for_session(meta)
            logger.info("[ROLLING] résumés chargés pour session reprise : %s", meta)

        # Charger le cache cognitif de la session reprise
        if self._conv_store.current_path:
            self._cognitive_cache.load(self._conv_store.current_path)
            logger.info(
                "[CACHE-COG] cache cognitif repris pour session '%s'",
                session_id,
            )

        # Afficher les messages dans l'AIPanel
        self.ai_panel.load_history(messages)

        # Rafraîchir la liste (la session sélectionnée est maintenant active)
        self.context_panel.history_panel.refresh()

        logger.info(
            "MainWindow._on_resume_session — session %s reprise (%d messages)",
            session_id, len(messages),
        )

    def _on_contradiction(self, description: str):
        """L'Archiviste a détecté une contradiction dans le texte injecté."""
        self.ai_panel.append_injected(
            tr("⚠ Contradiction détectée par l'Archiviste"),
            description,
        )

    def _on_archiviste_error(self, msg: str):
        """Erreur non fatale de l'Archiviste."""
        logger.error("Archiviste — %s", msg)

    # ------------------------------------------------------------------ #
    # Rechargement après sauvegarde des paramètres                        #
    # ------------------------------------------------------------------ #

    def _on_doc_mode_changed(self, enabled: bool) -> None:
        """Active ou désactive le mode document."""
        self._doc_mode = enabled
        logger.info("[DOC:MODE] mode document %s", "activé" if enabled else "désactivé")
        if enabled and self._doc_ctrl.is_connected():
            self.ai_panel.append_injected(
                tr("EUGENIA"),
                tr("Mode document activé. Je lirai le contenu de l'éditeur à chaque "
                "message et proposerai automatiquement d'y insérer mes réponses."),
            )

    def _on_config_saved(self, _config: dict):
        """
        Appelé par SettingsPanel après une sauvegarde.
        Réinitialise le moteur IA et l'Archiviste avec la nouvelle config.
        """
        logger.info("MainWindow — config sauvegardée, rechargement des moteurs")

        # Re-persister badge_x_offset : le panel settings ne l'inclut pas dans son dict
        self._persist_badge_x_offset()

        # Recharger ThemeConfig avec les nouvelles surcharges couleur puis réappliquer
        from ui.theme_config import ThemeConfig
        ThemeConfig.instance().load(_config.get("color_overrides", {"dark": {}, "light": {}}))
        if hasattr(self, '_ghost_overlay'):
            self._apply_badge_colors()

        # Propager les paramètres mémoire vers VectorIndex
        mem_cfg = _config.get("memory", {})
        if self._vector_index is not None:
            self._vector_index.set_dedup_config(
                enabled=mem_cfg.get("faiss_dedup_enabled", True),
                threshold=mem_cfg.get("faiss_dedup_threshold", 0.93),
            )
            self._vector_index.set_embed_config(
                resolve_engine_config(_config.get("ia_embed", {}))
            )

        # Fermer proprement l'Archiviste existant
        if self._archiviste:
            self._archiviste.close()
            self._archiviste = None

        # Déconnecter le signal d'envoi (il sera reconnecté dans _init_ai_engine)
        try:
            self.ai_panel.send_requested.disconnect(self._on_ai_send_requested)
        except RuntimeError:
            pass  # Pas connecté

        self._init_ai_engine()
        self._init_archiviste()

    def _open_ingest_dialog(self, prefill_path: str = "") -> None:
        """Ouvre le dialog d'import de document .docx."""
        if self._archiviste is None:
            logger.warning("IngestDialog — Archiviste non configuré")
        chunk_mgr = self._archiviste._chunk_mgr if self._archiviste else None
        if chunk_mgr is None:
            from core.chunk_manager import ChunkManager
            project_dir = PROJECTS_DIR / self._session["project"]["slug"]
            chunk_mgr = ChunkManager(project_dir)
        self._ingesting = True  # bloque le debounce Bible pendant l'ingest
        dlg = IngestDialog(chunk_mgr, self._archiviste, parent=self,
                           prefill_path=prefill_path)
        dlg.ingest_done.connect(lambda sid, n: self._on_ingest_done_with_meta(sid, n, dlg))
        dlg.exec()

    def _on_ingest_done_with_meta(self, source_id: str, nb_entities: int,
                                   dlg: "IngestDialog") -> None:
        self._last_ingest_meta = dlg.meta
        # Indexer les chunks dans FAISS (async-like : pas bloquant pour l'UI)
        if dlg.meta and hasattr(dlg, '_all_chunks') and dlg._all_chunks:
            try:
                self._vector_index.add_chunks(source_id, dlg._all_chunks)
                logger.info("MainWindow — FAISS mis a jour pour '%s'", source_id)
            except Exception as exc:
                logger.error("MainWindow — FAISS add_chunks echec : %s", exc)
        # Fin d'ingest : lever le blocage puis vectoriser la Bible une seule fois
        self._ingesting = False
        self._bible_sync_timer.stop()
        self._on_memorize_bible_requested()
        self._on_ingest_done(source_id, nb_entities)

    def _on_ingest_done(self, source_id: str, nb_entities: int) -> None:
        logger.info("MainWindow — ingest terminé : %s (%d entité(s))",
                    source_id, nb_entities)
        # Rafraichir la Bible UI si elle est ouverte
        if hasattr(self._bible_panel, "refresh"):
            self._bible_panel.refresh()
        # Mettre a jour le SourceStore avec les metadonnees du document
        dlg_data = getattr(self, "_last_ingest_meta", None)
        if dlg_data:
            self._source_store.upsert(
                source_id=source_id,
                filename=dlg_data["filename"],
                path=dlg_data["path"],
                nb_chunks=dlg_data["nb_chunks"],
                bible_source=dlg_data.get("bible_source", True),
            )
            self.context_panel.sources_panel.refresh()
            self._last_ingest_meta = None

    # ------------------------------------------------------------------ #
    # Gestion du panneau contextuel (collapse / expand)                   #
    # ------------------------------------------------------------------ #

    def _on_reingest_requested(self, source_id: str, path: str) -> None:
        """Relance l'ingest sur un fichier deja connu."""
        if self._archiviste is None:
            logger.warning("_on_reingest_requested — Archiviste non configure")
            return
        self._open_ingest_dialog(prefill_path=path)

    def _on_mute_requested(self, source_id: str) -> None:
        """Bascule l'etat sourdine d'une source et rafraichit le panneau."""
        if self._source_store is None:
            return
        try:
            is_now_muted = self._source_store.toggle_mute(source_id)
        except KeyError as exc:
            logger.error("_on_mute_requested — %s", exc)
            return
        state = "mis en sourdine" if is_now_muted else "reactivé"
        logger.info("[MUTE] '%s' %s", source_id, state)
        self.context_panel.sources_panel.refresh()

    def _on_remove_requested(self, source_id: str, remove_memory: bool) -> None:
        """Supprime ou orphanise un document source."""
        if remove_memory:
            try:
                self._source_store.remove(source_id)
            except KeyError as exc:
                logger.error("_on_remove_requested — source_store.remove: %s", exc)
                return
            self._vector_index.remove_source(source_id)
            # Suppression cascade : entrees Bible issues de ce document
            chunk_mgr = self._archiviste._chunk_mgr if self._archiviste else None
            if chunk_mgr is not None:
                chunk_ids = chunk_mgr.get_chunk_ids_for_source(source_id)
                if chunk_ids:
                    nb_deleted = self._archiviste.bible_db.delete_by_source_chunks(chunk_ids)
                    logger.info(
                        "_on_remove_requested — '%s' : %d entree(s) Bible supprimees",
                        source_id, nb_deleted,
                    )
                chunk_mgr.clear_source(source_id)
            # Re-memorisation automatique si la Bible etait vectorisee
            if self._vector_index.is_configured():
                all_entries = self._archiviste.bible_db.get_all_tables()
                self._vector_index.add_bible_entries(all_entries)
                logger.info(
                    "_on_remove_requested — Bible re-memorisee apres suppression '%s'",
                    source_id,
                )
            logger.info(
                "_on_remove_requested — '%s' : librairie + FAISS + Bible supprimes",
                source_id,
            )
        else:
            try:
                self._source_store.mark_orphan(source_id)
            except KeyError as exc:
                logger.error("_on_remove_requested — source_store.mark_orphan: %s", exc)
                return
            logger.info(
                "_on_remove_requested — '%s' : orphelin (memoire FAISS conservee)",
                source_id,
            )
        self.context_panel.sources_panel.refresh()
        if hasattr(self._bible_panel, "refresh"):
            self._bible_panel.refresh()

    def _on_memorize_bible_requested(self) -> None:
        """Vectorise toutes les entrees de la Bible dans FAISS.

        Declenche automatiquement :
          - 3 s apres le dernier bible_updated (ingest async, /mem_bible, clipboard...)
          - immediatement apres toute modification manuelle via BiblePanel (add/edit/delete)
        """
        if not self._vector_index.is_configured():
            logger.warning(
                "_on_memorize_bible_requested — ia_embed non configure, memorisation impossible"
            )
            return
        if self._archiviste is None:
            logger.warning("_on_memorize_bible_requested — Archiviste absent")
            return
        all_entries = self._archiviste.bible_db.get_all_tables()
        self._vector_index.add_bible_entries(all_entries)
        logger.info(
            "_on_memorize_bible_requested — %d entrees Bible vectorisees",
            len(all_entries),
        )

    def _on_doc_mode_changed(self, enabled: bool) -> None:
        """Active ou désactive le mode document."""
        self._doc_mode = enabled
        logger.info("[DOC:MODE] mode document %s", "activé" if enabled else "désactivé")
        if enabled and self._doc_ctrl.is_connected():
            self.ai_panel.append_injected(
                tr("EUGENIA"),
                tr("Mode document activé. Je lirai le contenu de l'éditeur à chaque message "
                "et proposerai automatiquement d'y insérer mes réponses."),
            )

    def _on_insert_in_editor(self, text: str) -> None:
        """
        Bouton 'Insérer dans l'éditeur' du panneau IA.
        Passe par l'ApprovalGate selon le mode de la session.
        """
        if not self._doc_ctrl.is_connected():
            self.ai_panel.append_injected(
                tr("EUGENIA"),
                tr("Aucun éditeur attaché. Utilisez [ attacher éditeur ] en bas du panneau."),
            )
            return
        original = self._doc_ctrl.read_selection()
        action = "replace" if original.strip() else "insert"
        self._approval_gate.request(
            proposed=text,
            original=original,
            action=action,
            on_accept=lambda final: self._doc_ctrl.replace_selection(final)
                if action == "replace"
                else self._doc_ctrl.insert_at_cursor(final),
            parent_widget=self,
        )

    def _on_splitter_moved(self, pos: int, index: int):
        """Sauvegarde l'etat splitter a chaque deplacement manuel.
        Ignore les mouvements programmes (repli AI ou repli ctx)."""
        if not self._ai_collapsed and not self._ctx_collapsed:
            s = QSettings("EUGENIA", "Layout")
            s.setValue("splitter/state", self.splitter.saveState())

    def _on_ai_panel_toggle(self):
        """Replie ou deplie le panneau IA (clic sur le titre EUGENIA)."""
        sizes = self.splitter.sizes()  # [col2, col3, col4]
        _COLLAPSED_W = 24

        if not self._ai_collapsed:
            self._ai_saved_width = sizes[2] if sizes[2] > 80 else DEFAULT_COL4
            # setFixedWidth(24) d'abord : le splitter voit min=max=24 et obeit
            self.ai_panel.set_collapsed(True)
            self.splitter.setSizes([sizes[0], sizes[1] + sizes[2] - _COLLAPSED_W, _COLLAPSED_W])
            self._ai_collapsed = True
        else:
            # Lever la contrainte fixe d'abord, puis restaurer
            self.ai_panel.set_collapsed(False)
            restore = self._ai_saved_width
            total = sizes[1] + sizes[2]
            self.splitter.setSizes([sizes[0], total - restore, restore])
            self._ai_collapsed = False

    def _on_icon_clicked(self, icon_id: str, active: bool):
        """
        Réaction au clic sur une icône :
        - active=True  → afficher le panneau contextuel avec le bon contenu
        - active=False → fermer le panneau (lui donner une largeur de 0)
        """
        sizes = self.splitter.sizes()  # [col2, col3, col4]

        if active:
            if icon_id == "sources":
                self.context_panel.set_content(icon_id)
                if sizes[0] == 0:
                    gain = self._ctx_saved_width
                    self._ctx_collapsed = False
                    self.splitter.setSizes([gain, sizes[1] - gain, sizes[2]])
                return
            self.context_panel.set_content(icon_id)
            if sizes[0] == 0:
                gain = self._ctx_saved_width
                self._ctx_collapsed = False
                self.splitter.setSizes([gain, sizes[1] - gain, sizes[2]])
        else:
            if sizes[0] > 0:
                self._ctx_saved_width = sizes[0]
                self._ctx_collapsed = True
                self.splitter.setSizes([0, sizes[1] + sizes[0], sizes[2]])

    # ------------------------------------------------------------------ #
    # Fermeture                                                            #
    # ------------------------------------------------------------------ #

    def closeEvent(self, event):
        """
        Fermeture en deux passes :

        Passe 1 (event.ignore) : bloque Qt, détache l'éditeur, sauvegarde
          le layout, puis lance les workers asynchrones (résumé de session
          + scan mémoire relationnelle).  Quand les deux sont terminés,
          _shutdown_done() est appelé.

        Passe 2 (_closing=True) : les workers sont finis, on ferme vraiment.
        """
        if getattr(self, "_closing", False):
            # Passe 2 — fermeture réelle
            self._relational_db.close()
            super().closeEvent(event)
            return

        # Passe 1 — bloquer Qt le temps que les workers terminent
        event.ignore()

        # Détacher l'éditeur embarqué en priorité (évite fenêtre orpheline)
        if self.editor_zone._embedded_hwnd is not None:
            self.editor_zone.detach_editor()
        self._save_layout()

        # Overlay "Fermeture en cours…"
        self._show_shutdown_overlay()

        self._shutdown_pending  = 0   # compteur de workers en attente
        self._shutdown_summary_done   = False
        self._shutdown_relational_done = False

        # ── Résumé de session ──────────────────────────────────────────
        needs_summary = (
            self._summarizer is not None
            and self._conv_store.has_active_session
        )
        if needs_summary:
            session_id = self._conv_store._current_path.stem
            try:
                messages = self._conv_store.load_session(session_id)
            except Exception:
                messages = []
            if messages:
                self._shutdown_pending += 1
                logger.info("MainWindow.closeEvent — résumation session %s", session_id)
                def _on_summary_done(sid: str, text: str):
                    try:
                        from core.chunk_manager import ChunkResult
                        import hashlib
                        cr = ChunkResult(
                            chunk_index=0,
                            text_small=text[:800],
                            text_parent=text,
                            hash=hashlib.sha256(text.encode()).hexdigest(),
                            text_index=""
                        )
                        self._vector_index.add_chunks(f"session_summary_{sid}", [cr])
                    except Exception as e:
                        logger.error("MainWindow — erreur FAISS session summary: %s", e)
                    self._on_shutdown_worker_done("summary")

                self._summarizer.summarize(
                    session_id=session_id,
                    messages=messages,
                    on_done=_on_summary_done,
                    on_error=lambda *_: self._on_shutdown_worker_done("summary"),
                )
            else:
                needs_summary = False

        # ── Scan mémoire relationnelle ─────────────────────────────────
        needs_scan = self._relational_scanner is not None
        if needs_scan:
            pending = self._conv_store.list_unscanned_sessions()
            if pending:
                self._shutdown_pending += 1
                logger.info("MainWindow.closeEvent — scan relationnel (%d sessions)", len(pending))
                # Déconnecter le signal normal pour utiliser notre callback de fermeture
                try:
                    self._relational_scanner.scan_complete.disconnect(
                        self._on_relational_scan_complete
                    )
                except Exception:
                    pass
                self._relational_scanner.scan_complete.connect(
                    lambda *_: self._on_shutdown_worker_done("relational")
                )
                self._relational_scanner.run_pending()
            else:
                needs_scan = False

        # ── Scan ego ──────────────────────────────────────────────────────
        # Lancer seulement si des messages sont presents (activite dans la session)
        ego_has_history = (
            self._engine is not None
            and self._conv_store is not None
            and self._conv_store.has_active_session
        )
        if ego_has_history:
            # Stopper le heartbeat pour eviter un double scan
            if hasattr(self, "_ego_heartbeat_timer"):
                self._ego_heartbeat_timer.stop()
            self._shutdown_pending += 1
            logger.info("MainWindow.closeEvent — scan ego a la fermeture")
            self._run_ego_scan(
                on_done=lambda: self._on_shutdown_worker_done("ego")
            )

        # Si aucun worker à attendre → fermer immédiatement
        if self._shutdown_pending == 0:
            logger.info("MainWindow.closeEvent — aucun worker, fermeture directe")
            self._do_close()

    def _show_shutdown_overlay(self) -> None:
        """Affiche un overlay centré 'Fermeture en cours…' pendant les workers."""
        from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget
        from PyQt6.QtCore import Qt
        from ui.font_config import FontConfig
        from ui.themes import get_colors
        c  = get_colors(getattr(self, '_current_theme', 'dark'))
        fc = FontConfig.instance()
        overlay = QWidget(self)
        overlay.setObjectName("ShutdownOverlay")
        overlay.setStyleSheet(f"""
            QWidget#ShutdownOverlay {{
                background-color: {c['bg_dialog']};
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}
            QLabel {{ color: {c['text_primary']}; font-size: {fc.size}px; }}
            QLabel#ShutdownSub {{ color: {c['text_dim']}; font-size: {fc.xs}px; }}
        """)
        lay = QVBoxLayout(overlay)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)
        lbl = QLabel("Fermeture en cours…")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("Mémorisation de la session en cours, merci de patienter.")
        sub.setObjectName("ShutdownSub")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        lay.addWidget(sub)
        # Centrer l'overlay sur la fenêtre
        ow, oh = 420, 90
        x = (self.width()  - ow) // 2
        y = (self.height() - oh) // 2
        overlay.setGeometry(x, y, ow, oh)
        overlay.raise_()
        overlay.show()
        self._shutdown_overlay = overlay

    def _on_shutdown_worker_done(self, which: str) -> None:
        """Appelé quand un worker de fermeture se termine (résumé ou scan)."""
        logger.info("MainWindow — worker fermeture '%s' terminé", which)
        

        self._shutdown_pending -= 1
        if self._shutdown_pending <= 0:
            self._do_close()

    def _do_close(self) -> None:
        """Déclenche la fermeture réelle (passe 2)."""
        overlay = getattr(self, "_shutdown_overlay", None)
        if overlay:
            overlay.hide()
            overlay.deleteLater()
        self._closing = True
        # Différer la fermeture à la prochaine boucle d'événements pour éviter
        # que l'événement initial ignoré n'annule la fermeture.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.close)   # relance closeEvent → passe 2

    def _init_resize_grips(self):
        """Initialise les 8 grips de redimensionnement transparents en bordure."""
        self._resize_widgets = {
            "top": ResizeGripWidget(self, "top", Qt.CursorShape.SizeVerCursor),
            "bottom": ResizeGripWidget(self, "bottom", Qt.CursorShape.SizeVerCursor),
            "left": ResizeGripWidget(self, "left", Qt.CursorShape.SizeHorCursor),
            "right": ResizeGripWidget(self, "right", Qt.CursorShape.SizeHorCursor),
            "top_left": ResizeGripWidget(self, "top_left", Qt.CursorShape.SizeFDiagCursor),
            "top_right": ResizeGripWidget(self, "top_right", Qt.CursorShape.SizeBDiagCursor),
            "bottom_left": ResizeGripWidget(self, "bottom_left", Qt.CursorShape.SizeBDiagCursor),
            "bottom_right": ResizeGripWidget(self, "bottom_right", Qt.CursorShape.SizeFDiagCursor),
        }
        for widget in self._resize_widgets.values():
            widget.raise_()
            widget.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_resize_widgets"):
            w = self.width()
            h = self.height()
            m = 5  # Épaisseur de la bordure réactive en pixels
            
            maximized = self.isMaximized()
            for widget in self._resize_widgets.values():
                widget.setVisible(not maximized)
            if maximized:
                return
                
            # Positionnement géométrique des grips
            self._resize_widgets["top_left"].setGeometry(0, 0, m, m)
            self._resize_widgets["top_right"].setGeometry(w - m, 0, m, m)
            self._resize_widgets["bottom_left"].setGeometry(0, h - m, m, m)
            self._resize_widgets["bottom_right"].setGeometry(w - m, h - m, m, m)
            
            self._resize_widgets["top"].setGeometry(m, 0, w - 2*m, m)
            self._resize_widgets["bottom"].setGeometry(m, h - m, w - 2*m, m)
            self._resize_widgets["left"].setGeometry(0, m, m, h - 2*m)
            self._resize_widgets["right"].setGeometry(w - m, m, m, h - 2*m)
            
            # Garantir la superposition au premier plan
            for widget in self._resize_widgets.values():
                widget.raise_()


class ResizeGripWidget(QWidget):
    """Bandeau invisible gérant le redimensionnement d'une fenêtre frameless."""
    def __init__(self, parent, edge: str, cursor_shape: Qt.CursorShape):
        super().__init__(parent)
        self._edge = edge
        self.setCursor(cursor_shape)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent;")
        self._drag_start_pos = None
        self._drag_start_geometry = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_start_geometry = self.window().geometry()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            geo = self._drag_start_geometry
            
            x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
            window = self.window()
            min_w = window.minimumWidth()
            min_h = window.minimumHeight()
            
            edge = self._edge
            
            if "left" in edge:
                new_w = w - delta.x()
                if new_w >= min_w:
                    x = geo.x() + delta.x()
                    w = new_w
            elif "right" in edge:
                new_w = w + delta.x()
                if new_w >= min_w:
                    w = new_w
                    
            if "top" in edge:
                new_h = h - delta.y()
                if new_h >= min_h:
                    y = geo.y() + delta.y()
                    h = new_h
            elif "bottom" in edge:
                new_h = h + delta.y()
                if new_h >= min_h:
                    h = new_h
                    
            window.setGeometry(x, y, w, h)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self._drag_start_geometry = None
        event.accept()

