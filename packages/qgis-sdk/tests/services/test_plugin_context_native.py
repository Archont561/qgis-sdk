"""Native-only: one call assembles every curated service into a ``PluginContext``.

``native_plugin_context`` is what a generated plugin's ``build_context`` calls
when QGIS handed it an ``iface``. The assertions are about wiring that review
cannot see: that the project service reads the layers service's registrations,
that ``HostServices.from_context`` wraps the same instances, and that closing
the one scope closes every service at once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qgis_sdk.core import PluginContext, ResourceScope
from qgis_sdk.models import QgisSdkScopeClosedError

pytestmark = pytest.mark.qgis

if TYPE_CHECKING:
    from .conftest import Services


def test_native_plugin_context_wires_every_curated_service(
    native_services: Services,
) -> None:
    from qgis_sdk.adapters.qgis import (
        NativeAlgorithms,
        NativeLayers,
        NativeNetworkTransport,
        NativeNotifications,
        NativeProject,
        NativeSettings,
        NativeStyles,
        ThreadPoolWorkers,
        native_plugin_context,
    )
    from qgis_sdk.bridge.host import HostServices
    from qgis_sdk.network import NetworkClient

    iface = object()
    scope = ResourceScope()

    context = native_plugin_context(scope, settings_prefix="qgis-sdk-test", iface=iface)

    assert isinstance(context, PluginContext)
    assert context.scope is scope
    assert context.require_native().iface is iface
    assert isinstance(context.require_layers(), NativeLayers)
    assert isinstance(context.require_project(), NativeProject)
    assert isinstance(context.require_settings(), NativeSettings)
    assert isinstance(context.require_styles(), NativeStyles)
    assert isinstance(context.require_algorithms(), NativeAlgorithms)
    assert isinstance(context.require_workers(), ThreadPoolWorkers)
    assert isinstance(context.require_network(), NetworkClient)
    assert isinstance(context.notifications, NativeNotifications)
    assert isinstance(context.network.transport, NativeNetworkTransport)

    # The project service reads what the layer service opened: one layer set.
    info = context.layers.open_vector(native_services.dataset)
    context.project.add_layer(info.id)
    assert info.id in context.project.layer_ids()

    # The web view would wrap exactly these instances.
    services = HostServices.from_context(context)
    assert services.layers is context.layers
    assert services.project is context.project
    assert services.styles is context.styles
    assert services.settings is context.settings
    assert services.network is context.network.transport

    scope.close()
    with pytest.raises(QgisSdkScopeClosedError):
        context.require_layers()


def test_native_plugin_context_without_an_iface_has_no_desktop_access(
    native_services: Services,
) -> None:
    from qgis_sdk.adapters.qgis import native_plugin_context
    from qgis_sdk.models import QgisSdkUnsupportedCapabilityError

    messages: list[str] = []

    class Bar:
        def info(self, message: str) -> None:
            messages.append(message)

    context = native_plugin_context(
        ResourceScope(), settings_prefix="qgis-sdk-test", notifications=Bar()
    )

    assert context.desktop is None
    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        context.require_native()
    context.notifications.info("hello")
    assert messages == ["hello"]
    context.scope.close()
