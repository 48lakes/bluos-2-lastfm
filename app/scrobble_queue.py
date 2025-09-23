"""
Persistent, capped scrobble queue.

- Stores pending scrobbles on disk (JSON file), so we don't lose plays on network errors.
- Enforces a max length (SCROBBLE_CACHE_LIMIT) to avoid unbounded growth.
- API is minimal: enqueue(), drain_iter(), size().
"""

from __future__ import annotations
import json
import os
import threading
from collections import deque
from typing import Deque, Dict, Iterator, Any

class ScrobbleQueue:
    def __init__(self, path: str, maxlen: int = 500):
        self.path = path
        self.maxlen = maxlen
        self._lock = threading.Lock()
        self._q: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self._load()

    # -------- persistence --------
    def _load(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data[-self.maxlen:]:
                            self._q.append(item)
        except Exception:
            # Corrupt or unreadable file? Start fresh.
            self._q.clear()

    def _save(self) -> None:
        # Write atomically to avoid corruption
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(list(self._q), f, ensure_ascii=False)
        os.replace(tmp, self.path)

    # -------- public API --------
    def enqueue(self, item: Dict[str, Any]) -> None:
        with self._lock:
            if len(self._q) == self.maxlen:
                # Drop oldest when at capacity
                self._q.popleft()
            self._q.append(item)
            self._save()

    def drain_iter(self) -> Iterator[Dict[str, Any]]:
        """
        Pops items from the left (oldest-first) one by one,
        saving after each pop so we don't lose progress.
        """
        while True:
            with self._lock:
                if not self._q:
                    return
                item = self._q.popleft()
                self._save()
            yield item

    def size(self) -> int:
        with self._lock:
            return len(self._q)
