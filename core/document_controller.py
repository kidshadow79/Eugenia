"""
document_controller.py — Contrôleur universel d'application d'édition de texte

Expose quatre opérations fondamentales sur n'importe quel éditeur embarqué
(Word, LibreOffice, Chrome/Google Docs, Notepad, VSCode...) :

    read_selection()        → str   — texte sélectionné dans l'éditeur
    read_visible_text()     → str   — texte visible / accessible dans la fenêtre
    insert_at_cursor(text)          — insère après le curseur
    replace_selection(text)         — remplace la sélection courante

Stratégie d'implémentation :
    1. UIAutomationDriver (primary) : lit l'arbre d'accessibilité UIA/MSAA
       → fonctionne sur Word, LibreOffice, Chrome (Google Docs), Notepad, Edge...
    2. ClipboardDriver (fallback) : Ctrl+C pour lire, Ctrl+V pour écrire
       → universel mais sensible au focus

Le HWND de l'éditeur embarqué est fourni par EditorZone.
Sans HWND, les opérations retournent "" / lèvent DocumentControllerError.

Signaux (QObject) :
    operation_done(str)   — confirmation d'une action (pour log/UI)
    operation_failed(str) — erreur non bloquante (pour log/UI)

Usage :
    ctrl = DocumentController(parent=main_window)
    ctrl.set_hwnd(editor_zone.embedded_hwnd)
    text = ctrl.read_selection()
    ctrl.replace_selection("Nouveau texte", original=text)  # → passe par ApprovalGate
"""

import logging
import re
import time
import win32gui
import win32con
import win32api
import win32clipboard
import win32process
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class DocumentControllerError(Exception):
    """Erreur levée quand une opération ne peut pas s'exécuter."""


