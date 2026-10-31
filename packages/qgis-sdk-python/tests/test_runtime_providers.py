"""``providers = [...]``: the runtime advertises them on start and removes them on unload."""

from __future__ import annotations

import pytest
from qgis_sdk import QgisSdkDeclarationError
from qgis_sdk.bridge.host import host_description
from qgis_sdk.bridge.protocol import HOST_SCHEMA_VERSION
from qgis_sdk.core import (
    AlgorithmContext,
    PluginContext,
    PluginRuntime,
    PluginRuntimeState,
    ResourceScope,
)
from qgis_sdk.declarations._describe import describe_plugin
from qgis_sdk.declarations._plugin import action, plugin
from qgis_sdk.models import VectorLayerInfo
from qgis_sdk.providers import Provider
from qgis_sdk.testing import FakeProcessing, RecordingNotifications
from qgis_sdk_tools.generate import contract_fingerprint
from sample_algorithms import sample_provider


def _context(scope: ResourceScope, processing: FakeProcessing | None) -> PluginContext:
    return PluginContext(
        notifications=RecordingNotifications(scope), scope=scope, processing=processing
    )


def _tools(provider_id: str = "tools") -> Provider:
    provider = Provider(id=provider_id, title="Tools")

    @provider.algorithm
    def copy_layer(ctx: AlgorithmContext) -> VectorLayerInfo: ...

    return provider


def test_start_registers_every_listed_provider_and_unload_removes_them() -> None:
    tools = _tools()

    @plugin(id="owner", title="Owner")
    class Owner:
        providers = (tools, sample_provider)

    scope = ResourceScope()
    processing = FakeProcessing(scope)
    runtime = PluginRuntime._from_plugin_class(Owner, _context(scope, processing))

    assert runtime.providers == (tools, sample_provider)
    assert (processing.registered, runtime.registered_providers) == ((), ())

    runtime.start()

    assert processing.registered == ("tools", "sample")
    assert runtime.registered_providers == ("tools", "sample")
    assert processing.provider("tools") is tools

    runtime.unload()

    assert (processing.registered, runtime.registered_providers) == ((), ())
    assert processing.events == [
        ("register", "tools"),
        ("register", "sample"),
        ("unregister", "sample"),
        ("unregister", "tools"),
    ]


def test_algorithms_lists_the_ids_the_registry_advertises_while_running() -> None:
    """TASK-73: the console reads what a running plugin added to Processing."""
    tools = _tools()

    @plugin(id="owner", title="Owner")
    class Owner:
        providers = (tools, sample_provider)

    scope = ResourceScope()
    runtime = PluginRuntime._from_plugin_class(
        Owner, _context(scope, FakeProcessing(scope))
    )

    assert runtime.algorithms == ()

    runtime.start()

    assert runtime.algorithms == (
        f"tools:{tools.describe().algorithms[0].id}",
        "sample:buffer",
        "sample:centroid",
    )

    runtime.unload()

    assert runtime.algorithms == ()


def test_the_same_class_over_a_host_without_processing_registers_nothing() -> None:
    @plugin(id="owner", title="Owner")
    class Owner:
        providers = (sample_provider,)

    runtime = PluginRuntime._from_plugin_class(Owner, _context(ResourceScope(), None))

    runtime.start()

    assert runtime.state is PluginRuntimeState.RUNNING
    assert runtime.providers == (sample_provider,)
    assert runtime.registered_providers == ()
    assert runtime.algorithms == ()
    runtime.unload()


def test_two_plugins_sharing_a_provider_id_are_refused_by_name() -> None:
    first, second = _tools("shared"), _tools("shared")

    @plugin(id="one", title="One")
    class One:
        providers = (first,)

    @plugin(id="two", title="Two")
    class Two:
        providers = (second,)

    scope = ResourceScope()
    processing = FakeProcessing(scope)
    PluginRuntime._from_plugin_class(One, _context(scope.child(), processing)).start()

    other = PluginRuntime._from_plugin_class(Two, _context(scope.child(), processing))
    with pytest.raises(QgisSdkDeclarationError, match="'shared' is already registered"):
        other.start()

    assert other.state is PluginRuntimeState.FAILED
    assert processing.registered == ("shared",)
    assert processing.provider("shared") is first


def test_a_refused_start_removes_what_it_had_already_registered() -> None:
    taken = _tools("taken")
    scope = ResourceScope()
    processing = FakeProcessing(scope)
    processing.register_provider(taken)

    @plugin(id="late", title="Late")
    class Late:
        providers = (_tools("fresh"), _tools("taken"))

    runtime = PluginRuntime._from_plugin_class(
        Late, _context(scope.child(), processing)
    )
    with pytest.raises(QgisSdkDeclarationError, match="'taken' is already registered"):
        runtime.start()

    assert processing.registered == ("taken",)
    assert processing.provider("taken") is taken
    assert runtime.registered_providers == ()


def test_a_bad_providers_attribute_is_refused_when_the_runtime_is_built() -> None:
    @plugin(id="typo", title="Typo")
    class Typo:
        providers = sample_provider

    with pytest.raises(QgisSdkDeclarationError, match="Typo.providers must be a list"):
        PluginRuntime._from_plugin_class(Typo, _context(ResourceScope(), None))


def test_unload_is_still_a_safe_no_op_after_a_refused_start() -> None:
    scope = ResourceScope()
    processing = FakeProcessing(scope)
    processing.register_provider(_tools("taken"))

    @plugin(id="late", title="Late")
    class Late:
        providers = (_tools("taken"),)

    runtime = PluginRuntime._from_plugin_class(
        Late, _context(scope.child(), processing)
    )
    with pytest.raises(QgisSdkDeclarationError):
        runtime.start()

    runtime.unload()
    runtime.unload()

    assert processing.registered == ("taken",)


def test_providers_do_not_change_the_plugin_description_or_the_host_contract() -> None:
    @plugin(id="same", title="Same")
    class Plain:
        @action(id="ping", title="Ping")
        def ping(self) -> str:
            return "pong"

    @plugin(id="same", title="Same")
    class WithProviders:
        providers = (sample_provider,)

        @action(id="ping", title="Ping")
        def ping(self) -> str:
            return "pong"

    assert describe_plugin(WithProviders).to_dict() == describe_plugin(Plain).to_dict()
    # Providers are host-side registrations, not page-callable operations: the
    # host contract the generated clients pin does not move (decision-42).
    assert HOST_SCHEMA_VERSION == 1
    assert contract_fingerprint(host_description()).startswith("sha256:8c6bd797")
