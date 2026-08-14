import pytest

from notifications_utils.file_types import format_file_type_nl


@pytest.mark.parametrize(
    "extension, pretty_description",
    (
        ("pdf", "PDF"),
        ("csv", "CSV-bestand"),
        ("txt", "tekstbestand"),
        ("json", "JSON-bestand"),
        ("doc", "Microsoft Word-document"),
        ("docx", "Microsoft Word-document"),
        ("xlsx", "Microsoft Excel-spreadsheet"),
        ("odt", "tekstbestand"),
        ("rtf", "tekstbestand"),
        ("jpeg", "JPEG-bestand"),
        ("jpg", "JPEG-bestand"),
        ("png", "PNG-bestand"),
        ("PNG", "PNG-bestand"),
        ("zip", None),
    ),
)
def test_format_file_type_nl(extension, pretty_description):
    assert format_file_type_nl(extension) == pretty_description
