from dataclasses import dataclass

# -------------------------
# Stateless identity for a track
# -------------------------
@dataclass(frozen=True)
class TrackIdentity:
    artist: str | None
    title: str | None
    album: str | None
    duration: int | None

class PlaybackTracker:
    """Tracks playback state and decides when to scrobble based on elapsed time.

    Last.fm guideline: scrobble at halfway or 240s (4min), whichever comes first.
    We also ensure we only scrobble once per TrackIdentity.
    """

    def __init__(self):
        self.current: TrackIdentity | None = None
        self.scrobbled: bool = False
        self.elapsed: int = 0
        self.state: str | None = None  # 'play', 'pause', 'stop'

    def update(self, *, identity: TrackIdentity, state: str | None, elapsed: int | None):
        # Reset scrobble state on track change
        if identity != self.current:
            self.current = identity
            self.scrobbled = False
            self.elapsed = 0

        self.state = state
        if elapsed is not None:
            self.elapsed = max(self.elapsed, int(elapsed))

    def threshold(self) -> int:
        # Default fallback threshold when duration is unknown: 240s
        if not self.current or not self.current.duration:
            return 240
        return min(240, int(self.current.duration / 2))

    def should_scrobble(self) -> bool:
        if not self.current:
            return False
        if self.scrobbled:
            return False
        if self.state != "play":
            return False
        return self.elapsed >= self.threshold()

    def mark_scrobbled(self):
        self.scrobbled = True
