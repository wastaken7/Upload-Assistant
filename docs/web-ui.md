# Upload Assistant Web UI

This folder contains the optional Web UI for Upload Assistant.

The Web UI is a small Flask app that:
- Serves a browser UI (`/`) for selecting content and running Upload Assistant.
- Exposes a JSON API under `/api/*`.

## Requirements

### Python
- Python 3.9+
- The main Upload Assistant dependencies (see the repo root `requirements.txt`)
- Web UI Python dependencies:
  - `flask`
  - `flask-cors`

Note: `werkzeug` is installed automatically as a dependency of `flask`.

### Docker image
If you use the `-webui` Docker image / Dockerfile that installs Flask, you do **not** need to install extra Python packages manually.

## Quick start (Docker)

1. Use an image that includes the Web UI dependencies (the `-webui` tagged image).
2. Set `ENABLE_WEB_UI=true`.
3. Configure **browse roots** (required): set `UA_BROWSE_ROOTS` to a comma-separated list of directories inside the container that you want the UI to be able to browse and execute against.

Example (compose-style, localhost-only by default):

```yaml
ports:
  # Localhost-only on the Docker host (recommended default).
  # Change to "0.0.0.0:5000:5000" (or "5000:5000") to allow access from other devices.
  # Note: "other devices" typically means LAN, but it can become WAN exposure if you port-forward, enable UPnP,
  # run a reverse proxy, or otherwise expose the host publicly.
  - "127.0.0.1:5000:5000"
environment:
  - ENABLE_WEB_UI=true
  - UA_WEBUI_HOST=0.0.0.0
  - UA_WEBUI_PORT=5000
  - UA_BROWSE_ROOTS=/data/torrents,/Upload-Assistant/tmp
  # Optional but strongly recommended if exposed beyond localhost:
  # - UA_WEBUI_USERNAME=admin
  # - UA_WEBUI_PASSWORD=change-me
  # Optional: only needed if you serve the UI from a different origin/domain.
  # - UA_WEBUI_CORS_ORIGINS=https://your-ui-host
```

Make sure your volume mounts align with `UA_BROWSE_ROOTS`.
For example, if you mount your torrent directory as `/data/torrents`, include `/data/torrents` in `UA_BROWSE_ROOTS`.

## Quick start (local / bare metal)

From the repo root:

```bash
python -m pip install -r requirements.txt
python -m pip install flask flask-cors
python web_ui/server.py
```

Then open the URL printed at startup (by default: `http://127.0.0.1:5000`).

To enable browsing/execution you must also set `UA_BROWSE_ROOTS` (see below).

## Configuration (environment variables)

### `UA_BROWSE_ROOTS` (required)
Comma-separated list of directories that the Web UI is allowed to browse and use for execution.

- If unset/empty, the Web UI will **deny browsing/execution** (fails closed).
- Each entry is trimmed and converted to an absolute path.
- Requests are restricted to paths under one of these roots (including symlink-escape protection).

Examples:

Linux:
```bash
export UA_BROWSE_ROOTS=/data/torrents,/mnt/media
```

Windows (PowerShell):
```powershell
$env:UA_BROWSE_ROOTS = "D:\torrents,D:\media"
```

### `UA_WEBUI_HOST` / `UA_WEBUI_PORT`
Controls where the server listens.

- `UA_WEBUI_HOST` default: `127.0.0.1` (localhost only)
- `UA_WEBUI_PORT` default: `5000`

### `UA_WEBUI_USERNAME` / `UA_WEBUI_PASSWORD`
Enables HTTP Basic Auth.

- If either variable is set, **both** must be set or authentication will fail.
- When configured, auth is applied to **all** routes (including `/` and static files), except `/api/health`.

### `UA_WEBUI_CORS_ORIGINS`
Optional comma-separated allowlist of origins for `/api/*` routes.

- If unset/empty, CORS is not configured.
- Example: `UA_WEBUI_CORS_ORIGINS=https://your-ui-host,https://another-host`

## API Endpoints

All API routes return JSON responses and use HTTP Basic Auth if `UA_WEBUI_USERNAME` / `UA_WEBUI_PASSWORD` are configured (except `/api/health`).

### `GET /api/health`

Health check endpoint (unauthenticated).

**Response:**
```json
{
  "status": "healthy",
  "success": true,
  "message": "Upload Assistant Web UI is running"
}
```

### `GET /api/browse`

Browse filesystem paths under `UA_BROWSE_ROOTS`.

**Query Parameters:**
- `path` (optional): The directory path to browse. Defaults to empty/root.

**Response (success):**
```json
{
  "items": [
    {
      "name": "My Movie (2024)",
      "path": "/data/torrents/My Movie (2024)",
      "type": "folder",
      "children": []
    },
    {
      "name": "example.mkv",
      "path": "/data/torrents/example.mkv",
      "type": "file",
      "children": null
    }
  ],
  "success": true,
  "path": "/data/torrents",
  "count": 2
}
```

**Error Responses:**
- `400`: Invalid path specified (path not under `UA_BROWSE_ROOTS` or symlink escape attempt)
- `403`: Permission denied
- `500`: Internal error

### `POST /api/execute`

Executes `upload.py` against a validated path and streams output via Server-Sent Events (SSE).

**Request Body:**
```json
{
  "path": "/data/torrents/My Movie (2024)",
  "args": "--debug --unattended"
}
```

**Response:** `text/event-stream` (Server-Sent Events)

**Event types:**
- `output`: stdout/stderr line from the running process
- `exit`: process terminated (includes exit code)
- `error`: execution failed

**Example events:**
```
data: {"type":"output","data":"[INFO] Starting upload...\n","session_id":"abc123"}

data: {"type":"exit","code":0,"session_id":"abc123"}
```

**Error Responses:**
- `400`: Invalid request (missing path, path not under `UA_BROWSE_ROOTS`)
- `500`: Execution error

### `POST /api/input`

Sends user input to a running Upload Assistant process (for interactive prompts).

**Request Body:**
```json
{
  "session_id": "abc123",
  "input": "1"
}
```

**Response (success):**
```json
{
  "success": true
}
```

**Error Responses:**
- `404`: No active process for the specified session
- `400`: Process not running
- `500`: Failed to write input

### `POST /api/kill`

Terminates a running Upload Assistant process.

**Request Body:**
```json
{
  "session_id": "abc123"
}
```

**Response (success):**
```json
{
  "success": true,
  "message": "Process terminated"
}
```

**Error Responses:**
- `404`: No active process for the specified session
- `500`: Kill error

## Security notes

- Do not expose the Web UI to the public internet.
- Docker: access scope is controlled by your published port. Using `ports: "5000:5000"` exposes the UI to other devices (typically LAN); adding a router port-forward / UPnP / reverse proxy can expose it to the internet.
- If you allow access from other devices, set `UA_WEBUI_USERNAME` and `UA_WEBUI_PASSWORD`.
- Keep `UA_BROWSE_ROOTS` as narrow as possible (only the directories you need).

## Troubleshooting

- Browsing returns “Invalid path specified”: ensure `UA_BROWSE_ROOTS` is set and includes the directory you’re trying to access.
- Can’t reach the UI from another machine (Docker): ensure `UA_WEBUI_HOST=0.0.0.0` and your compose `ports` publishes on the host LAN interface (e.g. `0.0.0.0:5000:5000` or `5000:5000`).
