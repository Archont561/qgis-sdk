"""The handler signature and the object that hands a handler what it may reach."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.host._services import HostServices
from qgis_sdk.models import FileRef
from qgis_sdk.models.errors import QgisSdkBridgeError

if TYPE_CHECKING:  # pragma: no cover - typing only; the peers import at runtime
    from qgis_sdk.bridge.authority import HostAuthority
    from qgis_sdk.bridge.dispatch import ViewBinding
    from qgis_sdk.bridge.host._sources import EditingSessions
    from qgis_sdk.services.algorithms import Algorithms
    from qgis_sdk.services.canvas import Canvas
    from qgis_sdk.services.connections import Connections
    from qgis_sdk.services.features import Features
    from qgis_sdk.services.layouts import Layouts
    from qgis_sdk.services.project import Project
    from qgis_sdk.services.rasters import Rasters

#: What every handler is: the host it may reach, the calling view's binding, and
#: the payload the request schema already validated. A handler for a streaming
#: id returns the source the dispatcher pumps instead of a result dict, which is
#: why the return type is the one place ``Any`` is honest here.
HostHandler = Callable[["_Host", "ViewBinding", Mapping[str, Any]], Any]


@dataclass(frozen=True)
class _Host:
    """The services, the view's authority and the open edit sessions, in one place.

    A handler reaches a service through this object rather than through its own
    parameters: the required services are plain attributes, and the optional
    ones raise the same "this host has no ... service configured" refusal they
    always did, so a host that left one out still fails by capability name
    instead of answering with nothing (decision-54 point 3).
    """

    services: HostServices
    editing: EditingSessions

    @property
    def authority(self) -> HostAuthority:
        """The authority the host minted refs on; every view's grant lives here."""
        return self.services.authority

    @property
    def project(self) -> Project:
        if self.services.project is None:  # pragma: no cover - a required field
            raise QgisSdkBridgeError("this host has no project service configured")
        return self.services.project

    @property
    def layouts(self) -> Layouts:
        if self.services.layouts is None:
            raise QgisSdkBridgeError("this host has no layouts service configured")
        return self.services.layouts

    @property
    def connections(self) -> Connections:
        if self.services.connections is None:
            raise QgisSdkBridgeError("this host has no connections service configured")
        return self.services.connections

    @property
    def rasters(self) -> Rasters:
        if self.services.rasters is None:
            raise QgisSdkBridgeError("this host has no raster service configured")
        return self.services.rasters

    @property
    def algorithms(self) -> Algorithms:
        if self.services.algorithms is None:
            raise QgisSdkBridgeError("this host has no algorithms service configured")
        return self.services.algorithms

    @property
    def canvas(self) -> Canvas:
        if self.services.canvas is None:
            raise QgisSdkBridgeError("this host has no canvas service configured")
        return self.services.canvas

    @property
    def features(self) -> Features:
        if self.services.features is None:
            raise QgisSdkBridgeError("this host has no features service configured")
        return self.services.features

    def plugin_file(
        self,
        path: Any,
        *,
        writable: bool = False,
        overwrite: bool = False,
    ) -> FileRef:
        """Re-mint one of the view's paths as a ref the plugin's files service holds.

        The view's ref names a path *for the view*; a service on this side of the
        seam resolves refs through the plugin's files service, so a path has to
        cross as the plugin's own ref - and it is refused here when the plugin
        has no files service, never quietly turned back into a string
        (decision-20: a path is not authority, on either side of the bridge).
        """
        files = self.services.files
        if files is None:
            raise QgisSdkBridgeError(
                "this host has no files service to hand a plugin-side ref out"
            )
        # A destination need not exist yet, and a read grant insists it does; a
        # write grant is the one an export destination can carry.
        operations: tuple[str, ...] = ("write",) if writable else ("read",)
        return files.grant_file(path, operations=operations, overwrite=overwrite)
