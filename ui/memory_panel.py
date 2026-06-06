"""
memory_panel.py — Panneau de visualisation de la memoire relationnelle

Deux onglets :
    Notes       : style, habitudes, preferences, contexte, objectifs
    Entites     : personnes, lieux, evenements reels

Chaque entree = une carte avec boutons Modifier et Supprimer.
Un bouton "Actualiser" recharge depuis la base SQLite.

Connexion externe :
    panel.set_db(relational_db)     -> charge et affiche les donnees
    panel.refresh()                 -> recharge depuis la base
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QTabWidget, QInputDialog, QMessageBox,
    QSizePolicy, QListWidget, QListWidgetItem, QAbstractItemView, QCheckBox, QSpinBox, QFormLayout, QDialog, QDialogButtonBox, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
import qtawesome as qta

from core.relational_db import RelationalDB
from core.i18n import tr

logger = logging.getLogger(__name__)

# Labels lisibles
_CATEGORY_LABELS = {
    "style":       "Style",
    "habitudes":   "Habitudes",
    "preferences": "Preferences",
    "contexte":    "Contexte",
    "objectifs":   "Objectifs",
}
_ENTITY_LABELS = {
    "person": "Personne",
    "place":  "Lieu",
    "event":  "Evenement",
    "other":  "Autre",
}


# ─── Carte memoire individuelle ───────────────────────────────────────────────

class _MemoryCard(QFrame):
    """
    Carte representant une entree de memoire (note ou entite).
    Signaux : edit_requested(id, current_text) | delete_requested(id)
    """

    edit_requested   = pyqtSignal(int, str)
    delete_requested = pyqtSignal(int)

    def __init__(self, entry_id: int, badge: str, content: str, parent=None):
        super().__init__(parent)
        self._id = entry_id
        self.setObjectName("MemoryCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._setup_ui(badge, content)

    def _setup_ui(self, badge: str, content: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        badge_lbl = QLabel(badge)
        badge_lbl.setObjectName("MemoryBadge")
        badge_lbl.setFixedWidth(80)
        badge_lbl.setWordWrap(True)
        layout.addWidget(badge_lbl)

        self._content_lbl = QLabel(content)
        self._content_lbl.setObjectName("MemoryContent")
        self._content_lbl.setWordWrap(True)
        self._content_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self._content_lbl)

        btn_edit = QPushButton("...")
        btn_edit.setObjectName("MemoryEditBtn")
        btn_edit.setFixedWidth(28)
        btn_edit.setToolTip(tr("Modifier"))
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(
            self._id, self._content_lbl.text()
        ))
        layout.addWidget(btn_edit)

        btn_del = QPushButton("x")
        btn_del.setObjectName("MemoryDeleteBtn")
        btn_del.setFixedWidth(28)
        btn_del.setToolTip(tr("Supprimer"))
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self._id))
        layout.addWidget(btn_del)

    def update_content(self, text: str):
        self._content_lbl.setText(text)


# ─── Onglet generique ─────────────────────────────────────────────────────────

class _MemoryTab(QWidget):
    """Onglet scrollable contenant une liste de cartes memoire categorisees."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db: RelationalDB | None = None
        self._category_items = {}
        self._category_expanded = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        scroll.setWidget(self._container)
        outer.addWidget(scroll)

        self._empty_lbl = QLabel(tr("Aucune entrée."))
        self._empty_lbl.setObjectName("MemoryEmpty")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._empty_lbl)

    def set_db(self, db: RelationalDB):
        self._db = db

    def _clear_cards(self):
        self._category_items.clear()
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_empty(self, empty: bool):
        self._empty_lbl.setVisible(empty)
        self._container.setVisible(not empty)

    def _toggle_category(self, cat_name: str) -> None:
        is_expanded = self._category_expanded.get(cat_name, True)
        self._category_expanded[cat_name] = not is_expanded
        
        for item in self._category_items.get(cat_name, []):
            item.setHidden(is_expanded)

    def _add_category_header(self, cat_name: str):
        if cat_name not in self._category_expanded:
            self._category_expanded[cat_name] = True
            
        self._category_items[cat_name] = []
        
        cat_widget = QPushButton(f"  {tr(cat_name).upper()}")
        cat_widget.setStyleSheet("QPushButton { background-color: #2b2b2b; color: #00d2ff; padding: 8px; font-weight: bold; border-radius: 4px; text-align: left; border: none; margin-top: 8px; } QPushButton:hover { background-color: #3b3b3b; }")
        cat_widget.setMinimumHeight(40)
        cat_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        cat_widget.clicked.connect(lambda checked=False, c=cat_name: self._toggle_category(c))
        
        self._list_layout.insertWidget(self._list_layout.count() - 1, cat_widget)

    def _add_card(self, entry_id: int, type_flag: str, badge: str, content: str, category: str = None):
        card = _MemoryCard(entry_id, badge, content)
        card.edit_requested.connect(lambda eid, text: self._on_edit(eid, type_flag, text))
        card.delete_requested.connect(lambda eid: self._on_delete(eid, type_flag))
        
        self._list_layout.insertWidget(self._list_layout.count() - 1, card)
        
        if category is not None:
            if category in self._category_items:
                self._category_items[category].append(card)
                # Apply current visibility state
                is_expanded = self._category_expanded.get(category, True)
                card.setHidden(not is_expanded)

    def _on_edit(self, entry_id: int, current_text: str):
        raise NotImplementedError

    def _on_delete(self, entry_id: int):
        raise NotImplementedError