class DocumentController(QObject):
    """
    Contrôleur universel d'édition de texte via UI Automation + Clipboard fallback.

    Thread-safety : toutes les méthodes publiques doivent être appelées
    depuis le thread principal (interaction Win32).
    """

    operation_done   = pyqtSignal(str)   # message de confirmation
    operation_failed = pyqtSignal(str)   # message d'erreur

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hwnd: int | None = None
        self._driver: "_BaseDriver | None" = None

    # ──────────────────────────────────────────────────────────────────
    # Configuration
    # ──────────────────────────────────────────────────────────────────

    def set_hwnd(self, hwnd: int | None) -> None:
        """
        Définit la fenêtre cible.
        Appelé par EditorZone après attach_editor() ou detach_editor().
        Priorité : WordDriver (COM) > UIAutomationDriver > ClipboardDriver
        """
        self._hwnd = hwnd
        if hwnd is None:
            self._driver = None
            logger.info("DocumentController — aucun éditeur cible")
            return

        app_name = _get_window_title(hwnd)

        # 1. Word natif via COM (classe OpusApp)
        if _get_window_class(hwnd) == "OpusApp":
            try:
                driver = WordDriver(hwnd)
                if driver.is_available():
                    self._driver = driver
                    logger.info(
                        "DocumentController — driver Word COM actif pour hwnd=%d (%s)",
                        hwnd, app_name,
                    )
                    self.operation_done.emit(f"Éditeur connecté (Word COM) : {app_name}")
                    return
            except Exception as exc:
                logger.debug("DocumentController — Word COM non disponible : %s", exc)

        # 2. UI Automation (Word peut aussi passer ici, LibreOffice, Chrome...)
        try:
            driver = UIAutomationDriver(hwnd)
            if driver.is_available():
                self._driver = driver
                logger.info(
                    "DocumentController — driver UIA actif pour hwnd=%d (%s)",
                    hwnd, app_name,
                )
                self.operation_done.emit(f"Éditeur connecté (UIA) : {app_name}")
                return
        except Exception as exc:
            logger.debug("DocumentController — UIA non disponible : %s", exc)

        # 3. Clipboard fallback universel
        self._driver = ClipboardDriver(hwnd)
        logger.info(
            "DocumentController — driver Clipboard actif pour hwnd=%d (%s)",
            hwnd, app_name,
        )
        self.operation_done.emit(f"Éditeur connecté (Clipboard) : {app_name}")

    def is_connected(self) -> bool:
        """True si un éditeur est attaché et opérationnel."""
        return self._driver is not None and self._hwnd is not None

    # ──────────────────────────────────────────────────────────────────
    # Opérations publiques
    # ──────────────────────────────────────────────────────────────────

    def read_selection(self) -> str:
        """
        Retourne le texte sélectionné dans l'éditeur.
        Retourne "" si rien n'est sélectionné ou si l'éditeur n'est pas connecté.
        """
        if not self.is_connected():
            return ""
        try:
            text = self._driver.read_selection()  # type: ignore[union-attr]
            logger.debug("DocumentController.read_selection — %d chars", len(text))
            return text
        except Exception as exc:
            msg = f"Lecture sélection échouée : {exc}"
            logger.warning("DocumentController — %s", msg)
            self.operation_failed.emit(msg)
            return ""

    def read_visible_text(self) -> str:
        """
        Retourne le texte accessible dans la fenêtre de l'éditeur.
        Peut être limité selon le driver (UIA retourne le document complet,
        Clipboard retourne le contenu du presse-papier après Ctrl+A / Ctrl+C).
        """
        if not self.is_connected():
            return ""
        try:
            text = self._driver.read_visible_text()  # type: ignore[union-attr]
            logger.debug("DocumentController.read_visible_text — %d chars", len(text))
            return text
        except Exception as exc:
            msg = f"Lecture texte échouée : {exc}"
            logger.warning("DocumentController — %s", msg)
            self.operation_failed.emit(msg)
            return ""

    def insert_at_cursor(self, text: str) -> bool:
        """
        Insère text à la position du curseur dans l'éditeur.
        Retourne True si l'opération a réussi.
        """
        if not self.is_connected():
            self.operation_failed.emit("Aucun éditeur connecté.")
            return False
        try:
            self._driver.insert_at_cursor(text)  # type: ignore[union-attr]
            logger.info(
                "DocumentController.insert_at_cursor — %d chars insérés", len(text)
            )
            self.operation_done.emit(f"Texte inséré ({len(text)} caractères).")
            return True
        except Exception as exc:
            msg = f"Insertion échouée : {exc}"
            logger.error("DocumentController — %s", msg)
            self.operation_failed.emit(msg)
            return False

    def replace_selection(self, text: str) -> bool:
        """
        Remplace la sélection courante par text.
        Si rien n'est sélectionné, insère à la position du curseur.
        Retourne True si l'opération a réussi.
        """
        if not self.is_connected():
            self.operation_failed.emit("Aucun éditeur connecté.")
            return False
        try:
            self._driver.replace_selection(text)  # type: ignore[union-attr]
            logger.info(
                "DocumentController.replace_selection — %d chars écrits", len(text)
            )
            self.operation_done.emit(f"Sélection remplacée ({len(text)} caractères).")
            return True
        except Exception as exc:
            msg = f"Remplacement échoué : {exc}"
            logger.error("DocumentController — %s", msg)
            self.operation_failed.emit(msg)
            return False


# ──────────────────────────────────────────────────────────────────────────────
# Drivers internes
# ──────────────────────────────────────────────────────────────────────────────

class _BaseDriver:
    """Interface commune des drivers."""

    def is_available(self) -> bool:
        raise NotImplementedError

    def read_selection(self) -> str:
        raise NotImplementedError

    def read_visible_text(self) -> str:
        raise NotImplementedError

    def insert_at_cursor(self, text: str) -> None:
        raise NotImplementedError

    def replace_selection(self, text: str) -> None:
        raise NotImplementedError


