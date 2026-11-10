"""The ``QgsProcessingProvider`` an SDK ``Provider`` becomes, and its registration."""

from __future__ import annotations

from typing import Any

from qgis.core import QgsApplication, QgsProcessingProvider

from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.bridge.dispatch import ViewBinding
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.providers import Provider

from ..algorithms import _processing
from ._algorithm import _BridgeAlgorithm
from ._services import _Services


class NativeProcessingProvider(QgsProcessingProvider):
    """A ``QgsProcessingProvider`` backed by an SDK ``Provider``.

    Holds the services the bridge needs. They are the caller's runtime objects on
    purpose: the layers an algorithm opens, the temporary outputs it writes and
    the scope that owns them stay the plugin's, not this adapter's.
    """

    def __init__(self, provider: Provider, services: _Services) -> None:
        super().__init__()
        self._provider = provider
        self.layers = services.layers
        #: The raster service a raster ``LayerInput`` re-opens through
        #: (TASK-87). Without one, a raster input on an algorithm refuses by
        #: name - the dialog would otherwise accept a layer nothing can read.
        self.rasters = services.rasters
        # Not ``self.algorithms``: that is ``QgsProcessingProvider.algorithms()``,
        # which the registry calls to enumerate what this provider offers.
        self.algorithm_service = services.algorithms
        self.project = services.project
        self.scope = services.scope
        #: Mints the refs for files a Processing dialog picked; a host that
        #: shares one authority with its views passes it in, so the refs a
        #: handler receives resolve wherever the runtime resolves refs.
        self.authority = (
            services.authority if services.authority is not None else HostAuthority()
        )
        self.binding = ViewBinding(
            view_id=f"processing:{provider.id}",
            origin="qgis://processing",
            generation=0,
        )

    @property
    def provider_id(self) -> str:
        return self._provider.id

    def function_for(self, algorithm_id: str) -> Any:
        """Return the declared function behind one bridge algorithm."""
        return self._provider.function_for(algorithm_id)

    def id(self) -> str:
        return self._provider.id

    def name(self) -> str:
        return self._provider.title

    def unregister(self) -> None:
        """Remove this provider and every algorithm it added from the registry.

        ``QgsProcessingProvider`` has no public removal method in QGIS 4.2, so the
        registry is the one that owns removal; exposing it here keeps the plugin
        from having to import ``QgsApplication`` just to unload itself.
        """
        QgsApplication.processingRegistry().removeProvider(self)

    def loadAlgorithms(self) -> None:
        for description in self._provider.describe().algorithms:
            self.addAlgorithm(_BridgeAlgorithm(self, description))


def register_provider(
    provider: Provider, services: _Services
) -> NativeProcessingProvider:
    """Register ``provider`` with QGIS and return the adapter that owns it.

    The adapter's own implementation behind :class:`NativeProcessing`; a plugin
    lists ``providers = [...]`` and lets the runtime call this (decision-42).
    The returned object is what ``QgsApplication.processingRegistry()`` now
    holds; calling ``unregister()`` on it removes every algorithm it added.
    """
    # The registry lives inside the Processing framework, so loading it is part
    # of registering: afterwards `processing.run` works for the caller too.
    _processing()
    bridge = NativeProcessingProvider(provider, services)
    if not QgsApplication.processingRegistry().addProvider(bridge):
        raise QgisSdkDeclarationError(
            f"provider {provider.id!r} is already registered with QGIS"
        )
    return bridge
