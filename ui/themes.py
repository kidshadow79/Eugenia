"""
themes.py -- Source unique de verite pour les couleurs et styles EUGENIA

Usage :
    from ui.themes import build_stylesheet, COLORS
    QApplication.instance().setStyleSheet(build_stylesheet("dark"))

Pourquoi centralise ici ?
    QSS applique via QApplication.setStyleSheet() cascade vers TOUS les
    widgets qui n'ont pas leur propre setStyleSheet() local.
    => ajouter un nouveau widget = zero config theme necessaire.
"""

# ─── Palettes de couleurs ─────────────────────────────────────────────────────

_DARK = {
    "bg_window":    "#1e1e1e",
    "bg_panel":     "#252526",
    "bg_elevated":  "#2d2d2d",
    "bg_input":     "#3c3c3c",
    "bg_dialog":    "#252526",
    "text_primary": "#cccccc",
    "text_bright":  "#ffffff",
    "text_dim":     "#858585",
    "text_muted":   "#555555",
    "text_title":   "#bbbbbb",
    "border":       "#3e3e42",
    "border_input": "#555555",
    "border_panel": "#3e3e42",
    "accent":       "#0e639c",
    "accent_hover": "#1177bb",
    "accent_press": "#0a4f80",
    "tab_bar_bg":   "#2d2d2d",
    "tab_bar_text": "#888888",
    "tab_active_bg":"#1e1e1e",
    "scroll_track": "#252526",
    "scroll_thumb": "#555555",
    "scroll_hover": "#888888",
    "item_hover":   "#2a2d2e",
    "item_select":  "#094771",
    "icon_bar_bg":  "#333333",
    "icon_color":   "#858585",
    "icon_active":  "#ffffff",
    "danger_text":  "#e07070",
    "danger_border":"#7a3535",
    "danger_hover": "#3e2020",
    "thinking":     "#4ec9b0",
    "notif_bg":     "#2d2d2d",
    "notif_text":   "#cccccc",
    "badge_bg":     "#1e1e3a",
    "badge_text":   "#e0e0e0",
}

_LIGHT = {
    "bg_window":    "#ede9e4",
    "bg_panel":     "#f7f5f2",
    "bg_elevated":  "#e4e0da",
    "bg_input":     "#f7f5f2",
    "bg_dialog":    "#f2efe9",
    "text_primary": "#1e1e1e",
    "text_bright":  "#000000",
    "text_dim":     "#555555",
    "text_muted":   "#999999",
    "text_title":   "#444444",
    "border":       "#d4d4d4",
    "border_input": "#b0b0b0",
    "border_panel": "#d4d4d4",
    "accent":       "#0e639c",
    "accent_hover": "#1177bb",
    "accent_press": "#0a4f80",
    "tab_bar_bg":   "#e4e0da",
    "tab_bar_text": "#666666",
    "tab_active_bg":"#ede9e4",
    "scroll_track": "#dedad4",
    "scroll_thumb": "#aaaaaa",
    "scroll_hover": "#777777",
    "item_hover":   "#e4e0da",
    "item_select":  "#cce5ff",
    "icon_bar_bg":  "#dedad4",
    "icon_color":   "#666666",
    "icon_active":  "#1e1e1e",
    "danger_text":  "#c0392b",
    "danger_border":"#e88080",
    "danger_hover": "#fde8e8",
    "thinking":     "#008080",
    "notif_bg":     "#e4e0da",
    "notif_text":   "#333333",
    "badge_bg":     "#1e4080",
    "badge_text":   "#ffffff",
}

