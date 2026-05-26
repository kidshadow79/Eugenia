"""
IconBar — Barre d'icônes gauche (style VS Code activity bar)

Rôle : présenter 5 icônes principales + 1 en bas (Paramètres).
Chaque clic envoie le signal icon_clicked(icon_id, is_active).
- Si on clique une icône inactive → elle s'active, l'ancienne se désactive.
- Si on clique l'icône déjà active → elle se désactive (ferme le panneau).
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QSize
import qtawesome as qta

# (identifiant, nom_icône_fa, tooltip)
ICONS_TOP = [
    ("bible",      "fa5s.journal-whills", "Bible"),
    ("historique", "fa5s.scroll",         "Historique"),
    ("sources",    "fa5s.archive",        "Sources"),
    ("style",      "fa5s.feather-alt",    "Profil de style"),
    ("memoire",    "fa5s.network-wired",  "Mémoire"),
    ("stats",      "fa5s.chart-pie",      "Statistiques"),
]
ICON_BOTTOM = ("parametres", "fa5s.sliders-h", "Paramètres")

# Couleurs par défaut (mode dark) — remplacées dès le premier apply_theme()
_CLR_NORMAL_DEFAULT = "#858585"
_CLR_ACTIVE_DEFAULT = "#ffffff"


class IconBar(QWidget):
    # Signal émis quand une icône est cliquée : (icon_id, is_active)
    icon_clicked = pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("IconBar")
        self.setFixedWidth(48)
        self._buttons: dict[str, QPushButton] = {}
        self._active_id: str | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)  # petit espacement pour que le tab actif "sorte" visuellement

        layout.addSpacing(30)  # marge haute pour dégager la barre de titre système

        for icon_id, emoji, tooltip in ICONS_TOP:
            btn = self._make_button(icon_id, emoji, tooltip)
            layout.addWidget(btn)

        layout.addStretch()

        # Paramètres toujours en bas
        icon_id, emoji, tooltip = ICON_BOTTOM
        btn = self._make_button(icon_id, emoji, tooltip)
        layout.addWidget(btn)
        layout.addSpacing(4)

    def _make_button(self, icon_id: str, icon_name: str, tooltip: str) -> QPushButton:
        btn = QPushButton()
        btn.setCheckable(True)
        btn.setToolTip(tooltip)
        btn.setFixedSize(48, 48)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Icône en état normal et actif (checked) — couleurs mises à jour par apply_theme()
        btn.setIcon(qta.icon(icon_name, color=_CLR_NORMAL_DEFAULT, color_active=_CLR_ACTIVE_DEFAULT))
        btn.setIconSize(QSize(22, 22))
        btn.clicked.connect(lambda checked, i=icon_id: self._on_click(i, checked))
        self._buttons[icon_id] = btn
        return btn

    def _on_click(self, icon_id: str, checked: bool):
        # Clique sur l'icône déjà active → toggle off (ferme le panneau)
        if not checked and self._active_id == icon_id:
            self._active_id = None
            self.icon_clicked.emit(icon_id, False)
            return

        # Désactive l'ancienne icône active si différente
        if self._active_id and self._active_id != icon_id:
            self._buttons[self._active_id].setChecked(False)

        self._active_id = icon_id if checked else None
        self.icon_clicked.emit(icon_id, checked)

    def apply_theme(self, theme: str) -> None:
        """Met à jour les couleurs des icônes qtawesome selon le thème et les overrides."""
        from ui.theme_config import ThemeConfig
        from ui.themes import get_colors
        overrides = ThemeConfig.instance().get_overrides(theme)
        c = {**get_colors(theme), **overrides}
        clr_normal = c.get("icon_color", _CLR_NORMAL_DEFAULT)
        clr_active = c.get("icon_active", _CLR_ACTIVE_DEFAULT)
        for icon_id, icon_name, _ in list(ICONS_TOP) + [ICON_BOTTOM]:
            if icon_id in self._buttons:
                self._buttons[icon_id].setIcon(
                    qta.icon(icon_name, color=clr_normal, color_active=clr_active)
                )

    def deselect(self, icon_id: str) -> None:
        """Désélectionne programmatiquement une icône (sans émettre de signal)."""
        if icon_id in self._buttons:
            self._buttons[icon_id].setChecked(False)
        if self._active_id == icon_id:
            self._active_id = None