# ─── Onglet Notes ─────────────────────────────────────────────────────────────

class _RelationalTab(_MemoryTab):

    def refresh(self):
        self._clear_cards()
        if self._db is None:
            self._show_empty(True)
            return
            
        notes = self._db.get_all_notes()
        entities = self._db.get_all_entities()
        
        if not notes and not entities:
            self._show_empty(True)
            return
            
        self._show_empty(False)
        
        # Group notes by category
        grouped = {}
        for n in notes:
            cat = n["category"]
            if cat not in grouped: grouped[cat] = []
            grouped[cat].append(n)
            
        for cat, group_notes in grouped.items():
            badge = tr(_CATEGORY_LABELS.get(cat, cat.capitalize()))
            self._add_category_header(badge)
            for n in group_notes:
                self._add_card(n["id"], "note", badge, n["content"], category=badge)
                
        # Group entities by type
        grouped_entities = {}
        for e in entities:
            etype = e["entity_type"]
            if etype not in grouped_entities: grouped_entities[etype] = []
            grouped_entities[etype].append(e)
            
        for etype, group_entities in grouped_entities.items():
            badge = tr(_ENTITY_LABELS.get(etype, etype.capitalize()))
            self._add_category_header(badge)
            for e in group_entities:
                content = f"<b>{e['label']}</b> : {e['content']}"
                self._add_card(e["id"], "entity", badge, content, category=badge)

    def _on_edit(self, entry_id: int, type_flag: str, current_text: str):
        if self._db is None: return
        new_text, ok = QInputDialog.getMultiLineText(
            self, tr("Modifier la mémoire"), tr("Contenu :"), current_text
        )
        if ok and new_text.strip():
            conn = self._db._get_conn()
            import hashlib
            h = hashlib.sha256(new_text.strip().lower().encode()).hexdigest()
            if type_flag == "note":
                conn.execute(
                    "UPDATE author_notes SET content=?, content_hash=?, updated_at=datetime('now') WHERE id=?",
                    (new_text.strip(), h, entry_id),
                )
            else:
                conn.execute(
                    "UPDATE author_entities SET content=?, content_hash=?, updated_at=datetime('now') WHERE id=?",
                    (new_text.strip(), h, entry_id),
                )
            conn.commit()
            self.refresh()

    def _on_delete(self, entry_id: int, type_flag: str):
        if self._db is None: return
        ans = QMessageBox.question(
            self, tr("Supprimer"), tr("Retirer cette entrée de la mémoire ?")
        )
        if ans == QMessageBox.StandardButton.Yes:
            conn = self._db._get_conn()
            if type_flag == "note":
                conn.execute("DELETE FROM author_notes WHERE id=?", (entry_id,))
            else:
                conn.execute("DELETE FROM author_entities WHERE id=?", (entry_id,))
            conn.commit()
            self.refresh()