_GLASS = {
    "bg_window":    "#0a0f18",
    "bg_panel":     "rgba(20, 28, 44, 0.65)",
    "bg_elevated":  "rgba(35, 45, 65, 0.75)",
    "bg_input":     "rgba(15, 20, 35, 0.8)",
    "bg_dialog":    "#121a28",
    "text_primary": "#e2e8f0",
    "text_bright":  "#ffffff",
    "text_dim":     "#94a3b8",
    "text_muted":   "#64748b",
    "text_title":   "#f8fafc",
    "border":       "rgba(255, 255, 255, 0.08)",
    "border_input": "rgba(255, 255, 255, 0.12)",
    "border_panel": "rgba(255, 255, 255, 0.05)",
    "accent":       "#3b82f6",
    "accent_hover": "#60a5fa",
    "accent_press": "#2563eb",
    "tab_bar_bg":   "rgba(15, 20, 35, 0.4)",
    "tab_bar_text": "#94a3b8",
    "tab_active_bg":"rgba(20, 28, 44, 0.85)",
    "scroll_track": "transparent",
    "scroll_thumb": "rgba(255, 255, 255, 0.15)",
    "scroll_hover": "rgba(255, 255, 255, 0.3)",
    "item_hover":   "rgba(255, 255, 255, 0.05)",
    "item_select":  "rgba(59, 130, 246, 0.25)",
    "icon_bar_bg":  "rgba(10, 15, 25, 0.8)",
    "icon_color":   "#94a3b8",
    "icon_active":  "#3b82f6",
    "danger_text":  "#ef4444",
    "danger_border":"rgba(239, 68, 68, 0.4)",
    "danger_hover": "rgba(239, 68, 68, 0.15)",
    "thinking":     "#10b981",
    "notif_bg":     "rgba(30, 41, 59, 0.9)",
    "notif_text":   "#e2e8f0",
    "badge_bg":     "rgba(59, 130, 246, 0.2)",
    "badge_text":   "#60a5fa",
}
_GLASS_LIGHT = {
    "bg_window":    "#f8fafc",
    "bg_panel":     "rgba(241, 245, 249, 0.65)",
    "bg_elevated":  "rgba(226, 232, 240, 0.75)",
    "bg_input":     "rgba(255, 255, 255, 0.8)",
    "bg_dialog":    "#f1f5f9",
    "text_primary": "#1e293b",
    "text_bright":  "#0f172a",
    "text_dim":     "#475569",
    "text_muted":   "#64748b",
    "text_title":   "#0f172a",
    "border":       "rgba(0, 0, 0, 0.08)",
    "border_input": "rgba(0, 0, 0, 0.12)",
    "border_panel": "rgba(0, 0, 0, 0.05)",
    "accent":       "#3b82f6",
    "accent_hover": "#2563eb",
    "accent_press": "#1d4ed8",
    "tab_bar_bg":   "rgba(226, 232, 240, 0.4)",
    "tab_bar_text": "#64748b",
    "tab_active_bg":"rgba(241, 245, 249, 0.85)",
    "scroll_track": "transparent",
    "scroll_thumb": "rgba(0, 0, 0, 0.15)",
    "scroll_hover": "rgba(0, 0, 0, 0.3)",
    "item_hover":   "rgba(0, 0, 0, 0.05)",
    "item_select":  "rgba(59, 130, 246, 0.15)",
    "icon_bar_bg":  "rgba(248, 250, 252, 0.8)",
    "icon_color":   "#64748b",
    "icon_active":  "#3b82f6",
    "danger_text":  "#ef4444",
    "danger_border":"rgba(239, 68, 68, 0.4)",
    "danger_hover": "rgba(239, 68, 68, 0.15)",
    "thinking":     "#10b981",
    "notif_bg":     "rgba(255, 255, 255, 0.9)",
    "notif_text":   "#1e293b",
    "badge_bg":     "rgba(59, 130, 246, 0.2)",
    "badge_text":   "#2563eb",
}

