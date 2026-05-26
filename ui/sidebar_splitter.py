"""
sidebar_splitter.py -- QSplitter horizontal avec zone de drag elargie.
"""

from PyQt6.QtWidgets import QSplitter, QSplitterHandle
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPainter, QColor

_HANDLE_W = 7    # largeur totale de la zone draggable (px)

# Couleurs de bordure alignees sur themes.py (cle "border")
_BORDER_DARK  = QColor("#3e3e42")
_BORDER_LIGHT = QColor("#d4d4d4")


class _BorderHandle(QSplitterHandle):
    """Handle elargi : zone draggable de 18px, fond aligne sur le theme."""

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setCursor(Qt.CursorShape.SplitHCursor)

    def sizeHint(self) -> QSize:
        # Force la largeur du handle, peu importe le QSS du theme global
        base = super().sizeHint()
        return QSize(_HANDLE_W, base.height())

    def paintEvent(self, event):
        p = QPainter(self)
        bg = self.palette().color(self.backgroundRole())
        is_dark = bg.lightness() < 128
        sep = _BORDER_DARK if is_dark else _BORDER_LIGHT
        p.fillRect(self.rect(), bg)
        cx = self.width() // 2
        p.fillRect(cx, 0, 1, self.height(), sep)
        p.end()


class SidebarSplitter(QSplitter):
    """QSplitter horizontal avec handles elargis pour faciliter le drag."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setHandleWidth(_HANDLE_W)
        # QSS local — force la largeur face au theme global qui ne cible
        # que QSplitter::handle:vertical
        self.setStyleSheet(
            f"QSplitter::handle:horizontal {{"
            f"  width: {_HANDLE_W}px;"
            f"  min-width: {_HANDLE_W}px;"
            f"  max-width: {_HANDLE_W}px;"
            f"  background-color: transparent;"
            f"  margin: 0px;"
            f"}}"
        )

    def createHandle(self) -> _BorderHandle:
        return _BorderHandle(self.orientation(), self)
