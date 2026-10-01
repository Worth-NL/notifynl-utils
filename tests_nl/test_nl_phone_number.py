import pytest

from notifications_utils.recipient_validation.notifynl.phone_number import PhoneNumber


@pytest.mark.parametrize(
    "phone_number",
    [
        "+31703456789",  # Den Haag landline, national number starts with a UK S7 prefix
        "+31700111111",
        "0612345678",
        "+31612345678",
    ],
)
def test_dutch_numbers_are_never_in_ofcom_s7_protected_range(phone_number):
    assert PhoneNumber(phone_number).is_number_in_S7_protected_range() is False
