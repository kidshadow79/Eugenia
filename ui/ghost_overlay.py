"""
ghost_overlay.py — Calque transparent Ghost Writer

Fenêtre PyQt6 sans bordure, transparente, posée par-dessus la zone éditeur tiers
(colonne 3 d'EUGENIA). Affiche les badges d'annotation ancrés sur le texte scanné.

Cycle de vie :
  - Invisible tant qu'aucune app tierce n'est attachée.
  - Activé via attach(editor_zone) quand l'éditeur est attaché.
  - Désactivé via detach() quand l'éditeur est détaché.
  - Se repositionne automatiquement quand EditorZone est redimensionné.

Badges :
  - Un badge = un petit label dans la marge droite, sur fond semi-transparent.
  - Tooltip complet au survol.
  - Croix de suppression au clic droit.

Usage depuis MainWindow :
    self._ghost = GhostOverlay(parent=self)
    self.editor_zone.editor_attached.connect(lambda: self._ghost.attach(self.editor_zone))
    self.editor_zone.editor_detached.connect(self._ghost.detach)
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QTextEdit, QFrame,
)
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QCursor, QBrush, QFont, QKeySequence, QShortcut

logger = logging.getLogger(__name__)

# ─── Constantes visuelles ──────────────────────────────────────────────────────

_BADGE_W         = 120   # largeur d'un badge (px)
_BADGE_H         = 120   # hauteur d'un badge (px)
_BADGE_MARGIN_R  = 30    # marge depuis le bord droit du calque
_BADGE_DRAG_THRESHOLD = 5  # pixels de mouvement avant que le glisser soit activé
_BADGE_BG        = QColor(40, 40, 60, 200)       # fond badge (semi-transparent)
_BADGE_BG_HOVER  = QColor(60, 60, 90, 230)       # fond au survol
_BADGE_TEXT      = QColor(220, 220, 220)          # couleur texte badge
_BADGE_RADIUS    = 4                              # arrondi des coins


# ─── Popup d'édition d'annotation ────────────────────────────────────────────

class _BadgePopup(QWidget):
    """
    Petite fenêtre flottante qui apparaît au clic sur un badge.
    Permet de modifier le texte de l'annotation ou de la supprimer.
    """

    saved   = pyqtSignal(int, str, str)   # annotation_id, new_label, new_note
    deleted = pyqtSignal(int)             # annotation_id

    def __init__(self, annotation_id: int, label: str, note: str, pos: QPoint, parent=None):
        super().__init__(parent)
        self._id = annotation_id
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setStyleSheet(
            "background: #1e1e2e; border: 1px solid #444; border-radius: 6px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Champ texte
        self._edit = QTextEdit()
        self._edit.setPlainText(note)
        self._edit.setPlaceholderText("Texte de l'annotation...")
        self._edit.setFixedHeight(80)
        self._edit.setStyleSheet(
            "QTextEdit { background: #2a2a3e; color: #ddd; border: 1px solid #555;"
            "  border-radius: 4px; padding: 4px; font-size: 12px; }"
        )
        layout.addWidget(self._edit)

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_save = QPushButton("Sauvegarder")
        self._btn_save.setStyleSheet(
            "QPushButton { background: #3a3a5c; color: #ddd; border: 1px solid #555;"
            "  border-radius: 4px; padding: 3px 10px; font-size: 12px; }"
            "QPushButton:hover { background: #4a4a7c; }"
        )
        self._btn_save.clicked.connect(self._on_save)

        self._btn_del = QPushButton("Supprimer")
        self._btn_del.setStyleSheet(
            "QPushButton { background: #5c2a2a; color: #ddd; border: 1px solid #855;"
            "  border-radius: 4px; padding: 3px 10px; font-size: 12px; }"
            "QPushButton:hover { background: #7c3a3a; }"
        )
        self._btn_del.clicked.connect(self._on_delete)

        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(self._btn_del)
        layout.addLayout(btn_row)

        self.adjustSize()
        # Positionner à gauche du badge
        self.move(pos.x() - self.width() - 6, pos.y())
        self._edit.setFocus()

        # Fermer sur Escape
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(self.close)

    def _on_save(self):
        note = self._edit.toPlainText().strip()
        if note:
            self.saved.emit(self._id, note, note)   # label = note (tronqué dans le badge)
        self.close()

    def _on_delete(self):
        self.deleted.emit(self._id)
        self.close()

    def focusOutEvent(self, event):
        # Ferme si le focus quitte le popup et ses enfants
        # (petit délai pour laisser les boutons internes recevoir le clic)
        QTimer.singleShot(150, self._check_focus)
        super().focusOutEvent(event)

    def _check_focus(self):
        if not self.isActiveWindow():
            self.close()


# ─── Widget badge individuel ───────────────────────────────────────────────────

class _Badge(QWidget):
    """
    Un badge = un petit rectangle semi-transparent positionné en absolu
    sur le calque, affichant le label court.

    Signaux :
        delete_requested(int)  → émis au clic droit, avec l'id de l'annotation
    """

    delete_requested = pyqtSignal(int)
    edit_requested   = pyqtSignal(int, str, str)   # id, label, note
    x_dragged        = pyqtSignal(int)             # delta_x appliqué au glisser

    def __init__(self, annotation_id: int, label: str, note: str, parent: QWidget):
        super().__init__(parent)
        self._id    = annotation_id
        self._label = label
        self._note  = note
        self._hovered = False
        self._drag_start_pos: QPoint | None = None  # position souris au mousePress
        self._dragging = False                       # True une fois le seuil dépassé
        self.setFixedSize(_BADGE_W, _BADGE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    # ─── Rendu ────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        overlay  = self.parentWidget()
        bg       = (
            getattr(overlay, '_badge_bg_hover_color', _BADGE_BG_HOVER)
            if self._hovered
            else getattr(overlay, '_badge_bg_color', _BADGE_BG)
        )
        text_col = getattr(overlay, '_badge_text_color', _BADGE_TEXT)

        p.setBrush(bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), _BADGE_RADIUS, _BADGE_RADIUS)

        p.setPen(text_col)
        pad = 6
        inner_w = _BADGE_W - pad * 2

        # ── Ligne 1 : label en gras (1 ligne, tronqué) ──
        f_bold = QFont(p.font())
        f_bold.setBold(True)
        p.setFont(f_bold)
        fm_b = p.fontMetrics()
        label_text = fm_b.elidedText(self._label, Qt.TextElideMode.ElideRight, inner_w)
        y_cursor = fm_b.ascent() + pad
        p.drawText(pad, y_cursor, label_text)
        y_cursor += fm_b.descent() + 4   # espace sous le titre

        # ── Lignes suivantes : note wrappée, tronquée avec "…" si débordement ──
        f_note = QFont(p.font())
        f_note.setBold(False)
        f_note.setItalic(True)
        p.setFont(f_note)
        fm_n = p.fontMetrics()
        line_h = fm_n.height()
        available_h = _BADGE_H - y_cursor - pad   # pixels restants
        max_lines = max(1, available_h // line_h)

        # Découper la note en mots et construire les lignes
        words = self._note.replace("\n", " ").split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if fm_n.horizontalAdvance(test) <= inner_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)

        # Tronquer à max_lines avec "…" sur la dernière
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            while last and fm_n.horizontalAdvance(last + "…") > inner_w:
                last = last[:-1].rstrip()
            lines[-1] = last + "…"

        for line in lines:
            p.drawText(pad, y_cursor + fm_n.ascent(), line)
            y_cursor += line_h

        p.end()

    # ─── Interactions ─────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is not None:
            delta = event.pos() - self._drag_start_pos
            if not self._dragging and abs(delta.x()) >= _BADGE_DRAG_THRESHOLD:
                self._dragging = True
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            if self._dragging:
                self.x_dragged.emit(delta.x())
                self._drag_start_pos = event.pos()  # reset pour que le delta soit incrémental
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was_dragging = self._dragging
            self._drag_start_pos = None
            self._dragging = False
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if not was_dragging:
                # Simple clic sans glisser → ouvre le popup
                self.edit_requested.emit(self._id, self._label, self._note)
        super().mouseReleaseEvent(event)

    # ─── API ──────────────────────────────────────────────────────────────────

    def update_content(self, label: str, note: str) -> None:
        self._label = label
        self._note  = note
        self.update()


# ─── Calque principal ──────────────────────────────────────────────────────────

class GhostOverlay(QWidget):
    """
    Fenêtre transparente sans bordure posée par-dessus EditorZone.

    Signaux :
        annotation_deleted(int)  → émis quand l'auteur supprime un badge (id)
    """

    annotation_deleted  = pyqtSignal(int)
    annotation_edited   = pyqtSignal(int, str, str)   # id, new_label, new_note
    scan_requested      = pyqtSignal()
    x_offset_changed    = pyqtSignal(int)             # offset X colonne badges (px)

    def __init__(self, parent: QWidget):
        # fenêtre top-level : seule solution pour s'afficher AU-DESSUS d'une
        # fenêtre Win32 d'un processus étranger (LibreOffice, Word...) embedée
        # via SetParent. Un widget Qt enfant est TOUJOURS sous ces fenêtres.
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background: transparent;")

        self._editor_zone: QWidget | None = None
        self._badges: dict[int, _Badge] = {}
        self._badge_x_offset: int = 0   # décalage horizontal global (glisser utilisateur)
        self._badge_margin_r: int = _BADGE_MARGIN_R  # marge droite configurable

        # Couleurs des badges — mises à jour via update_badge_colors() depuis MainWindow
        self._badge_bg_color       = QColor(40, 40, 60, 200)
        self._badge_bg_hover_color = QColor(60, 60, 90, 230)
        self._badge_text_color     = QColor(220, 220, 220)

        # Timer de repositionnement (anti-rafale resize/move)
        self._reposition_timer = QTimer(self)
        self._reposition_timer.setSingleShot(True)
        self._reposition_timer.setInterval(30)
        self._reposition_timer.timeout.connect(self._reposition)

        # Timer de masquage différé : évite que les dialogs internes (color picker, etc.)
        # déclenchent un hide/show inutile en passant par ApplicationInactive
        self._hide_delay_timer = QTimer(self)
        self._hide_delay_timer.setSingleShot(True)
        self._hide_delay_timer.setInterval(400)
        self._hide_delay_timer.timeout.connect(self.hide)

        self.hide()

    def set_x_offset(self, offset: int) -> None:
        """Charge l'offset X persisté depuis la session précédente."""
        self._badge_x_offset = offset
        self._reposition_badges()

    def set_margin_r(self, margin: int) -> None:
        """Définit la marge droite des badges et repositionne."""
        self._badge_margin_r = max(0, margin)
        self._reposition_badges()

    # ─── Cycle de vie ─────────────────────────────────────────────────────────

    def attach(self, editor_zone: QWidget) -> None:
        """
        Active le calque par-dessus editor_zone.
        Installé comme écouteur sur EditorZone ET sur la fenêtre principale
        pour suivre resize et déplacement.
        """
        self._editor_zone = editor_zone
        editor_zone.installEventFilter(self)
        # Suivre aussi les mouvements de la fenêtre principale
        if self.parent():
            self.parent().installEventFilter(self)
        # Masquer le calque quand l'application perd le focus
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().applicationStateChanged.connect(self._on_app_state_changed)
        self._reposition()
        self.show()
        self.raise_()
        logger.debug("GhostOverlay — activé sur EditorZone")

    def detach(self) -> None:
        """
        Désactive et cache le calque.
        """
        if self._editor_zone is not None:
            self._editor_zone.removeEventFilter(self)
            self._editor_zone = None
        if self.parent():
            self.parent().removeEventFilter(self)
        from PyQt6.QtWidgets import QApplication
        try:
            QApplication.instance().applicationStateChanged.disconnect(self._on_app_state_changed)
        except (RuntimeError, TypeError):
            pass
        self.hide()
        logger.debug("GhostOverlay — désactivé")

    def _on_app_state_changed(self, state: Qt.ApplicationState) -> None:
        """Cache le calque quand Eugenia perd le focus (autre app au premier plan).
        Un délai de 400 ms évite les faux positifs causés par les dialogs internes
        (sélecteur de couleur, QColorDialog) qui passent brièvement par Inactive.
        """
        if state == Qt.ApplicationState.ApplicationActive:
            self._hide_delay_timer.stop()   # annuler le masquage en attente
            if self._editor_zone is not None:
                self.show()
        else:
            self._hide_delay_timer.start()  # masquer seulement après 400 ms

    # ─── Repositionnement ─────────────────────────────────────────────────────

    def eventFilter(self, watched, event):
        """Intercepte Resize/Move de EditorZone et de la fenêtre principale."""
        from PyQt6.QtCore import QEvent
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._reposition_timer.start()
        return False

    def _reposition(self) -> None:
        """Aligne le calque sur EditorZone via coordonnées écran globales."""
        if self._editor_zone is None:
            return
        # Coordonnées écran : nécessaire car GhostOverlay est top-level
        top_left: QPoint = self._editor_zone.mapToGlobal(QPoint(0, 0))
        size = self._editor_zone.size()
        self.setGeometry(top_left.x(), top_left.y(), size.width(), size.height())
        self._reposition_badges()

    def _on_scan_clicked(self) -> None:
        self.scan_requested.emit()

    def scan_finished(self) -> None:
        pass  # conservé pour compatibilité appels existants

    def update_badge_colors(self, bg_hex: str, text_hex: str, opacity: float) -> None:
        """Met à jour les couleurs des badges et les repeint. Appelé par MainWindow."""
        opacity = max(0.1, min(1.0, opacity))
        bg = QColor(bg_hex)
        bg.setAlphaF(opacity)
        self._badge_bg_color = bg
        bg_h = QColor(bg_hex).lighter(130)
        bg_h.setAlphaF(min(1.0, opacity + 0.15))
        self._badge_bg_hover_color = bg_h
        self._badge_text_color = QColor(text_hex)
        for badge in self._badges.values():
            badge.update()

    # ─── Gestion des badges ───────────────────────────────────────────────────

    def place_badge(self, annotation_id: int, label: str, note: str, y: int) -> None:
        """
        Place ou met à jour un badge à la hauteur y (coordonnée relative au calque).
        Si plusieurs badges tombent au même y, ils sont décalés verticalement
        pour rester lisibles (anti-empilement).
        """
        if annotation_id in self._badges:
            self._badges[annotation_id].update_content(label, note)
            self._move_badge(self._badges[annotation_id], self._free_y(annotation_id, y))
            return

        badge = _Badge(annotation_id, label, note, parent=self)
        badge.delete_requested.connect(self._on_badge_deleted)
        badge.edit_requested.connect(self._on_badge_edit_requested)
        badge.x_dragged.connect(self._on_badge_x_dragged)
        self._badges[annotation_id] = badge
        self._move_badge(badge, self._free_y(annotation_id, y))
        badge.show()

    def _free_y(self, exclude_id: int, requested_y: int) -> int:
        """
        Retourne une position y libre proche de requested_y.
        Décale vers le bas par pas de (_BADGE_H + 2) si un badge existant
        occupe déjà cette plage.
        """
        step = _BADGE_H + 2
        used_ys = [
            b.y()
            for bid, b in self._badges.items()
            if bid != exclude_id
        ]
        y = requested_y
        for _ in range(20):   # max 20 décalages
            if all(abs(y - uy) >= step for uy in used_ys):
                break
            y += step
        return y

    def remove_badge(self, annotation_id: int) -> None:
        """Retire un badge du calque (sans toucher au store)."""
        badge = self._badges.pop(annotation_id, None)
        if badge is not None:
            badge.deleteLater()

    def clear_badges(self) -> None:
        """Retire tous les badges du calque (ex: avant un nouveau scan)."""
        for badge in list(self._badges.values()):
            badge.deleteLater()
        self._badges.clear()

    def shift_badges_by(self, delta_y: int) -> None:
        """
        Déplace tous les badges de delta_y pixels (scroll tracking).
        delta_y > 0 = scroll vers le haut → le texte descend → badges descendent.
        """
        for badge in self._badges.values():
            new_y = badge.y() + delta_y
            y_clamped = max(0, min(new_y, self.height() - _BADGE_H))
            badge.move(badge.x(), y_clamped)

    def _move_badge(self, badge: _Badge, y: int) -> None:
        """Positionne un badge dans la marge droite à la hauteur y."""
        x = self.width() - _BADGE_W - self._badge_margin_r + self._badge_x_offset
        # Clamp pour rester dans les limites du calque
        y_clamped = max(0, min(y, self.height() - _BADGE_H))
        badge.move(x, y_clamped)

    def _reposition_badges(self) -> None:
        """Recalcule la position x de tous les badges après resize."""
        for badge in self._badges.values():
            x = self.width() - _BADGE_W - self._badge_margin_r + self._badge_x_offset
            badge.move(x, badge.y())

    def _on_badge_x_dragged(self, delta_x: int) -> None:
        """Un badge a été glissé horizontalement — déplace toute la colonne."""
        self._badge_x_offset += delta_x
        self._reposition_badges()
        self.x_offset_changed.emit(self._badge_x_offset)

    def _on_badge_deleted(self, annotation_id: int) -> None:
        """L'auteur a cliqué Supprimer dans le popup → suppression."""
        self.remove_badge(annotation_id)
        self.annotation_deleted.emit(annotation_id)
        logger.debug("GhostOverlay — badge %d supprimé", annotation_id)

    def _on_badge_edit_requested(self, annotation_id: int, label: str, note: str) -> None:
        """L'auteur a cliqué gauche sur un badge → ouvre le popup d'édition."""
        badge = self._badges.get(annotation_id)
        if badge is None:
            return
        # Fermer tout popup existant
        existing = getattr(self, '_active_popup', None)
        if existing is not None:
            try:
                existing.close()
            except RuntimeError:
                pass
        pos = badge.mapToGlobal(QPoint(0, 0))
        popup = _BadgePopup(annotation_id, label, note, pos, parent=None)
        popup.saved.connect(self._on_popup_saved)
        popup.deleted.connect(self._on_badge_deleted)
        popup.show()
        self._active_popup = popup

    def _on_popup_saved(self, annotation_id: int, new_label: str, new_note: str) -> None:
        """L'auteur a sauvegardé une édition → met à jour le badge et émet le signal."""
        badge = self._badges.get(annotation_id)
        if badge is not None:
            badge.update_content(new_label, new_note)
        self.annotation_edited.emit(annotation_id, new_label, new_note)
        logger.debug("GhostOverlay — badge %d édité", annotation_id)

    # ─── Rendu du calque ──────────────────────────────────────────────────────

    def paintEvent(self, event):
        """
        Sur Windows, Qt remplit le fond avant d'appeler paintEvent même avec
        WA_NoSystemBackground. On efface explicitement avec CompositionMode_Clear
        pour garantir un calque 100 % transparent.
        """
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), QBrush(Qt.GlobalColor.transparent))
        painter.end()
