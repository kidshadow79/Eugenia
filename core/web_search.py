"""
web_search.py -- Recherche web pour la commande /web

Providers supportes :
    duckduckgo  -- gratuit, sans cle API (via ddgs)
    serper      -- Google Search JSON API (2 500 req. gratuites)
                   https://serper.dev
    brave       -- Brave Search API (2 000 req/mois gratuites)
                   https://brave.com/search/api/
    tavily      -- API concue pour les LLMs (1 000 req/mois gratuites)
                   https://tavily.com

Usage :
    searcher = create_searcher("serper", api_key="xxx")
    results  = searcher.search("Victor Hugo romantisme", max_results=5)
    block    = format_results_block("Victor Hugo romantisme", results)
    engine.inject_context_note(block)
"""

import logging
from dataclasses import dataclass

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

# Providers et leurs metadonnees d'affichage
WEB_PROVIDERS: dict[str, dict] = {
    "duckduckgo": {
        "label":    "DuckDuckGo (gratuit, sans cle)",
        "key_hint": "",
        "key_url":  "",
        "needs_key": False,
    },
    "serper": {
        "label":    "Serper — Google Search (2 500 req. gratuites)",
        "key_hint": "...",
        "key_url":  "https://serper.dev",
        "needs_key": True,
    },
    "brave": {
        "label":    "Brave Search (2 000 req/mois gratuites)",
        "key_hint": "BSA...",
        "key_url":  "https://brave.com/search/api/",
        "needs_key": True,
    },
    "tavily": {
        "label":    "Tavily (concu pour les LLMs, 1 000 req/mois gratuites)",
        "key_hint": "tvly-...",
        "key_url":  "https://app.tavily.com/home",
        "needs_key": True,
    },
}

WEB_PROVIDER_ORDER = ["duckduckgo", "serper", "brave", "tavily"]


# ── Resultat normalisé ────────────────────────────────────────────────────────

@dataclass
class WebSearchResult:
    title:   str
    snippet: str
    url:     str


# ── Searchers ─────────────────────────────────────────────────────────────────

class DuckDuckGoSearcher:
    """Recherche via ddgs (pip install ddgs)."""

    def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(WebSearchResult(
                    title=r.get("title", ""),
                    snippet=r.get("body", ""),
                    url=r.get("href", ""),
                ))
        logger.info("[WEB:DDGO] %d resultat(s) pour : %s", len(results), query[:60])
        return results


class SerperSearcher:
    """Recherche via l'API Serper (Google Search)."""

    _ENDPOINT = "https://google.serper.dev/search"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        import requests
        payload = {"q": query, "num": max_results, "gl": "fr", "hl": "fr"}
        headers = {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }
        resp = requests.post(self._ENDPOINT, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", [])[:max_results]:
            results.append(WebSearchResult(
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                url=item.get("link", ""),
            ))
        logger.info("[WEB:SERPER] %d resultat(s) pour : %s", len(results), query[:60])
        return results


class BraveSearcher:
    """Recherche via Brave Search API."""

    _ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        import requests
        params = {"q": query, "count": max_results, "search_lang": "fr"}
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }
        resp = requests.get(self._ENDPOINT, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", [])[:max_results]:
            results.append(WebSearchResult(
                title=item.get("title", ""),
                snippet=item.get("description", ""),
                url=item.get("url", ""),
            ))
        logger.info("[WEB:BRAVE] %d resultat(s) pour : %s", len(results), query[:60])
        return results


class TavilySearcher:
    """Recherche via l'API Tavily (concue pour les LLMs)."""

    _ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        import requests
        payload = {
            "query": query,
            "max_results": max_results,
            "api_key": self._api_key,
            "search_depth": "basic",
            "include_answer": False,
        }
        resp = requests.post(self._ENDPOINT, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", [])[:max_results]:
            results.append(WebSearchResult(
                title=item.get("title", ""),
                snippet=item.get("content", ""),
                url=item.get("url", ""),
            ))
        logger.info("[WEB:TAVILY] %d resultat(s) pour : %s", len(results), query[:60])
        return results


# ── Factory ───────────────────────────────────────────────────────────────────

def create_searcher(provider: str, api_key: str):
    """Retourne une instance du searcher pour le provider donne."""
    if provider == "duckduckgo":
        return DuckDuckGoSearcher()
    if provider == "serper":
        return SerperSearcher(api_key)
    if provider == "brave":
        return BraveSearcher(api_key)
    if provider == "tavily":
        return TavilySearcher(api_key)
    raise ValueError(f"Provider web inconnu : {provider!r}")


# ── Formattage ────────────────────────────────────────────────────────────────

def format_results_block(query: str, results: list[WebSearchResult]) -> str:
    """
    Formate les resultats en bloc texte injecte comme note de contexte.
    Retourne une chaine vide si la liste est vide.
    """
    if not results:
        return ""
    lines = [f"[Resultats de recherche Web pour : {query!r}]", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.title}")
        if r.snippet:
            lines.append(f"   {r.snippet[:300]}")
        if r.url:
            lines.append(f"   Source : {r.url}")
        lines.append("")
    return "\n".join(lines).strip()


# ── Worker QThread ────────────────────────────────────────────────────────────

class WebSearchWorker(QThread):
    """
    Thread de recherche web : evite de bloquer l'UI pendant la requete HTTP.

    Signaux :
        results_ready(str)  -- bloc formate pret a etre injecte
        search_error(str)   -- message d'erreur
    """

    results_ready = pyqtSignal(str)
    search_error  = pyqtSignal(str)

    def __init__(
        self,
        provider: str,
        api_key: str,
        query: str,
        max_results: int = 5,
    ):
        super().__init__()
        self._provider    = provider
        self._api_key     = api_key
        self._query       = query
        self._max_results = max_results

    def run(self) -> None:
        logger.info(
            "[WEB:WORKER] demarrage -- provider=%s | query=%s",
            self._provider, self._query[:60],
        )
        try:
            searcher = create_searcher(self._provider, self._api_key)
            results  = searcher.search(self._query, self._max_results)
            block    = format_results_block(self._query, results)
            self.results_ready.emit(block)
        except Exception as exc:
            logger.error("[WEB:WORKER] erreur : %s", exc, exc_info=True)
            self.search_error.emit(str(exc))


class WebKeyTestWorker(QThread):
    """
    Verifie qu'une cle API est fonctionnelle en lancant une micro-recherche.

    Signaux :
        test_ok()          -- cle valide, recherche OK
        test_error(str)    -- message d'erreur
    """

    test_ok    = pyqtSignal()
    test_error = pyqtSignal(str)

    def __init__(self, provider: str, api_key: str):
        super().__init__()
        self._provider = provider
        self._api_key  = api_key

    def run(self) -> None:
        logger.info("[WEB:TEST] test cle -- provider=%s", self._provider)
        try:
            searcher = create_searcher(self._provider, self._api_key)
            searcher.search("test", max_results=1)
            self.test_ok.emit()
        except Exception as exc:
            logger.warning("[WEB:TEST] echec : %s", exc)
            self.test_error.emit(str(exc))
