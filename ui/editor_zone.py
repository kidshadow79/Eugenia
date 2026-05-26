"""
EditorZone -- Zone centrale pour l'editeur tiers (colonne 3)

Supporte l'embed Win32 : reparente la fenetre d'un process externe (Word,
LibreOffice Writer) dans ce widget via SetParent / MoveWindow.

Test uniquement -- comportement variable selon la version de Word.
"""

import logging
import win32gui
import win32con
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QHBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

logger = logging.getLogger(__name__)

# Classes de fenetres Win32 des editeurs connus
_KNOWN_EDITOR_CLASSES = {
    "OpusApp":              "Microsoft Word",
    "SALFRAME":             "LibreOffice Writer",
    "rctrl_renwnd32":       "Microsoft Word (ancien)",
    "Chrome_WidgetWin_1":   "Navigateur Chromium (Chrome / Edge / Brave / Opera)",
    "MozillaWindowClass":   "Firefox",
    "Notepad":              "Bloc-notes (Classique)",
    "ApplicationFrameWindow": "Application Microsoft (Photos, etc.)",
    "WinUIDesktopWin32WindowClass": "Application Windows Moderne",
    "Qt5QWindowIcon":       "Lecteur Multim\u00e9dia (VLC...)",
    "Qt6QWindowIcon":       "Lecteur Multim\u00e9dia (VLC v3+...)",
    "MediaPlayerClassicW":  "Media Player Classic",
    "CabinetWClass":        "Explorateur Windows",
}

EDITOR_ZONE_STYLE = """
QWidget#EditorZone {
    background-color: #1a1a1a;
}
QLabel#Placeholder {
    color: #3e3e42;
    font-size: 12px;
}
"""