class UIAutomationDriver(_BaseDriver):
    """
    Driver basé sur UI Automation (pywin32 / comtypes).
    Fonctionne sur : Word, LibreOffice, Chrome/Edge (Google Docs),
                     Notepad, VSCode, Firefox...

    Pour Chrome/Google Docs : activer l'accessibilité Chrome une fois :
        chrome://accessibility/ → "Enable accessibility for every page"
        Ou lancer Chrome avec --force-renderer-accessibility
    """

    def __init__(self, hwnd: int):
        import uiautomation as auto
        self._auto = auto
        self._hwnd = hwnd
        self._control = auto.ControlFromHandle(hwnd)
        # Google Docs/Chrome : canvas, UIA TextPattern ne donne pas le doc
        self._is_browser = _get_window_class(hwnd) in (
            "Chrome_WidgetWin_1", "Chrome_WidgetWin_0",
            "MozillaWindowClass", "MozillaDialogClass",
        )

    def is_available(self) -> bool:
        """True si UI Automation peut accéder à la fenêtre cible."""
        try:
            if self._control is None:
                return False
            # Vérifier qu'on peut interroger le contrôle
            _ = self._control.ControlType
            return True
        except Exception:
            return False

    def read_selection(self) -> str:
        """Lit le texte sélectionné via le pattern TextPattern UIA."""
        try:
            # Chercher un élément avec TextPattern dans la hiérarchie
            text_ctrl = self._find_text_control()
            if text_ctrl is None:
                return self._read_selection_clipboard()
            pattern = text_ctrl.GetPattern(self._auto.PatternId.TextPatternId)
            if pattern:
                selections = pattern.GetSelection()
                if selections:
                    return "".join(r.GetText(-1) for r in selections).strip()
        except Exception as exc:
            logger.debug("UIAutomationDriver.read_selection — UIA fallback : %s", exc)
        return self._read_selection_clipboard()

    def read_visible_text(self) -> str:
        """Lit le contenu texte via TextPattern ou GetWindowText."""
        # Pour Chrome/Firefox (Google Docs, etc.) : le TextPattern UIA est peu
        # fiable car Google Docs utilise un canvas. L'UIA trouve souvent la
        # barre d'adresse ou les menus du browser plutôt que le document.
        # On passe directement au fallback clipboard (Ctrl+A → Ctrl+C).
        if self._is_browser:
            text = self._read_all_clipboard()
            logger.debug(
                "UIAutomationDriver.read_visible_text [browser-clipboard] "
                "\u2014 %d chars | aperçu: %.120r",
                len(text), text[:120],
            )
            return text
        try:
            text_ctrl = self._find_text_control()
            if text_ctrl is None:
                return self._read_all_clipboard()
            pattern = text_ctrl.GetPattern(self._auto.PatternId.TextPatternId)
            if pattern:
                doc_range = pattern.DocumentRange
                if doc_range:
                    text = doc_range.GetText(-1).strip()
                    logger.debug(
                        "UIAutomationDriver.read_visible_text [UIA] "
                        "\u2014 %d chars | aperçu: %.120r",
                        len(text), text[:120],
                    )
                    return text
        except Exception as exc:
            logger.debug("UIAutomationDriver.read_visible_text — fallback : %s", exc)
        return self._read_all_clipboard()

    def insert_at_cursor(self, text: str) -> None:
        """Insère via SetValue sur l'élément texte focalisé, sinon clipboard."""
        try:
            focused = self._auto.GetFocusedControl()
            if focused:
                pattern = focused.GetPattern(self._auto.PatternId.ValuePatternId)
                if pattern:
                    current = pattern.Value or ""
                    pattern.SetValue(current + text)
                    return
        except Exception as exc:
            logger.debug("UIAutomationDriver.insert_at_cursor — fallback : %s", exc)
        self._write_via_clipboard(text, replace=False)

    def replace_selection(self, text: str) -> None:
        """Remplace la sélection via clipboard + Ctrl+V (universel)."""
        self._write_via_clipboard(text, replace=True)

    # ── Méthodes internes ─────────────────────────────────────────────

    def _find_text_control(self):
        """Cherche un Document ou Edit dans l'arbre UIA à partir du HWND."""
        try:
            doc = self._control.DocumentControl(searchDepth=8)
            if doc and doc.Exists(0):
                return doc
            edit = self._control.EditControl(searchDepth=8)
            if edit and edit.Exists(0):
                return edit
        except Exception:
            pass
        return None

    def _read_selection_clipboard(self) -> str:
        """Fallback : Ctrl+C → lit le presse-papier."""
        _focus_hwnd(self._hwnd)
        old = _get_clipboard_text()
        _send_key(self._hwnd, "c", ctrl=True)
        time.sleep(0.15)
        result = _get_clipboard_text()
        # Restaurer si rien n'a changé
        return result if result != old else ""

    def _read_all_clipboard(self) -> str:
        """Fallback : Ctrl+A → Ctrl+C → lit le presse-papier."""
        if self._is_browser:
            canvas_hwnd = _find_chrome_canvas(self._hwnd) or self._hwnd
            logger.debug(
                "UIAutomationDriver._read_all_clipboard [browser] "
                "— canvas hwnd=%d (class=%s)",
                canvas_hwnd, _get_window_class(canvas_hwnd),
            )
            old = _get_clipboard_text()
            result = _browser_ctrlac_read(canvas_hwnd)
            logger.debug(
                "UIAutomationDriver._read_all_clipboard [browser] "
                "— %d chars lus (était %d avant)",
                len(result), len(old),
            )
            return result
        else:
            _focus_hwnd(self._hwnd)
            _send_key(self._hwnd, "a", ctrl=True)
            time.sleep(0.1)
            _send_key(self._hwnd, "c", ctrl=True)
            time.sleep(0.2)
        return _get_clipboard_text()

    def _write_via_clipboard(self, text: str, replace: bool) -> None:
        """Colle via presse-papier avec focus cross-process (AttachThreadInput)."""
        _paste_to_hwnd(self._hwnd, text)


