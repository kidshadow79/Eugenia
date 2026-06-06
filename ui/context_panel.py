"""
ContextPanel — Panneau contextuel (colonne 2)

Affiche le contenu lié à l'icône active dans l'IconBar.
Chaque section (Bible, Historique…) aura son propre widget plus tard.
Pour l'instant : titre + placeholder texte.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QStackedWidget
from PyQt6.QtCore import Qt
from ui.bible_panel import BiblePanel
from ui.settings_panel import SettingsPanel
from ui.history_panel import HistoryPanel
from ui.sources_panel import SourcesPanel
from ui.style_panel import StylePanel
from ui.memory_panel import MemoryPanel
from ui.stats_panel import StatsPanel
from core.i18n import tr

PANEL_TITLES = {
    "bible":        "BIBLE",
    "historique":   "HISTORIQUE",
    "sources":      "SOURCES",
    "style":        "PROFIL DE STYLE",    "memoire":      "MEMOIRE",    "stats":        "STATISTIQUES",
    "parametres":   "PARAMÈTRES",
}

CONTEXT_PANEL_STYLE = """
QWidget#ContextPanel {
    background-color: #252526;
}
QLabel#PanelTitle {
    color: #bbbbbb;
    font-size: 11px;
    font-weight: bold;
    padding: 10px 12px 6px 12px;
    letter-spacing: 1px;
    border-bottom: 1px solid #3e3e42;
}
QLabel#PanelContent {
    color: #858585;
    font-size: 13px;
    padding: 12px;
}
"""


class ContextPanel(QWidget):
    def __init__(self, author_slug: str = "", author_name: str = ""):
        super().__init__()
        self.setObjectName("ContextPanel")
        self.setMinimumWidth(150)
        self._author_slug = author_slug
        self._author_name = author_name
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_label = QLabel("—")
        self.title_label.setObjectName("PanelTitle")
        layout.addWidget(self.title_label)

        # Conteneur empilé : chaque section a son propre widget
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Page 0 : placeholder générique
        self._placeholder = QLabel(tr("Clique sur une icône\npour ouvrir ce panneau."))
        self._placeholder.setObjectName("PanelContent")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)   # index 0

        # Page 1 : Bible (5 onglets)
        self.bible_panel = BiblePanel()
        self._stack.addWidget(self.bible_panel)    # index 1

        # Page 2 : Parametres IA
        self.settings_panel = SettingsPanel(
            author_slug=self._author_slug,
            author_name=self._author_name,
        )
        self._stack.addWidget(self.settings_panel)  # index 2

        # Page 3 : Historique conversations
        self.history_panel = HistoryPanel()
        self._stack.addWidget(self.history_panel)   # index 3

        # Page 4 : Sources ingérees
        self.sources_panel = SourcesPanel()
        self._stack.addWidget(self.sources_panel)   # index 4

        # Page 5 : Profil de style
        self.style_panel = StylePanel()
        self._stack.addWidget(self.style_panel)     # index 5

        # Page 6 : Memoire relationnelle
        self.memory_panel = MemoryPanel()
        self._stack.addWidget(self.memory_panel)    # index 6

        # Page 7 : Statistiques
        self.stats_panel = StatsPanel()
        self._stack.addWidget(self.stats_panel)     # index 7

        self._stack.setCurrentIndex(0)

    def set_content(self, icon_id: str):
        """Appelé par MainWindow quand une icône est activée."""
        self.title_label.setText(tr(PANEL_TITLES.get(icon_id, "—")))

        if icon_id == "bible":
            self._stack.setCurrentIndex(1)
        elif icon_id == "parametres":
            self._stack.setCurrentIndex(2)
        elif icon_id == "historique":
            self._stack.setCurrentIndex(3)
        elif icon_id == "sources":
            self._stack.setCurrentIndex(4)
        elif icon_id == "style":
            self._stack.setCurrentIndex(5)
        elif icon_id == "memoire":
            self._stack.setCurrentIndex(6)
        elif icon_id == "stats":
            self._stack.setCurrentIndex(7)
        else:
            self._placeholder.setText(
                tr("Section « {} »\n— à construire.").format(tr(PANEL_TITLES.get(icon_id, icon_id)))
            )
            self._stack.setCurrentIndex(0)

    def set_memory_db(self, relational_db) -> None:
        """Branche la base relationnelle sur le MemoryPanel."""
        self.memory_panel.set_db(relational_db)

    def set_ego_manager(self, ego) -> None:
        """Branche le gestionnaire Ego sur le MemoryPanel."""
        self.memory_panel.set_ego(ego)

    def set_stats_store(self, store) -> None:
        """Expose le StatsPanel pour câblage depuis MainWindow."""
        # Le store est géré dans main_window ; ici on donne accès au widget.
        pass  # Le câblage des signaux est fait dans main_window.py

    def apply_theme(self, theme: str) -> None:
        pass
