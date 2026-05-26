"""
ghost_scanner.py - Scanner OCR pour Ghost Writer.
Backends disponibles : winrt (Windows OCR natif, défaut), easyocr.
Le backend actif est lu depuis la config JSON (clé "ocr_engine").
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import mss
from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal, QPoint
from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


@dataclass
class ScanBlock:
    text: str
    x: int
    y: int
    w: int
    h: int

    @property
    def center_y(self) -> int:
        return self.y + self.h // 2


# ─── Backend Windows OCR (winrt) ──────────────────────────────────────────────

def _scan_winrt(img: Image.Image) -> list[ScanBlock]:
    """OCR via Windows OCR natif (~0.1–0.5s). Nécessite winrt installé."""
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode

    img_rgba = img.convert("RGBA")
    w, h = img_rgba.size
    raw = img_rgba.tobytes()

    bmp = SoftwareBitmap(BitmapPixelFormat.RGBA8, w, h, BitmapAlphaMode.IGNORE)
    bmp.copy_from_buffer(raw)

    # Essai fr-FR puis en-US
    engine = OcrEngine.try_create_from_language(Language("fr-FR"))
    if engine is None:
        engine = OcrEngine.try_create_from_language(Language("en-US"))
    if engine is None:
        raise RuntimeError("Windows OCR : aucune langue disponible (fr-FR / en-US)")

    async def _recognize():
        return await engine.recognize_async(bmp)

    result = asyncio.run(_recognize())

    blocks = []
    for line in result.lines:
        for word in line.words:
            r = word.bounding_rect
            x, y, ww, hh = int(r.x), int(r.y), int(r.width), int(r.height)
            text = word.text.strip()
            if text:
                blocks.append(ScanBlock(text=text, x=x, y=y, w=ww, h=hh))
    return blocks


# ─── Backend EasyOCR ──────────────────────────────────────────────────────────

_easyocr_instance = None

def _scan_easyocr(img: Image.Image) -> list[ScanBlock]:
    """OCR via EasyOCR (3–8s, précis). Chargement paresseux au premier appel."""
    import numpy as np
    from PIL import ImageEnhance

    global _easyocr_instance
    if _easyocr_instance is None:
        import easyocr
        logger.info("GhostScanner (EasyOCR) — initialisation (première utilisation)…")
        _easyocr_instance = easyocr.Reader(["fr", "en"], gpu=False, verbose=False)
        logger.info("GhostScanner (EasyOCR) — prêt")

    img_array = np.array(ImageEnhance.Contrast(img).enhance(1.3))
    raw_results = _easyocr_instance.readtext(img_array, detail=1, paragraph=False)

    blocks = []
    for bbox, text, confidence in raw_results:
        if confidence < 0.4:
            continue
        text = text.strip()
        if not text:
            continue
        xs = [int(pt[0]) for pt in bbox]
        ys = [int(pt[1]) for pt in bbox]
        x, y = min(xs), min(ys)
        w, h = max(xs) - x, max(ys) - y
        blocks.append(ScanBlock(text=text, x=x, y=y, w=w, h=h))
    return blocks


# ─── Thread scanner ───────────────────────────────────────────────────────────

class GhostScanner(QThread):
    scan_done    = pyqtSignal(list)
    scan_error   = pyqtSignal(str)
    scan_started = pyqtSignal()

    def __init__(self, editor_zone: QWidget, backend: str = "winrt", parent=None):
        super().__init__(parent)
        top_left: QPoint = editor_zone.mapToGlobal(QPoint(0, 0))
        size = editor_zone.size()
        self._screen_x: int = top_left.x()
        self._screen_y: int = top_left.y()
        self._screen_w: int = size.width()
        self._screen_h: int = size.height()
        self._backend: str  = backend

    def run(self):
        self.scan_started.emit()
        try:
            blocks = self._scan()
            self.scan_done.emit(blocks)
        except Exception as exc:
            logger.error("GhostScanner.run — %s", exc, exc_info=True)
            self.scan_error.emit(str(exc))

    def _scan(self) -> list[ScanBlock]:
        if self._screen_w <= 0 or self._screen_h <= 0:
            raise ValueError("GhostScanner : EditorZone taille invalide")

        logger.debug(
            "GhostScanner [%s] — capture (%d,%d) %dx%d",
            self._backend, self._screen_x, self._screen_y, self._screen_w, self._screen_h,
        )

        # Pause pour laisser l'éditeur tiers finir son rendu après l'embed
        time.sleep(1.5)

        with mss.MSS() as sct:
            monitor = {
                "left": self._screen_x, "top": self._screen_y,
                "width": self._screen_w, "height": self._screen_h,
            }
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        t = time.perf_counter()
        if self._backend == "winrt":
            blocks = _scan_winrt(img)
        elif self._backend == "easyocr":
            blocks = _scan_easyocr(img)
        else:
            raise ValueError(f"GhostScanner : backend inconnu '{self._backend}'")

        logger.info(
            "GhostScanner [%s] — %d blocs en %.2fs",
            self._backend, len(blocks), time.perf_counter() - t,
        )
        return blocks