_FLAT_MAC = {
    "bg_window":    "#1e1e1e",
    "bg_panel":     "#252526",
    "bg_elevated":  "#333333",
    "bg_input":     "#2d2d2d",
    "bg_dialog":    "#252526",
    "text_primary": "#d4d4d4",
    "text_bright":  "#ffffff",
    "text_dim":     "#8a8a8a",
    "text_muted":   "#6a6a6a",
    "text_title":   "#e0e0e0",
    "border":       "#3a3a3a",
    "border_input": "#4a4a4a",
    "border_panel": "#333333",
    "accent":       "#007aff",
    "accent_hover": "#3395ff",
    "accent_press": "#005bb5",
    "tab_bar_bg":   "#1e1e1e",
    "tab_bar_text": "#8a8a8a",
    "tab_active_bg":"#252526",
    "scroll_track": "transparent",
    "scroll_thumb": "#555555",
    "scroll_hover": "#777777",
    "item_hover":   "#2a2d2e",
    "item_select":  "#005bb5",
    "icon_bar_bg":  "#181818",
    "icon_color":   "#8a8a8a",
    "icon_active":  "#ffffff",
    "danger_text":  "#ff453a",
    "danger_border":"#8a2c27",
    "danger_hover": "#4a1917",
    "thinking":     "#32d74b",
    "notif_bg":     "#333333",
    "notif_text":   "#d4d4d4",
    "badge_bg":     "#1a2b3c",
    "badge_text":   "#5ac8fa",
}
_FLAT_MAC_LIGHT = {
    "bg_window":    "#ececec",
    "bg_panel":     "#ffffff",
    "bg_elevated":  "#f5f5f5",
    "bg_input":     "#ffffff",
    "bg_dialog":    "#ececec",
    "text_primary": "#333333",
    "text_bright":  "#000000",
    "text_dim":     "#6a6a6a",
    "text_muted":   "#8a8a8a",
    "text_title":   "#1a1a1a",
    "border":       "#d1d1d1",
    "border_input": "#c1c1c1",
    "border_panel": "#e1e1e1",
    "accent":       "#007aff",
    "accent_hover": "#005bb5",
    "accent_press": "#004499",
    "tab_bar_bg":   "#ececec",
    "tab_bar_text": "#6a6a6a",
    "tab_active_bg":"#ffffff",
    "scroll_track": "transparent",
    "scroll_thumb": "#b0b0b0",
    "scroll_hover": "#808080",
    "item_hover":   "#f0f0f0",
    "item_select":  "#cce5ff",
    "icon_bar_bg":  "#e0e0e0",
    "icon_color":   "#6a6a6a",
    "icon_active":  "#007aff",
    "danger_text":  "#ff3b30",
    "danger_border":"#ffc1bd",
    "danger_hover": "#ffeae9",
    "thinking":     "#34c759",
    "notif_bg":     "#ffffff",
    "notif_text":   "#333333",
    "badge_bg":     "#e6f2ff",
    "badge_text":   "#007aff",
}

_CYBER = {
    "bg_window":    "#0d0d14",
    "bg_panel":     "#12121a",
    "bg_elevated":  "#1a1a24",
    "bg_input":     "#0a0a0f",
    "bg_dialog":    "#12121a",
    "text_primary": "#00ffcc",
    "text_bright":  "#ffffff",
    "text_dim":     "#008a7b",
    "text_muted":   "#004d44",
    "text_title":   "#ff0055",
    "border":       "#ff0055",
    "border_input": "#00ffcc",
    "border_panel": "#330011",
    "accent":       "#ff0055",
    "accent_hover": "#ff3377",
    "accent_press": "#cc0044",
    "tab_bar_bg":   "#0a0a0f",
    "tab_bar_text": "#008a7b",
    "tab_active_bg":"#12121a",
    "scroll_track": "#0a0a0f",
    "scroll_thumb": "#00ffcc",
    "scroll_hover": "#ff0055",
    "item_hover":   "#1a000a",
    "item_select":  "#330011",
    "icon_bar_bg":  "#050508",
    "icon_color":   "#00ffcc",
    "icon_active":  "#ff0055",
    "danger_text":  "#ff0000",
    "danger_border":"#cc0000",
    "danger_hover": "#330000",
    "thinking":     "#f0e68c",
    "notif_bg":     "#1a1a24",
    "notif_text":   "#00ffcc",
    "badge_bg":     "#330011",
    "badge_text":   "#ff0055",
}


def get_colors(theme: str) -> dict:
    if theme == "light": return _LIGHT
    if theme == "glass": return _GLASS
    if theme == "glass_light": return _GLASS_LIGHT
    if theme == "flat_mac": return _FLAT_MAC
    if theme == "flat_mac_light": return _FLAT_MAC_LIGHT
    if theme == "cyber": return _CYBER
    return _DARK


