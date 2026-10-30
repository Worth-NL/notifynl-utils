import json
import uuid
from unittest.mock import ANY, Mock

import pytest
from freezegun import freeze_time

from notifications_utils.clients.audit.audit_client import (
    AUDIT_ROUTING_KEY,
    LEVEL_ERROR,
    LEVEL_INFO,
    TAG_GEBRUIKSLOGGING,
    TAG_SECURITYLOGGING,
    TAG_VERWERKINGSLOGGING,
    AuditClient,
    AuditCode,
    AuditLog,
    Key,
    subject_bsn,
    subject_email,
)


@pytest.fixture
def mocked_producer(mocker):
    mocker.patch("notifications_utils.clients.audit.audit_client.Connection")
    producer = Mock()
    mocker.patch("notifications_utils.clients.audit.audit_client.Producer", return_value=producer)
    return producer


def build_audit_client(app, enabled=True):
    client = AuditClient()
    app.config["AUDIT_ENABLED"] = enabled
    app.config["AUDIT_BROKER_URL"] = "amqp://notify:notify@localhost:5672/notify"
    app.config["AUDIT_SERVICE_NAME"] = "notify_api"
    client.init_app(app)
    return client


@pytest.fixture
def enabled_audit_client(app, mocked_producer):
    return build_audit_client(app, enabled=True)


@pytest.fixture
def disabled_audit_client(app, mocked_producer):
    return build_audit_client(app, enabled=False)


def published_payload(mocked_producer):
    args, kwargs = mocked_producer.publish.call_args
    return json.loads(args[0]), kwargs


def test_init_app_sets_app_audit_client(app, enabled_audit_client):
    assert app.audit_client is enabled_audit_client
    assert enabled_audit_client.active is True
    assert enabled_audit_client.service_name == "notify_api"
    assert enabled_audit_client.routing_key == AUDIT_ROUTING_KEY


def test_init_app_raises_when_enabled_without_broker_url(app, mocked_producer):
    client = AuditClient()
    app.config["AUDIT_ENABLED"] = True
    app.config["AUDIT_BROKER_URL"] = None
    with pytest.raises(ValueError):
        client.init_app(app)


def test_disabled_client_does_not_publish(disabled_audit_client, mocked_producer):
    disabled_audit_client.log(AuditCode.RESULTAAT_NOTIFICATIEMAIL_VERSTUREN_GELUKT)
    assert not mocked_producer.publish.called


@freeze_time("2023-12-15 10:30:45.123456")
def test_log_publishes_expected_auditlog_message(enabled_audit_client, mocked_producer):
    enabled_audit_client.log(
        AuditCode.RESULTAAT_NOTIFICATIE_AANMAKEN,
        items={Key.SUBJECT: subject_email("test@example.com")},
    )

    payload, kwargs = published_payload(mocked_producer)

    assert payload == {
        "id": ANY,
        "tijdstip": "2023-12-15T10:30:45.123456Z",
        "level": LEVEL_INFO,
        "code": 2041,
        "message": "Resultaat notificatie aanmaken",
        "service": "notify_api",
        "tags": [TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING],
        "items": {"subject": {"identificatieType": "EMAIL", "identificatieNummer": None, "email": "test@example.com"}},
    }
    # id is een geldige UUID
    uuid.UUID(payload["id"])

    assert kwargs["routing_key"] == AUDIT_ROUTING_KEY
    assert kwargs["content_type"] == "application/json"
    assert kwargs["delivery_mode"] == 2
    assert kwargs["retry"] is True


def test_level_and_tags_default_from_audit_code(enabled_audit_client, mocked_producer):
    # Zoals Java AuditLog.builder(AuditCode): level en tags komen uit de code
    enabled_audit_client.log(AuditCode.RESULTAAT_NOTIFICATIEMAIL_VERSTUREN_MISLUKT)

    payload, _ = published_payload(mocked_producer)
    assert payload["code"] == 2052
    assert payload["level"] == LEVEL_ERROR
    assert payload["tags"] == [TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING, TAG_SECURITYLOGGING]
    assert payload["message"] == "Resultaat notificatiemail versturen mislukt"


