"""
scroll_tracker.py — Suivi du scroll d'une fenêtre embarquée via hook souris bas niveau.

Approche :
  Un hook WH_MOUSE_LL (niveau OS) tourne dans un thread dédié avec boucle de messages Win32.
  Quand la molette tourne sur la fenêtre cible, on calcule delta_pixels et on le poste
  dans une queue thread-safe. Un QTimer draine la queue sur le thread Qt principal et émet
  scroll_delta(int). Après DEBOUNCE_MS d'inactivité, rescan_requested() est émis.

  Avantage : fonctionne pour n'importe quelle app (LibreOffice VCL, Word, etc.) sans
  dépendre des scrollbars Win32 natives.
"""

import ctypes
import ctypes.wintypes
import logging
import queue
import threading
from typing import Optional

import win32gui
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────

DEBOUNCE_MS   = 1500   # délai d'inactivité avant rescan (ms)
DRAIN_MS       = 50    # intervalle de vidage de la queue Qt (ms)
WHEEL_DELTA    = 120   # unités Windows par cran de molette
LINE_HEIGHT_PX = 22    # hauteur de ligne estimée en pixels (à 100% zoom) — vitesse 5
DRAG_BASE_FACTOR = 8  # facteur drag scrollbar de base — vitesse 5

# WM_MOUSEWHEEL = 0x020A, WH_MOUSE_LL = 14
_WM_MOUSEWHEEL   = 0x020A
_WM_MOUSEMOVE    = 0x0200
_WM_LBUTTONDOWN  = 0x0201
_WM_LBUTTONUP    = 0x0202
_WH_MOUSE_LL     = 14
_SPI_GETWHEELSCROLLLINES = 0x0068

# Facteur d'amplification du déplacement souris → pixels de contenu pendant un drag scrollbar.
# 1 px de mouvement curseur ≈ DRAG_SCROLL_FACTOR px de scroll dans le document.
DRAG_SCROLL_FACTOR = 8


# ─── Structs ctypes ───────────────────────────────────────────────────────────

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt",          _POINT),
        ("mouseData",   ctypes.c_uint),
        ("flags",       ctypes.c_uint),
        ("time",        ctypes.c_uint),
        ("dwExtraInfo", ctypes.c_ulong),
    ]


# ─── Thread hook ──────────────────────────────────────────────────────────────

