"""Simple server: the reference example's data, answered on the third host.

``examples/simple`` is one plugin class run by QGIS Desktop and by a standalone
PyQGIS app; this project is the same fixture on the host decision-52 left:
QGIS Server. What changes is the shape of the declaration, not the work - a
server plugin declares *hooks* instead of actions, has no window, and its
context carries the request, the response and, when the deployment loads one,
the request's project. Nothing here imports QGIS or Qt.

``SIMPLE_SERVER`` is an OGC-style service this plugin owns. It answers
``REQUEST=extent`` with the bounding box and the feature count of
``data/points.geojson`` - the fixture the Desktop example opens through QGIS,
read here in plain Python, because a hook is a plain function and the work it
does needs no QGIS at all. Three hooks make the slice:

- ``default_version`` (a ``@filter``) fills in a missing ``VERSION`` before any
  service runs, the way QGIS' own filters normalise a request;
- ``answer`` (a ``@service``) owns ``SERVICE=SIMPLE_SERVER``;
- ``no_private_layers`` (an ``@access_control``) refuses the layers this
  deployment marks private, and the host turns that ``False`` into a 403
  naming the layer.

``qgis-sdk test`` drives all three through ``qgis_sdk.testing.FakeServerInterface``
on a machine whose QGIS has no server bindings; ``test --target server`` runs
the same hooks in-process under a real ``QgsServer`` where the build has them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from qgis_sdk import QgisSdkPlugin
from qgis_sdk.server import (
    ServerContext,
    ServerRequest,
    ServerResponse,
    access_control,
    filter,
    service,
)

PLUGIN_ID = "simple_server"
TITLE = "Simple server"

#: The OGC ``SERVICE`` this plugin owns, and the version it advertises. QGIS
#: keys a service by ``name_version``, so an unknown version falls back to this
#: one instead of failing the request.
SERVICE = "SIMPLE_SERVER"
SERVICE_VERSION = "1.0.0"

#: The reference example's point fixture, read as data rather than opened.
FIXTURE = Path(__file__).with_name("data") / "points.geojson"

#: Layers whose name starts with this belong to another tenant; the access hook
#: refuses them instead of letting QGIS render a filtered map.
PRIVATE_PREFIX = "private_"

app = QgisSdkPlugin(id=PLUGIN_ID, title=TITLE)


@dataclass(frozen=True, slots=True)
class FixtureExtent:
    """What the fixture measures: a WGS84 bounding box and a feature count."""

    bounds: tuple[float, float, float, float]
    """``min_x, min_y, max_x, max_y`` in EPSG:4326."""

    features: int


def measure(path: Path = FIXTURE) -> FixtureExtent:
    """Read one point GeoJSON and measure it.

    A plain function over a path: the service below is a thin adapter over it,
    and a test asserts the number without a request in sight.
    """
    collection = json.loads(path.read_text(encoding="utf-8"))
    coordinates = [
        feature["geometry"]["coordinates"] for feature in collection["features"]
    ]
    xs = [coordinate[0] for coordinate in coordinates]
    ys = [coordinate[1] for coordinate in coordinates]
    return FixtureExtent(
        bounds=(min(xs), min(ys), max(xs), max(ys)),
        features=len(coordinates),
    )


@filter()
def default_version(
    ctx: ServerContext, request: ServerRequest, response: ServerResponse
):
    """Give a request that names no ``VERSION`` the one this service answers.

    Returning the request rewrites what the hooks after this one see; returning
    ``None`` passes it on and a ``ServerResponse`` would answer it here.
    """
    if request.param("VERSION") is None:
        return request.with_params(VERSION=SERVICE_VERSION)
    return None


@service(name=SERVICE, version=SERVICE_VERSION)
def answer(ctx: ServerContext, request: ServerRequest) -> ServerResponse:
    """Answer ``REQUEST=extent``; anything else is a 400 naming the service."""
    if request.param("REQUEST") != "extent":
        return ServerResponse.denied(
            f"{SERVICE} answers REQUEST=extent only", status=400
        )
    measured = measure()
    return ServerResponse.json(
        {
            "service": SERVICE,
            "version": request.param("VERSION"),
            "features": measured.features,
            "bbox": list(measured.bounds),
        }
    )


@access_control()
def no_private_layers(ctx: ServerContext, request: ServerRequest, layer: str) -> bool:
    """Allow every layer but this deployment's private ones.

    ``True`` lets the request read ``layer``; ``False`` is a 403 naming it,
    never a silently narrowed map (decision-52).
    """
    return not layer.startswith(PRIVATE_PREFIX)
