"""Acceso a la web para ATLAS: buscar y leer páginas.

Búsqueda: la API de Brave si hay clave (BRAVE_API_KEY); si no, DuckDuckGo en su
versión HTML y, si bloquea, Wikipedia en español. La lectura de páginas rechaza direcciones internas
(loopback, red local): el texto de una página podría pedirle al modelo que
lea servicios de tu red, y esto lo impide aunque el modelo obedezca.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TIMEOUT = 15
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5


class WebError(Exception):
    """Fallo esperable al usar la web; el mensaje es apto para el usuario."""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


class _DuckDuckGoParser(HTMLParser):
    """Extrae título, link y resumen de cada resultado de html.duckduckgo.com."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._field: str | None = None
        self._buffer: list[str] = []
        self._href = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag != "a":
            return
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if "result__a" in classes:
            self._field, self._buffer, self._href = "title", [], attributes.get("href") or ""
        elif "result__snippet" in classes:
            self._field, self._buffer = "snippet", []

    def handle_data(self, data: str) -> None:
        if self._field:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._field:
            return
        text = _clean("".join(self._buffer))
        if self._field == "title":
            self.results.append(SearchResult(title=text, url=_unwrap_duckduckgo(self._href), snippet=""))
        elif self.results:
            self.results[-1].snippet = text
        self._field = None


def _unwrap_duckduckgo(href: str) -> str:
    """Los links vienen como //duckduckgo.com/l/?uddg=<url real>."""
    if href.startswith("//"):
        href = "https:" + href
    target = parse_qs(urlparse(href).query).get("uddg")
    return target[0] if target else href


def _search_duckduckgo(query: str, limit: int) -> list[SearchResult]:
    response = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query, "kl": "es-es"},
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    parser = _DuckDuckGoParser()
    parser.feed(response.text)
    # Los anuncios apuntan a duckduckgo.com/y.js: se descartan.
    return [r for r in parser.results if r.url.startswith("http") and "duckduckgo.com/y.js" not in r.url][:limit]


def _search_brave(query: str, limit: int, api_key: str) -> list[SearchResult]:
    """API oficial de Brave Search (https://brave.com/search/api): necesita clave propia."""
    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": limit, "search_lang": "es"},
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    items = (response.json().get("web") or {}).get("results") or []
    return [
        SearchResult(
            title=_clean(item.get("title", "")),
            url=item.get("url", ""),
            snippet=_clean(re.sub(r"<[^>]+>", "", item.get("description", ""))),
        )
        for item in items[:limit]
        if item.get("url")
    ]


def _search_wikipedia(query: str, limit: int) -> list[SearchResult]:
    response = requests.get(
        "https://es.wikipedia.org/w/api.php",
        params={"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"},
        headers={"User-Agent": "ATLAS-personal-assistant/1.0"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return [
        SearchResult(
            title=item["title"],
            url="https://es.wikipedia.org/wiki/" + item["title"].replace(" ", "_"),
            snippet=_clean(re.sub(r"<[^>]+>", "", item.get("snippet", ""))),
        )
        for item in response.json().get("query", {}).get("search", [])
    ]


def search(query: str, limit: int = 5, brave_api_key: str = "") -> tuple[list[SearchResult], str]:
    """Devuelve (resultados, fuente). Lanza WebError si no hay forma de buscar.

    Con clave de Brave se usa su API. Sin clave se intenta DuckDuckGo, que suele
    bloquear a quien no es un navegador; si falla, queda Wikipedia, que sirve
    para datos enciclopédicos pero no para noticias ni precios del día.
    """
    engines = [("DuckDuckGo", _search_duckduckgo)]
    if brave_api_key:
        engines.insert(0, ("Brave", lambda q, n: _search_brave(q, n, brave_api_key)))
    for name, engine in engines:
        try:
            results = engine(query, limit)
            if results:
                return results, name
        except requests.RequestException:
            continue
    try:
        return _search_wikipedia(query, limit), "Wikipedia"
    except requests.RequestException as exc:
        raise WebError(f"No pude buscar en internet ({exc}).") from exc


def _assert_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise WebError("Solo puedo leer direcciones http o https.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, None)}
    except socket.gaierror as exc:
        raise WebError(f"No existe el sitio '{parsed.hostname}'.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            raise WebError("No leo direcciones internas (esta PC o tu red local).")


class _TextExtractor(HTMLParser):
    """Texto legible de una página. Si la página marca su contenido principal
    (<main> o <article>) se devuelve solo eso, sin menús ni barras laterales."""

    _SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "form", "iframe"}
    _BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}
    _MAIN = {"main", "article"}
    _MIN_MAIN_CHARS = 200  # un <main> casi vacío no es el contenido: se usa la página entera

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._parts: list[str] = []
        self._main_parts: list[str] = []
        self._skip_depth = 0
        self._main_depth = 0
        self._in_title = False

    def _add(self, text: str) -> None:
        self._parts.append(text)
        if self._main_depth:
            self._main_parts.append(text)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "title":
            self._in_title = True
        if tag in self._MAIN:
            self._main_depth += 1
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self._add("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in self._MAIN and self._main_depth:
            self._main_depth -= 1
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip_depth:
            self._add(data)

    @staticmethod
    def _tidy(parts: list[str]) -> str:
        lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in "".join(parts).split("\n")]
        return "\n".join(line for line in lines if line)

    def text(self) -> str:
        main = self._tidy(self._main_parts)
        return main if len(main) >= self._MIN_MAIN_CHARS else self._tidy(self._parts)


def _read_wikipedia(host: str, title: str) -> tuple[str, str] | None:
    """Texto limpio de un artículo por la API de Wikipedia: el HTML de la página
    trae cientos de enlaces a otros idiomas que se comerían el límite de texto."""
    try:
        response = requests.get(
            f"https://{host}/w/api.php",
            params={
                "action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
                "titles": title.replace("_", " "), "format": "json",
            },  # fmt: skip
            headers={"User-Agent": "ATLAS-personal-assistant/1.0"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
    except (requests.RequestException, ValueError):
        return None  # se intenta leer la página como cualquier otra
    for page in pages.values():
        if page.get("extract"):
            return page.get("title", title), page["extract"]
    return None


def read_page(url: str) -> tuple[str, str]:
    """Devuelve (título, texto) de una página pública. Lanza WebError si no se puede."""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if (parsed.hostname or "").endswith(".wikipedia.org") and parsed.path.startswith("/wiki/"):
        article = _read_wikipedia(parsed.hostname, unquote(parsed.path[len("/wiki/"):]))
        if article:
            return article
    try:
        for _ in range(MAX_REDIRECTS + 1):
            _assert_public(url)  # también en cada redirección
            response = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, allow_redirects=False, stream=True
            )
            if response.is_redirect and response.headers.get("location"):
                url = urljoin(url, response.headers["location"])
                continue
            break
        else:
            raise WebError("Demasiadas redirecciones.")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            raise WebError(f"Esa dirección no es una página de texto ({content_type or 'tipo desconocido'}).")
        raw = response.raw.read(MAX_PAGE_BYTES, decode_content=True)
    except requests.RequestException as exc:
        raise WebError(f"No pude abrir la página ({exc}).") from exc

    html = raw.decode(response.encoding or "utf-8", errors="replace")
    if "html" not in content_type:
        return url, html
    extractor = _TextExtractor()
    extractor.feed(html)
    return _clean(extractor.title) or url, extractor.text()
