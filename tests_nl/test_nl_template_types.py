import pytest
from freezegun import freeze_time

from notifications_utils.template import LetterPreviewTemplate, LetterPrintTemplate


@pytest.mark.parametrize(
    "extra_template_kwargs, should_have_notify_tag",
    (
        ({}, True),
        ({"includes_first_page": True}, True),
        ({"includes_first_page": False}, False),
    ),
)
def test_rendered_letter_template_for_print_can_toggle_notify_tag_and_always_hides_barcodes(
    extra_template_kwargs, should_have_notify_tag
):
    template = LetterPrintTemplate(
        {"template_type": "letter", "subject": "subject", "content": "content"}, {}, **extra_template_kwargs
    )
    assert ("content: 'NOTIFY';" in str(template)) == should_have_notify_tag


@freeze_time("2001-01-01 12:00:00.000000")
def test_nested_lists_in_letter_markup():
    template_content = str(
        LetterPreviewTemplate(
            {
                "content": (
                    "nested list:\n\n1. one\n2. two\n3. three\n  - three one\n  - three two\n  - three three\n"
                ),
                "subject": "foo",
                "template_type": "letter",
            }
        )
    )

    assert (
        "<p>nested list:</p><ol>\n"
        "<li>one</li>\n"
        "<li>two</li>\n"
        "<li>three<ul>\n"
        "<li>three one</li>\n"
        "<li>three two</li>\n"
        "<li>three three</li>\n"
        "</ul></li>\n"
        "</ol>"
    ) in template_content


def _extras(**overrides):
    # `letter_pdf_nl`'s jinja templates use a StrictUndefined environment, so every
    # `extras.*` key referenced anywhere in the templates must be present (even if falsy)
    # whenever an `extras` dict is supplied at all.
    extras = {
        "aantal_bijlagen": None,
        "afdeling": None,
        "classificatie": None,
        "contactpersoon": None,
        "dienst_code": None,
        "dienst_naam": None,
        "emailadres": None,
        "footer_links_eerste_pagina": None,
        "footer_midden_eerste_pagina": None,
        "footer_rechts_eerste_pagina": None,
        "handtekening": None,
        "header_vanaf_tweede_pagina": None,
        "ondertekening": None,
        "ons_kenmerk": None,
        "retour_adres": None,
        "secundaire_afzender": None,
        "telefoonnummer": None,
        "uw_brief_van": None,
        "uw_kenmerk": None,
    }
    extras.update(overrides)
    return extras


def test_pingen_address_placement_class_applied_to_all_envelope_window_elements():
    template_content = str(
        LetterPreviewTemplate(
            {"content": "content", "subject": "subject", "template_type": "letter"},
            {"extras": _extras(sender_organisation="pingen", dienst_code="1234")},
        )
    )

    assert 'class="dienstcode align-with-envelope-window pingen ' in template_content
    assert 'class="recipient-address align-with-envelope-window pingen">' in template_content
    assert 'class="rand-info align-with-envelope-window pingen">' in template_content


def test_pingen_address_placement_class_absent_by_default():
    # `.pingen` is always present as a CSS selector in the rendered <style> block -
    # what matters is that no element's `class` attribute actually carries it. With no
    # `sender_organisation` supplied, `BaseLetterTemplate._extras` defaults it to "custom".
    template_content = str(
        LetterPreviewTemplate(
            {"content": "content", "subject": "subject", "template_type": "letter"},
            {"extras": _extras(dienst_code="1234")},
        )
    )

    assert 'class="dienstcode align-with-envelope-window custom ' in template_content
    assert 'class="recipient-address align-with-envelope-window custom">' in template_content
    assert 'class="rand-info align-with-envelope-window custom">' in template_content
