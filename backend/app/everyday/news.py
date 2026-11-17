"""Titulares con Google News RSS (sin clave), en español."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime

from app.everyday.http import get
from app.web.client import WebError

TOP_URL = "https://news.google.com/rss"
SEARCH_URL = "https://news.google.com/rss/search"
# Español latinoamericano; Google elige las fuentes según la región.
LOCALE = {"hl": "es-419", "gl": "US", "ceid": "US:es-419"}

TOPICS = {
    "tecnologia": "TECHNOLOGY",
    "tecnología": "TECHNOLOGY",
    "negocios": "BUSINESS",
    "economia": "BUSINESS",
    "economía": "BUSINESS",
    "deportes": "SPORTS",
    "ciencia": "SCIENCE",
    "salud": "HEALTH",
    "entretenimiento": "ENTERTAINMENT",
    "mundo": "WORLD",
    "internacional": "WORLD",
}


@dataclass
class Headline:
    title: str
    source: str
    published: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


def get_news(query: str = "", limit: int = 8) -> list[Headline]:
    query = query.strip()
    limit = max(1, min(int(limit), 20))
    topic = TOPICS.get(query.lower())
    if topic:
        url, params = f"{TOP_URL}/headlines/section/topic/{topic}", dict(LOCALE)
    elif query:
        url, params = SEARCH_URL, {"q": query, **LOCALE}
    else:
        url, params = TOP_URL, dict(LOCALE)
    try:
        root = ET.fromstring(get(url, params).content)
    except ET.ParseError as exc:
        raise WebError("El servicio de noticias devolvió una respuesta inválida.") from exc

    headlines: list[Headline] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        # Google agrega " - Fuente" al final del título.
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].strip()
        published = ""
        raw_date = item.findtext("pubDate")
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date).astimezone().strftime("%d/%m %H:%M")
            except (TypeError, ValueError):
                published = ""
        if title:
            headlines.append(Headline(title=title, source=source, published=published, url=item.findtext("link") or ""))
        if len(headlines) >= limit:
            break
    return headlines
