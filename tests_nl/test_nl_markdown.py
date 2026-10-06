import pytest

from notifications_utils.markdown import (
    notify_email_markdown,
    notify_letter_preview_markdown,
    notify_plain_text_email_markdown,
)
from notifications_utils.template import HTMLEmailTemplate, PlainTextEmailTemplate

# Content reaches markdown already HTML-escaped, so a `&` in a link url arrives as `&amp;`.
# mistune 3's escape_url decodes it again; these pin the mistune 0.8.4 output upstream relies on.


@pytest.mark.parametrize(
    "markdown_function, expected_output",
    (
        (
            notify_email_markdown,
            '<a style="word-wrap: break-word; color: #1D70B8;" '
            'href="https://example.com/d/abc?key=xyz&amp;template_version=1">your file</a>',
        ),
        (
            notify_plain_text_email_markdown,
            "your file: https://example.com/d/abc?key=xyz&amp;template_version=1",
        ),
        (
            notify_letter_preview_markdown,
            "[your file](https://example.com/d/abc?key=xyz&amp;template_version=1)",
        ),
    ),
)
def test_markdown_link_keeps_ampersand_in_url_escaped(markdown_function, expected_output):
    assert expected_output in markdown_function("[your file](https://example.com/d/abc?key=xyz&amp;template_version=1)")


def test_markdown_link_title_and_text_keep_ampersand_escaped():
    assert notify_email_markdown('[Tom &amp; Jerry](https://example.com/?a=1&amp;b=2 "Title &amp; more")') == (
        '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
        '<a style="word-wrap: break-word; color: #1D70B8;" href="https://example.com/?a=1&amp;b=2" '
        'title="Title &amp; more">Tom &amp; Jerry</a>'
        "</p>"
    )


def test_email_file_link_with_ampersand_renders_valid_html_and_plain_text():
    template = {"content": "Download: [your file](((link)))", "subject": "subject", "template_type": "email"}
    values = {"link": "https://example.com/d/abc?key=xyz&template_version=1"}

    assert 'href="https://example.com/d/abc?key=xyz&amp;template_version=1"' in str(HTMLEmailTemplate(template, values))
    assert "your file: https://example.com/d/abc?key=xyz&template_version=1" in str(
        PlainTextEmailTemplate(template, values)
    )