class ClipboardDriver(_BaseDriver):
    """
    Driver presse-papier pur — fallback universel.
    Fonctionne partout mais sensible au focus.
    """

    def __init__(self, hwnd: int):
        self._hwnd = hwnd

    def is_available(self) -> bool:
        return True

    def read_selection(self) -> str:
        _focus_hwnd(self._hwnd)
        old = _get_clipboard_text()
        _send_key(self._hwnd, "c", ctrl=True)
        time.sleep(0.2)
        result = _get_clipboard_text()
        return result if result != old else ""

    def read_visible_text(self) -> str:
        _focus_hwnd(self._hwnd)
        _send_key(self._hwnd, "a", ctrl=True)
        time.sleep(0.1)
        _send_key(self._hwnd, "c", ctrl=True)
        time.sleep(0.25)
        return _get_clipboard_text()

    def insert_at_cursor(self, text: str) -> None:
        _paste_to_hwnd(self._hwnd, text)

    def replace_selection(self, text: str) -> None:
        _paste_to_hwnd(self._hwnd, text)


class WordDriver(_BaseDriver):
    """
    Driver Word natif via COM (win32com.client).

    Avantages sur les autres drivers :
    - Lecture sans Ctrl+A/C (ne touche pas au presse-papier ni à la sélection)
    - Écriture via Selection.TypeText() : insère au curseur OU remplace la
      sélection courante, sans presse-papier
    - Accès au document complet, même si partiellement hors écran

    Détection : classe Win32 "OpusApp" (toutes versions de Word)
    Prérequis  : Word doit être déjà ouvert (GetActiveObject)
    """

    def __init__(self, hwnd: int):
        import win32com.client
        self._hwnd = hwnd
        # GetActiveObject lève une exception si Word n'est pas en cours d'exécution
        self._app = win32com.client.GetActiveObject("Word.Application")

    def is_available(self) -> bool:
        try:
            _ = self._app.Version
            return True
        except Exception:
            return False

    def read_selection(self) -> str:
        """
        Retourne le texte sélectionné dans le document Word actif.
        Ne modifie pas la sélection ni le presse-papier.
        """
        try:
            sel = self._app.Selection
            text = sel.Text or ""
            # Word ajoute \r au marqueur de fin — on le retire
            return text.rstrip("\r")
        except Exception as exc:
            logger.debug("WordDriver.read_selection — %s", exc)
            return ""

    def read_visible_text(self) -> str:
        """
        Retourne le texte complet du document actif.
        Ne touche pas au presse-papier ni à la sélection.
        """
        try:
            doc = self._app.ActiveDocument
            return doc.Content.Text
        except Exception as exc:
            logger.debug("WordDriver.read_visible_text — %s", exc)
            return ""

    def insert_at_cursor(self, text: str) -> None:
        """
        Insère text à la position du curseur Word.
        Si une sélection existe, elle est préservée (curseur placé après).
        Utilise TypeParagraph() pour les sauts de ligne afin de créer
        de vrais paragraphes Word (pas de simples '\\n' ignorés par TypeText).
        """
        self._focus_word()
        time.sleep(0.05)
        sel = self._app.Selection
        sel.Collapse(1)   # wdCollapseStart=1
        _word_type_text(sel, text)

    def replace_selection(self, text: str) -> None:
        """
        Remplace la sélection courante par text.
        TypeText() remplace automatiquement une sélection non vide.
        """
        self._focus_word()
        time.sleep(0.05)
        _word_type_text(self._app.Selection, text)

    def _focus_word(self) -> None:
        """Remet le focus sur la fenêtre Word embarquée."""
        try:
            self._app.Activate()
            win32gui.SetForegroundWindow(self._hwnd)
            time.sleep(0.1)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Utilitaires Win32
