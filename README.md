# Webhook2MQTT
This enable a pretty easy python/flask Application that takes all incoming (json) message as a webhook/API Integration (for example for netatmo.com or telegram or thethingsnetwork.com (TTN)) and forwards it to a given mqtt-adress.

## Setup
change in docker-compose the environment variable to connect to your mqtt server
```docker-compose
MQTT_SERVER: '192.168.176.6'
MQTT_PORT: 1883
MQTT_PATH: 'webhook'
```
Change the desired "listening-port/server-ip" of your webports:
```docker-compose
"127.0.0.1:5058:80"
```
i strongly suggest to put some reverse-proxy ahead of your installation. 

## Architecture

Pretty simple - a flask app initiating a new thread to forward the expected json object to mqtt. No pathes implemented.
Checkout app/main.py - it is really simple - so modifications are easy.

## Test
a simple curl test should do the trick - you should see the json-object in your mqtt-browser
```bash
curl -X POST -H "Content-Type: application/json" -d '{"username":"abc","password":"abc"}' http://localhost:5058/
```
## remarks

The webhook uses [meinheld-gunicorn-flask](https://github.com/tiangolo/meinheld-gunicorn-flask-docker) which should be able to be running in a productive environment. 
