"""Pure-Python contracts seen by plugin authors and runtime adapters."""

from dataclasses import dataclass, field

import pytest
from qgis_sdk.core import (
    AlgorithmContext,
    JobContext,
    PluginContext,
    ResourceScope,
    UiContext,
)
from qgis_sdk.models import QgisSdkScopeClosedError, QgisSdkUnsupportedCapabilityError


@dataclass
class RecordingNotifications:
    messages: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(message)


def test_pure_plugin_context_rejects_native_desktop_access() -> None:
    context = PluginContext(
        notifications=RecordingNotifications(), scope=ResourceScope()
    )

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as caught:
        _ = context.desktop

    assert (caught.value.code, caught.value.capability) == (
        "unsupported_capability",
        "desktop",
    )


# -- capabilities are attributes that refuse by name (decision-39) ----------------


class FakeWorkers:
    def offload(self, work: object) -> object:
        raise AssertionError("never offloaded in a context test")


@pytest.mark.parametrize(
    "capability",
    [
        "desktop",
        "network",
        "layers",
        "project",
        "settings",
        "styles",
        "algorithms",
        "workers",
    ],
)
def test_every_optional_plugin_capability_is_refused_by_name_when_absent(
    capability: str,
) -> None:
    context = PluginContext(
        notifications=RecordingNotifications(), scope=ResourceScope()
    )

    assert context.has(capability) is False
    with pytest.raises(QgisSdkUnsupportedCapabilityError) as caught:
        getattr(context, capability)
    assert caught.value.capability == capability


def test_a_provided_capability_is_the_very_instance_the_host_passed() -> None:
    workers = FakeWorkers()
    context = JobContext(
        progress=RecordingProgress(),
        cancellation=ControlledCancellation(),
        scope=ResourceScope(),
        workers=workers,
    )

    assert context.workers is workers
    assert context.has("workers") is True
    assert context.has("network") is False
    assert context.capabilities == frozenset({"workers"})
    with pytest.raises(QgisSdkUnsupportedCapabilityError) as caught:
        _ = context.network
    assert caught.value.capability == "network"


def test_capabilities_lists_what_the_host_provided() -> None:
    context = PluginContext(
        notifications=RecordingNotifications(),
        scope=ResourceScope(),
        workers=FakeWorkers(),
    )

    assert context.capabilities == frozenset({"workers"})
    assert context.has("workers") is True


def test_probing_an_unknown_capability_is_a_mistake_not_a_false() -> None:
    context = UiContext(
        notifications=RecordingNotifications(),
        view=RecordingView(),
        scope=ResourceScope(),
    )

    with pytest.raises(ValueError, match="no capability named 'styles'"):
        context.has("styles")


def test_a_capability_read_on_a_closed_scope_is_refused_as_closed() -> None:
    scope = ResourceScope()
    context = JobContext(
        progress=RecordingProgress(),
        cancellation=ControlledCancellation(),
        scope=scope,
        workers=FakeWorkers(),
    )
    scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        _ = context.workers
    assert context.has("workers") is True  # probing does not touch the scope


def test_the_require_accessors_are_gone() -> None:
    for context_type in (PluginContext, UiContext, AlgorithmContext, JobContext):
        leftovers = [name for name in dir(context_type) if name.startswith("require_")]
        assert leftovers == [], (context_type.__name__, leftovers)


def test_a_context_is_immutable_once_assembled() -> None:
    context = PluginContext(
        notifications=RecordingNotifications(), scope=ResourceScope()
    )

    with pytest.raises(AttributeError):
        context.workers = FakeWorkers()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        context.scope = ResourceScope()  # type: ignore[misc]


def test_two_plugin_handlers_use_only_their_injected_services() -> None:
    first = RecordingNotifications()
    second = RecordingNotifications()

    def handler(context: PluginContext, message: str) -> None:
        context.notifications.info(message)

    handler(PluginContext(notifications=first, scope=ResourceScope()), "first")
    handler(PluginContext(notifications=second, scope=ResourceScope()), "second")

    assert (first.messages, second.messages) == (["first"], ["second"])


def test_scope_releases_owned_resources_once() -> None:
    released: list[str] = []
    scope = ResourceScope()
    scope.on_close(lambda: released.append("listener"))

    scope.close()
    scope.close()

    assert released == ["listener"]


def test_scope_runs_cleanup_in_reverse_registration_order() -> None:
    released: list[str] = []
    scope = ResourceScope()
    scope.on_close(lambda: released.append("first"))
    scope.on_close(lambda: released.append("second"))

    scope.close()

    assert released == ["second", "first"]


def test_plugin_scope_closes_owned_view_before_plugin_cleanup() -> None:
    released: list[str] = []
    plugin_scope = ResourceScope()
    plugin_scope.on_close(lambda: released.append("plugin"))
    view_scope = plugin_scope.child()
    view_scope.on_close(lambda: released.append("view"))

    plugin_scope.close()

    assert released == ["view", "plugin"]


def test_closing_one_view_leaves_other_views_and_plugin_running() -> None:
    released: list[str] = []
    plugin_scope = ResourceScope()
    first = plugin_scope.child()
    second = plugin_scope.child()
    first.on_close(lambda: released.append("first"))
    second.on_close(lambda: released.append("second"))

    first.close()
    assert (released, second.closed, plugin_scope.closed) == (["first"], False, False)

    plugin_scope.close()
    assert released == ["first", "second"]


@dataclass
class RecordingView:
    close_requests: int = 0

    def request_close(self) -> None:
        self.close_requests += 1


