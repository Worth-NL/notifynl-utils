import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from flask import current_app
from kombu import Connection, Producer, Queue

AUDIT_ROUTING_KEY = "bewaar-audit-log"

LEVEL_DEBUG = "DEBUG"
LEVEL_INFO = "INFO"
LEVEL_ERROR = "ERROR"

TAG_GEBRUIKSLOGGING = "gebruikslogging"
TAG_SECURITYLOGGING = "securitylogging"
TAG_VERWERKINGSLOGGING = "verwerkingslogging"


class Key:
    SUBJECT = "subject"
    INGELOGDE_GEBRUIKER = "ingelogdeGebruiker"
    GEBRUIKER = "gebruiker"
    NAAM = "naam"
    KANAAL = "kanaal"
    ADRES = "adres"
    KANAAL_ADRESSEN = "kanaalAdressen"
    NOTIFICATIE_STATUS = "notificatieStatus"
    NOTIFICATIE_ID = "notificatieId"
    TEMPLATE = "template"
    TEMPLATE_NAMEN = "templateNamen"
    TEMPLATE_NAAM = "templateNaam"
    TEMPLATE_DATA = "templateData"
    TEMPLATE_VERSIE = "templateVersie"
    BATCH_REFERENTIE = "batchReferentie"
    OPDRACHT_REFERENTIE = "opdrachtReferentie"
    OPDRACHT_ID = "opdrachtId"
    OPDRACHTGEVER_ID = "opdrachtgeverId"
    OPDRACHT_STATUS = "opdrachtStatus"
    TO = "to"
    NOTIFICATIE_INHOUD = "notificatieInhoud"
    REDEN = "reden"
    HTTP_STATUS_CODE = "httpStatusCode"
    HTTP_RESPONSE_MESSAGE = "httpResponseMessage"
    SOURCE_QUEUE = "sourceQueue"
    TARGET_QUEUE = "targetQueue"
    RESULTAAT = "resultaat"
    ZOEKARGUMENTEN = "zoekargumenten"
    INCIDENT_ID = "incidentId"
    AANTAL_GEVONDEN_RECORDS = "aantalGevondenRecords"
    CRITERIA = "criteria"
    AANTAL_VERWIJDERD = "aantalVerwijderd"
    BEWAARTERMIJN = "bewaartermijn"
    HANDMATIGE_POD_COUNT = "handmatigePodCount"
    BSN = "bsn"
    DATUM_TIJD = "datumTijd"
    BERICHT_ID = "berichtId"
    VALIDATION_ERROR = "validationError"
    TOEPASSING = "toepassing"

    # fmt: off
    ALL = frozenset(
        {
            SUBJECT, INGELOGDE_GEBRUIKER, GEBRUIKER, NAAM,
            KANAAL, ADRES, KANAAL_ADRESSEN,
            NOTIFICATIE_STATUS, NOTIFICATIE_ID,
            TEMPLATE, TEMPLATE_NAMEN, TEMPLATE_NAAM, TEMPLATE_DATA, TEMPLATE_VERSIE,
            BATCH_REFERENTIE, OPDRACHT_REFERENTIE, OPDRACHT_ID,
            OPDRACHTGEVER_ID, OPDRACHT_STATUS,
            TO,
            NOTIFICATIE_INHOUD,
            REDEN,
            HTTP_STATUS_CODE, HTTP_RESPONSE_MESSAGE,
            SOURCE_QUEUE, TARGET_QUEUE,
            RESULTAAT,
            ZOEKARGUMENTEN, INCIDENT_ID, AANTAL_GEVONDEN_RECORDS,
            CRITERIA, AANTAL_VERWIJDERD, BEWAARTERMIJN,
            HANDMATIGE_POD_COUNT,
            BSN,
            DATUM_TIJD,
            BERICHT_ID,
            VALIDATION_ERROR,
            TOEPASSING,
        }
    )
    # fmt: on


def subject_email(email: str) -> dict:
    return {"identificatieType": "EMAIL", "identificatieNummer": None, "email": email}


def subject_bsn(identificatie_nummer: str) -> dict:
    return {"identificatieType": "BSN", "identificatieNummer": identificatie_nummer, "email": None}