# ──────────────────────────────────────────────────────────────────────────────

def _browser_ctrlac_read(hwnd: int) -> str:
    """
    Envoie Ctrl+A puis Ctrl+C à hwnd en maintenant AttachThreadInput actif
    pendant TOUTE la séquence (SetFocus → touches → délai clipboard).

    Pourquoi atomique ? _focus_hwnd() détache AttachThreadInput dans son
    finally avant que _send_key() n'envoie les touches → Qt reprend le focus
    entre les deux appels → keybd_event tape dans le chat EUGENIA au lieu de
    la fenêtre Chrome.
    """
    import ctypes
    lo_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
    our_tid   = win32api.GetCurrentThreadId()
    attached  = False
    try:
        if lo_tid != our_tid:
            win32process.AttachThreadInput(our_tid, lo_tid, True)
            attached = True

        win32gui.BringWindowToTop(hwnd)
        win32gui.SetFocus(hwnd)
        time.sleep(0.15)        # laisser le focus s'installer

        # Ctrl+A  (sélectionner tout)
        ctypes.windll.user32.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(ord('A'),            0, 0, 0)
        time.sleep(0.03)
        ctypes.windll.user32.keybd_event(ord('A'),            0, win32con.KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.25)

        # Ctrl+C  (copier)
        ctypes.windll.user32.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(ord('C'),            0, 0, 0)
        time.sleep(0.03)
        ctypes.windll.user32.keybd_event(ord('C'),            0, win32con.KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.70)        # Google Docs est lent à remplir le clipboard

    finally:
        if attached:
            win32process.AttachThreadInput(our_tid, lo_tid, False)

    return _get_clipboard_text()


def _find_chrome_canvas(parent_hwnd: int) -> int | None:
    """
    Cherche récursivement le hwnd Chrome_RenderWidgetHostHWND dans les enfants
    de parent_hwnd. C'est le vrai canvas de rendu de Chrome/Google Docs —
    le seul qui reçoit correctement Ctrl+A / Ctrl+C quand Chrome est embarqué.
    """
    result: list[int] = []

    def _callback(hwnd: int, _) -> bool:
        cls = _get_window_class(hwnd)
        if cls == "Chrome_RenderWidgetHostHWND":
            result.append(hwnd)
            return False  # arrêt à la première trouvée
        return True

    try:
        win32gui.EnumChildWindows(parent_hwnd, _callback, None)
    except Exception:
        pass
    return result[0] if result else None


