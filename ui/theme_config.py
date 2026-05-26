"""
theme_config.py — Surcharges de couleurs par thème, définies par l'utilisateur.

Usage :
    from ui.theme_config import ThemeConfig
    tc = ThemeConfig.instance()
    tc.get_overrides("dark")   # dict des clés surchargées
    tc.set_override("light", "item_select", "#D4B896")
    tc.reset_override("light", "item_select")
    tc.dump()   # {"dark": {...}, "light": {...}}
    tc.load(data)
"""

from __future__ import annotations


class ThemeConfig:
    """Singleton léger stockant les surcharges de couleurs par thème."""

    _instance: "ThemeConfig | None" = None

    def __init__(self):
        self._overrides: dict[str, dict[str, str]] = {"dark": {}, "light": {}}

    @classmethod
    def instance(cls) -> "ThemeConfig":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_overrides(self, theme: str) -> dict[str, str]:
        return dict(self._overrides.get(theme, {}))

    def set_override(self, theme: str, key: str, color: str) -> None:
        self._overrides.setdefault(theme, {})[key] = color

    def reset_override(self, theme: str, key: str) -> None:
        self._overrides.get(theme, {}).pop(key, None)

    def reset_all(self, theme: str) -> None:
        self._overrides[theme] = {}

    def load(self, data: dict) -> None:
        """Charge depuis un dict {"dark": {...}, "light": {...}}."""
        for t in ("dark", "light"):
            self._overrides[t] = dict(data.get(t, {}))

    def dump(self) -> dict:
        """Retourne un dict sérialisable."""
        return {t: dict(v) for t, v in self._overrides.items()}
