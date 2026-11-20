# AGENT.md

Guidance for AI coding agents (and humans) working in this repository.

## What this project is

Webhook2MQTT is a tiny HTTP → MQTT bridge. It accepts JSON `POST` requests
(e.g. from Netatmo, Telegram, The Things Network) and republishes the body to an
MQTT topic, typically consumed by Home Assistant / Node-RED.

The whole application is one file: `app/main.py` (Flask + paho-mqtt v2, served
by gunicorn as an app factory: `gunicorn 'main:create_app()'`).

## Repository layout

| Path                   | Purpose                                                     |
|------------------------|-------------------------------------------------------------|
| `app/main.py`          | The entire app: config, logging, MQTT client, Flask routes  |
| `tests/`               | pytest suite (Flask test client + mocked MQTT client)       |
| `requirements.txt`     | Pinned runtime deps: Flask, paho-mqtt, gunicorn             |
| `requirements-dev.txt` | Pinned dev deps: pytest, ruff                               |
| `pyproject.toml`       | ruff + pytest configuration                                 |
| `Dockerfile`           | `python:3.12-slim`, non-root user, healthcheck, port 80     |
| `docker-compose.yml`   | Example deployment; Traefik and syslog blocks are opt-in    |
| `.env.example`         | Documented env vars; copy to `.env` (git-ignored)           |
| `.github/`             | CI (ruff, pytest, docker build) and Dependabot              |

## Architecture

- `load_config(env)` reads all env vars into a dict and raises `RuntimeError` on
  invalid config (missing `MQTT_SERVER`, bad `MQTT_QOS`).
- `create_app(env=None, mqtt_client=None)` builds the Flask app. Tests pass a
  plain dict for `env` and a mock for `mqtt_client`; nothing happens at import.
- `create_mqtt_client(cfg)` creates **one long-lived client per gunicorn worker**
  (`connect_async` + `loop_start`, auto-reconnect 1–30 s).

### Request flow (`POST /` or `POST /<subtopic>`)

1. Body limit 1 MB (`MAX_CONTENT_LENGTH`).
2. If `WEBHOOK_TOKEN` is set: `Authorization: Bearer <token>` checked with
   `hmac.compare_digest`, else `401`.
3. Sub-path → `404` unless `ALLOW_SUBTOPICS` is on and the path has no `+`, `#`,
   empty/`.`/`..` segments or control characters; topic becomes
   `MQTT_PATH/<subtopic>`.
4. Invalid/empty JSON → `400`. Non-object JSON is wrapped as `{"payload": ...}`.
5. `TIMESTAMP_FIELD` (default `timestamp`) is added with local, tz-aware ISO
   time **only if absent**; empty value disables it.
6. Publish with `MQTT_QOS` / `MQTT_RETAIN`.
   - `MQTT_REPORT_ERRORS=false` (default): don't wait, always `200`; failures are
     only logged. Deliberate: some providers (e.g. Netatmo) disable webhooks that
     fail repeatedly.
   - `MQTT_REPORT_ERRORS=true`: wait up to `MQTT_PUBLISH_TIMEOUT` s, `503` on
     failure.

`GET /healthz` returns `{"mqtt_connected": bool}` with `200`/`503`.

Logging: INFO logs sender, topic, size and keys only; full payload at DEBUG
(`LOG_LEVEL`).

## Configuration

See `.env.example` for the authoritative, documented list.

## Running locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest && ruff check app tests

cd app && MQTT_SERVER=localhost WEBHOOK_TOKEN=dev flask --app 'main:create_app()' run -p 5058
mosquitto_sub -h localhost -t 'webhook/#' -v
curl -X POST -H 'Authorization: Bearer dev' -H 'Content-Type: application/json' \
     -d '{"hello":"world"}' http://localhost:5058/
```

Docker: `cp .env.example .env`, edit, then `docker compose up --build`.

## Conventions and constraints for agents

- Keep it small. The project's value is that `main.py` is readable in one sitting;
  don't add frameworks or layers without a clear reason.
- Use the paho-mqtt **v2** callback API (`mqtt.CallbackAPIVersion.VERSION2`).
- Keep deps pinned exactly; Dependabot proposes updates.
- New config goes through env vars in `load_config`, documented in
  `.env.example`, `docker-compose.yml` (commented if optional) and the README
  table. Defaults must preserve existing behaviour for current deployments.
- Never commit `.env` or secrets. Don't log payloads or credentials above DEBUG.
- Every behaviour change needs a test in `tests/test_main.py`; CI runs ruff,
  pytest and a Docker build.
- Container port stays 80 (existing port mappings/proxies depend on it).
- License is GPL-3.0.

## Remaining improvement ideas

1. Make the token mandatory unless `ALLOW_UNAUTHENTICATED=1` is set.
2. Support provider-specific secrets: configurable header name
   (`WEBHOOK_TOKEN_HEADER`, e.g. Telegram's `X-Telegram-Bot-Api-Secret-Token`)
   or a `?token=` query parameter.
3. Optional MQTT client certificate/key for mutual TLS.
4. With `MQTT_REPORT_ERRORS=false` and QoS 0, messages sent while the broker is
   down are dropped; a small bounded in-memory buffer could replay them on
   reconnect.
5. Publish a prebuilt image (GHCR) from CI on tags.