class EditorZone(QWidget):
    # Emis apres embed/detach reussi — AIPanel met a jour son bouton
    editor_attached = pyqtSignal()
    editor_detached = pyqtSignal()
    # Emis avec le HWND apres attach (int) ou None apres detach
    hwnd_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setObjectName("EditorZone")
        self._embedded_hwnd: int | None = None
        self._original_style: int = 0
        self._original_exstyle: int = 0
        self._original_placement = None
        self._setup_ui()

    @property
    def embedded_hwnd(self) -> int | None:
        """HWND de la fenêtre actuellement embarquée, ou None."""
        return self._embedded_hwnd

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Placeholder visible quand aucun editeur n'est attache
        self._placeholder = QWidget()
        ph_layout = QVBoxLayout(self._placeholder)

        self._status_label = QLabel(
            "Aucun editeur attache\n\n"
            "Utilisez le bouton en bas du panneau EUGENIA"
        )
        self._status_label.setObjectName("Placeholder")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ph_layout.addStretch()
        ph_layout.addWidget(self._status_label)
        ph_layout.addStretch()

        root.addWidget(self._placeholder)

    # ------------------------------------------------------------------
    # Detection de l'editeur
    # ------------------------------------------------------------------

    def _find_editor_candidates(self) -> list[tuple[int, str, str]]:
        """Retourne tous les candidats (hwnd, app_name, title) visibles."""
        found: list[tuple[int, str, str]] = []

        def _cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            cls = win32gui.GetClassName(hwnd)
            if cls in _KNOWN_EDITOR_CLASSES:
                title = win32gui.GetWindowText(hwnd)
                if title:  # ignore les fenetres sans titre (fenetres filles)
                    found.append((hwnd, _KNOWN_EDITOR_CLASSES[cls], title))
            return True

        win32gui.EnumWindows(_cb, None)
        return found

    # ------------------------------------------------------------------
    # Attach / Detach
    # ------------------------------------------------------------------

    def attach_editor(self):
        """Cherche un editeur ouvert et l'embarque dans ce widget."""
        candidates = self._find_editor_candidates()

        if not candidates:
            self._status_label.setText(
                "Aucun editeur detecte.\n\n"
                "Ouvrez Word, LibreOffice Writer, Chrome, Firefox…\n"
                "puis cliquez sur 'Attacher'."
            )
            return

        if len(candidates) == 1:
            hwnd, app_name, title = candidates[0]
            logger.info("EditorZone — 1 candidat : %s '%s' hwnd=%d", app_name, title, hwnd)
            self._embed(hwnd)
            return

        # Plusieurs candidats : dialog de selection
        hwnd = self._pick_window_dialog(candidates)
        if hwnd is not None:
            self._embed(hwnd)

    def _pick_window_dialog(self, candidates: list[tuple[int, str, str]]) -> int | None:
        """Ouvre un dialog listant les fenetres candidates groupees, retourne le hwnd choisi."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Choisir une fenetre")
        dlg.setMinimumWidth(450)
        dlg.setMinimumHeight(350)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Plusieurs fenetres detectees. Laquelle embarquer ?"))

        from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
        from collections import defaultdict

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setIndentation(15)

        # Grouper par application
        groups = defaultdict(list)
        for hwnd, app_name, title in candidates:
            groups[app_name].append((hwnd, title))

        for app_name, windows in groups.items():
            if len(windows) == 1:
                # 1 seule fenetre pour cette app -> racine
                hwnd, title = windows[0]
                item = QTreeWidgetItem([f"{app_name}  \u2014  {title}"])
                item.setData(0, Qt.ItemDataRole.UserRole, hwnd)
                tree.addTopLevelItem(item)
            else:
                # Plusieurs fenetres -> dossier deroulant
                parent = QTreeWidgetItem([f"{app_name} ({len(windows)} fenetres)"])
                parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                for hwnd, title in windows:
                    child = QTreeWidgetItem([title])
                    child.setData(0, Qt.ItemDataRole.UserRole, hwnd)
                    parent.addChild(child)
                tree.addTopLevelItem(parent)
                parent.setExpanded(False)

        layout.addWidget(tree)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        
        ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setEnabled(False)

        def _on_selection_changed():
            selected = tree.selectedItems()
            if selected and selected[0].data(0, Qt.ItemDataRole.UserRole) is not None:
                ok_btn.setEnabled(True)
            else:
                ok_btn.setEnabled(False)
                
        tree.itemSelectionChanged.connect(_on_selection_changed)
        
        def _on_double_click(item, column):
            if item.data(0, Qt.ItemDataRole.UserRole) is not None:
                dlg.accept()
                
        tree.itemDoubleClicked.connect(_on_double_click)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
            
        selected = tree.selectedItems()
        if not selected:
            return None
        return selected[0].data(0, Qt.ItemDataRole.UserRole)

    def _embed(self, hwnd: int):
        """Reparente hwnd dans ce widget via createWindowContainer."""
        try:
            # Sauvegarde de l'etat exact de la fenetre (taille, position, plein ecran)
            self._original_placement = win32gui.GetWindowPlacement(hwnd)
            
            # Sauvegarde des styles originaux pour restauration
            self._original_style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            self._original_exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)

            # Retire la barre de titre, les bordures
            new_style = (
                self._original_style
                & ~win32con.WS_CAPTION
                & ~win32con.WS_THICKFRAME
                & ~win32con.WS_BORDER
                & ~win32con.WS_DLGFRAME
                & ~win32con.WS_SYSMENU
                & ~win32con.WS_MINIMIZEBOX
                & ~win32con.WS_MAXIMIZEBOX
            )
            # Ne pas forcer manuellement WS_CHILD, on laisse Qt gerer
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
            
            # Utilisation du conteneur natif Qt
            from PyQt6.QtGui import QWindow
            self._embedded_qwindow = QWindow.fromWinId(hwnd)
            
            # On autorise la fenetre a capter le clavier
            self._embedded_widget = QWidget.createWindowContainer(self._embedded_qwindow, self)
            self._embedded_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            
            # Ajout du container par dessus le placeholder
            self.layout().addWidget(self._embedded_widget)

            # Force le recalcul du frame win32
            win32gui.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
            )
            
            self._embedded_hwnd = hwnd
            self._placeholder.setVisible(False)

            # Demarrage du scanner de clic souris pour le focus clavier dynamique
            if not hasattr(self, '_click_timer'):
                self._click_timer = QTimer(self)
                self._click_timer.timeout.connect(self._check_mouse_clicks)
            self._click_timer.start(50)

            # On donne le focus immediatement apres l'embed
            QTimer.singleShot(100, self._give_focus_to_browser)

            self.editor_attached.emit()
            self.hwnd_changed.emit(hwnd)
            logger.info("EditorZone._embed — hwnd=%d embarque via createWindowContainer", hwnd)

        except Exception as exc:
            logger.error("EditorZone._embed — echec : %s", exc)
            self._status_label.setText(f"Echec de l'embed :\n{exc}")

    def detach_editor(self):
        """Restaure la fenetre embarquee comme fenetre independante."""
        if self._embedded_hwnd is None:
            return

        if hasattr(self, '_click_timer'):
            self._click_timer.stop()

        hwnd = self._embedded_hwnd
        try:
            # 1. Retirer du layout Qt et detruire le container proprement
            if hasattr(self, '_embedded_widget'):
                self.layout().removeWidget(self._embedded_widget)
                self._embedded_widget.setParent(None)
                self._embedded_widget.deleteLater()
                del self._embedded_widget
                
            if hasattr(self, '_embedded_qwindow'):
                self._embedded_qwindow.setParent(None)
                del self._embedded_qwindow

            # 3. Restaurer le parent natif a 0 (Bureau) et les styles
            win32gui.SetParent(hwnd, 0)
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, self._original_style)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, self._original_exstyle)
            
            # 4. Restaurer la taille, position et etat exacts
            if self._original_placement:
                win32gui.SetWindowPlacement(hwnd, self._original_placement)
                self._original_placement = None
            else:
                win32gui.SetWindowPos(
                    hwnd, 0, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                    | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
                )
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWDEFAULT)

            self._embedded_hwnd = None
            self._placeholder.setVisible(True)
            self._status_label.setText(
                "Editeur detache.\n\n"
                "Utilisez le bouton en bas du panneau EUGENIA pour recapturer."
            )
            self.editor_detached.emit()
            self.hwnd_changed.emit(None)
            logger.info("EditorZone._detach_editor — hwnd=%d detache", hwnd)

        except Exception as exc:
            logger.error("EditorZone._detach_editor — echec : %s", exc)

    # ------------------------------------------------------------------
    # Fermeture propre
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """Detache l'editeur avant la destruction du widget pour eviter la fenetre orpheline."""
        if self._embedded_hwnd is not None:
            self.detach_editor()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Focus Clavier pour les navigateurs Multi-Processus
    # ------------------------------------------------------------------

    def _check_mouse_clicks(self):
        """Scrute les clics de souris pour forcer le focus sur le navigateur embarque."""
        if not self._embedded_hwnd or not self.window().isActiveWindow():
            return
            
        import win32api
        lbtn = (win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000) != 0
        rbtn = (win32api.GetAsyncKeyState(win32con.VK_RBUTTON) & 0x8000) != 0
        
        if lbtn or rbtn:
            try:
                x, y = win32gui.GetCursorPos()
                tl = self.mapToGlobal(self.rect().topLeft())
                br = self.mapToGlobal(self.rect().bottomRight())
                
                # Si le clic a lieu dans la zone d'edition
                if tl.x() <= x <= br.x() and tl.y() <= y <= br.y():
                    self._give_focus_to_browser()
            except Exception:
                pass

    def _give_focus_to_browser(self):
        """Hacking win32 pour forcer le focus clavier sur le vrai HWND de rendu de Chrome/Firefox."""
        if not self._embedded_hwnd:
            return
            
        try:
            # 1. Simuler l'activation pour tromper les toolkits externes (Chrome Aura)
            win32gui.SendMessage(self._embedded_hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
            
            # 2. Chercher la vraie zone de texte (le sous-composant de rendu)
            target_hwnd = self._embedded_hwnd
            def cb(child, _):
                nonlocal target_hwnd
                cls = win32gui.GetClassName(child)
                if cls in ("Chrome_RenderWidgetHostHWND", "MozillaWindowClass", "SALFRAME", "_WwG", "OpusApp"):
                    target_hwnd = child
                    return False
                return True
                
            try:
                win32gui.EnumChildWindows(self._embedded_hwnd, cb, None)
            except Exception:
                pass
                
            # 3. Voler le focus au niveau OS (Attachement thread eclair)
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            
            current_thread = kernel32.GetCurrentThreadId()
            target_thread = user32.GetWindowThreadProcessId(target_hwnd, None)
            
            attached = False
            if target_thread and target_thread != current_thread:
                attached = user32.AttachThreadInput(current_thread, target_thread, True)
                
            win32gui.SetFocus(target_hwnd)
            
            # On detache immediatement pour eviter le blocage / lags du navigateur
            if attached:
                user32.AttachThreadInput(current_thread, target_thread, False)
                
        except Exception as e:
            logger.warning("EditorZone._give_focus_to_browser — echec du focus : %s", e)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._give_focus_to_browser()
