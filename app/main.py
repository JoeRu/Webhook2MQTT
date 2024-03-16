from flask import Flask, request, Response
import threading
import logging
import paho.mqtt.client as mqtt
import json
import datetime

import os
#$env:MQTT_SERVER='192.168.176.6'
#-------------Output Logger
# create logger
logger = logging.getLogger("Webhook2MQTT")
#logger.setLevel(logging.INFO)
logger.setLevel(logging.INFO)
# create console handler with a higher log level
ch = logging.StreamHandler()
#ch.setLevel(logging.INFO)
ch.setLevel(logging.INFO)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
#formatter = logging.Formatter('%(levelname)s - %(message)s')
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(ch)
#-------------Output Logger

if 'MQTT_SERVER' in os.environ:
    mqtt_server = os.environ['MQTT_SERVER']
else:
    logger.error("Please set environment-Variable for MQTT_SERVER")
    os.exit()
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


app = Flask(__name__)

def workit(params):
    logger.info("workit:")
    logger.info(params) 
    params['timestamp'] = datetime.datetime.now().isoformat()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    client.connect(mqtt_server, mqtt_port, 60)
    client.publish(mqtt_path, json.dumps(params),qos=0,retain=True)
    client.disconnect()

@app.route('/', methods=['POST'])
def respond():
    logger.info(request)
    myparams=request.get_json()
    x = threading.Thread(target=workit, args=(myparams,))
    x.start()
    return Response(status=200)

#app.run (host = "localhost", port = 5050)