def test_log_with_overridden_message_and_items(enabled_audit_client, mocked_producer):
    enabled_audit_client.log(
        AuditCode.RESULTAAT_NOTIFICATIEMAIL_VERSTUREN_MISLUKT,
        message="Notificatiemail versturen mislukt: authenticatie mislukt",
        items={Key.KANAAL: "EMAIL", Key.REDEN: "SMTPAuthenticationError"},
    )

    payload, _ = published_payload(mocked_producer)
    assert payload["message"] == "Notificatiemail versturen mislukt: authenticatie mislukt"
    assert payload["items"] == {"kanaal": "EMAIL", "reden": "SMTPAuthenticationError"}


def test_unknown_items_key_raises_value_error(enabled_audit_client, mocked_producer):
    with pytest.raises(ValueError, match="message_id"):
        enabled_audit_client.log(
            AuditCode.RESULTAAT_NOTIFICATIEMAIL_VERSTUREN_GELUKT,
            items={"message_id": "abc-123"},
        )
    assert not mocked_producer.publish.called


def test_subject_helpers_match_java_subject():
    assert subject_email("a@b.nl") == {"identificatieType": "EMAIL", "identificatieNummer": None, "email": "a@b.nl"}
    assert subject_bsn("123456789") == {"identificatieType": "BSN", "identificatieNummer": "123456789", "email": None}


def test_audit_code_enum_matches_java_enum_samples():
    assert AuditCode.START_NOTIFICATIEOPDRACHT_ONTVANGEN.code == 2010
    assert AuditCode.RESULTAAT_BOUNCE_EVENT_MISLUKT.code == 2092
    assert AuditCode.RESULTAAT_BOUNCE_EVENT_MISLUKT.level == LEVEL_ERROR
    assert AuditCode.RESULTAAT_BOUNCE_EVENT_MISLUKT.tags == [TAG_SECURITYLOGGING]
    assert AuditCode.RESULTAAT_AFLEVERING_EMAIL_KANAALADRES.code == 2170
    assert AuditCode.ZOEKVRAAG_FUNCTIONELE_LOG_GELUKT.code == 6011
    codes = [ac.code for ac in AuditCode]
    assert len(codes) == len(set(codes))


def test_log_audit_log_publishes_full_object(enabled_audit_client, mocked_producer):
    audit_log = AuditLog(
        code=2170,
        message="Resultaat aflevering e-mail kanaaladres",
        service="dsn_ontvanger",
        items={Key.NOTIFICATIE_ID: "550e8400-e29b-41d4-a716-446655440001"},
    )
    enabled_audit_client.log_audit_log(audit_log)

    payload, _ = published_payload(mocked_producer)
    assert payload["code"] == 2170
    assert payload["service"] == "dsn_ontvanger"
    assert payload["id"] == audit_log.id
    assert payload["tijdstip"] == audit_log.tijdstip


def test_publish_failure_is_logged_and_does_not_raise(app, enabled_audit_client, mocked_producer, mocker):
    mocked_producer.publish.side_effect = OSError("broker down")
    mock_logger = mocker.patch.object(app.logger, "exception")
    app.statsd_client = Mock()

    enabled_audit_client.log(AuditCode.RESULTAAT_NOTIFICATIE_AANMAKEN_MISLUKT)

    mock_logger.assert_called_once()
    app.statsd_client.incr.assert_called_once_with("clients.audit.error")


def test_each_auditlog_gets_unique_id(enabled_audit_client, mocked_producer):
    enabled_audit_client.log(AuditCode.RESULTAAT_NOTIFICATIE_AANMAKEN)
    enabled_audit_client.log(AuditCode.RESULTAAT_NOTIFICATIE_AANMAKEN)

    first = json.loads(mocked_producer.publish.call_args_list[0].args[0])
    second = json.loads(mocked_producer.publish.call_args_list[1].args[0])
    assert first["id"] != second["id"]
