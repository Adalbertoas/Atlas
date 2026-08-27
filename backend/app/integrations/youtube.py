"""Cliente de YouTube Data API v3 (necesita YOUTUBE_API_KEY — gratis,
Google Cloud Console: habilitar "YouTube Data API v3" y crear una API key).

Solo búsqueda: no descarga ni reproduce nada, devuelve título/canal/link.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

_TIMEOUT = 10


class YouTubeNotConfigured(Exception):
    """YOUTUBE_API_KEY vacía — falta configurar .env."""


@dataclass
class YouTubeVideo:
    title: str
    channel: str
    url: str
    published_at: str


def search_youtube(query: str, api_key: str, max_results: int = 5) -> list[YouTubeVideo]:
    if not api_key:
        raise YouTubeNotConfigured(
            "YOUTUBE_API_KEY vacía. Consigue una gratis en Google Cloud Console "
            "(habilita 'YouTube Data API v3' y creá una API key) y ponela en backend/.env."
        )

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "key": api_key,
        },
        timeout=_TIMEOUT,
    )
    response.raise_for_status()

    videos = []
    for item in response.json().get("items", []):
        # A pesar de type="video", YouTube a veces cuela un resultado de
        # canal (ej. buscar "Bruno Mars" trae su canal oficial primero) —
        # visto en vivo, rompía con KeyError en "videoId". Se lo salteamos.
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = item["snippet"]
        videos.append(
            YouTubeVideo(
                title=snippet["title"],
                channel=snippet["channelTitle"],
                url=f"https://www.youtube.com/watch?v={video_id}",
                published_at=snippet["publishedAt"],
            )
        )
    return videos
