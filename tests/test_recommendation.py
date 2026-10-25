from types import SimpleNamespace

import pytest

from admin_views import recommendation_for


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (None, "approve"),
        (70, "approve"),
        (69, "reject"),
        (0, "reject"),
    ],
)
def test_recommendation_for_approves_at_seventy_and_when_missing(confidence, expected):
    material = SimpleNamespace(confidence=confidence)

    decision = recommendation_for(material)

    assert decision == expected
