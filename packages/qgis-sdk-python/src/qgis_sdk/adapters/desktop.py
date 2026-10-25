"""Desktop lifecycle glue for QGIS ``classFactory``/``initGui``/``unload``.

The adapter delegates construction and disposal to :class:`PluginRuntime`. It
does not import QGIS or Qt: the host passes ``iface`` and an author-provided
``context_factory`` supplies the typed capabilities (including Desktop access)
for that host. This keeps native services and imports outside the pure core and
lets the same adapter be exercised without a display.
"""

from __future__ import annotations

from collections.abc import Callable

from qgis_sdk.core import PluginContext, PluginFactory, PluginRuntime

ContextFactory = Callable[[object], PluginContext]
"""Build the plugin context from the host's opaque Desktop ``iface``."""


class DesktopLifecycleAdapter:
    """The object a generated plugin's ``classFactory`` returns to QGIS."""

    def __init__(
        self,
        plugin_class: type,
        iface: object,
        *,
        context_factory: ContextFactory,
        instance_factory: PluginFactory | None = None,
    ) -> None:
        self._iface = iface
        self._runtime = PluginRuntime(
            plugin_class,
            context_factory(iface),
            instance_factory=instance_factory,
        )

    @property
    def iface(self) -> object:
        """Return the opaque host interface; never serialize or expose it."""
        return self._iface

    @property
    def runtime(self) -> PluginRuntime:
        """Return the lifecycle owner for advanced adapters and tests."""
        return self._runtime

    def initGui(self) -> None:
        """Construct and bind the author plugin once; QGIS calls this."""
        self._runtime.start()

    def unload(self) -> None:
        """Dispose owned resources; repeated calls are safe."""
        self._runtime.unload()


def create_class_factory(
    plugin_class: type,
    *,
    context_factory: ContextFactory,
    instance_factory: PluginFactory | None = None,
) -> Callable[[object], DesktopLifecycleAdapter]:
    """Return a QGIS ``classFactory(iface)`` callable for one plugin class."""

    def class_factory(iface: object) -> DesktopLifecycleAdapter:
        return DesktopLifecycleAdapter(
            plugin_class,
            iface,
            context_factory=context_factory,
            instance_factory=instance_factory,
        )

    return class_factory
