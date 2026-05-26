"""
font_config.py — Configuration typographique partagee dans toute l'UI EUGENIA.

Usage :
    from ui.font_config import FontConfig
    fc = FontConfig.instance()
    fc.size        # int, ex. 13
    fc.family      # str, ex. "Segoe UI"
    fc.chat_lh     # float, ex. 1.6  (line-height du chat)
"""

from __future__ import annotations

FONT_FAMILIES = [
    "Segoe UI",
    "Georgia",
    "Calibri",
    "Consolas",
]

_DEFAULT_SIZE   = 13
_DEFAULT_FAMILY = "Segoe UI"
_DEFAULT_CHAT_LH = 1.6   # line-height dans les bulles de chat


class FontConfig:
    """Singleton leger contenant la configuration typographique courante."""

    _instance: FontConfig | None = None

    def __init__(self):
        self.size:     int   = _DEFAULT_SIZE
        self.family:   str   = _DEFAULT_FAMILY
        self.chat_lh:  float = _DEFAULT_CHAT_LH

    @classmethod
    def instance(cls) -> FontConfig:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def update(self, size: int | None = None,
               family: str | None = None,
               chat_lh: float | None = None) -> None:
        if size is not None:
            self.size = max(12, min(16, size))
        if family is not None and family in FONT_FAMILIES:
            self.family = family
        if chat_lh is not None:
            self.chat_lh = round(max(1.0, min(2.2, chat_lh)), 1)

    # Tailles relatives derivees (utilisees dans les styles)
    @property
    def sm(self) -> int:
        """Taille petite = size - 1 (minimum 11)."""
        return max(11, self.size - 1)

    @property
    def xs(self) -> int:
        """Taille tres petite = size - 2 (minimum 10)."""
        return max(10, self.size - 2)

    @property
    def lg(self) -> int:
        """Taille grande = size + 1."""
        return self.size + 1

    @property
    def xl(self) -> int:
        """Taille tres grande = size + 3 (titres)."""
        return self.size + 3