def build_stylesheet(theme: str, fc=None) -> str:
    """Retourne la feuille de style complete pour le theme donne.

    fc : FontConfig | None — si None, utilise le singleton FontConfig.instance().
    La signature accepte aussi un int (compat ascendante) : build_stylesheet(t, 13).
    """
    from ui.font_config import FontConfig
    if fc is None:
        fc = FontConfig.instance()
    elif isinstance(fc, int):
        # compat ascendante : build_stylesheet(theme, font_size_int)
        FontConfig.instance().update(size=fc)
        fc = FontConfig.instance()

    c = {**get_colors(theme)}
    from ui.theme_config import ThemeConfig
    c.update(ThemeConfig.instance().get_overrides(theme))
    return f"""
/* ── Base ──────────────────────────────────────────────────────────── */
QMainWindow, QWidget, QDialog {{
    background-color: {c['bg_window']};
    color: {c['text_primary']};
    font-family: '{fc.family}', 'Inter', 'Segoe UI Variable', 'Segoe UI', 'Arial', sans-serif;
    font-size: {fc.size}px;
}}

/* ── Splitter ───────────────────────────────────────────────────────── */
QSplitter::handle:vertical {{
    height: 5px;
    background-color: {c['border']};
    margin: 1px 0px;
}}
QSplitter::handle:vertical:hover {{
    background-color: {c['bg_elevated']};
}}

/* ── Scrollbars ─────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {c['scroll_track']};
    width: 10px;
    border: none;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {c['scroll_thumb']};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c['scroll_hover']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {c['scroll_track']};
    height: 10px;
    border: none;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {c['scroll_thumb']};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c['scroll_hover']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ── QLineEdit ──────────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {c['bg_input']};
    border: 1px solid {c['border_input']};
    border-radius: 8px;
    color: {c['text_bright']};
    font-size: {fc.size}px;
    padding: 8px 12px;
    font-family: 'Consolas', 'Courier New', monospace;
    min-height: 24px;
}}
QLineEdit:focus {{
    border: 1px solid {c['accent']};
    background-color: {c['bg_elevated']};
}}

/* ── QTextEdit ──────────────────────────────────────────────────────── */
QTextEdit {{
    background-color: {c['bg_input']};
    border: 1px solid {c['border_input']};
    border-radius: 8px;
    color: {c['text_primary']};
    padding: 8px;
}}

/* ── QComboBox ──────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {c['bg_elevated']};
    border: 1px solid {c['border_input']};
    border-radius: 8px;
    color: {c['text_bright']};
    padding: 6px 12px;
    font-size: {fc.sm}px;
    min-height: 24px;
}}
QComboBox:focus {{
    border: 1px solid {c['accent']};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {c['text_dim']};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {c['bg_panel']};
    color: {c['text_primary']};
    selection-background-color: {c['accent']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    outline: none;
}}

/* ── QListWidget ────────────────────────────────────────────────────── */
QListWidget {{
    background-color: {c['bg_window']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    color: {c['text_primary']};
    font-size: {fc.size}px;
    padding: 6px;
}}
QListWidget::item {{
    padding: 8px 12px;
    border-bottom: 1px solid {c['border']};
    border-radius: 6px;
    margin-bottom: 2px;
}}
QListWidget::item:selected {{
    background-color: {c['item_select']};
    color: {c['text_bright']};
}}
QListWidget::item:hover:!selected {{
    background-color: {c['item_hover']};
}}

/* ── QTabWidget ─────────────────────────────────────────────────────── */
QTabWidget {{
    background-color: {c['bg_window']};
    border: none;
}}
QTabWidget::pane {{
    border: none;
    background-color: {c['bg_window']};
}}
QTabBar {{
    background-color: {c['tab_bar_bg']};
    border-bottom: 1px solid {c['border']};
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {c['tab_bar_text']};
    padding: 10px 20px;
    border: none;
    border-bottom: 3px solid transparent;
    font-size: {fc.sm}px;
    font-weight: bold;
    min-width: 80px;
    margin-right: 4px;
}}
QTabBar::tab:selected {{
    color: {c['text_bright']};
    border-bottom: 3px solid {c['accent']};
    background-color: {c['tab_active_bg']};
}}
QTabBar::tab:hover:!selected {{
    color: {c['text_primary']};
    background-color: {c['item_hover']};
}}
QTabBar QToolButton {{
    background-color: transparent;
    border: none;
    color: {c['text_dim']};
    padding: 2px;
}}
QTabBar QToolButton:hover {{
    color: {c['text_primary']};
}}

/* ── QPushButton generiques ─────────────────────────────────────────── */
QPushButton {{
    background-color: {c['bg_elevated']};
    border: 1px solid {c['border_input']};
    border-radius: 8px;
    color: {c['text_primary']};
    padding: 8px 16px;
    font-size: {fc.sm}px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {c['item_hover']};
    border: 1px solid {c['accent']};
    color: {c['text_bright']};
}}
QPushButton:disabled {{
    color: {c['text_muted']};
    border-color: {c['border']};
    background-color: transparent;
}}

/* ── Bouton primaire (SaveBtn, PrimaryBtn, SendButton) ──────────────── */
QPushButton#SaveBtn, QPushButton#PrimaryBtn, QPushButton#SendButton {{
    background-color: {c['accent']};
    color: #ffffff;
    border: none;
    font-weight: bold;
    padding: 10px 20px;
}}
QPushButton#SaveBtn:hover, QPushButton#PrimaryBtn:hover,
QPushButton#SendButton:hover {{
    background-color: {c['accent_hover']};
}}
QPushButton#SaveBtn:pressed, QPushButton#PrimaryBtn:pressed,
QPushButton#SendButton:pressed {{
    background-color: {c['accent_press']};
}}
QPushButton#PrimaryBtn:disabled {{
    background-color: {c['border']};
    color: {c['text_muted']};
}}

/* ── Bouton secondaire ──────────────────────────────────────────────── */
QPushButton#SecondaryBtn {{
    background-color: transparent;
    color: {c['text_primary']};
    border: 1px solid {c['border_input']};
    border-radius: 8px;
    padding: 8px 16px;
}}
QPushButton#SecondaryBtn:hover {{
    background-color: {c['item_hover']};
    border-color: {c['accent']};
    color: {c['text_bright']};
}}

/* ── Bouton danger ──────────────────────────────────────────────────── */
QPushButton#HistBtnDanger, QPushButton#SrcBtnDanger, QPushButton#DeleteBtn {{
    color: {c['danger_text']};
    border: 1px solid {c['danger_border']};
    background-color: transparent;
    border-radius: 8px;
    padding: 8px 16px;
}}
QPushButton#HistBtnDanger:hover, QPushButton#SrcBtnDanger:hover,
QPushButton#DeleteBtn:hover {{
    background-color: {c['danger_hover']};
    border-color: {c['danger_text']};
}}

/* ── QFrame separateur ──────────────────────────────────────────────── */
QFrame#Separator {{
    color: {c['border']};
    border: none;
    border-top: 1px solid {c['border']};
    margin: 12px 0px;
}}

/* ── QProgressBar ───────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {c['bg_elevated']};
    border: 1px solid {c['border_input']};
    border-radius: 4px;
    height: 12px;
    text-align: center;
    color: {c['text_primary']};
    font-size: {fc.xs}px;
}}
QProgressBar::chunk {{
    background-color: {c['accent']};
    border-radius: 4px;
}}

/* ── QRadioButton ───────────────────────────────────────────────────── */
QRadioButton {{
    color: {c['text_primary']};
    spacing: 8px;
    font-size: {fc.sm}px;
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 2px solid {c['border_input']};
    background-color: {c['bg_input']};
}}
QRadioButton::indicator:hover {{
    border-color: {c['accent']};
}}
QRadioButton::indicator:checked {{
    border: 2px solid {c['accent']};
    background-color: {c['accent']};
    image: none;
}}
QRadioButton::indicator:checked:hover {{
    border-color: {c['accent_hover']};
    background-color: {c['accent_hover']};
}}

/* ── IconBar ────────────────────────────────────────────────────────── */
QWidget#IconBar {{
    background-color: {c['icon_bar_bg']};
    border-right: 1px solid {c['border']};
}}
QWidget#IconBar QPushButton {{
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: {c['icon_color']};
    padding: 0px;
    width: 48px;
    height: 48px;
    margin: 2px 0px;
}}
QWidget#IconBar QPushButton:hover {{
    background-color: {c['item_hover']};
    border-left: 3px solid {c['border']};
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
}}
QWidget#IconBar QPushButton:checked {{
    color: {c['icon_active']};
    background-color: {c['bg_panel']};
    border-top: 1px solid {c['border']};
    border-left: 3px solid {c['accent']};
    border-bottom: 1px solid {c['border']};
    border-right: none;
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
    margin-right: 0px;
}}

/* ── ContextPanel ───────────────────────────────────────────────────── */
QWidget#ContextPanel {{
    background-color: {c['bg_panel']};
    border-right: 1px solid {c['border']};
}}
QLabel#PanelTitle {{
    color: {c['text_title']};
    font-size: {fc.sm}px;
    font-weight: bold;
    padding: 14px 16px 8px 16px;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QLabel#PanelContent {{
    color: {c['text_dim']};
    font-size: {fc.size}px;
    padding: 16px;
}}

/* ── AIPanel ────────────────────────────────────────────────────────── */
QWidget#AIPanel {{
    background-color: {c['bg_panel']};
    border-left: 1px solid {c['border']};
}}
QLabel#AITitle {{
    color: {c['text_title']};
    font-size: {fc.sm}px;
    font-weight: bold;
    padding: 14px 16px 8px 16px;
    letter-spacing: 1px;
    text-transform: uppercase;
    border-bottom: 1px solid {c['border']};
}}
QTextEdit#ChatHistory {{
    background-color: {c['bg_window']};
    border: none;
    color: {c['text_primary']};
    padding: 12px;
    font-size: {fc.size}px;
}}
QWidget#InputArea {{
    background-color: {c['bg_elevated']};
    border-top: 1px solid {c['border']};
    padding: 8px;
}}
QTextEdit#ChatInput {{
    background-color: {c['bg_input']};
    border: 1px solid {c['border_input']};
    border-radius: 8px;
    color: {c['text_primary']};
    padding: 8px;
    font-size: {fc.size}px;
}}
QTextEdit#ChatInput:focus {{
    border: 1px solid {c['accent']};
}}
QLabel#ThinkingLabel {{
    color: {c['thinking']};
    font-size: {fc.xs}px;
    font-style: italic;
    padding: 6px 12px;
}}
QWidget#EmbedFooter {{
    background-color: {c['bg_elevated']};
    border-top: 1px solid {c['border']};
}}
QPushButton#EmbedBtn {{
    background: transparent;
    color: {c['text_muted']};
    border: none;
    font-size: {fc.xs}px;
    padding: 4px 10px;
    text-align: left;
}}
QPushButton#EmbedBtn:hover {{
    color: {c['text_dim']};
}}
QCheckBox#DocModeCheck {{
    color: {c['text_dim']};
    padding: 0px 6px;
    spacing: 4px;
}}
QCheckBox#DocModeCheck:hover {{
    color: {c['text_primary']};
}}
QCheckBox#DocModeCheck:checked {{
    color: {c['thinking']};
}}
QCheckBox#DocModeCheck:disabled {{
    color: {c['text_muted']};
}}
QCheckBox#DocModeCheck::indicator {{
    width: 12px;
    height: 12px;
    border: 1px solid {c['border']};
    border-radius: 3px;
    background: {c['bg_input']};
}}
QCheckBox#DocModeCheck::indicator:checked {{
    background: {c['thinking']};
    border-color: {c['thinking']};
}}

/* ── EditorZone ─────────────────────────────────────────────────────── */
QWidget#EditorZone {{
    background-color: {c['bg_window']};
}}
QLabel#Placeholder {{
    color: {c['border']};
    font-size: {fc.sm}px;
}}

/* ── SettingsPanel ──────────────────────────────────────────────────── */
QScrollArea, QWidget#SettingsPanel, QWidget#ScrollContent {{
    background-color: {c['bg_window']};
    border: none;
}}
QLabel#SectionTitle {{
    color: {c['text_title']};
    font-size: {fc.sm}px;
    font-weight: bold;
    padding: 12px 0px 6px 0px;
    letter-spacing: 0.5px;
    border-bottom: 1px solid {c['border']};
    margin-bottom: 8px;
}}
QLabel#FieldLabel {{
    color: {c['text_dim']};
    font-size: {fc.xs}px;
    font-weight: 500;
    min-width: 80px;
}}
QLabel#StatusLabel {{
    color: {c['thinking']};
    font-size: {fc.xs}px;
    padding: 4px 0px;
}}
QLabel#HintLabel {{
    color: {c['text_muted']};
    font-size: {fc.xs}px;
    font-style: italic;
}}
QPushButton#ToggleBtn, QPushButton#RefreshBtn {{
    background-color: {c['bg_elevated']};
    border: 1px solid {c['border_input']};
    border-radius: 6px;
    color: {c['text_dim']};
    font-size: {fc.xs}px;
    padding: 4px 8px;
    min-height: 24px;
    min-width: 32px;
}}
QPushButton#ToggleBtn:hover, QPushButton#RefreshBtn:hover {{
    background-color: {c['bg_input']};
    color: {c['text_bright']};
    border-color: {c['accent']};
}}
QPushButton#RefreshBtn:disabled {{
    color: {c['text_muted']};
}}
QTextEdit#PromptEdit {{
    background-color: {c['bg_elevated']};
    border: 1px solid {c['border_input']};
    border-radius: 6px;
    color: {c['text_primary']};
    font-size: {fc.xs}px;
    font-family: 'Consolas', 'Courier New', monospace;
    padding: 8px;
}}
QTextEdit#PromptEdit:focus {{
    border: 1px solid {c['accent']};
}}
QPushButton#ResetPromptBtn {{
    background-color: transparent;
    border: 1px solid {c['border_input']};
    border-radius: 6px;
    color: {c['text_dim']};
    font-size: {fc.xs}px;
    padding: 4px 10px;
    min-height: 20px;
}}
QPushButton#ResetPromptBtn:hover {{
    color: {c['text_bright']};
    border-color: {c['accent']};
    background-color: {c['item_hover']};
}}

/* ── HistoryPanel / SourcesPanel / StylePanel ───────────────────────── */
QWidget#HistoryPanel, QWidget#SourcesPanel, QWidget#StylePanel {{
    background-color: {c['bg_panel']};
}}
QTextEdit#ProfileView {{
    background-color: {c['bg_window']};
    border: none;
    color: {c['text_primary']};
    font-size: {fc.sm}px;
    padding: 8px;
}}
QPushButton#StyleBtn, QPushButton#HistBtn, QPushButton#SrcBtn {{
    background-color: {c['bg_elevated']};
    color: {c['text_primary']};
    border: 1px solid {c['border_input']};
    border-radius: 8px;
    padding: 8px 16px;
    font-size: {fc.sm}px;
    font-weight: 500;
}}
QPushButton#StyleBtn:hover, QPushButton#HistBtn:hover,
QPushButton#SrcBtn:hover {{
    background-color: {c['item_hover']};
    border-color: {c['accent']};
    color: {c['text_bright']};
}}
QPushButton#StyleBtn:disabled {{
    color: {c['text_muted']};
}}
QPushButton#HistBtnNew {{
    background-color: transparent;
    color: {c['thinking']};
    border: 1px solid {c['thinking']};
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: bold;
}}
QPushButton#HistBtnNew:hover {{
    background-color: {c['item_hover']};
}}
QLabel#EmptyLabel {{
    color: {c['text_muted']};
    font-size: {fc.sm}px;
}}
QLabel#StatusLabel {{
    color: {c['thinking']};
    font-size: {fc.xs}px;
    font-style: italic;
    padding: 4px 8px;
}}

/* ── ClipboardNotification ──────────────────────────────────────────── */
QWidget#ClipboardNotif {{
    background-color: {c['notif_bg']};
    border: 1px solid {c['accent']};
    border-radius: 12px;
    padding: 10px;
}}
QLabel#NotifTitle {{
    color: {c['notif_text']};
    font-weight: bold;
    padding: 2px 0px;
}}
QLabel#NotifPreview {{
    color: {c['notif_text']};
    font-style: italic;
}}
QPushButton#SendBtn {{
    background-color: {c['accent']};
    color: {c['text_bright']};
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: bold;
}}
QPushButton#SendBtn:hover {{ background-color: {c['accent_hover']}; }}
QPushButton#IgnoreBtn {{
    background-color: transparent;
    color: {c['text_dim']};
    border: 1px solid {c['border_input']};
    border-radius: 8px;
    padding: 8px 16px;
}}
QPushButton#IgnoreBtn:hover {{ color: {c['notif_text']}; border-color: {c['accent']}; }}

/* ── IngestDialog ───────────────────────────────────────────────────── */
QDialog {{
    background-color: {c['bg_dialog']};
    color: {c['text_primary']};
}}
QLabel#Title {{
    color: {c['thinking']};
    font-size: {fc.lg}px;
    font-weight: bold;
    padding-bottom: 8px;
}}
QLabel#StatusLabel {{
    color: {c['text_dim']};
    font-size: {fc.sm}px;
    font-style: italic;
}}
QLabel#SummaryLabel {{
    color: {c['thinking']};
    font-size: {fc.sm}px;
}}

/* ── QTableWidget ──────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {c['bg_window']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    font-size: {fc.sm}px;
    gridline-color: {c['border']};
    alternate-background-color: {c['bg_elevated']};
}}
QTableWidget::item {{
    padding: 8px 12px;
    border: none;
}}
QTableWidget::item:hover {{
    background-color: {c['item_hover']};
}}
QTableWidget::item:selected {{
    background-color: {c['item_select']};
    color: {c['text_bright']};
}}
QHeaderView::section {{
    background-color: {c['bg_window']};
    color: {c['text_title']};
    font-size: {fc.xs}px;
    font-weight: bold;
    padding: 8px 12px;
    border: none;
    border-bottom: 2px solid {c['border']};
}}

/* ── StartupDialog ──────────────────────────────────────────────────── */
QLabel#PageTitle {{
    font-size: 22px;
    font-weight: bold;
    color: {c['text_bright']};
    padding-bottom: 4px;
}}
QLabel#PageSubtitle {{
    font-size: {fc.size}px;
    color: {c['text_dim']};
    padding-bottom: 16px;
}}
QLabel#SectionLabel {{
    font-size: {fc.xs}px;
    font-weight: bold;
    color: {c['text_title']};
    letter-spacing: 1px;
    padding-bottom: 4px;
}}
QPushButton#CreateBtn {{
    background-color: transparent;
    color: {c['accent']};
    border: none;
    font-size: {fc.sm}px;
    padding: 4px 0px;
    text-align: left;
}}
QPushButton#CreateBtn:hover {{
    color: {c['accent_hover']};
}}
QPushButton#DeleteBtn {{
    background-color: transparent;
    color: {c['danger_text']};
    border: 1px solid {c['danger_border']};
    border-radius: 8px;
    font-size: {fc.sm}px;
    padding: 8px 16px;
}}
QPushButton#DeleteBtn:hover {{
    background-color: {c['danger_hover']};
    border-color: {c['danger_text']};
}}
QPushButton#DeleteBtn:disabled {{
    color: {c['text_muted']};
    border-color: {c['border']};
}}

/* ── StatsPanel ─────────────────────────────────────────────────────── */
QWidget#StatsPanelRoot {{
    background-color: {c['bg_window']};
}}
QWidget#DropZone {{
    background-color: {c['bg_window']};
    border: 1px dashed {c['border_input']};
    border-radius: 6px;
}}
QWidget#DropZone[drag_over="true"] {{
    border-color: #e0a020;
    background-color: {c['item_hover']};
}}
QLabel#DropLabel {{
    color: {c['text_dim']};
    font-size: {fc.xs}px;
}}
QLabel#SectionHeader {{
    color: {c['text_dim']};
    font-size: {fc.xs}px;
    font-weight: bold;
    letter-spacing: 1px;
    padding: 4px 8px 2px 8px;
    border-bottom: 1px solid {c['border']};
}}
QListWidget#StatsList {{
    background: transparent;
    border: none;
    outline: none;
    font-size: {fc.sm}px;
}}
QListWidget#StatsList::item {{
    padding: 5px 8px;
    border-bottom: 1px solid {c['border']};
    color: {c['text_primary']};
}}
QListWidget#StatsList::item:selected {{
    background-color: {c['item_select']};
    color: {c['text_bright']};
}}
QListWidget#StatsList::item:hover:!selected {{
    background-color: {c['item_hover']};
}}
QPushButton#BtnRefresh, QPushButton#BtnBrowse {{
    background: transparent;
    color: {c['text_dim']};
    border: 1px solid {c['border']};
    border-radius: 3px;
    padding: 3px 10px;
    font-size: {fc.xs}px;
}}
QPushButton#BtnRefresh:hover, QPushButton#BtnBrowse:hover {{
    color: {c['text_primary']};
    border-color: {c['border_input']};
}}
QPushButton#BtnDelete {{
    background: transparent;
    color: {c['danger_text']};
    border: 1px solid {c['border']};
    border-radius: 3px;
    padding: 3px 8px;
    font-size: {fc.xs}px;
}}
QPushButton#BtnDelete:hover {{ border-color: {c['danger_text']}; }}
QPushButton#BtnDelete:disabled {{
    color: {c['text_muted']};
    border-color: {c['border']};
}}
QCheckBox#StatSource {{
    color: {c['text_dim']};
    font-size: {fc.xs}px;
    spacing: 6px;
}}
QCheckBox#StatSource::indicator {{
    width: 13px;
    height: 13px;
    border: 1px solid {c['border_input']};
    border-radius: 2px;
    background: {c['bg_input']};
}}
QCheckBox#StatSource::indicator:checked {{
    background: #e0a020;
    border-color: #e0a020;
}}
QCheckBox#StatSource:hover {{ color: {c['text_primary']}; }}
QLabel#EmptyHint {{
    color: {c['text_muted']};
    font-size: {fc.xs}px;
    font-style: italic;
    padding: 4px 8px;
}}
"""
