# Telegram Analysis API

Service that fetches the latest messages from Telegram channels or groups using Telethon, optionally relays them to a webhook, and exposes an HTTP API.

The project ships with a Docker image ready for production deployment (e.g. Dokploy + Traefik) and relies on a pre-authorised Telethon session file that is mounted into the container.

---

## Project layout

```
app/
   main.py               # Flask entrypoint + HTTP routes
   config.py             # Settings dataclass loading environment variables
   services/
      telegram.py         # Shared Telethon client, history fetcher, listener
      webhook.py          # Webhook header parsing and async delivery
ChannelUsers.py         # Helper script (example usage outside the API)
data/                   # Session files, downloaded media, last webhook payload
```

The Flask app instantiates `TelegramService` and `WebhookService` once at startup so that every HTTP request, background listener, and webhook call share the same Telethon client and configuration.

---

## Requirements

- Telegram API credentials: `api_id` and `api_hash` from https://my.telegram.org.
- A phone number or username that already joined the target channels.
- Python 3.11+ if you plan to run locally, or Docker if you only deploy.
- An authenticated Telethon session file (generated with `python -m app.auth`).

### Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_API_ID` | ✅ | Telegram API ID |
| `TELEGRAM_API_HASH` | ✅ | Telegram API hash |
| `TELEGRAM_PHONE` | ✅ | Phone number including country code |
| `TELEGRAM_USERNAME` | ✅ | Username used for the Telethon session |
| `TELEGRAM_SESSION_FILE` | ➖ | Session file name or absolute path (defaults to `TELEGRAM_USERNAME` inside `/app/data`) |
| `TELEGRAM_SESSION_DIR` | ➖ | Directory that contains the session file (defaults to `/app/data`) |
| `DATA_DIR` | ➖ | Base directory for persisted data such as `last_response.json` (defaults to `TELEGRAM_SESSION_DIR`) |
| `TELEGRAM_MEDIA_DIR` | ➖ | Directory where downloaded media (photos/documents) are stored (defaults to `/app/data/media`) |
| `MEDIA_BASE_URL` | ➖ | Public base URL that maps to `TELEGRAM_MEDIA_DIR` for exposing downloadable links |
| `MEDIA_URL_TTL_SECONDS` | ➖ | Seconds a signed `/media/<token>` link remains valid (defaults to `3600`) |
| `MEDIA_SIGNING_SECRET` | ➖ | Secret used to sign media tokens (defaults to `API_KEY`) |
| `WEBHOOK_HEADERS` | ➖ | Extra headers (JSON or comma-separated) sent with every webhook POST |
| `TELEGRAM_LISTENER_ENTITY` | ➖ | Channel/group to monitor for live updates (username like `@channel` or numeric ID) |
| `LISTENER_WEBHOOK_URL` | ➖ | Webhook that receives live updates (defaults to `N8N_WEBHOOK_URL` when omitted) |
| `LISTENER_WEBHOOK_HEADERS` | ➖ | Additional headers applied only to the listener webhook (merges with `WEBHOOK_HEADERS`) |
| `API_KEY` | ✅ | Shared secret required in the `X-API-Key` header |
| `N8N_WEBHOOK_URL` | ➖ | Default webhook invoked when `webhook_url` is omitted |

Copy `.env.example` to `.env`, fill it with your values, and keep the file out of version control if it contains secrets.

---

## Local setup (optional but recommended)

1. **Copy the sample env file**
   ```bash
   cp .env.example .env
   ```
   Update the new `.env` with your credentials, webhook defaults, and listener options.
2. **Create and activate a virtualenv**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Authorise Telethon**
   ```bash
   python -m app.auth
   ```
   Enter the OTP you receive from Telegram (or provide `TELEGRAM_LOGIN_CODE` in the environment). The command writes the session file, typically `@username.session`, to the project root.
