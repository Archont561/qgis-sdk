"""Native-only: one call assembles every curated service into a ``PluginContext``.

``native_plugin_context`` is what ``host()`` calls for a plugin when a
``QgsApplication`` is running (decision-43). The assertions are about wiring that review
cannot see: that the project service reads the layers service's registrations,
that ``HostServices.from_context`` wraps the same instances, and that closing
the one scope closes every service at once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qgis_sdk.core import PluginContext, ResourceScope
from qgis_sdk.models import QgisSdkScopeClosedError


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_test_native_plug_p1(_s):
    from qgis.core import QgsApplication

    _s.QgsApplication = QgsApplication


def _cc_test_native_plug_p2(_s):
    from qgis_sdk.adapters.qgis import (
        NativeAlgorithms,
        NativeContextOptions,
        NativeLayers,
        NativeNetworkTransport,
        NativeNotifications,
        NativeProject,
        NativeSettings,
        NativeStyles,
        QgsTaskWorkers,
        native_plugin_context,
    )

    _s.NativeAlgorithms = NativeAlgorithms
    _s.NativeContextOptions = NativeContextOptions
    _s.NativeLayers = NativeLayers
    _s.NativeNetworkTransport = NativeNetworkTransport
    _s.NativeNotifications = NativeNotifications
    _s.NativeProject = NativeProject
    _s.NativeSettings = NativeSettings
    _s.NativeStyles = NativeStyles
    _s.QgsTaskWorkers = QgsTaskWorkers
    _s.native_plugin_context = native_plugin_context


def _cc_test_native_plug_p3(_s):
    from qgis_sdk.bridge.host import HostServices

    _s.HostServices = HostServices
    from qgis_sdk.network import NetworkClient

    _s.NetworkClient = NetworkClient

    _s.iface = object()
    _s.scope = ResourceScope()

    _s.context = _s.native_plugin_context(
        _s.scope,
        _s.NativeContextOptions(settings_prefix="qgis-sdk-test", iface=_s.iface),
    )

    assert isinstance(_s.context, PluginContext)
    assert _s.context.scope is _s.scope


def _cc_test_native_plug_p4(_s):
    assert _s.context.desktop.iface is _s.iface
    assert isinstance(_s.context.layers, _s.NativeLayers)
    assert isinstance(_s.context.project, _s.NativeProject)
    assert isinstance(_s.context.settings, _s.NativeSettings)
    assert isinstance(_s.context.styles, _s.NativeStyles)
    assert isinstance(_s.context.algorithms, _s.NativeAlgorithms)
    # The worker backend is the task manager since 0.9.0 (decision-65).
    assert isinstance(_s.context.workers, _s.QgsTaskWorkers)
    assert _s.context.workers.manager is _s.QgsApplication.taskManager()
    assert isinstance(_s.context.network, _s.NetworkClient)
    assert isinstance(_s.context.notifications, _s.NativeNotifications)


def _cc_test_native_plug_p5(_s):
    _native_plugin_context_wires_phase3(
        _s.HostServices,
        _s.NativeNetworkTransport,
        _s.context,
        _s.native_services,
        _s.scope,
    )


def _native_plugin_context_wires_phase3(
    HostServices, NativeNetworkTransport, context, native_services, scope
):
    assert isinstance(context.network.transport, NativeNetworkTransport)

    # The project service reads what the layer service opened: one layer set.
    info = context.layers.open_vector(native_services.dataset)
    context.project.add_layer(info.id)
    _native_plugin_context_wires_phase2(HostServices, context, info, scope)


def _native_plugin_context_wires_phase2(HostServices, context, info, scope):
    assert info.id in context.project.layer_ids()

    # The web view would wrap exactly these instances.
    services = HostServices.from_context(context)
    assert services.layers is context.layers
    assert services.project is context.project
    assert services.styles is context.styles
    _native_plugin_context_wires_phase1(context, scope, services)


def _native_plugin_context_wires_phase1(context, scope, services):
    assert services.settings is context.settings
    assert services.network is context.network.transport

    scope.close()
    with pytest.raises(QgisSdkScopeClosedError):
        _ = context.layers


pytestmark = pytest.mark.qgis

if TYPE_CHECKING:
    from .conftest import Services


def test_native_plugin_context_wires_every_curated_service(
    native_services: Services,
) -> None:
    _s = _CcState(native_services=native_services)
    for _p in (
        _cc_test_native_plug_p1,
        _cc_test_native_plug_p2,
        _cc_test_native_plug_p3,
        _cc_test_native_plug_p4,
        _cc_test_native_plug_p5,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def test_native_plugin_context_without_an_iface_has_no_desktop_access(
    native_services: Services,
) -> None:
    from qgis_sdk.adapters.qgis import NativeContextOptions, native_plugin_context
    from qgis_sdk.models import QgisSdkUnsupportedCapabilityError

    messages: list[str] = []

    class Bar:
        def info(self, message: str) -> None:
            messages.append(message)

    context = native_plugin_context(
        ResourceScope(),
        NativeContextOptions(settings_prefix="qgis-sdk-test", notifications=Bar()),
    )

    assert context.has("desktop") is False
    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        _ = context.desktop
    context.notifications.info("hello")
    assert messages == ["hello"]
    context.scope.close()
