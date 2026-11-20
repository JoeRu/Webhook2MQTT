"""Webhook2MQTT: forward JSON webhooks to an MQTT broker.

Served by gunicorn as an app factory: ``gunicorn 'main:create_app()'``.
All configuration comes from environment variables (see .env.example).
"""
import datetime
import hmac
import json
import logging
import os

import paho.mqtt.client as mqtt
from flask import Flask, Response, jsonify, request

logger = logging.getLogger("Webhook2MQTT")

TRUE_VALUES = ('1', 'true', 'yes', 'on')


def _env_bool(env, name, default):
    value = env.get(name)
    if value is None or value.strip() == '':
        return default
    return value.strip().lower() in TRUE_VALUES


def setup_logging(level_name):
    level = getattr(logging, level_name.upper(), None)
    if not isinstance(level, int):
        level = logging.INFO
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
    logger.setLevel(level)


def load_config(env=None):
    env = os.environ if env is None else env
    server = env.get('MQTT_SERVER')
    if not server:
        raise RuntimeError("Please set environment variable MQTT_SERVER")
    qos = int(env.get('MQTT_QOS') or 0)
    if qos not in (0, 1, 2):
        raise RuntimeError("MQTT_QOS must be 0, 1 or 2")
    return {
        'server': server,
        'port': int(env.get('MQTT_PORT') or 1883),
        'topic': (env.get('MQTT_PATH') or 'webhook').rstrip('/'),
        'user': env.get('MQTT_USER') or None,
        'password': env.get('MQTT_PASSWORD') or None,
        'tls': _env_bool(env, 'MQTT_TLS', False),
        'ca_certs': env.get('MQTT_CA_CERTS') or None,
        'qos': qos,
        'retain': _env_bool(env, 'MQTT_RETAIN', True),
        'report_errors': _env_bool(env, 'MQTT_REPORT_ERRORS', False),
        'publish_timeout': float(env.get('MQTT_PUBLISH_TIMEOUT') or 5),
        'allow_subtopics': _env_bool(env, 'ALLOW_SUBTOPICS', False),
        'timestamp_field': env.get('TIMESTAMP_FIELD', 'timestamp'),
        'token': env.get('WEBHOOK_TOKEN') or None,
        'log_level': env.get('LOG_LEVEL') or 'INFO',
    }


def create_mqtt_client(cfg):
    """Create a long-lived MQTT client that reconnects in the background."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if cfg['user']:
        client.username_pw_set(cfg['user'], cfg['password'])
    if cfg['tls']:
        client.tls_set(ca_certs=cfg['ca_certs'])
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            logger.error("MQTT connection refused: %s", reason_code)
        else:
            logger.info("Connected to MQTT broker %s:%s", cfg['server'], cfg['port'])

    def on_disconnect(client, userdata, flags, reason_code, properties):
        logger.warning("Disconnected from MQTT broker: %s", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect_async(cfg['server'], cfg['port'], keepalive=60)
    client.loop_start()
    return client


def valid_subtopic(subtopic):
    """Reject MQTT wildcards, empty/relative segments and control characters."""
    if any(c in subtopic for c in '+#') or any(ord(c) < 32 for c in subtopic):
        return False
    return all(part not in ('', '.', '..') for part in subtopic.split('/'))


def create_app(env=None, mqtt_client=None):
    cfg = load_config(env)
    setup_logging(cfg['log_level'])

    logger.info("MQTT broker %s:%s, topic '%s', qos=%s, retain=%s",
                cfg['server'], cfg['port'], cfg['topic'], cfg['qos'], cfg['retain'])
    if cfg['user']:
        logger.info("MQTT authentication enabled")
    if cfg['tls']:
        logger.info("MQTT TLS enabled")
    if cfg['report_errors']:
        logger.info("MQTT errors are reported to webhook senders (HTTP 503)")
    if cfg['allow_subtopics']:
        logger.info("Sub-topics via request path enabled")
    if cfg['token']:
        logger.info("Webhook token authentication enabled")
    else:
        logger.warning("WEBHOOK_TOKEN is not set — webhook endpoint is unauthenticated")

    client = mqtt_client if mqtt_client is not None else create_mqtt_client(cfg)
    expected_auth = 'Bearer {}'.format(cfg['token']).encode() if cfg['token'] else None

    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1 MB limit
    app.extensions['mqtt_client'] = client

    def publish(topic, payload):
        """Publish payload; return True on success (or when not waiting)."""
        info = client.publish(topic, payload, qos=cfg['qos'], retain=cfg['retain'])
        if not cfg['report_errors']:
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error("Failed to publish MQTT message: %s", mqtt.error_string(info.rc))
            return True
        try:
            info.wait_for_publish(timeout=cfg['publish_timeout'])
        except (ValueError, RuntimeError) as e:
            logger.error("Failed to publish MQTT message: %s", e)
            return False
        if not info.is_published():
            logger.error("Timed out publishing MQTT message after %ss", cfg['publish_timeout'])
            return False
        return True

    @app.route('/healthz', methods=['GET'])
    def healthz():
        connected = client.is_connected()
        return jsonify(mqtt_connected=connected), (200 if connected else 503)

    @app.route('/', methods=['POST'], defaults={'subtopic': ''})
    @app.route('/<path:subtopic>', methods=['POST'])
    def respond(subtopic):
        if expected_auth is not None:
            auth_header = request.headers.get('Authorization', '').encode()
            if not hmac.compare_digest(auth_header, expected_auth):
                logger.warning("Unauthorized request from %s", request.remote_addr)
                return Response(status=401)

        topic = cfg['topic']
        if subtopic:
            if not cfg['allow_subtopics'] or not valid_subtopic(subtopic):
                return Response(status=404)
            topic = f'{topic}/{subtopic}'

        params = request.get_json(silent=True)
        if params is None:
            logger.warning("Received non-JSON or empty request body from %s", request.remote_addr)
            return Response(status=400)
        if not isinstance(params, dict):
            params = {'payload': params}
        if cfg['timestamp_field'] and cfg['timestamp_field'] not in params:
            params[cfg['timestamp_field']] = datetime.datetime.now().astimezone().isoformat()

        payload = json.dumps(params)
        logger.info("Webhook from %s -> '%s' (%d bytes, keys: %s)",
                    request.remote_addr, topic, len(payload), ', '.join(sorted(params)))
        logger.debug("Payload: %s", payload)

        if not publish(topic, payload):
            return Response(status=503)
        return Response(status=200)

    return app
