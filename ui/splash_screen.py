from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QColor
import os

class EugeniaSplashScreen(QDialog):
    def __init__(self, theme: str = "dark"):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.SplashScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Main container to handle background
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # The user wants the splash screen to always be the dark premium version
        bg_color = "#1e1e1e"
        container.setStyleSheet(f"background-color: {bg_color}; border-radius: 8px;")
        
        # Logo
        self.logo_label = QLabel()
        logo_path = "assets/logo.png"
        if not os.path.exists(logo_path):
            pass # fallback
            
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setContentsMargins(40, 40, 40, 40)
        
        container_layout.addWidget(self.logo_label)
        
        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        progress_color = "#0e639c"
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: transparent;
            }}
            QProgressBar::chunk {{
                background-color: {progress_color};
                border-radius: 2px;
            }}
        """)
        container_layout.addWidget(self.progress)
        
        # Status Label
        self.status_label = QLabel("")
        text_color = "#cccccc"
        self.status_label.setStyleSheet(f"color: {text_color}; font-size: 13px; font-family: 'Segoe UI', sans-serif;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setContentsMargins(0, 4, 0, 10)
        self.status_label.hide() # Caché par défaut
        container_layout.addWidget(self.status_label)
        
        layout.addWidget(container)

    def set_message(self, text: str):
        self.status_label.setText(text)
        self.status_label.show()
