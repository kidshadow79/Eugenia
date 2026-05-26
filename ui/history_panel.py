"""
HistoryPanel -- Panneau Historique (page du ContextPanel)

Affiche la liste des conversations passees et permet :
- de les consulter (ouvre un dialog de lecture seule)
- de les supprimer

Signaux publics :
  session_load_requested(session_id: str)  -- emit quand l'utilisateur veut recharger
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QDialog, QTextEdit, QDialogButtonBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.conversation_store import ConversationStore
from ui.font_config import FontConfig

logger = logging.getLogger(__name__)


def _build_history_style(fc: FontConfig) -> str:
    return f"""
QListWidget {{ font-size: {fc.sm}px; }}
QPushButton#HistBtn {{ font-size: {fc.sm}px; }}
QPushButton#HistBtnDanger {{ font-size: {fc.sm}px; }}
QPushButton#HistBtnNew {{ font-size: {fc.sm}px; }}
"""


class HistoryPanel(QWidget):

    resume_requested = pyqtSignal(str)   # session_id -> MainWindow reprend la conv
    new_requested    = pyqtSignal()      # -> MainWindow démarre une nouvelle session
    scan_requested   = pyqtSignal()      # -> Index FAISS manquant
    session_deleted  = pyqtSignal(str)   # session_id -> Nettoyer FAISS et résumés

    def __init__(self):
        super().__init__()
        self.setObjectName("HistoryPanel")
        self.setStyleSheet(_build_history_style(FontConfig.instance()))
        self._store: ConversationStore | None = None
        self._setup_ui()

    def apply_font_config(self, fc: FontConfig) -> None:
        self.setStyleSheet(_build_history_style(fc))

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def set_store(self, store: ConversationStore) -> None:
        """Branche le store. Appele par MainWindow apres creation de la session."""
        self._store = store
        self._refresh()

    def set_new_enabled(self, enabled: bool) -> None:
        """Active/désactive le bouton Nouvelle (ex: désactivé si conv vide)."""
        self._new_btn.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(4)

        # Bouton Nouvelle conversation (en haut)
        new_row = QHBoxLayout()
        new_row.setContentsMargins(8, 0, 8, 4)
        self._new_btn = QPushButton("＋  Nouvelle conversation")
        self._new_btn.setObjectName("HistBtnNew")
        self._new_btn.setToolTip("Sauvegarder la conversation en cours et en démarrer une nouvelle")
        self._new_btn.clicked.connect(self._on_new)
        new_row.addWidget(self._new_btn)
        layout.addLayout(new_row)

        # Label vide
        self._empty_label = QLabel("Aucune conversation enregistree.")
        self._empty_label.setObjectName("EmptyLabel")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        # Liste
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_view)
        layout.addWidget(self._list)

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setContentsMargins(8, 4, 8, 8)

        self._view_btn = QPushButton("Voir")
        self._view_btn.setObjectName("HistBtn")
        self._view_btn.setEnabled(False)
        self._view_btn.clicked.connect(self._on_view)

        self._resume_btn = QPushButton("↩ Reprendre")
        self._resume_btn.setObjectName("HistBtn")
        self._resume_btn.setEnabled(False)
        self._resume_btn.setToolTip("Recharge cette conversation et continue à partir d'où elle s'est arrêtée")
        self._resume_btn.clicked.connect(self._on_resume)

        self._del_btn = QPushButton("Supprimer")
        self._del_btn.setObjectName("HistBtnDanger")
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._on_delete)

        self._scan_btn = QPushButton("🔍 Indexer")
        self._scan_btn.setObjectName("HistBtn")
        self._scan_btn.setToolTip("Scanner et indexer les anciennes conversations manquantes dans la base sémantique (FAISS).")
        self._scan_btn.clicked.connect(self.scan_requested.emit)

        self._rename_btn = QPushButton("Renommer")
        self._rename_btn.setObjectName("HistBtn")
        self._rename_btn.setEnabled(False)
        self._rename_btn.clicked.connect(self._on_rename)

        btn_row.addWidget(self._view_btn)
        btn_row.addWidget(self._resume_btn)
        btn_row.addWidget(self._scan_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._rename_btn)
        btn_row.addWidget(self._del_btn)
        layout.addLayout(btn_row)

        self._list.currentItemChanged.connect(self._on_selection_changed)

    # ------------------------------------------------------------------
    # Rafraichissement
    # ------------------------------------------------------------------

    def _refresh(self):
        self._list.clear()
        if self._store is None:
            return
        sessions = self._store.list_sessions()
        self._empty_label.setVisible(len(sessions) == 0)
        self._list.setVisible(len(sessions) > 0)
        for s in sessions:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, s.get("title", ""))
            
            title = s.get("title", "")
            if title:
                item.setText(f"{title} ({s['ts']})\n{s['preview']}")
            else:
                item.setText(f"{s['ts']}\n{s['preview']}")
                
            self._list.addItem(item)

    def refresh(self) -> None:
        """Appele par MainWindow apres chaque message enregistre."""
        self._refresh()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_selection_changed(self, current, _previous):
        has = current is not None
        self._view_btn.setEnabled(has)
        self._resume_btn.setEnabled(has)
        self._del_btn.setEnabled(has)
        self._rename_btn.setEnabled(has)

    def _current_session_id(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_view(self, *_):
        sid = self._current_session_id()
        if sid is None or self._store is None:
            return
        try:
            messages = self._store.load_session(sid)
        except FileNotFoundError as exc:
            logger.error("HistoryPanel._on_view — %s", exc)
            return
        _ViewDialog(sid, messages, parent=self).exec()

    def _on_new(self):
        reply = QMessageBox.question(
            self,
            "Nouvelle conversation",
            "Démarrer une nouvelle conversation ?\n\n"
            "La conversation en cours sera sauvegardée dans l'historique.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.new_requested.emit()

    def _on_resume(self):
        sid = self._current_session_id()
        if sid is None:
            return
        reply = QMessageBox.question(
            self,
            "Reprendre la conversation",
            f"Reprendre la conversation du {sid} ?\n\n"
            "La conversation en cours sera sauvegardée et l'historique "
            "de la session sélectionnée sera rechargé.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.resume_requested.emit(sid)

    def _on_rename(self):
        import logging
        try:
            from PyQt6.QtWidgets import QInputDialog
            item = self._list.currentItem()
            if not item or not self._store:
                logging.error("[HISTORY] _on_rename : item or store is None")
                return
            session_id = item.data(Qt.ItemDataRole.UserRole)
            current_title = item.data(Qt.ItemDataRole.UserRole + 1)
            if not current_title:
                current_title = ""
                
            logging.info(f"[HISTORY] _on_rename session={session_id} title={current_title}")
            from PyQt6.QtWidgets import QLineEdit
            new_title, ok = QInputDialog.getText(
                self, "Renommer la conversation", 
                "Nouveau titre (vide pour utiliser la date):",
                QLineEdit.EchoMode.Normal,
                current_title
            )
            logging.info(f"[HISTORY] _on_rename result ok={ok} new_title={new_title}")
            if ok:
                self._store.rename_session(session_id, new_title.strip())
                self._refresh()
        except Exception as e:
            logging.error(f"[HISTORY] _on_rename ERROR: {e}", exc_info=True)

    def _on_delete(self):
        sid = self._current_session_id()
        if sid is None or self._store is None:
            return
        reply = QMessageBox.warning(
            self,
            "Supprimer la conversation",
            f"Supprimer definitivement la conversation du {sid} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._store.delete_session(sid)
            self.session_deleted.emit(sid)
        except FileNotFoundError as exc:
            logger.error("HistoryPanel._on_delete — %s", exc)
        self._refresh()


# ------------------------------------------------------------------
# Dialog de lecture
# ------------------------------------------------------------------

class _ViewDialog(QDialog):
    def __init__(self, session_id: str, messages: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Conversation — {session_id}")
        self.setMinimumSize(560, 480)

        layout = QVBoxLayout(self)

        viewer = QTextEdit()
        viewer.setReadOnly(True)
        viewer.setObjectName("ChatHistory")
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            ts = msg.get("ts", "")
            if role == "user":
                viewer.append(f'<span style="color:#4ec9b0"><b>Vous</b></span> <span style="color:#555;font-size:11px">{ts}</span>')
            else:
                viewer.append(f'<span style="color:#ce9178"><b>EUGENIA</b></span> <span style="color:#555;font-size:11px">{ts}</span>')
            viewer.append(f'<p style="margin:2px 0 10px 0">{content}</p>')
        layout.addWidget(viewer)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