class _MouseHookThread(threading.Thread):
    """Thread dédié avec boucle de messages Win32 et hook WH_MOUSE_LL."""

    def __init__(self, hwnd: int, delta_queue: queue.Queue):
        super().__init__(daemon=True, name="ScrollHookThread")
        self._hwnd        = hwnd
        self._queue       = delta_queue
        self._tid: int    = 0
        self._hook        = None
        # Lire les lignes par cran depuis les préférences système
        lpc = ctypes.c_uint(3)
        ctypes.windll.user32.SystemParametersInfoW(
            _SPI_GETWHEELSCROLLLINES, 0, ctypes.byref(lpc), 0
        )
        self._lines_per_notch: int = max(1, lpc.value)
        self._dragging: bool = False
        self._drag_prev_y: int = 0
        # Vitesse synchro (1–10, défaut 5)
        self._line_height_px: int  = LINE_HEIGHT_PX
        self._drag_scroll_factor: float = DRAG_BASE_FACTOR

    def stop(self) -> None:
        if self._tid:
            ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)  # WM_QUIT

    def run(self) -> None:
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()

        # Activer DPI awareness pour que GetWindowRect retourne des coordonnées physiques
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

        _HOOKPROC = ctypes.CFUNCTYPE(
            ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
        )

        def _proc(nCode, wParam, lParam):
            if nCode >= 0:
                ms = ctypes.cast(lParam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                try:
                    rect = win32gui.GetWindowRect(self._hwnd)
                    over = rect[0] <= ms.pt.x <= rect[2] and rect[1] <= ms.pt.y <= rect[3]

                    if wParam == _WM_MOUSEWHEEL:
                        raw_delta = ctypes.c_short(ms.mouseData >> 16).value
                        logger.debug(
                            "ScrollTracker — molette raw=%d pos=(%d,%d) rect=%s over=%s",
                            raw_delta, ms.pt.x, ms.pt.y, rect, over,
                        )
                        if over:
                            notches  = raw_delta / WHEEL_DELTA
                            delta_px = int(notches * self._lines_per_notch * self._line_height_px)
                            if delta_px != 0:
                                self._queue.put(delta_px)

                    elif wParam == _WM_MOUSEMOVE:
                        if self._dragging:
                            dy = ms.pt.y - self._drag_prev_y
                            self._drag_prev_y = ms.pt.y
                            if dy != 0:
                                delta_px = int(-dy * self._drag_scroll_factor)  # barre descend → contenu monte
                                self._queue.put(delta_px)

                    elif wParam == _WM_LBUTTONDOWN:
                        # Activer le drag UNIQUEMENT si le clic est dans la bande scrollbar
                        # (bord droit de la fenêtre). Un clic dans le texte pour sélectionner
                        # ne doit PAS déclencher le tracking de position des badges.
                        if over:
                            scrollbar_w = ctypes.windll.user32.GetSystemMetrics(2)  # SM_CXVSCROLL
                            in_scrollbar = ms.pt.x >= rect[2] - max(scrollbar_w, 20)
                            if in_scrollbar:
                                self._dragging = True
                                self._drag_prev_y = ms.pt.y
                                logger.debug("ScrollTracker — drag scrollbar démarré pos=(%d,%d)", ms.pt.x, ms.pt.y)
                            else:
                                logger.debug("ScrollTracker — clic texte (pas scrollbar), drag ignoré pos=(%d,%d)", ms.pt.x, ms.pt.y)

                    elif wParam == _WM_LBUTTONUP:
                        # Le relâché peut arriver hors fenêtre (drag long) → pas de check over
                        if self._dragging:
                            self._dragging = False
                            self._queue.put(None)  # sentinel → rescan immédiat précis
                            logger.debug("ScrollTracker — drag terminé → rescan")

                except Exception as exc:
                    logger.debug("ScrollTracker — _proc exception : %s", exc)
            return ctypes.windll.user32.CallNextHookEx(
                self._hook, nCode, wParam, ctypes.c_long(lParam)
            )

        self._cb   = _HOOKPROC(_proc)
        self._hook = ctypes.windll.user32.SetWindowsHookExW(
            _WH_MOUSE_LL, self._cb, None, 0
        )
        if not self._hook:
            logger.warning("ScrollTracker — SetWindowsHookExW a échoué")
            return

        logger.debug("ScrollTracker — hook WH_MOUSE_LL actif (tid=%d)", self._tid)
        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

        ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        logger.debug("ScrollTracker — hook WH_MOUSE_LL arrêté")


# ─── ScrollTracker ────────────────────────────────────────────────────────────

class ScrollTracker(QObject):
    """
    Signaux :
      scroll_delta(int)    → delta en pixels estimé (positif = scroll vers le bas)
      rescan_requested()   → l'utilisateur a arrêté de scroller, relancer un scan
    """

    scroll_delta     = pyqtSignal(int)
    rescan_requested = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._hwnd:         Optional[int]          = None
        self._hook_thread:  Optional[_MouseHookThread] = None
        self._delta_queue:  queue.Queue            = queue.Queue()
        self._active:       bool                   = False
        self._speed:        int                    = 5  # vitesse courante (1–10)

        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(DRAIN_MS)
        self._drain_timer.timeout.connect(self._drain_queue)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._on_debounce)

    # ─── API publique ─────────────────────────────────────────────────────────

    def attach(self, hwnd: int, visible_height_px: int) -> bool:
        """
        Démarre le tracking sur hwnd.
        Retourne toujours True (le hook fonctionne pour toute app).
        """
        self.detach()
        self._hwnd   = hwnd
        self._active = True
        # Vider la queue résiduelle
        while not self._delta_queue.empty():
            try:
                self._delta_queue.get_nowait()
            except queue.Empty:
                break
        self._hook_thread = _MouseHookThread(hwnd, self._delta_queue)
        # Appliquer la vitesse courante avant de démarrer le thread
        self._apply_speed_to_thread(self._hook_thread, self._speed)
        self._hook_thread.start()
        self._drain_timer.start()
        logger.info("ScrollTracker.attach — hook démarré pour hwnd=%d", hwnd)
        return True

    @staticmethod
    def _apply_speed_to_thread(thread: "_MouseHookThread", speed: int) -> None:
        factor = max(1, min(10, speed)) / 5.0
        thread._line_height_px     = round(LINE_HEIGHT_PX * factor)
        thread._drag_scroll_factor = round(DRAG_BASE_FACTOR * factor, 1)

    def set_speed(self, speed: int) -> None:
        """
        Définit la vitesse de synchronisation scroll (1 = lent, 5 = défaut, 10 = rapide).
        Modifie LINE_HEIGHT_PX et DRAG_SCROLL_FACTOR proportionnellement.
        """
        self._speed = max(1, min(10, speed))
        if self._hook_thread is not None:
            self._apply_speed_to_thread(self._hook_thread, self._speed)
        factor = self._speed / 5.0
        logger.debug("ScrollTracker.set_speed — speed=%d line_h=%d drag_f=%.1f",
                     self._speed, round(LINE_HEIGHT_PX * factor), round(DRAG_BASE_FACTOR * factor, 1))

    def recalibrate(self, visible_height_px: int) -> None:
        """Remet à zéro après un rescan (aucun état interne à réinitialiser ici)."""
        pass   # le hook continue de tourner, rien à recalibrer

    def detach(self) -> None:
        """Arrête le hook et les timers."""
        if self._hook_thread is not None:
            self._hook_thread.stop()
            self._hook_thread = None
        self._drain_timer.stop()
        self._debounce_timer.stop()
        self._hwnd   = None
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    # ─── Interne ──────────────────────────────────────────────────────────────

    def _drain_queue(self) -> None:
        """Draine la queue sur le thread Qt et émet scroll_delta si nécessaire."""
        total = 0
        rescan_now = False
        while True:
            try:
                item = self._delta_queue.get_nowait()
                if item is None:
                    rescan_now = True  # sentinel drag scrollbar
                else:
                    total += item
            except queue.Empty:
                break
        if total != 0:
            self.scroll_delta.emit(total)
            self._debounce_timer.start()
        if rescan_now:
            self._debounce_timer.stop()
            logger.debug("ScrollTracker — drag terminé, rescan immédiat")
            self.rescan_requested.emit()

    def _on_debounce(self) -> None:
        """L'utilisateur a cessé de scroller → demander un rescan précis."""
        logger.debug("ScrollTracker — debounce expiré, rescan demandé")
        self.rescan_requested.emit()