4. *(Optional)* **Run locally with Docker Compose**
   ```bash
   docker compose up --build
   ```
   - Hit `http://localhost:8000/trigger` with the API key to ensure everything works.
   - Stop the stack with `Ctrl+C` when you are done.

The generated session file must accompany your deployment; without it Telethon will refuse to run inside the container.

---

## Running the API locally

With the virtualenv active and `.env` configured, start the Flask development server:

```bash
python -m app.main
```

The app listens on `http://127.0.0.1:5000/`. Sample requests:

```bash
curl -X POST http://127.0.0.1:5000/trigger \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: ${API_KEY}" \
  -d '{"entity": "@telegram", "limit": 2}'

curl "http://127.0.0.1:5000/message?entity=@telegram&message_id=123" \
  -H "X-API-Key: ${API_KEY}"
```

Set `TELEGRAM_LISTENER_ENTITY` (and optionally `LISTENER_WEBHOOK_URL`) in the environment before launching the server if you want the background listener to stream new messages to your webhook while you develop locally. Disable the Flask reloader (`FLASK_ENV=production python -m app.main`) to avoid spawning two listeners.

---

## Production deployment on Dokploy (step by step)

1. **Prepare the session file**
   - Generate it locally (see the previous section).
   - Upload it to your VPS, e.g. `scp ./@username.session root@your-vps:/etc/dokploy/applications/<app-id>/session/`.
2. **Create a bind mount** in Dokploy → your application → *Advanced Options → Volumes / Mounts*:
   - Mount Type: `Bind Mount`.
   - Host Path: `/etc/dokploy/applications/<app-id>/session` (folder containing the session).
   - Container Path: `/app/data` (the default path the app expects).
3. **Configure environment variables**
   - Dokploy → *Environment*.
   - Add the variables listed in the table (at minimum the Telegram credentials and `API_KEY`).
   - Add `TELEGRAM_SESSION_FILE=@username.session` if your session file uses the `@…` filename.
   - Save the changes.
4. **Deployment settings**
   - Source: connect the Git repository (`PejarRu/telegram-analysis-fork`).
   - Build Type: Dockerfile.
   - Dockerfile path: `.` (root of the repo).
   - Internal Port: `8000` (Gunicorn listens there).
   - Domain: assign the domain or subdomain you want (e.g. `api-telegram.example.com`).
5. **Deploy / Redeploy**
   - Trigger the deployment.
   - Wait until Dokploy reports `Docker build completed` and `1/1` replicas.
6. **Validate the container**
   - SSH into the VPS and run:
   - Optional request from inside the container:
     ```bash
     docker ps --filter label=com.docker.swarm.service.name=<service-name>
     docker exec -i <container-id> python - <<'PY'
     import urllib.request
     resp = urllib.request.urlopen('http://127.0.0.1:8000/', timeout=5)
     print(resp.status, resp.read().decode())
     PY
     ```
7. **Smoke test from the internet**
   ```bash
   # Using X-API-Key header
   curl -X POST https://your-domain/trigger \
     -H 'Content-Type: application/json' \
     -H 'X-API-Key: <your api key>' \
     -d '{"entity": "@telegram", "limit": 1}'
   
   # Or using Authorization Bearer token
   curl -X POST https://your-domain/trigger \
     -H 'Content-Type: application/json' \
     -d '{"entity": "@telegram", "limit": 1}'
   ```
   Expect a JSON array with the latest messages. A `500` with `Telegram client not authorized` means the session file was not found; a `502` usually means the internal port is misconfigured.

If you edit environment variables or mounts in Dokploy, click *Redeploy* afterwards so the container picks up the new configuration.

---

## Real-time listener

When you want the service to push every new message from a specific Telegram channel or group to a webhook without polling the `/trigger` endpoint, set the following variables:

