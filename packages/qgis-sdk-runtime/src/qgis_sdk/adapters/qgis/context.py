"""Assemble every PyQGIS-backed service into one ``PluginContext``.

``qgis_sdk.adapters.desktop.host()`` is the one place that knows a plugin is
running inside QGIS Desktop (decision-43). This module is what it calls there -
or what a plugin's own ``context_factory`` calls - so a plugin gets the whole
curated surface - layers, project, settings, styles, Processing,
workers and the network client - on ``self.ctx`` with one line, and the web
view built from the same context (``HostServices.from_context``) answers from
the very same instances. Everything is owned by the scope passed in: closing
it releases the layers, aborts the requests in flight and drains the pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qgis_sdk.core import PluginContext, ResourceScope
from qgis_sdk.network import NetworkClient
from qgis_sdk.services import Notifications

from .algorithms import NativeAlgorithms
from .layers import NativeLayers
from .network import NativeNetworkTransport
from .notifications import NativeNotifications
from .processing import NativeProcessing
from .project import NativeProject
from .settings import NativeSettings
from .styles import NativeStyles
from .workers import ThreadPoolWorkers


@dataclass(frozen=True, slots=True)
class IfaceDesktopAccess:
    """``DesktopAccess`` over the ``QgisInterface`` QGIS handed ``classFactory``."""

    iface: object


def native_plugin_context(
    scope: ResourceScope,
    *,
    settings_prefix: str,
    iface: object | None = None,
    notifications: Notifications | None = None,
    working_directory: Path | None = None,
) -> PluginContext:
    """Build the plugin context a QGIS Desktop host offers.

    ``settings_prefix`` scopes the settings service to this plugin's keys in
    the QGIS profile. ``iface`` becomes ``ctx.desktop``; without one (a
    standalone ``QgsApplication``) reading ``ctx.desktop`` refuses by name,
    and the other services still work. ``notifications`` defaults to the QGIS message log;
    a plugin passes its own to reach the message bar. ``working_directory``
    is where Processing outputs land; left out, the service owns a temporary
    directory and removes it with the scope. ``processing`` is the registry
    ``PluginRuntime.start()`` advertises the plugin's ``providers`` with.
    """
    scope.ensure_open()
    layers = NativeLayers(scope)
    transport = NativeNetworkTransport(scope)
    project = NativeProject(layers, scope)
    algorithms = NativeAlgorithms(layers, scope, working_directory=working_directory)
    return PluginContext(
        notifications=(
            notifications if notifications is not None else NativeNotifications(scope)
        ),
        scope=scope,
        desktop=None if iface is None else IfaceDesktopAccess(iface),
        network=NetworkClient(transport, scope),
        layers=layers,
        project=project,
        settings=NativeSettings(scope, prefix=settings_prefix),
        styles=NativeStyles(layers, scope),
        algorithms=algorithms,
        workers=ThreadPoolWorkers(scope),
        processing=NativeProcessing(
            layers=layers, algorithms=algorithms, project=project, scope=scope
        ),
    )