class _EgoEditDialog(QDialog):
    def __init__(self, rule_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Modifier la règle ({})").format(tr(rule_data.get('categorie', 'Ego'))))
        self.resize(400, 300)
        
        layout = QFormLayout(self)
        
        self.texte_edit = QTextEdit(rule_data.get("texte", ""))
        layout.addRow(tr("Règle :"), self.texte_edit)
        
        self.force_spin = QSpinBox()
        self.force_spin.setRange(1, 5)
        self.force_spin.setValue(rule_data.get("force", 3))
        layout.addRow(tr("Force (1-5) :"), self.force_spin)
        
        self.actif_check = QCheckBox()
        self.actif_check.setChecked(rule_data.get("actif", True))
        layout.addRow(tr("Actif :"), self.actif_check)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)
        
    def get_data(self):
        return {
            "texte": self.texte_edit.toPlainText().strip(),
            "force": self.force_spin.value(),
            "actif": self.actif_check.isChecked()
        }

class _EgoTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ego = None
        self._category_items = {}
        self._category_expanded = {}
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_widget.setWordWrap(True)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.list_widget)

    def set_ego(self, ego):
        self._ego = ego

    def _toggle_category(self, cat_name: str) -> None:
        is_expanded = self._category_expanded.get(cat_name, True)
        self._category_expanded[cat_name] = not is_expanded
        
        for item in self._category_items.get(cat_name, []):
            item.setHidden(is_expanded)

    def refresh(self):
        self.list_widget.clear()
        if self._ego is None:
            return
            
        categories = self._ego.get_categories()
        for cat_name, rules in categories.items():
            if not rules: continue
            
            # Category Header
            self._category_items[cat_name] = []
            if cat_name not in self._category_expanded:
                self._category_expanded[cat_name] = True
                
            cat_item = QListWidgetItem(self.list_widget)
            cat_widget = QPushButton(tr("🗂 CATÉGORIE : {}").format(tr(cat_name).upper()))
            cat_widget.setStyleSheet("QPushButton { background-color: #2b2b2b; color: #00d2ff; padding: 8px; font-weight: bold; border-radius: 4px; text-align: left; border: none; } QPushButton:hover { background-color: #3b3b3b; }")
            cat_widget.setMinimumHeight(35)
            cat_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            cat_widget.clicked.connect(lambda checked=False, c=cat_name: self._toggle_category(c))
            
            cat_item.setSizeHint(cat_widget.sizeHint())
            self.list_widget.addItem(cat_item)
            self.list_widget.setItemWidget(cat_item, cat_widget)
            
            # Rules
            for i, rule in enumerate(rules):
                item = QListWidgetItem(self.list_widget)
                
                widget = QWidget()
                h_layout = QHBoxLayout(widget)
                h_layout.setContentsMargins(16, 4, 4, 4)
                h_layout.setSpacing(8)
                
                check = QCheckBox()
                check.setChecked(rule.get("actif", True))
                check.stateChanged.connect(lambda state, c=cat_name, idx=i: self._on_toggle_active(c, idx, state))
                h_layout.addWidget(check)
                
                force_lbl = QLabel(tr("[F:{}]").format(rule.get('force', 3)))
                force_lbl.setStyleSheet("color: #888;")
                h_layout.addWidget(force_lbl)
                
                lbl = QLabel(f"<b>[{tr(cat_name)}]</b> {rule.get('texte', '')}")
                lbl.setWordWrap(True)
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                if not rule.get("actif", True):
                    lbl.setStyleSheet("color: #666; text-decoration: line-through;")
                h_layout.addWidget(lbl)
                
                edit_btn = QPushButton("E")
                edit_btn.setFixedWidth(28)
                edit_btn.setToolTip(tr("Éditer la règle"))
                edit_btn.clicked.connect(lambda checked, c=cat_name, idx=i, r=rule: self._on_edit(c, idx, r))
                h_layout.addWidget(edit_btn)

                del_btn = QPushButton("x")
                del_btn.setFixedWidth(28)
                del_btn.setToolTip(tr("Supprimer la règle"))
                del_btn.clicked.connect(lambda checked, c=cat_name, idx=i: self._on_delete(c, idx))
                h_layout.addWidget(del_btn)
                
                widget.adjustSize()
                item.setSizeHint(widget.sizeHint())
                
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, widget)
                self._category_items[cat_name].append(item)
                item.setHidden(not self._category_expanded[cat_name])

    def _on_toggle_active(self, cat_name: str, index: int, state: int):
        if self._ego is None: return
        cats = self._ego.get_categories()
        if cat_name in cats and 0 <= index < len(cats[cat_name]):
            cats[cat_name][index]["actif"] = bool(state)
            self._ego.save(cats)
            self.refresh()

    def _on_edit(self, cat_name: str, index: int, rule_data: dict):
        if self._ego is None: return
        dlg = _EgoEditDialog(rule_data, self)
        if dlg.exec():
            new_data = dlg.get_data()
            if new_data["texte"]:
                cats = self._ego.get_categories()
                if cat_name in cats and 0 <= index < len(cats[cat_name]):
                    cats[cat_name][index].update(new_data)
                    self._ego.save(cats)
                    self.refresh()

    def _on_delete(self, cat_name: str, index: int):
        if self._ego is None: return
        cats = self._ego.get_categories()
        if cat_name in cats and 0 <= index < len(cats[cat_name]):
            cats[cat_name].pop(index)
            if not cats[cat_name]:
                del cats[cat_name]
            self._ego.save(cats)
            self.refresh()

