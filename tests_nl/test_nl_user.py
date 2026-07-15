import pytest

from notifications_utils.user import (
    GOVERNMENT_EMAIL_DOMAIN_NAMES,
    email_address_ends_with,
)


@pytest.mark.parametrize(
    "email_address, expected_result",
    [
        ("example@aalsmeer.nl", True),
        ("Example@AALSMEER.nl", True),
        ("Example@gemeente.aalsmeer.nl", True),
        ("example@worth.nl", True),
        ("user@example.com", False),
    ],
)
def test_email_address_ends_with(email_address, expected_result):
    assert email_address_ends_with(email_address, GOVERNMENT_EMAIL_DOMAIN_NAMES) is expected_result
