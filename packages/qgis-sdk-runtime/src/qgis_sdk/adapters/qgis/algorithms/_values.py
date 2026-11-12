"""Scalar outputs and the working-CRS rule the native algorithms share.

``plain`` turns whatever a provider answered into Python values, and
``require_metric_projected_crs`` is the one rule the buffer path applies to a
caller's working CRS. The run path and the publishing path both need them, so
they live in a leaf module neither of them owns.
"""

from __future__ import annotations

from typing import Any

from qgis.core import Qgis, QgsCoordinateReferenceSystem

from qgis_sdk.models import QgisSdkAlgorithmRejectedError

#: The unit a distance is measured in; a CRS in anything else is refused.
METRES_ONLY: str = "metres"


def plain(value: Any) -> object:
    """A scalar output as Python: QGIS hands numbers, strings and booleans
    over already; anything else is kept only by its text."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    return str(value)


def require_metric_projected_crs(authid: str, request: str) -> None:
    """Refuse a working CRS a distance cannot honestly be measured in."""
    crs = QgsCoordinateReferenceSystem(authid)
    if not crs.isValid():
        raise QgisSdkAlgorithmRejectedError(
            request, [f"working_crs {authid!r} is not a known CRS"]
        )
    if crs.isGeographic():
        raise QgisSdkAlgorithmRejectedError(
            request,
            [
                f"working_crs {authid!r} is geographic; a distance there would be degrees"
            ],
        )
    if crs.mapUnits() != Qgis.DistanceUnit.Meters:
        raise QgisSdkAlgorithmRejectedError(
            request,
            [
                f"working_crs {authid!r} is not in {METRES_ONLY}; distance_metres would be wrong"
            ],
        )
