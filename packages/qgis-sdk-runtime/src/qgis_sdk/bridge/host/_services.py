"""HostServices: the curated services a host hands the bridge, resolved from a context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.core import PluginContext
from qgis_sdk.services.algorithms import Algorithms
from qgis_sdk.services.contracts import Notifications
from qgis_sdk.services.features import Features
from qgis_sdk.services.layers import Layers
from qgis_sdk.services.network import NetworkTransport
from qgis_sdk.services.project import Project
from qgis_sdk.services.settings import Settings
from qgis_sdk.services.styles import Styles

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from qgis_sdk.files import FilesService


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

        This is how a page and a Python handler end up reading one project:
        the bridge answers ``layers.list`` from the very ``Layers`` the plugin
        reaches as ``self.ctx.layers``. A context missing one of the four
        required services fails here, by capability name, before anything is
        registered. ``network`` is the transport ``network.fetch`` sends through;
        left out, it is the transport under the context's own client when that
        client exposes one (``NetworkClient.transport``), so a page's fetch and
        a handler's ``await self.ctx.network.get(...)`` leave through one door.
        ``authority`` likewise defaults to the one under the context's
        ``files`` service when it exposes one (``FilesService.authority``):
        a ref the page received is then the ref ``ctx.files`` resolves.
        """
        if network is None and context.has("network"):
            network = getattr(context.network, "transport", None)
        files = context.files if context.has("files") else None
        if authority is None and files is not None:
            authority = getattr(files, "authority", None)
        return cls(
            layers=context.layers,
            project=context.project,
            settings=context.settings,
            styles=context.styles,
            notifications=context.notifications,
            features=context.features if context.has("features") else None,
            authority=authority if authority is not None else HostAuthority(),
            network=network,
            algorithms=context.algorithms if context.has("algorithms") else None,
            files=files,
        )
