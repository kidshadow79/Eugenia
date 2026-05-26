"""
StartupDialog — Écran de démarrage EUGENIA

Deux pages dans un QStackedWidget :
  Page 0 — Qui écrit ?   (sélection ou création d'auteur)
  Page 1 — Quel projet ? (sélection ou création de projet)

En cas d'acceptation, le dialog expose :
  .selected_author  → dict auteur
  .selected_project → dict projet
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QStackedWidget,
    QWidget, QFrame, QMessageBox, QCheckBox, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon
import core.session_manager as sm
from ui.title_bar import CustomTitleBar

DIALOG_STYLE = """
QDialog {
    background-color: #1e1e1e;
    color: #cccccc;
    font-family: 'Segoe UI', 'Arial', sans-serif;
}
QLabel#PageTitle {
    font-size: 22px;
    font-weight: bold;
    color: #ffffff;
    padding-bottom: 4px;
}
QLabel#PageSubtitle {
    font-size: 13px;
    color: #858585;
    padding-bottom: 16px;
}
QLabel#SectionLabel {
    font-size: 11px;
    font-weight: bold;
    color: #bbbbbb;
    letter-spacing: 1px;
    padding-bottom: 4px;
}
QListWidget {
    background-color: #252526;
    border: 1px solid #3e3e42;
    border-radius: 4px;
    color: #cccccc;
    font-size: 13px;
    padding: 4px;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 3px;
}
QListWidget::item:selected {
    background-color: #094771;
    color: #ffffff;
}
QListWidget::item:hover:!selected {
    background-color: #2a2d2e;
}
QLineEdit {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 4px;
    color: #cccccc;
    font-size: 13px;
    padding: 7px 10px;
}
QLineEdit:focus {
    border: 1px solid #0e639c;
}
QPushButton#PrimaryBtn {
    background-color: #0e639c;
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 13px;
    padding: 8px 20px;
}
QPushButton#PrimaryBtn:hover  { background-color: #1177bb; }
QPushButton#PrimaryBtn:disabled { background-color: #3e3e42; color: #666; }
QPushButton#SecondaryBtn {
    background-color: transparent;
    color: #cccccc;
    border: 1px solid #555555;
    border-radius: 4px;
    font-size: 13px;
    padding: 8px 20px;
}
QPushButton#SecondaryBtn:hover { background-color: #2a2d2e; }
QPushButton#CreateBtn {
    background-color: transparent;
    color: #0e639c;
    border: none;
    font-size: 12px;
    padding: 4px 0px;
    text-align: left;
}
QPushButton#CreateBtn:hover { color: #1177bb; }
QPushButton#DeleteBtn {
    background-color: transparent;
    color: #f48771;
    border: 1px solid #6b3a38;
    border-radius: 4px;
    font-size: 12px;
    padding: 4px 12px;
}
QPushButton#DeleteBtn:hover { background-color: #3d1f1f; }
QPushButton#DeleteBtn:disabled { color: #555555; border-color: #3e3e42; }
QFrame#Separator {
    border: none;
    border-top: 1px solid #3e3e42;
}
QCheckBox {
    color: #cccccc;
    font-size: 12px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #555555;
    border-radius: 3px;
    background-color: #3c3c3c;
}
QCheckBox::indicator:checked {
    background-color: #0e639c;
    border-color: #0e639c;
}
QCheckBox::indicator:disabled {
    background-color: #2a2a2a;
    border-color: #3e3e42;
}
QCheckBox:disabled { color: #555555; }
QLabel#CatCounter { font-size: 11px; color: #858585; }
"""


# ─────────────────────────────────────────────────────────────────────────────
# Widget interne : sélecteur de catégories Bible
# ─────────────────────────────────────────────────────────────────────────────

from PyQt6.QtCore import pyqtSignal

class _CategoryPicker(QWidget):
    validation_changed = pyqtSignal(bool)
    """
    Grille de QCheckBox pour choisir les catégories Bible d'un projet.
    Maximum MAX_CATEGORIES cases cochées simultanément.
    Les catégories DEFAULT_CATEGORIES sont pré-cochées.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.project_types import CATEGORY_CATALOG, MAX_CATEGORIES, MIN_CATEGORIES, DEFAULT_CATEGORIES
        self._max = MAX_CATEGORIES
        self._min = MIN_CATEGORIES
        self._checks: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        self._counter_label = QLabel()
        self._counter_label.setObjectName("CatCounter")
        layout.addWidget(self._counter_label)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(8)

        for idx, cat in enumerate(CATEGORY_CATALOG):
            cb = QCheckBox(cat['label'])
            cb.setChecked(cat["key"] in DEFAULT_CATEGORIES)
            cb.stateChanged.connect(self._on_state_changed)
            self._checks[cat["key"]] = cb
            row, col = divmod(idx, 3)
            grid.addWidget(cb, row, col)

        layout.addWidget(grid_widget)
        self._refresh_state()

    # ─── Logique ──────────────────────────────────────────────────────────────

    def _on_state_changed(self) -> None:
        selected = self.selected_keys()
        sender = self.sender()
        if len(selected) > self._max:
            # Annuler le dernier cochage (max dépassé)
            sender.blockSignals(True)
            sender.setChecked(False)
            sender.blockSignals(False)
        self._refresh_state()
        self.validation_changed.emit(len(self.selected_keys()) >= self._min)

    def _refresh_state(self) -> None:
        selected = self.selected_keys()
        n = len(selected)
        at_max = n >= self._max
        at_min = n <= self._min
        if at_max:
            color = "#e0c060"
        elif at_min:
            color = "#e07060"
        else:
            color = "#858585"
        self._counter_label.setText(
            f"{n}/{self._max} catégories sélectionnées (min {self._min})"
        )
        self._counter_label.setStyleSheet(f"font-size: 11px; color: {color};")
        # Désactiver les cases non cochées quand le max est atteint
        for key, cb in self._checks.items():
            if cb.isChecked():
                cb.setEnabled(True)
            else:
                cb.setEnabled(not at_max)

    # ─── API ──────────────────────────────────────────────────────────────────

    def selected_keys(self) -> list[str]:
        """Retourne la liste ordonnée des clés cochées (ordre catalogue)."""
        return [k for k, cb in self._checks.items() if cb.isChecked()]


class StartupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EUGENIA — Démarrage")
        self.setWindowIcon(QIcon("assets/logo.png"))
        self.setMinimumSize(520, 680)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self.selected_author: dict | None = None
        self.selected_project: dict | None = None

        self._stack = QStackedWidget()
        self._page0 = self._build_page_author()
        self._page1 = self._build_page_project()
        self._stack.addWidget(self._page0)  # index 0
        self._stack.addWidget(self._page1)  # index 1

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        
        self._title_bar = CustomTitleBar("EUGENIA — Démarrage")
        self._title_bar.close_requested.connect(self.reject)
        self._title_bar.minimize_requested.connect(self.showMinimized)
        self._title_bar.btn_maximize.hide() # Désactiver l'agrandissement pour le dialog de démarrage
        root.addWidget(self._title_bar)
        
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(40, 20, 40, 40)
        content_layout.addWidget(self._stack)
        
        root.addWidget(content_container)

    # ------------------------------------------------------------------ #
    # Page 0 — Auteur                                                      #
    # ------------------------------------------------------------------ #

    def _build_page_author(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("Qui écrit ?")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("Choisis ton profil ou crée-en un nouveau.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        # Liste des auteurs existants
        existing_label = QLabel("PROFILS EXISTANTS")
        existing_label.setObjectName("SectionLabel")
        layout.addWidget(existing_label)

        self._author_list = QListWidget()
        self._author_list.itemSelectionChanged.connect(self._on_author_selected)
        self._author_list.itemDoubleClicked.connect(lambda: self._go_to_projects())
        self._refresh_author_list()
        layout.addWidget(self._author_list)

        # Bouton supprimer auteur
        self._author_delete_btn = QPushButton("Supprimer ce profil")
        self._author_delete_btn.setObjectName("DeleteBtn")
        self._author_delete_btn.setEnabled(False)
        self._author_delete_btn.clicked.connect(self._delete_author)
        layout.addWidget(self._author_delete_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # Créer un nouveau profil
        sep = QFrame(); sep.setObjectName("Separator")
        layout.addWidget(sep)

        create_label = QLabel("NOUVEAU PROFIL")
        create_label.setObjectName("SectionLabel")
        layout.addWidget(create_label)

        name_row = QHBoxLayout()
        self._author_input = QLineEdit()
        self._author_input.setPlaceholderText("Ton prénom ou pseudonyme…")
        self._author_input.returnPressed.connect(self._create_author)
        name_row.addWidget(self._author_input)

        create_btn = QPushButton("Créer")
        create_btn.setObjectName("SecondaryBtn")
        create_btn.clicked.connect(self._create_author)
        name_row.addWidget(create_btn)
        layout.addLayout(name_row)

        layout.addStretch()

        # Bouton continuer
        self._author_next_btn = QPushButton("Continuer →")
        self._author_next_btn.setObjectName("PrimaryBtn")
        self._author_next_btn.setEnabled(False)
        self._author_next_btn.clicked.connect(self._go_to_projects)
        layout.addWidget(self._author_next_btn, alignment=Qt.AlignmentFlag.AlignRight)

        return page

    # ------------------------------------------------------------------ #
    # Page 1 — Projet                                                      #
    # ------------------------------------------------------------------ #

    def _build_page_project(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._project_title = QLabel("Quel projet ?")
        self._project_title.setObjectName("PageTitle")
        layout.addWidget(self._project_title)

        self._project_subtitle = QLabel("")
        self._project_subtitle.setObjectName("PageSubtitle")
        layout.addWidget(self._project_subtitle)

        existing_label = QLabel("PROJETS EXISTANTS")
        existing_label.setObjectName("SectionLabel")
        layout.addWidget(existing_label)

        self._project_list = QListWidget()
        self._project_list.itemSelectionChanged.connect(self._on_project_selected)
        self._project_list.itemDoubleClicked.connect(lambda: self._open_project())
        layout.addWidget(self._project_list)

        # Bouton supprimer projet
        self._project_delete_btn = QPushButton("Supprimer ce projet")
        self._project_delete_btn.setObjectName("DeleteBtn")
        self._project_delete_btn.setEnabled(False)
        self._project_delete_btn.clicked.connect(self._delete_project)
        layout.addWidget(self._project_delete_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # Créer un nouveau projet
        sep = QFrame(); sep.setObjectName("Separator")
        layout.addWidget(sep)

        create_label = QLabel("NOUVEAU PROJET")
        create_label.setObjectName("SectionLabel")
        layout.addWidget(create_label)

        name_row = QHBoxLayout()
        self._project_input = QLineEdit()
        self._project_input.setPlaceholderText("Titre du roman, essai, projet…")
        self._project_input.returnPressed.connect(self._create_project)
        name_row.addWidget(self._project_input)

        self._project_create_btn = QPushButton("Créer")
        self._project_create_btn.setObjectName("SecondaryBtn")
        self._project_create_btn.clicked.connect(self._create_project)
        name_row.addWidget(self._project_create_btn)
        layout.addLayout(name_row)

        # Sélecteur de catégories Bible
        cat_label = QLabel("CATÉGORIES DE LA BIBLE (min 2, max 5)")
        cat_label.setObjectName("SectionLabel")
        layout.addWidget(cat_label)

        self._category_picker = _CategoryPicker()
        self._category_picker.validation_changed.connect(
            lambda is_valid: self._project_create_btn.setEnabled(
                is_valid and bool(self._project_input.text().strip())
            )
        )
        self._project_input.textChanged.connect(
            lambda text: self._project_create_btn.setEnabled(
                bool(text.strip()) and (len(self._category_picker.selected_keys()) >= self._category_picker._min)
            )
        )
        
        layout.addWidget(self._category_picker)
        
        # Initial validation state
        self._project_create_btn.setEnabled(False)

        layout.addStretch()

        # Boutons navigation
        btn_row = QHBoxLayout()
        back_btn = QPushButton("← Retour")
        back_btn.setObjectName("SecondaryBtn")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        btn_row.addWidget(back_btn)

        btn_row.addStretch()

        self._project_open_btn = QPushButton("Ouvrir EUGENIA →")
        self._project_open_btn.setObjectName("PrimaryBtn")
        self._project_open_btn.setEnabled(False)
        self._project_open_btn.clicked.connect(self._open_project)
        btn_row.addWidget(self._project_open_btn)

        layout.addLayout(btn_row)

        return page

    # ------------------------------------------------------------------ #
    # Logique — Auteur                                                     #
    # ------------------------------------------------------------------ #

    def _refresh_author_list(self):
        self._author_list.clear()
        for author in sm.list_authors():
            item = QListWidgetItem(f"  {author['name']}")
            item.setData(Qt.ItemDataRole.UserRole, author)
            self._author_list.addItem(item)

    def _on_author_selected(self):
        selected = self._author_list.selectedItems()
        self._author_next_btn.setEnabled(bool(selected))
        self._author_delete_btn.setEnabled(bool(selected))
        if selected:
            self.selected_author = selected[0].data(Qt.ItemDataRole.UserRole)

    def _create_author(self):
        name = self._author_input.text().strip()
        if not name:
            return
        try:
            author = sm.create_author(name)
        except ValueError as e:
            QMessageBox.warning(self, "Nom déjà utilisé", str(e))
            return
        self._author_input.clear()
        self._refresh_author_list()
        # Sélectionner automatiquement le nouvel auteur
        for i in range(self._author_list.count()):
            item = self._author_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole)['uuid'] == author['uuid']:
                self._author_list.setCurrentItem(item)
                break

    def _go_to_projects(self):
        if not self.selected_author:
            return
        self._project_title.setText(f"Quel projet, {self.selected_author['name']} ?")
        self._project_subtitle.setText("Choisis un projet existant ou crée-en un nouveau.")
        self._refresh_project_list()
        self._stack.setCurrentIndex(1)

    # ------------------------------------------------------------------ #
    # Logique — Projet                                                     #
    # ------------------------------------------------------------------ #

    def _refresh_project_list(self):
        self._project_list.clear()
        if not self.selected_author:
            return
        for project in sm.list_projects(self.selected_author['uuid']):
            item = QListWidgetItem(f"  {project['name']}")
            item.setData(Qt.ItemDataRole.UserRole, project)
            self._project_list.addItem(item)

    def _on_project_selected(self):
        selected = self._project_list.selectedItems()
        self._project_open_btn.setEnabled(bool(selected))
        self._project_delete_btn.setEnabled(bool(selected))
        if selected:
            self.selected_project = selected[0].data(Qt.ItemDataRole.UserRole)

    def _create_project(self):
        name = self._project_input.text().strip()
        if not name or not self.selected_author:
            return
        categories = self._category_picker.selected_keys() or None
        try:
            project = sm.create_project(name, self.selected_author['uuid'],
                                        categories)
        except ValueError as e:
            QMessageBox.warning(self, "Nom déjà utilisé", str(e))
            return
        self._project_input.clear()
        self._refresh_project_list()
        # Sélectionner automatiquement le nouveau projet
        for i in range(self._project_list.count()):
            item = self._project_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole)['uuid'] == project['uuid']:
                self._project_list.setCurrentItem(item)
                break

    def _open_project(self):
        if not self.selected_project:
            return
        self.accept()

    # ------------------------------------------------------------------ #
    # Suppression                                                          #
    # ------------------------------------------------------------------ #

    def _delete_author(self):
        author = self.selected_author
        if not author:
            return
        reply = QMessageBox.warning(
            self,
            "Supprimer le profil",
            f"Supprimer le profil \u00ab\u00a0{author['name']}\u00a0\u00bb ?\n\n"
            "Cette action supprimera aussi TOUS ses projets, sa Bible\n"
            "et sa m\u00e9moire relationnelle.\n\nImpossible d'annuler.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        sm.delete_author(author['slug'])
        self.selected_author = None
        self._author_next_btn.setEnabled(False)
        self._author_delete_btn.setEnabled(False)
        self._refresh_author_list()

    def _delete_project(self):
        project = self.selected_project
        if not project:
            return
        reply = QMessageBox.warning(
            self,
            "Supprimer le projet",
            f"Supprimer le projet \u00ab\u00a0{project['name']}\u00a0\u00bb ?\n\n"
            "La Bible, les chunks et tous les donn\u00e9es du projet\n"
            "seront supprim\u00e9s d\u00e9finitivement.\n\nImpossible d'annuler.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        sm.delete_project(project['slug'])
        self.selected_project = None
        self._project_open_btn.setEnabled(False)
        self._project_delete_btn.setEnabled(False)
        self._refresh_project_list()
