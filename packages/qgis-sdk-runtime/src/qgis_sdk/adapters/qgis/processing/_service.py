"""``ctx.processing``: the plugin's providers, in the registry."""

from __future__ import annotations

from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.core import ResourceScope
from qgis_sdk.providers import Provider

from ..algorithms import NativeAlgorithms
from ..layers import NativeLayers
from ..project import NativeProject
from ..rasters import NativeRasters
from ._provider import NativeProcessingProvider, register_provider
from ._services import _Services


class NativeProcessing:
    """``ctx.processing`` for a QGIS host: the plugin's providers in the registry.

    Holds the services every registered bridge needs. They are the plugin's
    runtime objects on purpose: the layers an algorithm opens, the temporary
    outputs it writes and the scope that owns them stay the plugin's.
    """

    def __init__(
        self,
        *,
        layers: NativeLayers,
        algorithms: NativeAlgorithms,
        project: NativeProject,
        scope: ResourceScope,
        authority: HostAuthority | None = None,
        rasters: NativeRasters | None = None,
    ) -> None:
        self._scope = scope
        self._services = _Services(
            layers=layers,
            algorithms=algorithms,
            project=project,
            scope=scope,
            # One authority per runtime (decision-20): resolved here, so every
            # provider this service registers mints into the same one.
            authority=authority if authority is not None else HostAuthority(),
            rasters=rasters,
        )

    def register_provider(self, provider: Provider) -> NativeProcessingProvider:
        """Advertise ``provider``; ``unregister()`` on the result removes it."""
        self._scope.ensure_open()
        return register_provider(provider, self._services)
