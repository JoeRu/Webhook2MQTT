import json
from unittest import mock

import paho.mqtt.client as mqtt
import pytest

import main

BASE_ENV = {'MQTT_SERVER': 'broker'}


class FakeInfo:
    def __init__(self, rc=mqtt.MQTT_ERR_SUCCESS, published=True, raises=None):
        self.rc = rc
        self._published = published
        self._raises = raises

    def wait_for_publish(self, timeout=None):
        if self._raises:
            raise self._raises

    def is_published(self):
        return self._published


def make_client(info=None, connected=True):
    client = mock.Mock()
    client.publish.return_value = info or FakeInfo()
    client.is_connected.return_value = connected
    return client


def make_app(client=None, **env):
    client = client or make_client()
    app = main.create_app({**BASE_ENV, **env}, mqtt_client=client)
    return app.test_client(), client


def published(client):
    (topic, payload), kwargs = client.publish.call_args
    return topic, json.loads(payload), kwargs


def test_missing_server_raises():
    with pytest.raises(RuntimeError):
        main.load_config({})


def test_publishes_object_with_defaults():
    http, client = make_app()
    r = http.post('/', json={'a': 1})
    assert r.status_code == 200
    topic, payload, kwargs = published(client)
    assert topic == 'webhook'
    assert payload['a'] == 1
    assert 'timestamp' in payload
    assert kwargs == {'qos': 0, 'retain': True}


def test_existing_timestamp_is_kept():
    http, client = make_app()
    http.post('/', json={'timestamp': 'original'})
    assert published(client)[1]['timestamp'] == 'original'


def test_timestamp_field_configurable_and_disableable():
    http, client = make_app(TIMESTAMP_FIELD='received_at')
    http.post('/', json={})
    assert 'received_at' in published(client)[1]
    http, client = make_app(TIMESTAMP_FIELD='')
    http.post('/', json={})
    assert published(client)[1] == {}


@pytest.mark.parametrize('body', [[1, 2], 'text', 42, True])
def test_non_object_json_is_wrapped(body):
    http, client = make_app()
    assert http.post('/', json=body).status_code == 200
    assert published(client)[1]['payload'] == body


def test_invalid_json_is_rejected():
    http, client = make_app()
    r = http.post('/', data='not json', content_type='application/json')
    assert r.status_code == 400
    client.publish.assert_not_called()


def test_token_required():
    http, client = make_app(WEBHOOK_TOKEN='secret')
    assert http.post('/', json={}).status_code == 401
    assert http.post('/', json={}, headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert http.post('/', json={}, headers={'Authorization': 'Bearer secret'}).status_code == 200
    assert client.publish.call_count == 1


def test_qos_and_retain_configurable():
    http, client = make_app(MQTT_QOS='1', MQTT_RETAIN='false')
    http.post('/', json={})
    assert published(client)[2] == {'qos': 1, 'retain': False}


def test_invalid_qos_rejected():
    with pytest.raises(RuntimeError):
        main.load_config({**BASE_ENV, 'MQTT_QOS': '3'})


def test_errors_hidden_by_default():
    http, _ = make_app(make_client(FakeInfo(rc=mqtt.MQTT_ERR_NO_CONN)))
    assert http.post('/', json={}).status_code == 200


@pytest.mark.parametrize('info', [
    FakeInfo(rc=mqtt.MQTT_ERR_NO_CONN, raises=RuntimeError('no conn')),
    FakeInfo(published=False),
])
def test_errors_reported_when_enabled(info):
    http, _ = make_app(make_client(info), MQTT_REPORT_ERRORS='true')
    assert http.post('/', json={}).status_code == 503


def test_success_when_reporting_enabled():
    http, _ = make_app(MQTT_REPORT_ERRORS='true')
    assert http.post('/', json={}).status_code == 200


def test_subtopics_disabled_by_default():
    http, client = make_app()
    assert http.post('/netatmo', json={}).status_code == 404
    client.publish.assert_not_called()


def test_subtopics_enabled():
    http, client = make_app(ALLOW_SUBTOPICS='1', MQTT_PATH='home/webhook/')
    assert http.post('/ttn/device1', json={}).status_code == 200
    assert published(client)[0] == 'home/webhook/ttn/device1'


@pytest.mark.parametrize('path', ['/a/+/b', '/a/%23', '/a//b', '/a/../b', '/a/%01'])
def test_invalid_subtopics_rejected(path):
    http, client = make_app(ALLOW_SUBTOPICS='1')
    assert http.post(path, json={}).status_code == 404
    client.publish.assert_not_called()


def test_healthz():
    http, _ = make_app(make_client(connected=True))
    r = http.get('/healthz')
    assert r.status_code == 200 and r.get_json() == {'mqtt_connected': True}
    http, _ = make_app(make_client(connected=False))
    assert http.get('/healthz').status_code == 503


def test_payload_not_logged_at_info(caplog):
    http, _ = make_app()
    with caplog.at_level('INFO', logger='Webhook2MQTT'):
        http.post('/', json={'password': 'hunter2'})
    assert 'hunter2' not in caplog.text
