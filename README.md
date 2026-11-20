# Webhook2MQTT

A small Python/Flask app that accepts incoming JSON webhooks (e.g. from netatmo.com,
Telegram or The Things Network) and forwards them to an MQTT topic, for example for
Home Assistant or Node-RED.

## Setup

```bash
cp .env.example .env     # set at least MQTT_SERVER, ideally WEBHOOK_TOKEN
docker compose up -d --build
```

By default the service listens on `127.0.0.1:5058`. I strongly suggest putting a
reverse proxy (with HTTPS) in front of it; `docker-compose.yml` contains a
commented Traefik example.

## Configuration

All settings are environment variables; see [`.env.example`](.env.example) for the
full documented list. The most important ones:

| Variable             | Default     | Description                                                   |
|----------------------|-------------|---------------------------------------------------------------|
| `MQTT_SERVER`        | (required)  | Broker host                                                   |
| `MQTT_PORT`          | `1883`      | Broker port                                                   |
| `MQTT_PATH`          | `webhook`   | Topic to publish to                                           |
| `MQTT_USER` / `MQTT_PASSWORD` | – | Broker credentials                                          |
| `MQTT_TLS` / `MQTT_CA_CERTS`  | off / – | TLS to the broker, optional custom CA                    |
| `MQTT_QOS` / `MQTT_RETAIN`    | `0` / `true` | Publish options                                     |
| `MQTT_REPORT_ERRORS` | `false`     | `true`: answer `503` if the message could not be published    |
| `ALLOW_SUBTOPICS`    | `false`     | `true`: `POST /a/b` publishes to `MQTT_PATH/a/b`              |
| `TIMESTAMP_FIELD`    | `timestamp` | Receive time added if missing; empty disables it              |
| `WEBHOOK_TOKEN`      | –           | Require `Authorization: Bearer <token>`                       |
| `LOG_LEVEL`          | `INFO`      | `DEBUG` also logs full payloads                               |

## Behaviour

- `POST /` with a JSON body → published to `MQTT_PATH`. JSON objects are forwarded
  as-is (plus the timestamp field); other JSON values are wrapped as
  `{"payload": <value>, "timestamp": ...}`.
- Responses: `200` ok, `400` no/invalid JSON, `401` wrong token, `404` unknown or
  invalid path, `503` broker failure (only with `MQTT_REPORT_ERRORS=true`).
- `GET /healthz` → `200 {"mqtt_connected": true}` or `503`; used by the Docker
  healthcheck.
- Each gunicorn worker keeps one persistent MQTT connection and reconnects
  automatically.

## Test

```bash
curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
     -d '{"hello":"world"}' http://localhost:5058/
```

You should see the JSON object in your MQTT browser.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest && ruff check app tests
```

See [`AGENT.md`](AGENT.md) for architecture notes and conventions.