```bash
TELEGRAM_LISTENER_ENTITY=@your_channel
LISTENER_WEBHOOK_URL=https://n8n.domain.com/webhook/telegram-live  # optional, falls back to N8N_WEBHOOK_URL
# Optional auth headers
# WEBHOOK_HEADERS={"Authorization": "Bearer <token>"}
# LISTENER_WEBHOOK_HEADERS={"Authorization": "Bearer <live-token>"}
```

On startup the app spawns a daemon thread that keeps a Telethon client connected, listens for `NewMessage` events, downloads associated media (using the `TELEGRAM_MEDIA_DIR`/`MEDIA_BASE_URL` settings if applicable), and POSTs the payload to the configured webhook. The last pushed payload is also stored in `data/last_response.json` for inspection through the root endpoint when authenticated.

> ℹ️ Running the Flask development server with the reloader may instantiate the listener twice. For production use Gunicorn (as provided in the Dockerfile) or disable the reloader when testing the listener locally.

---

## API reference

### POST `/trigger`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `entity` | string | ✅ | Channel username (`@channel`) or numeric ID |
| `webhook_url` | string | ➖ | Destination webhook. Defaults to `N8N_WEBHOOK_URL` if set |
| `limit` | integer | ➖ | Number of messages to fetch (default 2) |

Headers: `Content-Type: application/json`, and either `X-API-Key: <API_KEY>` or `Authorization: Bearer <API_KEY>`.

Returns: JSON array with the requested messages. When `webhook_url` is provided, each message is also POSTed individually to that URL.

### GET `/message`

Fetch a single message by its Telegram ID while keeping the response format identical to the `/trigger` endpoint (i.e. an array of messages).

| Query | Type | Required | Description |
| --- | --- | --- | --- |
| `entity` | string | ✅ | Channel username (`@channel`) or numeric ID |
| `message_id` | integer | ✅ | Telegram message ID to fetch |
| `webhook_url` | string | ➖ | Optional webhook override. Defaults to `N8N_WEBHOOK_URL` |

Authentication works the same as `/trigger` (API key header or Bearer token). The endpoint returns `404` when the message is not found.

### GET `/media/<token>`

Every media attachment now includes a `signed_url` that points to `/media/<token>`. Tokens are signed with `MEDIA_SIGNING_SECRET` (defaults to `API_KEY`) and expire after `MEDIA_URL_TTL_SECONDS` (60 minutes by default). You can safely embed the relative link in dashboards or forward it with your webhook payloads; unauthenticated users will only access the file while the token remains valid.

If you already expose `TELEGRAM_MEDIA_DIR` through a CDN using `MEDIA_BASE_URL`, both URLs are present in the payload (`signed_url` and absolute `url`) so you can pick the best option for your flow.

### GET `/`
Health endpoint. Without authentication (`X-API-Key` header or `Authorization: Bearer` token) it responds with `{"status": "ok"}` for simple uptime checks. When properly authenticated it returns the last webhook payload (`last_response.json`) or `{"message": "No response yet"}` if nothing has been processed yet.

---

## Maintenance tips

- **Disk usage on the VPS**: run `df -h /` regularly. If usage is high, prune old images/containers (`docker system prune`) or move artefacts such as session backups elsewhere.
- **Logs**: `docker service logs <service-name> -f` shows the combined stdout/stderr of all replicas.
- **Updating the app**: push to `master` (or the branch Dokploy tracks) and click *Redeploy*. Ensure you have a recent session file if the account changes.
- **Security**: keep the API key secret and rotate it periodically. Limit who can access Dokploy and the VPS.

---

## Troubleshooting quick reference
- **`502 Bad Gateway` from Traefik** → internal port is not set to `8000`, or the service is restarting.
- **`Telegram client not authorized`** → mount the session file in `/app/data` and set `TELEGRAM_SESSION_FILE`.
- **Container unhealthy** → check the health check by running the inline Python snippet above; confirm Telegram credentials in the environment.

---

With this checklist you can replicate the deployment on any VPS with Dokploy and Traefik.
