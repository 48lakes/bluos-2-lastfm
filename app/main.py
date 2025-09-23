import os
import time
import logging
from datetime import datetime, timezone

from bluos import BluOSClient, BluOSStatus
from lastfm_client import (
    LastFMClient, LastFMAuthError, LastFMNetworkError,
    LastFMRateLimitError, LastFMUnknownError
)
from state import TrackIdentity, PlaybackTracker
from scrobble_queue import ScrobbleQueue
from notifier import from_env as webhook_notifier_from_env
from notifier_gotify import from_env as gotify_notifier_from_env

# -------------------------
# Configuration via ENV VARS
# -------------------------
BLUOS_HOST = os.getenv("BLUOS_HOST", "127.0.0.1")
BLUOS_PORT = int(os.getenv("BLUOS_PORT", "11000"))
POLL_INTERVAL = max(1, int(os.getenv("POLL_INTERVAL", "3")))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_SECRET = os.getenv("LASTFM_API_SECRET")
LASTFM_SESSION_KEY = os.getenv("LASTFM_SESSION_KEY")
LASTFM_USERNAME = os.getenv("LASTFM_USERNAME")
LASTFM_PASSWORD_MD5 = os.getenv("LASTFM_PASSWORD_MD5")

SCROBBLE_CACHE_PATH = os.getenv("SCROBBLE_CACHE_PATH", "/data/scrobble_queue.json")
SCROBBLE_CACHE_LIMIT = int(os.getenv("SCROBBLE_CACHE_LIMIT", "500"))

# -------------------------
# Logging setup
# -------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,  # ensure our config is used even if libs pre-configure logging
)
log = logging.getLogger("bluos-lastfm")

def main():
    # Validate Last.fm configuration up-front for clear errors
    if not LASTFM_API_KEY or not LASTFM_API_SECRET:
        raise SystemExit("LASTFM_API_KEY and LASTFM_API_SECRET are required")

    if not (LASTFM_SESSION_KEY or (LASTFM_USERNAME and LASTFM_PASSWORD_MD5)):
        raise SystemExit("Provide LASTFM_SESSION_KEY or LASTFM_USERNAME + LASTFM_PASSWORD_MD5")

    # Initialize clients
    blu = BluOSClient(BLUOS_HOST, BLUOS_PORT)
    lfm = LastFMClient(
        api_key=LASTFM_API_KEY,
        api_secret=LASTFM_API_SECRET,
        session_key=LASTFM_SESSION_KEY,
        username=LASTFM_USERNAME,
        password_md5=LASTFM_PASSWORD_MD5,
    )
    queue = ScrobbleQueue(SCROBBLE_CACHE_PATH, SCROBBLE_CACHE_LIMIT)
    webhook = webhook_notifier_from_env()     # ok if NOTIFY_WEBHOOK_URL is empty
    gotify = gotify_notifier_from_env()       # ok if GOTIFY_URL/TOKEN missing

    def alert(level: str, title: str, message: str, extra: dict | None = None):
        # Fan out to both; each will ignore if not configured or below min_level
        try: webhook.send(level, title, message, extra)
        except Exception: pass
        try: gotify.send(level, title, message, extra)
        except Exception: pass

    tracker = PlaybackTracker()
    log.info("Starting BluOS → Last.fm bridge. Poll interval: %ss", POLL_INTERVAL)
    log.info("BluOS device: %s:%s | Cache: %s (limit=%s, size=%s)",
             BLUOS_HOST, BLUOS_PORT, SCROBBLE_CACHE_PATH, SCROBBLE_CACHE_LIMIT, queue.size())
    
    # 🔔 Send startup notification here
    alert("INFO", "Bridge started",
          f"Polling {BLUOS_HOST}:{BLUOS_PORT}; cache path {SCROBBLE_CACHE_PATH}.")

    while True:
        try:
            status: BluOSStatus | None = blu.get_status()
        except Exception as e:
            log.warning("BluOS status fetch failed: %s", e)
            time.sleep(POLL_INTERVAL)
            continue

        if status is not None:
            log.info("Parsed: state=%s artist=%s title=%s album=%s elapsed=%s duration=%s",
                     status.state, status.artist, status.title, status.album, status.secs, status.duration)
        else:
            log.info("Parsed: status=None (unreachable or XML parse failed)")
            time.sleep(POLL_INTERVAL)
            continue

        # Build a stable track identity to avoid duplicate scrobbles
        identity = TrackIdentity(
            artist=status.artist,
            title=status.title,
            album=status.album,
            duration=int(status.duration) if status.duration else None,
        )

        tracker.update(identity=identity, state=status.state, elapsed=status.secs)

        # Only act when playback is active and we have meaningful metadata
        if status.state == "play" and status.artist and status.title:
            # 1) Update Now Playing (best-effort)
            try:
                lfm.update_now_playing(
                    artist=status.artist,
                    title=status.title,
                    album=status.album,
                    duration=int(status.duration) if status.duration else None,
                )
            except Exception:
                # update_now_playing is best-effort; errors already logged at debug level inside client
                pass

            # Prepare the scrobble payload (used whether we scrobble now or enqueue)
            now = datetime.now(timezone.utc).timestamp()
            started_at = int(now - (status.secs or 0))
            scrobble_payload = dict(
                artist=status.artist,
                title=status.title,
                album=status.album,
                duration=int(status.duration) if status.duration else None,
                timestamp=started_at,
            )

            # 2) Scrobble when threshold crossed, otherwise nothing yet
            if tracker.should_scrobble():
                try:
                    lfm.scrobble(**scrobble_payload)
                    tracker.mark_scrobbled()
                    log.info("Scrobbled: %s — %s%s",
                             status.artist, status.title, f" [{status.album}]" if status.album else "")
                    # Drain any backlog after a successful scrobble
                    drained = 0
                    for pending in queue.drain_iter():
                        try:
                            lfm.scrobble(**pending)
                            drained += 1
                        except LastFMAuthError as e:
                            # Stop draining on auth error (user must fix config); re-enqueue the item we just popped
                            queue.enqueue(pending)
                            alert("ERROR", "Last.fm auth error while draining",
                                        str(e), {"pending_queue_size": queue.size()})
                            break
                        except (LastFMNetworkError, LastFMRateLimitError, LastFMUnknownError) as e:
                            # Put it back and stop draining; try later
                            queue.enqueue(pending)
                            log.info("Draining paused due to error: %s; queue size=%s", e, queue.size())
                            break
                    if drained:
                        log.info("Drained %s cached scrobbles. Queue size now %s", drained, queue.size())
                except LastFMAuthError as e:
                    # Auth issue — notify and do NOT cache (user must re-auth)
                    log.error("Scrobble failed (auth): %s", e)
                    alert("ERROR", "Last.fm authentication failed", str(e), scrobble_payload)
                except LastFMRateLimitError as e:
                    # Rate-limited — enqueue for later
                    queue.enqueue(scrobble_payload)
                    log.info("Rate limited; queued scrobble. queue=%s", queue.size())
                except LastFMNetworkError as e:
                    # Network problem — enqueue for later
                    queue.enqueue(scrobble_payload)
                    log.info("Network error; queued scrobble. queue=%s", queue.size())
                except LastFMUnknownError as e:
                    # Unknown API issue — enqueue and notify at WARNING
                    queue.enqueue(scrobble_payload)
                    log.warning("Unknown Last.fm error; queued scrobble. queue=%s err=%s", queue.size(), e)
                    alert("WARNING", "Last.fm scrobble error", str(e), scrobble_payload)
        else:
            log.debug("Playback not in 'play' state or missing metadata; skipping.")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Shutting down…")
