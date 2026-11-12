"""The published declarations keep their bodies reachable under the pure suite.

A wide parameter list that becomes declaration data must still be exercised
where its body has branches that no other test happened to take. These three
cases cover the ``from_bounds`` classmethod and the two constructor refusals
that the published record made reachable through a new call path.
"""

from __future__ import annotations

import pytest
from qgis_sdk.models import CanvasExtent, QgisSdkUiError
from qgis_sdk.ui import Choice, Number


def test_published_classmethod_builds_the_extent() -> None:
    extent = CanvasExtent.from_bounds(1.0, 2.0, 3.0, 4.0, crs="EPSG:4326")

    assert (extent.x_min, extent.y_min, extent.x_max, extent.y_max) == (
        1.0,
        2.0,
        3.0,
        4.0,
    )
    assert extent.crs == "EPSG:4326"


def test_published_number_refuses_an_integer_flag_on_fractional_bounds() -> None:
    with pytest.raises(QgisSdkUiError, match="integer range needs integer bounds"):
        Number(range=(0.5, 1.5), integer=True)


def test_published_choice_refuses_an_empty_option_list() -> None:
    with pytest.raises(QgisSdkUiError, match="needs at least one option"):
        Choice(options=())
