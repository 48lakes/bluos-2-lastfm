import pylast
import logging

log = logging.getLogger("lastfm")

# Custom error classes so callers can branch
class LastFMAuthError(Exception): ...
class LastFMRateLimitError(Exception): ...
class LastFMNetworkError(Exception): ...
class LastFMUnknownError(Exception): ...

class LastFMClient:
    """Thin wrapper over pylast for update-now-playing + scrobbling."""

    def __init__(self, api_key: str, api_secret: str, session_key: str | None,
                 username: str | None, password_md5: str | None):
        if session_key:
            log.info("Using Last.fm session key auth")
            self.network = pylast.LastFMNetwork(
                api_key=api_key,
                api_secret=api_secret,
                session_key=session_key,
            )
        elif username and password_md5:
            log.info("Using Last.fm username + MD5 password auth")
            self.network = pylast.LastFMNetwork(
                api_key=api_key,
                api_secret=api_secret,
                username=username,
                password_hash=password_md5,
            )
        else:
            raise ValueError("Missing Last.fm credentials")

    def update_now_playing(self, *, artist: str, title: str, album: str | None, duration: int | None):
        """Push a Now Playing update. Non-fatal on failure."""
        try:
            self.network.update_now_playing(
                artist=artist, title=title, album=album, duration=duration
            )
        except pylast.WSError as e:
            # NOW PLAYING failures aren't critical; log at DEBUG
            log.debug("update_now_playing failed: code=%s msg=%s", getattr(e, "code", "?"), e)
        except Exception as e:
            log.debug("update_now_playing network error: %s", e)

    def scrobble(self, *, artist: str, title: str, album: str | None, duration: int | None, timestamp: int):
        """Submit a scrobble to Last.fm with a start timestamp (unix seconds)."""
        try:
            self.network.scrobble(
                artist=artist, title=title, album=album, duration=duration, timestamp=timestamp
            )
        except pylast.WSError as e:
            code = getattr(e, "code", None)
            msg = str(e)
            # Map common Last.fm error codes
            if code in (9, 4, 14):  # 9=Invalid session, 4=Auth failed, 14=Token expired
                raise LastFMAuthError(msg)
            elif code in (29,):  # 29=Rate limit exceeded
                raise LastFMRateLimitError(msg)
            else:
                raise LastFMUnknownError(f"Last.fm API error {code}: {msg}")
        except Exception as e:
            raise LastFMNetworkError(str(e))
