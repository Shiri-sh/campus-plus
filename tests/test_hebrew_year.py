import pytest

from models import hebrew_year


@pytest.mark.parametrize(
    ("gregorian", "expected"),
    [
        (None, "לא ידוע"),
        (0, "לא ידוע"),
        ("", "לא ידוע"),
        (2017, 'תשע"ז'),
        (2024, 'תשפ"ד'),
        (2026, 'תשפ"ו'),
        (2030, "2030"),
    ],
)
def test_hebrew_year_maps_known_years_and_unknown_input(gregorian, expected):
    label = hebrew_year(gregorian)

    assert label == expected