def _focus_hwnd(hwnd: int) -> None:
    """
    Donne le focus clavier à hwnd via AttachThreadInput (cross-process).
    Utilisé pour les opérations de LECTURE (Ctrl+C, Ctrl+A).
    Pour l'écriture, utiliser _paste_to_hwnd() qui gère tout en un bloc atomique.
    """
    try:
        lo_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
        our_tid = win32api.GetCurrentThreadId()
        attached = False
        try:
            if lo_tid != our_tid:
                win32process.AttachThreadInput(our_tid, lo_tid, True)
                attached = True
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetFocus(hwnd)
            time.sleep(0.08)
        finally:
            if attached:
                win32process.AttachThreadInput(our_tid, lo_tid, False)
    except Exception as exc:
        logger.debug("_focus_hwnd — %s", exc)


def _paste_to_hwnd(hwnd: int, text: str) -> None:
    """
    Place text dans le presse-papier et l'insère dans la fenêtre hwnd.

    Utilise AttachThreadInput pour partager la file d'entrée clavier avec
    le process cible. Contrairement à SetFocus seul ou WM_PASTE, cette
    méthode fonctionne cross-process sur les fenêtres embarquées (LibreOffice,
    Chrome, Notepad...).

    Stratégie :
      1. AttachThreadInput(notre_thread, thread_de_hwnd)
      2. BringWindowToTop + SetFocus(hwnd) — maintenant valide cross-thread
      3. keybd_event Ctrl+V — envoyé au thread focalisé = hwnd
      4. Détacher les threads
    """
    _set_clipboard_rich(text)

    try:
        lo_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
        our_tid = win32api.GetCurrentThreadId()
        attached = False
        try:
            if lo_tid != our_tid:
                win32process.AttachThreadInput(our_tid, lo_tid, True)
                attached = True

            win32gui.BringWindowToTop(hwnd)
            win32gui.SetFocus(hwnd)
            time.sleep(0.1)  # laisser le focus s'établir

            # Ctrl+V — keybd_event envoie au thread focalisé (hwnd) grâce à AttachThreadInput
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord('V'), 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)

            logger.debug("_paste_to_hwnd — %d chars -> hwnd=%d (class=%s)",
                         len(text), hwnd, _get_window_class(hwnd))
        finally:
            if attached:
                win32process.AttachThreadInput(our_tid, lo_tid, False)

    except Exception as exc:
        logger.warning("_paste_to_hwnd — %s", exc)
        # Dernier recours : WM_PASTE direct (Edit, RichEdit)
        try:
            win32gui.SendMessage(hwnd, 0x0302, 0, 0)
        except Exception:
            pass


def _word_type_text(selection, text: str) -> None:
    """
    Insère text dans une sélection Word en gérant correctement les sauts de ligne.
    Word utilise TypeParagraph() pour créer de vrais paragraphes (pas \\r ni \\n).
    Un \\n simple → TypeParagraph() (nouveau paragraphe).
    """
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line:
            selection.TypeText(line)
        if i < len(lines) - 1:
            selection.TypeParagraph()


def _send_key(hwnd: int, key: str, ctrl: bool = False) -> None:
    """Envoie une combinaison de touches via keybd_event (lecture uniquement)."""
    vk = ord(key.upper())
    if ctrl:
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    if ctrl:
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def _get_clipboard_text() -> str:
    """Lit le contenu texte du presse-papier."""
    try:
        win32clipboard.OpenClipboard()
        try:
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ""
        except Exception:
            return ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return ""


def _set_clipboard_text(text: str) -> None:
    """Écrit du texte brut dans le presse-papier (utilisé pour restaurer après lecture)."""
    try:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        finally:
            win32clipboard.CloseClipboard()
    except Exception as exc:
        logger.warning("_set_clipboard_text — échec : %s", exc)


