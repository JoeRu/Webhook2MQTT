from flask import Flask, request, Response
import threading
import logging
import paho.mqtt.client as mqtt
import json
import datetime
import os
import sys

#-------------Output Logger
# create logger
logger = logging.getLogger("Webhook2MQTT")
logger.setLevel(logging.INFO)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(ch)
#-------------Output Logger

if 'MQTT_SERVER' in os.environ:
    mqtt_server = os.environ['MQTT_SERVER']
else:
    logger.error("Please set environment-Variable for MQTT_SERVER")
    sys.exit(1)
logger.info("set MQTT_SERVER to {}".format(mqtt_server))

if 'MQTT_PORT' in os.environ:
    mqtt_port = int(os.environ['MQTT_PORT'])
else:
    mqtt_port = 1883
logger.info("set MQTT_PORT to {}".format(mqtt_port))

if 'MQTT_PATH' in os.environ:
    mqtt_path = os.environ['MQTT_PATH']
else:
    mqtt_path = 'webhook'
logger.info("set mqtt-path to '{}'".format(mqtt_path))

mqtt_user = os.environ.get('MQTT_USER')
mqtt_password = os.environ.get('MQTT_PASSWORD')
mqtt_tls = os.environ.get('MQTT_TLS', '').lower() in ('1', 'true', 'yes')
if mqtt_user:
    logger.info("MQTT authentication enabled")
if mqtt_tls:
    logger.info("MQTT TLS enabled")

webhook_token = os.environ.get('WEBHOOK_TOKEN')
if webhook_token:
    logger.info("Webhook token authentication enabled")
else:
    logger.warning("WEBHOOK_TOKEN is not set — webhook endpoint is unauthenticated")

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1 MB limit


def workit(params):
    logger.info("workit:")
    logger.info(params)
    try:
        params['timestamp'] = datetime.datetime.now().isoformat()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if mqtt_user:
            client.username_pw_set(mqtt_user, mqtt_password)
        if mqtt_tls:
            client.tls_set()
        client.connect(mqtt_server, mqtt_port, 60)
        client.publish(mqtt_path, json.dumps(params), qos=0, retain=True)
        client.disconnect()
    except Exception as e:
        logger.error("Failed to publish MQTT message: {}".format(e))


@app.route('/', methods=['POST'])
def respond():
    logger.info(request)
    if webhook_token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header != 'Bearer {}'.format(webhook_token):
            logger.warning("Unauthorized request from {}".format(request.remote_addr))
            return Response(status=401)
    myparams = request.get_json()
    if myparams is None:
        logger.warning("Received non-JSON or empty request body")
        return Response(status=400)
    x = threading.Thread(target=workit, args=(myparams,))
    x.start()
    return Response(status=200)

