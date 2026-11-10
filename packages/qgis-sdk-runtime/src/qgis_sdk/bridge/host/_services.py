"""HostServices: the curated services a host hands the bridge, resolved from a context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.core import PluginContext
from qgis_sdk.services.algorithms import Algorithms
from qgis_sdk.services.canvas import Canvas
from qgis_sdk.services.connections import Connections
from qgis_sdk.services.contracts import Notifications
from qgis_sdk.services.features import Features
from qgis_sdk.services.layers import Layers
from qgis_sdk.services.layouts import Layouts
from qgis_sdk.services.network import NetworkTransport
from qgis_sdk.services.project import Project
from qgis_sdk.services.rasters import Rasters
from qgis_sdk.services.settings import Settings
from qgis_sdk.services.styles import Styles

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.files import FilesService


def _optional_service(context: PluginContext, name: str) -> Any:
    """Return the service ``name`` when the context holds one, and nothing when it does not."""
    return getattr(context, name) if context.has(name) else None


def _authority_of(
    context: PluginContext, authority: HostAuthority | None
) -> HostAuthority:
    """The authority refs are minted on: the given one, the context's, or a fresh one.

    Defaulting to the one under the context's ``files`` service is what makes a
    ref the page received the ref ``ctx.files`` resolves (``FilesService.authority``).
    """
    if authority is not None:
        return authority
    files = _optional_service(context, "files")
    inherited = getattr(files, "authority", None) if files is not None else None
    return inherited if inherited is not None else HostAuthority()


def _network_of(
    context: PluginContext, network: NetworkTransport | None
) -> NetworkTransport | None:
    """The transport a fetch leaves through, defaulting to the context client's own.

    A page's ``network.fetch`` and a handler's ``await self.ctx.network.get(...)``
    then leave through one door: ``NetworkClient.transport``.
    """
    if network is not None:
        return network
    if not context.has("network"):
        return None
    return getattr(context.network, "transport", None)


@dataclass(frozen=True)
class HostServices:
    """The curated Protocols, plus the authority that scopes files and network.

    ``authority`` mints the file refs ``layers.open_vector`` and
    ``files.export`` accept and holds each view's network grant; the
    application mints refs on it after a picker closes and grants network per
    view. ``network`` is the transport ``network.fetch`` sends through;
    without one the operation is declared but fails, never silently served.
    ``algorithms`` answers the ``algorithms.*`` operations the same way, and
    ``files`` is the plugin's own files service: a file a run produced is a
    ref the plugin holds, and the host re-mints it for the calling view
    through ``files.resolve`` and the shared authority.
    """

    layers: Layers
    project: Project
    settings: Settings
    styles: Styles
    notifications: Notifications
    #: Layer data, expressions and editing (decision-54 point 3). Without one
    #: the ``features.*``, ``expressions.*`` and ``editing.*`` operations are
    #: declared and fail by name, never silently answered with nothing.
    features: Features | None = None
    #: The map the user is looking at (TASK-85). A server host has no canvas, so
    #: the ``canvas.*`` operations are declared there and fail by name.
    canvas: Canvas | None = None
    #: Raster reads (TASK-87). Without one the ``rasters.*`` operations are
    #: declared and fail by name, never silently answered with nothing.
    rasters: Rasters | None = None
    #: Registered data-source connections and authentication configs (TASK-92).
    #: Without one the ``connections.*`` and ``auth.*`` operations are declared
    #: and fail by name, never silently answered with an empty registry.
    connections: Connections | None = None
    #: Print layouts and atlases (TASK-89). The operations answer through the
    #: blocking render forms, so a page's export is one request that ends with a
    #: file ref; the job forms are the plugin's own path, with a bar and a
    #: cancel button in the task manager.
    layouts: Layouts | None = None
    authority: HostAuthority = field(default_factory=HostAuthority)
    network: NetworkTransport | None = None
    algorithms: Algorithms | None = None
    files: FilesService | None = None

    @classmethod
    def from_context(
        cls,
        context: PluginContext,
        *,
        authority: HostAuthority | None = None,
        network: NetworkTransport | None = None,
    ) -> HostServices:
        """Wrap the services a plugin context already holds, instance for instance.

        This is how a page and a Python handler end up reading one project, the
        very ``Layers`` the plugin reaches as ``self.ctx.layers``. A missing
        required service fails here, by capability name, before anything is
        registered; the optional ones and the two defaults are the helpers below.
        """
        return cls(
            layers=context.layers,
            project=context.project,
            settings=context.settings,
            styles=context.styles,
            notifications=context.notifications,
            features=_optional_service(context, "features"),
            canvas=_optional_service(context, "canvas"),
            rasters=_optional_service(context, "rasters"),
            layouts=_optional_service(context, "layouts"),
            connections=_optional_service(context, "connections"),
            authority=_authority_of(context, authority),
            network=_network_of(context, network),
            algorithms=_optional_service(context, "algorithms"),
            files=_optional_service(context, "files"),
        )