def _text_to_html(text: str) -> str:
    """
    Convertit du texte (avec markdown basique) en fragment HTML.
    Utilisé pour CF_HTML dans le presse-papier.

    Conversions :
      - Double saut de ligne \\n\\n  → nouveau paragraphe <p>
      - Saut de ligne simple \\n    → <br>
      - **gras** / __gras__         → <b>
      - *italique* / _italique_     → <i>
      - `code inline`               → <code>
    """
    import html as _html
    escaped = _html.escape(text)

    paragraphs = re.split(r'\n{2,}', escaped)
    parts = []
    for para in paragraphs:
        if not para.strip():
            continue
        # Sauts de ligne simples
        para = para.replace('\n', '<br>\n')
        # Markdown gras
        para = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', para, flags=re.DOTALL)
        para = re.sub(r'__(.+?)__',     r'<b>\1</b>', para, flags=re.DOTALL)
        # Markdown italique
        para = re.sub(r'\*(.+?)\*',    r'<i>\1</i>', para, flags=re.DOTALL)
        para = re.sub(r'_(.+?)_',      r'<i>\1</i>', para, flags=re.DOTALL)
        # Code inline
        para = re.sub(r'`(.+?)`',      r'<code>\1</code>', para)
        parts.append(f'<p>{para}</p>')
    return '\n'.join(parts)


def _build_cf_html(html_body: str) -> bytes:
    """
    Construit le format CF_HTML Windows avec les offsets décimaux corrects.
    Requis par Word, LibreOffice et Chrome pour accépter le HTML du presse-papier.
    """
    # Le header a une taille fixe avec des placeholders à 8 chiffres
    HEADER = (
        "Version:1.0\r\n"
        "StartHTML:{sh:08d}\r\n"
        "EndHTML:{eh:08d}\r\n"
        "StartFragment:{sf:08d}\r\n"
        "EndFragment:{ef:08d}\r\n"
    )
    # Calculer la taille du header avec des zéros (même longueur qu'avec les vraies valeurs)
    header_len = len(HEADER.format(sh=0, eh=0, sf=0, ef=0).encode('utf-8'))

    pre  = "<html><body>\r\n<!--StartFragment-->"
    post = "<!--EndFragment-->\r\n</body></html>"

    sh = header_len
    sf = sh + len(pre.encode('utf-8'))
    ef = sf + len(html_body.encode('utf-8'))
    eh = ef + len(post.encode('utf-8'))

    result = HEADER.format(sh=sh, eh=eh, sf=sf, ef=ef) + pre + html_body + post
    return result.encode('utf-8')


def _set_clipboard_rich(text: str) -> None:
    """
    Place text dans le presse-papier avec deux formats :
      - CF_UNICODETEXT : texte brut (\\n → \\r\\n) pour compatibilité universelle
      - CF_HTML        : HTML avec formatage (LibreOffice et Word préfèrent CF_HTML)

    La conversion markdown → HTML gère : paragraphes, sauts de ligne,
    **gras**, *italique*, `code inline`.
    """
    CF_HTML = win32clipboard.RegisterClipboardFormat('HTML Format')
    plain   = text.replace('\n', '\r\n')  # Windows line endings
    html_body = _text_to_html(text)
    cf_html_bytes = _build_cf_html(html_body)
    try:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, plain)
            win32clipboard.SetClipboardData(CF_HTML, cf_html_bytes)
        finally:
            win32clipboard.CloseClipboard()
        logger.debug("_set_clipboard_rich — %d chars (plain) + %d bytes (CF_HTML)",
                     len(plain), len(cf_html_bytes))
    except Exception as exc:
        logger.warning("_set_clipboard_rich — échec CF_HTML, fallback plain : %s", exc)
        _set_clipboard_text(plain)


def _get_window_title(hwnd: int) -> str:
    try:
        return win32gui.GetWindowText(hwnd) or f"hwnd={hwnd}"
    except Exception:
        return f"hwnd={hwnd}"


def _get_window_class(hwnd: int) -> str:
    """Retourne la classe Win32 de la fenêtre (ex. 'OpusApp' pour Word)."""
    try:
        return win32gui.GetClassName(hwnd) or ""
    except Exception:
        return ""
