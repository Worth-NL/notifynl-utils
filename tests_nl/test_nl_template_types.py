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
