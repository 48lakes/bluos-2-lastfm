"""
Gotify notifier: POST /message with app token.

Env:
- GOTIFY_URL (e.g., http://nas:8080)
- GOTIFY_TOKEN (App token)
- GOTIFY_PRIORITY (1..10; default 5)
- GOTIFY_MIN_LEVEL (DEBUG|INFO|WARNING|ERROR|CRITICAL; default WARNING)
"""

from __future__ import annotations
import os
import logging
import requests

_LEVELS = {"DEBUG":10,"INFO":20,"WARNING":30,"ERROR":40,"CRITICAL":50}

class GotifyNotifier:
    def __init__(self, url: str | None, token: str | None, min_level: str = "WARNING", default_priority: int = 5, app_tag: str = "BluOS→Last.fm"):
        self.url = url.rstrip("/") if url else None
        self.token = token.strip() if token else None
        self.min_level = _LEVELS.get(min_level.upper(), 30)
        self.default_priority = default_priority
        self.app_tag = app_tag

    def send(self, level: str, title: str, message: str, extra: dict | None = None, priority: int | None = None):
        if not self.url or not self.token:
            return
        lvl = _LEVELS.get(level.upper(), 30)
        if lvl < self.min_level:
            return

        body = {
            "title": f"{self.app_tag}: {title}",
            "message": message if not extra else f"{message}\n\n{extra}",
            "priority": priority if priority is not None else self.default_priority,
        }
        headers = {"X-Gotify-Key": self.token}
        try:
            requests.post(f"{self.url}/message", json=body, headers=headers, timeout=5)
        except Exception as e:
            logging.getLogger("notifier").debug("Gotify send failed: %s", e)

def from_env() -> GotifyNotifier:
    url = os.getenv("GOTIFY_URL")
    token = os.getenv("GOTIFY_TOKEN")
    prio = int(os.getenv("GOTIFY_PRIORITY", "5"))
    min_level = os.getenv("GOTIFY_MIN_LEVEL", "WARNING")
    app_tag = os.getenv("APP_TAG", "BluOS→Last.fm")
    return GotifyNotifier(url, token, min_level=min_level, default_priority=prio, app_tag=app_tag)