def test_view_can_request_close_without_disposing_its_plugin() -> None:
    released: list[str] = []
    plugin_scope = ResourceScope()
    view_scope = plugin_scope.child()
    view_scope.on_close(lambda: released.append("view"))
    view = RecordingView()
    context = UiContext(
        notifications=RecordingNotifications(), view=view, scope=view_scope
    )

    context.view.request_close()

    assert (view.close_requests, released, view_scope.closed) == (1, [], False)
    view_scope.close()
    assert (released, plugin_scope.closed) == (["view"], False)


@dataclass
class RecordingProgress:
    fractions: list[float] = field(default_factory=list)

    def report(self, fraction: float) -> None:
        self.fractions.append(fraction)


@dataclass
class ControlledCancellation:
    cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self.cancelled


class NoAlgorithms:
    """Stand-in for the execution capability; these tests never execute."""

    def execute(self, request: object) -> object:
        raise AssertionError("no algorithm runs in a context test")


def test_algorithm_receives_execution_capabilities_not_plugin_state() -> None:
    owner = ResourceScope()
    progress = RecordingProgress()
    cancellation = ControlledCancellation()
    context = AlgorithmContext(
        progress=progress,
        cancellation=cancellation,
        scope=owner.child(),
        algorithms=NoAlgorithms(),
    )

    context.progress.report(0.5)
    cancellation.cancelled = True

    assert (progress.fractions, context.cancellation.is_cancelled()) == ([0.5], True)
    assert context.scope is not owner


def test_view_owned_job_scope_does_not_close_plugin_owned_work() -> None:
    plugin_scope = ResourceScope()
    view_scope = plugin_scope.child()
    cancel_requests: list[str] = []
    job_scope = view_scope.child()
    job_scope.on_close(lambda: cancel_requests.append("request cancellation"))
    view_job = JobContext(
        progress=RecordingProgress(),
        cancellation=ControlledCancellation(),
        scope=job_scope,
    )
    plugin_job = JobContext(
        progress=RecordingProgress(),
        cancellation=ControlledCancellation(),
        scope=plugin_scope.child(),
    )

    view_scope.close()

    assert (cancel_requests, view_job.scope.closed, plugin_job.scope.closed) == (
        ["request cancellation"],
        True,
        False,
    )
    assert plugin_scope.closed is False


def test_scope_runs_remaining_cleanup_after_an_error() -> None:
    released: list[str] = []
    scope = ResourceScope()
    scope.on_close(lambda: released.append("other listener"))

    def fail() -> None:
        raise ValueError("broken listener")

    scope.on_close(fail)

    with pytest.raises(ExceptionGroup) as caught:
        scope.close()

    assert released == ["other listener"]
    assert scope.closed is True
    assert isinstance(caught.value.exceptions[0], ValueError)


def test_failed_view_cleanup_does_not_skip_siblings_or_plugin_cleanup() -> None:
    released: list[str] = []
    plugin_scope = ResourceScope()
    plugin_scope.on_close(lambda: released.append("plugin"))
    sibling = plugin_scope.child()
    sibling.on_close(lambda: released.append("sibling"))
    failing_view = plugin_scope.child()

    def fail() -> None:
        raise ValueError("view cleanup failed")

    failing_view.on_close(fail)

    with pytest.raises(ExceptionGroup):
        plugin_scope.close()

    assert released == ["sibling", "plugin"]
    assert (plugin_scope.closed, sibling.closed, failing_view.closed) == (
        True,
        True,
        True,
    )


@dataclass
class DesktopStub:
    iface: object


def test_closed_scope_rejects_registration_and_native_access() -> None:
    scope = ResourceScope()
    desktop = DesktopStub(iface=object())
    context = PluginContext(
        notifications=RecordingNotifications(), scope=scope, desktop=desktop
    )
    assert context.desktop is desktop
    scope.close()

    with pytest.raises(QgisSdkScopeClosedError) as caught:
        _ = context.desktop
    assert caught.value.code == "scope_closed"
    with pytest.raises(QgisSdkScopeClosedError):
        scope.on_close(lambda: None)
    with pytest.raises(QgisSdkScopeClosedError):
        scope.child()


def test_a_plugin_context_hands_back_the_injected_services() -> None:
    sentinels = {
        name: object()
        for name in ("layers", "project", "settings", "styles", "algorithms", "workers")
    }
    context = PluginContext(
        notifications=RecordingNotifications(), scope=ResourceScope(), **sentinels
    )

    for name, service in sentinels.items():
        assert getattr(context, name) is service
    assert context.capabilities == frozenset(sentinels)


def test_requiring_a_service_on_a_closed_scope_fails_closed() -> None:
    scope = ResourceScope()
    context = PluginContext(
        notifications=RecordingNotifications(), scope=scope, layers=object()
    )
    scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        _ = context.layers


def test_with_services_adds_a_capability_over_the_same_scope() -> None:
    scope = ResourceScope()
    notifications = RecordingNotifications()
    context = PluginContext(notifications=notifications, scope=scope, settings=object())
    ui = object()

    extended = context.with_services(ui=ui)

    assert extended is not context
    assert extended.scope is scope
    assert extended.notifications is notifications
    assert extended.ui is ui
    assert extended.settings is context.settings
    assert context.has("ui") is False
    with pytest.raises(ValueError, match="already provides 'settings'"):
        context.with_services(settings=object())
    with pytest.raises(ValueError, match="no capability named 'iface'"):
        context.with_services(iface=object())
