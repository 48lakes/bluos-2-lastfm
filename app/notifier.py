"""
Simple webhook notifier.

- Sends a POST with JSON body to NOTIFY_WEBHOOK_URL.
- Respects NOTIFY_MIN_LEVEL (e.g., WARNING and above).
- Non-blocking best-effort: failures are logged but do not crash the app.
"""

from __future__ import annotations
import os
import logging
import requests

_LEVELS = {
    "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50
}

class Notifier:
    def __init__(self, webhook_url: str | None, min_level: str = "WARNING", app_tag: str = "BluOS→Last.fm"):
        self.webhook_url = webhook_url.strip() if webhook_url else None
        self.min_level = _LEVELS.get(min_level.upper(), 30)
        self.app_tag = app_tag

    def send(self, level: str, title: str, message: str, extra: dict | None = None):
        if not self.webhook_url:
            return
        lvl = _LEVELS.get(level.upper(), 30)
        if lvl < self.min_level:
            return

        payload = {
            "level": level.upper(),
            "title": f"{self.app_tag}: {title}",
            "message": message,
            "extra": extra or {},
        }
        try:
            # Most webhooks accept JSON; Slack/Discord-compatible webhooks also work.
            requests.post(self.webhook_url, json=payload, timeout=5)
        except Exception as e:
            logging.getLogger("notifier").debug("Notification send failed: %s", e)

def from_env() -> Notifier:
    return Notifier(
        webhook_url=os.getenv("NOTIFY_WEBHOOK_URL"),
        min_level=os.getenv("NOTIFY_MIN_LEVEL", "WARNING"),
        app_tag=os.getenv("APP_TAG", "BluOS→Last.fm"),
    )
