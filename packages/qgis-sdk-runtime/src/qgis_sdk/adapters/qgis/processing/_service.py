"""``ctx.processing``: the plugin's providers, in the registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qgis_sdk.providers import Provider

from ._provider import NativeProcessingProvider, register_provider
from ._services import ProcessingServices


class NativeProcessing:
    """``ctx.processing`` for a QGIS host: the plugin's providers in the registry.

    Holds the services every registered bridge needs. They are the plugin's
    runtime objects on purpose: the layers an algorithm opens, the temporary
    outputs it writes and the scope that owns them stay the plugin's.
    """

    def __init__(self, services: ProcessingServices | Mapping[str, Any]) -> None:
        """Take one record of the runtime services, or the same keys as a mapping.

        ``ProcessingServices`` is the typed way in; a mapping is there for a host
        that already holds the services in a dict (``{"layers": layers, ...}``),
        and an unknown key or a missing required one fails at construction.
        """
        if isinstance(services, Mapping):
            services = ProcessingServices(**services)
        # One authority per runtime (decision-20): resolved here, so every
        # provider this service registers mints into the same one.
        self._services = services.with_default_authority()
        self._scope = self._services.scope

    def register_provider(self, provider: Provider) -> NativeProcessingProvider:
        """Advertise ``provider``; ``unregister()`` on the result removes it."""
        self._scope.ensure_open()
        return register_provider(provider, self._services)