class AuditCode(Enum):
    START_NOTIFICATIEOPDRACHT_ONTVANGEN = (
        2010,
        "Start notificatieopdracht ontvangen",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )
    RESULTAAT_NOTIFICATIEOPDRACHT_ONTVANGEN_GELUKT = (
        2011,
        "Resultaat notificatieopdracht ontvangen gelukt",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )

    START_NOTIFICATIEOPDRACHTBATCH_ONTVANGEN = (
        2015,
        "Start notificatieopdrachtbatch ontvangen",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )
    RESULTAAT_NOTIFICATIEOPDRACHTBATCH_ONTVANGEN_GELUKT = (
        2016,
        "Resultaat notificatieopdrachtbatch ontvangen gelukt",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )

    START_OPHALEN_MO_NOTIFICATIEPROFIEL = (
        2020,
        "Start ophalen MO notificatieprofiel",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )
    RESULTAAT_OPHALEN_MO_NOTIFICATIEPROFIEL = (
        2021,
        "Resultaat ophalen MO notificatieprofiel gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )
    RESULTAAT_OPHALEN_MO_NOTIFICATIEPROFIEL_MISLUKT = (
        2022,
        "Resultaat ophalen MO notificatieprofiel mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )

    START_NOTIFICATIE_AANMAKEN = (
        2040,
        "Start notificatie aanmaken",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING),
    )
    RESULTAAT_NOTIFICATIE_AANMAKEN = (
        2041,
        "Resultaat notificatie aanmaken",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING),
    )
    RESULTAAT_NOTIFICATIE_AANMAKEN_MISLUKT = (
        2042,
        "Resultaat notificatie aanmaken mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING, TAG_SECURITYLOGGING),
    )

    START_NOTIFICATIEMAIL_VERSTUREN = (
        2050,
        "Start notificatiemail versturen",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING),
    )
    RESULTAAT_NOTIFICATIEMAIL_VERSTUREN_GELUKT = (
        2051,
        "Resultaat notificatiemail versturen gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING),
    )
    RESULTAAT_NOTIFICATIEMAIL_VERSTUREN_MISLUKT = (
        2052,
        "Resultaat notificatiemail versturen mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING, TAG_SECURITYLOGGING),
    )

    START_HERHAAL_SERVICE = (2060, "Start ontvangen Opdracht opslaan", LEVEL_INFO, (TAG_VERWERKINGSLOGGING,))
    RESULTAAT_HERHAAL_SERVICE_GELUKT = (
        2061,
        "Resultaat ontvangen Opdracht opslaan gelukt",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )
    RESULTAAT_HERHAAL_SERVICE_MISLUKT = (
        2062,
        "Resultaat ontvangen Opdracht opslaan mislukt",
        LEVEL_ERROR,
        (TAG_VERWERKINGSLOGGING,),
    )

    START_OPSCHONEN_ONTVANGENOPDRACHTEN = (
        2070,
        "Start opschonen ontvangenopdrachten",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING),
    )
    RESULTAAT_OPSCHONEN_ONTVANGENOPDRACHTEN_GELUKT = (
        2071,
        "Resultaat opschonen ontvangenopdrachten gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING),
    )

    RESULTAAT_HERHAAL_OPDRACHT_VERZENDEN_GELUKT = (
        2080,
        "Resultaat ontvangen Opdracht opslaan verzenden gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING),
    )

    RESULTAAT_BOUNCE_EVENT_GELUKT = (
        2091,
        "Resultaat bounce event opslaan gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING, TAG_SECURITYLOGGING),
    )
    RESULTAAT_BOUNCE_EVENT_MISLUKT = (
        2092,
        "Resultaat bounce event opslaan mislukt",
        LEVEL_ERROR,
        (TAG_SECURITYLOGGING,),
    )
    RESULTAAT_BOUNCE_EVENT_NIET_VERSTUURD = (
        2093,
        "Resultaat bounce event niet verzonden",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING, TAG_SECURITYLOGGING),
    )

    START_TERUGKOPPELING_VERZENDEN = (2120, "Start terugkoppeling verzenden", LEVEL_INFO, (TAG_VERWERKINGSLOGGING,))
    RESULTAAT_TERUGKOPPELING_VERZENDEN = (
        2121,
        "Resultaat terugkoppeling verzenden gelukt",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )
    RESULTAAT_TERUGKOPPELING_VERZENDEN_MISLUKT = (
        2122,
        "Resultaat terugkoppeling versturen mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING, TAG_SECURITYLOGGING),
    )
    TERUGKOPPELING_VERZENDEN_NIET_GEWENST = (
        2123,
        "Terugkoppeling verzenden niet gewenst",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )

    START_OPHALEN_NOTIFICATIE_STATUS = (
        2130,
        "Start ophalen notificatie status details",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )
    RESULTAAT_OPHALEN_NOTIFICATIE_STATUS = (
        2131,
        "Resultaat ophalen notificatie status details gelukt",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )
    RESULTAAT_OPHALEN_NOTIFICATIE_STATUS_MISLUKT = (
        2132,
        "Resultaat ophalen notificatie status details mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING, TAG_SECURITYLOGGING),
    )

    START_ZOEKEN_NOTIFICATIE_STATUS = (
        2140,
        "Start zoeken notificatie status details",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )
    RESULTAAT_ZOEKEN_NOTIFICATIE_STATUS = (
        2141,
        "Resultaat zoeken notificatie status details gelukt",
        LEVEL_INFO,
        (TAG_VERWERKINGSLOGGING,),
    )
    RESULTAAT_ZOEKEN_NOTIFICATIE_STATUS_MISLUKT = (
        2142,
        "Resultaat zoeken notificatie status details mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING, TAG_SECURITYLOGGING),
    )

    RESULTAAT_AFLEVERING_EMAIL_KANAALADRES = (
        2170,
        "Resultaat aflevering e-mail kanaaladres",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_VERWERKINGSLOGGING),
    )

    START_OPSCHONEN_STATUSOPDRACHTEN = (2200, "Start opschonen statusopdrachten", LEVEL_INFO, (TAG_GEBRUIKSLOGGING,))
    RESULTAAT_OPSCHONEN_STATUSOPDRACHTEN_GELUKT = (
        2201,
        "Resultaat opschonen statusopdrachten gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )
    RESULTAAT_OPSCHONEN_STATUSOPDRACHTEN_MISLUKT = (
        2202,
        "Resultaat opschonen statusopdrachten mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING,),
    )

    VALIDATION_ERROR = (2300, "Validatiefout template data", LEVEL_ERROR, (TAG_SECURITYLOGGING, TAG_VERWERKINGSLOGGING))

    START_OPHALEN_TEMPLATELIJST = (3001, "Start ophalen templatelijst", LEVEL_INFO, (TAG_GEBRUIKSLOGGING,))
    RESULTAAT_OPHALEN_TEMPLATELIJST = (3002, "Resultaat ophalen templatelijst", LEVEL_INFO, (TAG_GEBRUIKSLOGGING,))

    START_OPHALEN_TEMPLATE = (3003, "Start ophalen template", LEVEL_INFO, (TAG_GEBRUIKSLOGGING,))
    RESULTAAT_OPHALEN_TEMPLATE = (3004, "Resultaat ophalen template", LEVEL_INFO, (TAG_GEBRUIKSLOGGING,))
    RESULTAAT_OPHALEN_TEMPLATE_MISLUKT = (
        3005,
        "Resultaat ophalen template mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )

    START_AANMAKEN_MUTEREN_TEMPLATE = (3006, "Start aanmaken/mutatie template", LEVEL_INFO, (TAG_GEBRUIKSLOGGING,))
    RESULTAAT_AANMAKEN_MUTEREN_TEMPLATE = (
        3007,
        "Resultaat aanmaken/mutatie template",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )
    RESULTAAT_AANMAKEN_MUTEREN_TEMPLATE_MISLUKT = (
        3008,
        "Resultaat aanmaken/mutatie template mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )

    START_OPHALEN_PARAMETERS = (3020, "Start opvragen parameters", LEVEL_INFO, (TAG_GEBRUIKSLOGGING,))
    RESULTAAT_OPHALEN_PARAMETERS_GELUKT = (
        3021,
        "Resultaat opvragen parameters gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )
    RESULTAAT_OPHALEN_PARAMETERS_MISLUKT = (
        3022,
        "Resultaat opvragen parameters mislukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )

    START_OPSCHONEN_LOGREGELS = (3030, "Start opschonen logregels", LEVEL_INFO, (TAG_GEBRUIKSLOGGING,))
    RESULTAAT_OPSCHONEN_LOGREGELS_GELUKT = (
        3031,
        "Resultaat opschonen logregels gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )

    START_VERWIJDEREN_BERICHTEN_QUEUE = (
        5000,
        "Start verwijderen berichten van queue",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )
    RESULTAAT_VERWIJDEREN_BERICHTEN_QUEUE = (
        5001,
        "Resultaat verwijderen berichten van queue",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )
    RESULTAAT_VERWIJDEREN_BERICHTEN_QUEUE_MISLUKT = (
        5002,
        "Resultaat verwijderen berichten van queue mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )

    START_VERPLAATSEN_BERICHTEN_QUEUE = (
        5010,
        "Start verplaatsen berichten naar queue",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )
    RESULTAAT_VERPLAATSEN_BERICHTEN_QUEUE = (
        5011,
        "Resultaat verplaatsen berichten naar queue",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING,),
    )
    RESULTAAT_VERPLAATSEN_BERICHTEN_QUEUE_MISLUKT = (
        5012,
        "Resultaat verplaatsen berichten naar queue mislukt",
        LEVEL_ERROR,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )

    START_HANDMATIG_AANPASSEN_AANTAL_INSTANTIES_SERVICES = (
        5020,
        "Start handmatig aanpassen aantal instanties van services",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )
    RESULTAAT_HANDMATIG_AANPASSEN_AANTAL_INSTANTIES_SERVICES = (
        5021,
        "Resultaat handmatig aanpassen aantal instanties van services gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )

    START_HANDMATIG_AANPASSEN_AANTAL_INSTANTIES_SERVICE = (
        5030,
        "Start handmatig aanpassen aantal instanties van een service",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )
    RESULTAAT_HANDMATIG_AANPASSEN_AANTAL_INSTANTIES_SERVICE = (
        5031,
        "Resultaat handmatig aanpassen aantal instanties van een service gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )

    START_OPHEFFEN_HANDMATIGE_AANPASSING_AANTAL_INSTANTIES_SERVICE = (
        5040,
        "Start opheffen handmatige aanpassing aantal instanties van een service",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )
    RESULTAAT_OPHEFFEN_HANDMATIGE_AANPASSING_AANTAL_INSTANTIES_SERVICE = (
        5041,
        "Resultaat opheffen handmatige aanpassing aantal instanties van een service gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )

    START_ZOEKVRAAG_FUNCTIONELE_LOG = (
        6010,
        "Start zoekvraag functionele log",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )
    ZOEKVRAAG_FUNCTIONELE_LOG_GELUKT = (
        6011,
        "Zoekvraag functionele log gelukt",
        LEVEL_INFO,
        (TAG_GEBRUIKSLOGGING, TAG_SECURITYLOGGING),
    )

    def __init__(self, code: int, message: str, level: str, tags: tuple):
        self.code = code
        self.message = message
        self.level = level
        self.tags = list(tags)


def _tijdstip() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass
class AuditLog:
    code: int
    message: str
    level: str = LEVEL_INFO
    service: str = "ONBEKEND"
    tags: list[str] = field(default_factory=lambda: [TAG_GEBRUIKSLOGGING])
    items: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tijdstip: str = field(default_factory=_tijdstip)

    def __post_init__(self):
        unknown_keys = set(self.items) - Key.ALL
        if unknown_keys:
            raise ValueError(
                f"Onbekende AuditLog.items keys: {sorted(unknown_keys)}. Gebruik de constanten uit de Key class."
            )

    def serialize(self) -> dict:
        return {
            "id": self.id,
            "tijdstip": self.tijdstip,
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "service": self.service,
            "tags": self.tags,
            "items": self.items,
        }


class AuditClient:
    def __init__(self):
        self.active = False
        self.broker_url = None
        self.service_name = "ONBEKEND"
        self.routing_key = AUDIT_ROUTING_KEY
        self._connection = None
        self._queue = None

    def init_app(self, app):
        app.audit_client = self
        self.active = app.config.get("AUDIT_ENABLED", False)
        self.broker_url = app.config.get("AUDIT_BROKER_URL")
        self.service_name = app.config.get("AUDIT_SERVICE_NAME") or app.config.get("NOTIFY_APP_NAME") or "ONBEKEND"
        self.routing_key = app.config.get("AUDIT_ROUTING_KEY", AUDIT_ROUTING_KEY)

        if self.active and not self.broker_url:
            raise ValueError("AUDIT_ENABLED is True, maar AUDIT_BROKER_URL is niet geconfigureerd")

        if self.active:
            self._connection = Connection(self.broker_url)
            # Durable queue op de default exchange, zodat berichten niet
            # verloren gaan als de audit-service niet draait.
            self._queue = Queue(self.routing_key, routing_key=self.routing_key, durable=True)

    def log(
        self,
        audit_code: AuditCode,
        *,
        items: dict | None = None,
        message: str | None = None,
        level: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        audit_log = AuditLog(
            code=audit_code.code,
            message=message or audit_code.message,
            level=level or audit_code.level,
            service=self.service_name,
            tags=tags if tags is not None else list(audit_code.tags),
            items=items or {},
        )
        self.log_audit_log(audit_log)

    def log_audit_log(self, audit_log: AuditLog) -> None:
        if not self.active:
            return

        try:
            producer = Producer(self._connection)
            producer.publish(
                json.dumps(audit_log.serialize()),
                routing_key=self.routing_key,
                content_type="application/json",
                delivery_mode=2,  # persistent
                declare=[self._queue],
                retry=True,
                retry_policy={"max_retries": 3, "interval_start": 0, "interval_step": 0.5, "interval_max": 1},
            )
        except Exception:
            current_app.logger.exception(
                "Versturen van auditlog naar queue mislukt: %s",
                audit_log.serialize(),
            )
            statsd_client = getattr(current_app, "statsd_client", None)
            if statsd_client:
                statsd_client.incr("clients.audit.error")
