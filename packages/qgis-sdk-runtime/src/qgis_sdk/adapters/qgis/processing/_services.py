"""The runtime services one registered provider borrows, and how to reach them."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from qgis.core import QgsProcessingException

from qgis_sdk.adapters.qgis.algorithms import NativeAlgorithms
from qgis_sdk.adapters.qgis.layers import NativeLayers
from qgis_sdk.adapters.qgis.project import NativeProject
from qgis_sdk.adapters.qgis.rasters import NativeRasters
from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.core import ResourceScope


@dataclass(frozen=True, slots=True)
class ProcessingServices:
    """The caller's runtime objects, which an algorithm borrows and does not own.

    One record rather than six keyword parameters: registering a provider and
    building the service that registers it are the same facts, and passing them
    as a record is what keeps the two from drifting apart. ``NativeProcessing``
    takes one of these - or the same keys as a plain mapping - so a host names
    the services once instead of unpacking them into a constructor.
    """

    layers: NativeLayers
    algorithms: NativeAlgorithms
    project: NativeProject
    scope: ResourceScope
    #: Mints the refs for files a Processing dialog picked; a host that shares
    #: one authority with its views passes it in, so the refs a handler receives
    #: resolve wherever the runtime resolves refs.
    authority: HostAuthority | None = None
    #: The raster service a raster ``LayerInput`` re-opens through (TASK-87).
    #: Without one, a raster input on an algorithm refuses by name - the dialog
    #: would otherwise accept a layer nothing can read.
    rasters: NativeRasters | None = None

    def with_default_authority(self) -> ProcessingServices:
        """The same record, minting into a fresh authority when it has none.

        One authority per runtime (decision-20): resolving it here is what makes
        every provider a service registers mint into the same one.
        """
        if self.authority is not None:
            return self
        return replace(self, authority=HostAuthority())


def rasters_of(bridge: Any) -> Any:
    """Return the provider's raster service, or refuse a raster input by name."""
    rasters = getattr(bridge, "rasters", None)
    if rasters is None:
        raise QgsProcessingException(
            "this host has no raster service, so a raster input cannot be read"
        )
    return rasters


def files_of(bridge: Any) -> Any:
    """Return the files service that resolves a produced ref, or ``None``.

    The bridge resolves a handler's ``FileRef`` result through the same files
    service the run machinery owns, so a file output is published from the
    exact path the ref names and nothing else.
    """
    return getattr(bridge.algorithm_service, "_files", None)
