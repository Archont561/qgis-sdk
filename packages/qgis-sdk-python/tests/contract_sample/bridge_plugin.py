"""A QGIS-free sample plugin, used as the generator's fixture.

The declarations live here rather than inside a test so the artifact under
``packages/qgis-sdk-typescript/tests/contracts/bridge/generated`` can be regenerated
by a script, the way a real plugin's build step would, and so a drift test can
compare the checked-in file with a fresh run.

It imports nothing from QGIS on purpose: generating a client must not need a
QGIS installation, which is also the rule a plugin's own declaration module has
to follow.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext


@dataclass(frozen=True)
class Summary:
    """A primitive-heavy result: a count, a name and a bounded integer."""

    total: int
    largest: str
    mode: Literal["fast", "exact"] = "fast"


@dataclass(frozen=True)
class DetailsOptions:
    """A nested input object, which the generator names after its path."""

    include_fields: bool = False
    limit: int = 10


@dataclass(frozen=True)
class Details:
    """A result that carries a list and a nested object."""

    layer_id: str
    field_names: tuple[str, ...]
    options: DetailsOptions


@dataclass(frozen=True)
class SiteChange:
    """A data event: what changed on a layer, and how many features it touched."""

    layer_id: str
    change: Literal["added", "removed", "modified"]
    count: int


@dataclass(frozen=True)
class ScanProgress:
    """A progress event, which the host may coalesce while it is queued."""

    done: int
    total: int


app = QgisSdkPlugin(id="org.example.sites", title="Sites")


@app.action(id="sites.summary", title="Summarize one layer")
def summary(
    ctx: PluginContext,
    layer_id: str,
    limit: int = 100,
    mode: Literal["fast", "exact"] = "fast",
    label: str | None = None,
) -> Summary:
    return Summary(total=limit, largest=layer_id, mode=mode)


@app.action(id="sites.details", title="Describe one layer")
def details(ctx: PluginContext, layer_id: str, options: DetailsOptions) -> Details:
    return Details(layer_id=layer_id, field_names=("a", "b"), options=options)


@app.action(id="sites.refresh", title="Refresh the panel")
def refresh(ctx: PluginContext) -> Summary:
    """No inputs at all: the generated method's argument is optional."""
    return Summary(total=0, largest="")


@app.stream(
    id="sites.watch",
    title="Watch one layer for changes",
    events={"data": SiteChange, "progress": ScanProgress},
)
def watch(ctx: PluginContext, layer_id: str, every_ms: int = 500) -> Iterator[Any]:
    """A stream beside the actions: typed data and progress events."""
    yield {"kind": "progress", "payload": ScanProgress(done=0, total=1)}
    yield SiteChange(layer_id=layer_id, change="added", count=every_ms)


__all__ = [
    "Details",
    "DetailsOptions",
    "ScanProgress",
    "SiteChange",
    "Summary",
    "app",
]
