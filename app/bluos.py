import requests
import xml.etree.ElementTree as ET
from dataclasses import dataclass

@dataclass
class BluOSStatus:
    title: str | None
    artist: str | None
    album: str | None
    duration: int | None  # seconds
    secs: int | None      # elapsed seconds
    state: str | None     # 'play', 'pause', 'stop'

class BluOSClient:
    """
    Minimal BluOS client that fetches and parses /Status (XML).
    Uses recursive lookup + tag fallbacks. Matches your XML: name/title1, artist, album, secs, totlen, state.
    """
    def __init__(self, host: str, port: int = 11000, timeout: int = 5):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout

    def _findtext_any(self, root: ET.Element, *tags: str):
        for t in tags:
            el = root.find(f".//{t}")
            if el is not None and el.text:
                return el.text.strip()
        return None

    def _to_int(self, s):
        if s is None: return None
        try:
            return int(float(s))
        except Exception:
            return None

    def get_status(self) -> BluOSStatus | None:
        try:
            resp = requests.get(f"{self.base}/Status", timeout=self.timeout)
            resp.raise_for_status()
        except Exception:
            return None

        try:
            root = ET.fromstring(resp.text)

            # ——— Your device’s fields ———
            # title appears as <name> and also as <title1>; fallbacks included
            title  = self._findtext_any(root, "name", "title1", "title", "song")
            artist = self._findtext_any(root, "artist", "title2")
            album  = self._findtext_any(root, "album", "title3")

            secs     = self._findtext_any(root, "secs", "elapsed", "position", "time")
            duration = self._findtext_any(root, "totlen", "duration", "total", "trackLength", "length")

            state = self._findtext_any(root, "state", "status", "mode")
            state = state.lower() if state else None

            return BluOSStatus(
                title=title,
                artist=artist,
                album=album,
                duration=self._to_int(duration),
                secs=self._to_int(secs),
                state=state,
            )
        except Exception:
            return None
