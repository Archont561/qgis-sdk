"""The host the native suite runs on is a row of the support matrix (TASK-9 AC 2).

The matrix in :mod:`qgis_sdk_tools.targets` is a statement; this test is what
keeps it true. When the locked QGIS, Qt or Chromium moves (a relock, a new
candidate), the row has to move with it, in the same change.
"""

from __future__ import annotations

from typing import Any

import pytest
from qgis_sdk_tools.targets import describe_host, qualified_target

pytestmark = pytest.mark.webengine


def test_this_host_is_a_qualified_target(qgis_app: Any, webengine_profile: Any) -> None:
    """``qgis_app`` and ``webengine_profile`` are what make this a native test:
    without the bindings the layer skips, the way every native test does, and
    the QGIS-free matrix rows are the ``cross-platform`` job's business."""
    host = describe_host()

    assert host.qgis is not None, "the native suite runs under QGIS"
    target = qualified_target(host)

    assert target is not None, (
        f"{host} is not in the support matrix; add or move its row in "
        "qgis_sdk_tools.targets and re-render doc-12"
    )
    assert target.status == "qualified", f"{host} is on record as {target.status}"
