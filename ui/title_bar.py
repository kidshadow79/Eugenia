import qtawesome as qta
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QMouseEvent, QIcon

class CustomTitleBar(QWidget):
    """Custom title bar for frameless windows."""
    
    close_requested = pyqtSignal()
    maximize_requested = pyqtSignal()
    minimize_requested = pyqtSignal()

    def __init__(self, title: str = ""):
        super().__init__()
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(32)
        
        # We need the parent window for moving/maximizing
        self._parent_window = None
        self._is_maximized = False
        
        self._start_pos = None

        self._setup_ui(title)

    def _setup_ui(self, title: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(0)

        # Title Label
        self.title_label = QLabel(title)
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #b0b0b0;")
        layout.addWidget(self.title_label)

        layout.addStretch()

        # Window Controls
        self.btn_minimize = QPushButton()
        self.btn_minimize.setIcon(qta.icon("fa5s.window-minimize", color="#b0b0b0"))
        self.btn_minimize.setFixedSize(40, 32)
        self.btn_minimize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minimize.setObjectName("TitleBarBtn")
        self.btn_minimize.clicked.connect(self.minimize_requested.emit)
        
        self.btn_maximize = QPushButton()
        self.btn_maximize.setIcon(qta.icon("fa5s.window-maximize", color="#b0b0b0"))
        self.btn_maximize.setFixedSize(40, 32)
        self.btn_maximize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_maximize.setObjectName("TitleBarBtn")
        self.btn_maximize.clicked.connect(self.maximize_requested.emit)

        self.btn_close = QPushButton()
        self.btn_close.setIcon(qta.icon("fa5s.times", color="#b0b0b0"))
        self.btn_close.setFixedSize(40, 32)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setObjectName("TitleBarCloseBtn")
        self.btn_close.clicked.connect(self.close_requested.emit)

        layout.addWidget(self.btn_minimize)
        layout.addWidget(self.btn_maximize)
        layout.addWidget(self.btn_close)

        # Style pour la barre elle-même
        self.setStyleSheet("""
            QWidget#CustomTitleBar {
                background-color: transparent;
            }
            QPushButton#TitleBarBtn, QPushButton#TitleBarCloseBtn {
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }
            QPushButton#TitleBarBtn:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton#TitleBarCloseBtn:hover {
                background-color: #e81123;
            }
        """)

    def set_title(self, title: str):
        self.title_label.setText(title)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._start_pos is not None:
            parent = self.window()
            if parent.isMaximized():
                parent.showNormal()
                # Laisser à l'OS le temps de repasser en mode normal avant de déplacer.
                # On met simplement à jour le point de départ du glissement.
                self._start_pos = event.globalPosition().toPoint()
                return
                
            delta = event.globalPosition().toPoint() - self._start_pos
            parent.move(parent.pos() + delta)
            self._start_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._start_pos = None
        
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximize_requested.emit()
