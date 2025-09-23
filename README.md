# BluOS → Last.fm Middleware

A small middleware service that bridges [BluOS](https://bluos.net/) playback (tested on NAD C368 with BluOS module) to [Last.fm](https://www.last.fm/) scrobbling.  
Runs as a lightweight Docker container on your local network (tested on Synology DSM).

## ✨ Features

- Polls a BluOS device every few seconds (`/Status` endpoint over HTTP).
- Parses current playback (artist, title, album, elapsed, duration, state).
- Sends **Now Playing** and **Scrobbles** to Last.fm using the official API.
- Tracks playback internally (only scrobbles after 50% or 4 minutes).
- **Offline caching**: if Last.fm is unreachable, scrobbles are queued and retried later (persistent JSON file).
- **Notifications**: optional push via [Gotify](https://gotify.net/), generic webhook, or both.
- Informative logs (`INFO` level is human-readable; `DEBUG` shows full HTTP traffic).

---

## 🛠 Requirements

- A BluOS device accessible on your LAN (e.g. NAD C368 with BluOS module).
- Last.fm API account:
  - Create an API key & secret: https://www.last.fm/api/account/create
  - Authenticate once to get a **session key** (see below).
- Docker + Docker Compose (tested on Synology DSM 7).
- (Optional) Gotify server for push notifications (can run on the same NAS).

---

## 📦 Setup

### 1. Clone and build
```bash
git clone https://github.com/yourname/bluos-lastfm-middleware.git
cd bluos-lastfm-middleware
cp sample.env .env
```

### 2. Configure `.env`

Edit `.env` with your values:

```dotenv
# --- BluOS ---
BLUOS_HOST=192.168.1.50      # IP of your BluOS device
BLUOS_PORT=11000             # default for BluOS

# --- Last.fm ---
LASTFM_API_KEY=xxxxxxxxxxxx
LASTFM_API_SECRET=xxxxxxxxxxxx
LASTFM_SESSION_KEY=xxxxxxxxxxxx   # see "Obtain Session Key" below

# --- Polling & Logs ---
POLL_INTERVAL=3
LOG_LEVEL=INFO

# --- Scrobble cache ---
SCROBBLE_CACHE_PATH=/data/scrobble_queue.json
SCROBBLE_CACHE_LIMIT=500

# --- Gotify (optional notifications) ---
GOTIFY_URL=http://192.168.1.2:8080
GOTIFY_TOKEN=your-gotify-app-token
GOTIFY_PRIORITY=5
GOTIFY_MIN_LEVEL=WARNING
APP_TAG=BluOS→Last.fm
```

### 3. Obtain a Last.fm Session Key

Last.fm now requires an API key flow. Steps:

1. Visit:  
   ```
   https://www.last.fm/api/auth/?api_key=YOUR_API_KEY&cb=http://localhost/callback
   ```
2. Log in and allow access. Copy the token from the callback URL.
3. Run this helper **once** inside the container to exchange the token for a session key:

   ```bash
   docker compose exec -T bluos-lastfm python - <<'PY'
   import os, pylast, hashlib
   API_KEY=os.getenv("LASTFM_API_KEY")
   API_SECRET=os.getenv("LASTFM_API_SECRET")
   TOKEN="paste-token-here"
   sg = pylast.SessionKeyGenerator(pylast.LastFMNetwork(api_key=API_KEY, api_secret=API_SECRET))
   sk = sg.get_session_key(TOKEN)
   print("SESSION KEY:", sk)
   PY
   ```

4. Put that `SESSION KEY` into `.env` as `LASTFM_SESSION_KEY`.

### 4. Start the container

```bash
docker compose up -d --build
docker compose logs -f bluos-lastfm
```

---

## 🔔 Notifications

### Gotify (recommended)
- Install Gotify server (Docker or Synology package).  
- In Gotify, create an App → copy its token.  
- Put `GOTIFY_URL` and `GOTIFY_TOKEN` into `.env`.  
- On startup, the app will send a "Bridge started" message.  
- You’ll also get alerts on:
  - Last.fm auth errors (e.g., expired session key),
  - network issues (scrobbles cached),
  - queue high-water mark warnings.

### Generic Webhook (optional)
If you’d rather use Slack/Discord/Teams/Gotify via webhook:
- Set `NOTIFY_WEBHOOK_URL=...` in `.env`.
- Messages are sent as JSON with `title`, `message`, `level`, and `extra`.

---

## 🔍 How It Works

1. **Polling BluOS**  
   Every `POLL_INTERVAL` seconds, the app fetches `/Status` from your BluOS device.  
   Example fields:  
   ```xml
   <status>
     <artist>Messa</artist>
     <title1>Fire on the Roof</title1>
     <album>The Spin</album>
     <state>play</state>
     <secs>205</secs>
     <totlen>273</totlen>
   </status>
   ```

2. **PlaybackTracker**  
   Tracks which song is playing, elapsed time, and ensures scrobbling rules:
   - at least 50% played OR 4 minutes, whichever comes first.

3. **Last.fm client**  
   - Sends *Now Playing* immediately when playback starts.
   - Sends *Scrobble* when thresholds are met.
   - Uses API key + session key auth.

4. **Error handling**  
   - If Last.fm is unreachable or rate-limited, scrobbles are added to a persistent queue (`/data/scrobble_queue.json`).
   - Queue drains automatically once connectivity returns.
   - Auth errors trigger immediate notification (won’t queue, since you must fix credentials).

5. **Notifications**  
   - Startup ping.  
   - Auth errors → Gotify / webhook alert.  
   - Queue high-water mark (>80% full) → warning alert.  
   - Other errors are logged at INFO/WARNING level.

---

## 🗂 Project Structure

```
app/
  main.py             # Entry point, polling loop, orchestration
  bluos.py            # BluOS client (fetch + parse XML)
  lastfm_client.py    # Last.fm client wrapper with error classes
  state.py            # PlaybackTracker (when to scrobble)
  scrobble_queue.py   # Persistent capped queue
  notifier_gotify.py  # Gotify notifier
  notifier.py         # (optional) generic webhook notifier
Dockerfile
docker-compose.yml
sample.env
README.md
```

---

## 📖 Logs

With `LOG_LEVEL=INFO`, you’ll see entries like:

```
2025-09-23 18:26:14 [INFO] bluos-lastfm: Parsed: state=play artist=Messa title=Fire on the Roof album=The Spin elapsed=205 duration=273
2025-09-23 18:26:14 [INFO] bluos-lastfm: Scrobbled: Messa — Fire on the Roof [The Spin]
2025-09-23 18:26:14 [INFO] bluos-lastfm: Drained 3 cached scrobbles. Queue size now 0
```

---

## 🧩 Development Notes

- Python 3.11 inside container.  
- Key dependencies:
  - `pylast` (Last.fm API)
  - `httpx` (HTTP client)
  - `requests` (notifications)
- State is persisted only in `/data/scrobble_queue.json`.  
- Safe to rebuild / restart without losing offline scrobbles.  

---

## 📜 License

MIT License — see [LICENSE](LICENSE).
