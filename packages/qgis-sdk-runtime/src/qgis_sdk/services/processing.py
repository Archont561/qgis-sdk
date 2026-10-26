"""Make a plugin's providers visible in the host's Processing framework."""

from __future__ import annotations

from typing import Protocol


class RegistrableProvider(Protocol):
    """What the registry reads from a ``qgis_sdk.providers.Provider``.

    Spelled structurally because this layer sits below the providers module:
    the id is what a host refuses duplicates by, the title is what it shows.
    """

    @property
    def id(self) -> str: ...

    @property
    def title(self) -> str: ...


class ProviderRegistration(Protocol):
    """One provider the host currently advertises; ``unregister`` takes it down."""

    def unregister(self) -> None:
        """Remove the provider and every algorithm it added from the host."""
        ...


class Processing(Protocol):
    """Register the providers a plugin owns with the host's Processing registry.

    This is a host-side service, not a page-callable one: a QGIS Desktop host
    provides it so ``PluginRuntime.start()`` can advertise ``providers = [...]``
    in the toolbox, the modeler and ``processing.run`` (decision-42), and
    ``unload()`` can remove them again. A host without a Processing framework
    (the fakes, a standalone Qt application) leaves it out, and the same plugin
    class lists its providers and registers nothing.

    ``register_provider`` refuses, by provider id, a provider the host already
    advertises - two plugins sharing one id would otherwise overwrite each
    other's algorithms silently.
    """

    def register_provider(self, provider: RegistrableProvider) -> ProviderRegistration:
        """Advertise ``provider``; the returned registration removes it again."""
        ...