# ==========================================
# Panneau principal ────────────────────────────────────────────────────────

class MemoryPanel(QWidget):
    """
    Panneau memoire relationnelle.
    Instancier, puis appeler set_db(relational_db) pour charger les donnees.
    """

    scan_requested = pyqtSignal()   # bouton Analyser → MainWindow lance le scanner

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MemoryPanel")
        self._db: RelationalDB | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Barre d'actions
        bar = QWidget()
        bar.setObjectName("MemoryBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 6, 8, 6)
        bar_layout.setSpacing(6)

        lbl = QLabel(tr("Memoire de l'auteur"))
        lbl.setObjectName("MemoryBarTitle")
        bar_layout.addWidget(lbl)
        bar_layout.addStretch()

        refresh_btn = QPushButton(tr("Actualiser"))
        refresh_btn.setObjectName("MemoryRefreshBtn")
        refresh_btn.clicked.connect(self.refresh)
        bar_layout.addWidget(refresh_btn)

        self._scan_btn = QPushButton(tr("Analyser"))
        self._scan_btn.setIcon(qta.icon("fa5s.search", color="white"))
        self._scan_btn.setObjectName("MemoryScanBtn")
        self._scan_btn.setToolTip(
            tr("Scanne toutes les conversations non encore analysées\n"
            "et extrait de nouveaux éléments pour la mémoire relationnelle")
        )
        self._scan_btn.clicked.connect(self._on_scan_clicked)
        bar_layout.addWidget(self._scan_btn)

        layout.addWidget(bar)

        # Onglets
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        layout.addWidget(self._tabs)

        self._relational_tab = _RelationalTab()
        
        self._ego_tab      = _EgoTab()

        self._tabs.addTab(self._relational_tab, tr("Relationnel"))
        
        self._tabs.addTab(self._ego_tab,      tr("Ego"))

    def set_ego(self, ego) -> None:
        self._ego_tab.set_ego(ego)
        self.refresh()

    def set_db(self, db: RelationalDB) -> None:
        """Charge la base relationnelle et affiche les donnees."""
        self._db = db
        self._relational_tab.set_db(db)
        
        self.refresh()

    def refresh(self) -> None:
        """Recharge les donnees depuis la base SQLite et Ego."""
        self._relational_tab.refresh()
        
        self._ego_tab.refresh()
        logger.debug("MemoryPanel — actualise")

    def set_scanning(self, scanning: bool) -> None:
        """Appele par MainWindow pour griser le bouton pendant un scan en cours."""
        self._scan_btn.setEnabled(not scanning)
        self._scan_btn.setText(tr("Analyse en cours…") if scanning else tr("Analyser"))

    def _on_scan_clicked(self) -> None:
        self.set_scanning(True)
        self.scan_requested.emit()
