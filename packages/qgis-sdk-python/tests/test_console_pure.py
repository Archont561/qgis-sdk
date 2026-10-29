"""``qgis_sdk.console`` without QGIS or Qt (TASK-73 AC 1-2, the pure half).

The native half - a session over a real ``iface``, ``native_plugin_context``
and a real ``qgis.utils.plugins`` entry - lives in
``test_console_native.py``; the vendored, installed plugin in the build-install
harness. Here the plugin's adapter is what :func:`qgis_sdk.console.bind` is
handed, so the mapping ``qgis.utils`` would provide is monkeypatched and every
assertion is about this module's own resolution and refusal rules.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from typing import Any

import pytest
from qgis_sdk import QgisSdkPlugin, describe, menu
from qgis_sdk.bindings import describe_bindings
from qgis_sdk.console import (
    ConsoleSession,
    PluginHandle,
    QgisSdkConsoleError,
    bind,
    connect,
    dev_session,
)
from qgis_sdk.core import (
    AlgorithmContext,
    PluginContext,
    PluginRuntime,
    PluginRuntimeState,
    ResourceScope,
)
from qgis_sdk.environment import DEV_REQUEST_ENV
from qgis_sdk.models import (
    CentroidRequest,
    LayerInput,
    QgisSdkBridgeError,
    QgisSdkError,
    QgisSdkUnsupportedCapabilityError,
    VectorLayerInfo,
)
from qgis_sdk.providers import Provider
from qgis_sdk.testing.fakes import FakeProcessing, RecordingNotifications
from qgis_sdk.ui import Dialog


@dataclass
class Recording:
    messages: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(message)


@menu("Plugins/Field tools")
class BufferDialog(Dialog):
    title = "Buffer a layer"

    def build(self) -> object:
        return object()


class LayerPanel(Dialog):
    def build(self) -> object:
        return object()


tools = QgisSdkPlugin(id="field_tools", title="Field tools")
tools.add_surface(BufferDialog)
tools.add_surface(LayerPanel)


@tools.action(id="count", title="Count")
def count(ctx: PluginContext) -> int:
    return len(ctx.capabilities)


@tools.action(id="buffer", title="Buffer")
def buffer_layer(ctx: PluginContext, distance: float, layer_id: str = "roads") -> str:
    return f"{layer_id}+{distance:g}"


@tools.stream(id="ticks", title="Ticks", events={"data": int})
def ticks(ctx: PluginContext, payload: int) -> int:
    raise AssertionError("a console never calls a stream factory")
    yield payload


counter_provider = Provider(id="field_tools", title="Field tools")


@counter_provider.algorithm(id="centroid", title="Centroid")
def centroid(ctx: AlgorithmContext, layer_id: LayerInput) -> VectorLayerInfo:
    """Replace geometries with their centroid."""
    return ctx.algorithms.execute(CentroidRequest(layer_id=layer_id))


tools.add_provider(counter_provider)


class FakeSurfaces:
    """``SurfaceHost.open`` as the console reaches it: records, opens nothing."""

    def __init__(self) -> None:
        self.opened: list[type] = []

    def open(self, surface: type, *, initial: object = None) -> object:
        self.opened.append(surface)
        return surface()


@dataclass
class FakeAdapter:
    """What ``classFactory`` hands QGIS, narrowed to what a handle reads."""

    runtime: PluginRuntime
    context: PluginContext
    surfaces: Any = None

    @property
    def bindings(self) -> Any:
        return describe_bindings(tools)


def context() -> PluginContext:
    scope = ResourceScope()
    return PluginContext(
        notifications=RecordingNotifications(scope),
        scope=scope,
        processing=FakeProcessing(scope),
    )


def started() -> tuple[FakeAdapter, PluginRuntime]:
    runtime = PluginRuntime(tools, context())
    runtime.start()
    return FakeAdapter(runtime, runtime._context, surfaces=FakeSurfaces()), runtime


@pytest.fixture
def adapter_and_runtime() -> Any:
    adapter, runtime = started()
    yield adapter, runtime
    runtime.unload()


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch, adapter_and_runtime: Any) -> Any:
    """A plugin-bound session whose ``qgis.utils.plugins`` holds the adapter."""
    adapter, _runtime = adapter_and_runtime
    monkeypatch.setattr(
        "qgis_sdk.console._loaded_plugins", lambda: {"field_tools": adapter}
    )
    return bind(adapter)


# -- sessions ----------------------------------------------------------------------


@pytest.fixture
def bare_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    """A process with no QGIS in it, even when the suite started one elsewhere.

    The default suite runs the pure modules in the same interpreter as the
    native ones, and this file may run after an application exists; "without a
    host" is a property of the branch, so it is pinned rather than assumed.
    """
    monkeypatch.setattr("qgis_sdk.adapters.desktop.qgis_is_running", lambda: False)
    monkeypatch.setattr("qgis_sdk.console._desktop_iface", lambda: None)


def test_connect_without_a_desktop_gives_a_context_that_refuses_desktop_by_name(
    bare_interpreter: None,
) -> None:
    with connect() as session:
        assert isinstance(session, ConsoleSession)
        assert session.closed is False
        assert session.owns_scope is True
        assert session.scope is session.ctx.scope

        with pytest.raises(QgisSdkUnsupportedCapabilityError) as refused:
            _ = session.ctx.desktop
        assert refused.value.capability == "desktop"

        # Everything that needs no interface still works: the same context a
        # plugin would get, with the absent services refused one name at a time.
        session.ctx.notifications.info("still usable")
        assert session.ctx.has("desktop") is False
        assert session.ctx.has("processing") is False


def test_close_disposes_the_scope_and_a_second_close_is_a_no_op(
    bare_interpreter: None,
) -> None:
    session = connect()
    scope = session.scope

    session.close()
    session.close()

    assert session.closed is True
    assert scope.closed is True

    for read in (lambda: session.ctx, session.plugins):
        with pytest.raises(QgisSdkConsoleError) as refused:
            read()
        assert "closed" in str(refused.value)


def test_a_plugin_session_borrows_the_plugin_context_and_owns_no_scope() -> None:
    adapter, _runtime = started()
    session = bind(adapter)

    assert session.ctx is adapter.context
    assert session.owns_scope is False
    assert session.plugin_name == "field_tools"

    session.close()

    assert adapter.context.scope.closed is False
    assert session.closed is True


def test_bind_refuses_an_adapter_that_holds_no_context() -> None:
    with pytest.raises(QgisSdkConsoleError) as refused:
        bind(object())

    assert "exposes no plugin context" in str(refused.value)


def test_the_context_a_session_hands_out_is_the_object_the_plugin_instance_gets() -> (
    None
):
    adapter, runtime = started()
    session = bind(adapter)

    assert session.ctx is runtime.instance.ctx
    assert session.scope is adapter.context.scope


# -- handles -----------------------------------------------------------------------


def test_plugins_lists_what_qgis_loaded_and_names_the_one_it_lacks(
    monkeypatch: pytest.MonkeyPatch, adapter_and_runtime: Any
) -> None:
    adapter, _runtime = adapter_and_runtime
    monkeypatch.setattr(
        "qgis_sdk.console._loaded_plugins",
        lambda: {"field_tools": adapter, "zzz_other": object()},
    )
    session = connect()

    assert session.plugins() == ("field_tools", "zzz_other")

    with pytest.raises(QgisSdkConsoleError) as refused:
        session.plugin("missing")
    assert "field_tools, zzz_other" in str(refused.value)


def test_a_handle_reports_what_the_plugin_declares(session: Any) -> None:
    handle = session.plugin("field_tools")

    assert isinstance(handle, PluginHandle)
    assert handle.name == "field_tools"
    assert handle.ctx is session.ctx
    assert handle.description == describe(tools)
    assert handle.actions == ("buffer", "count")
    assert handle.streams == ("ticks",)
    assert handle.state is PluginRuntimeState.RUNNING
    assert handle.surfaces() == ("buffer_dialog", "layer_panel")
    assert "field_tools" in repr(handle)


def test_algorithms_lists_the_processing_ids_the_plugin_registered(
    session: Any,
) -> None:
    handle = session.plugin("field_tools")

    assert handle.algorithms == ("field_tools:centroid",)


def test_a_runtime_without_algorithms_refuses_the_attribute_by_name() -> None:
    @dataclass
    class Older:
        description: Any
        actions: dict[str, Any]
        state: str = "running"

    adapter = types.SimpleNamespace(runtime=Older(describe(tools), {}))
    handle = PluginHandle("vendored", adapter, session=connect())

    with pytest.raises(QgisSdkConsoleError) as refused:
        _ = handle.algorithms
    assert "'algorithms'" in str(refused.value)

    with pytest.raises(QgisSdkConsoleError) as refused_surface:
        handle.surfaces()
    assert "places no surfaces" in str(refused_surface.value)


def test_an_adapter_without_a_runtime_refuses_the_handle_by_name() -> None:
    handle = PluginHandle("broken", object(), session=connect())

    with pytest.raises(QgisSdkConsoleError) as refused:
        _ = handle.description
    assert "exposes no 'runtime'" in str(refused.value)


# -- run ---------------------------------------------------------------------------


def test_run_calls_the_handler_with_the_inputs_it_was_given(session: Any) -> None:
    assert session.plugin("field_tools").run("count") == len(session.ctx.capabilities)
    assert session.plugin("field_tools").run("buffer", distance=10.5) == "roads+10.5"
    assert (
        session.plugin("field_tools").run("buffer", distance=1.0, layer_id="rivers")
        == "rivers+1"
    )


def test_run_refuses_inputs_exactly_as_the_bridge_dispatcher_does(session: Any) -> None:
    handle = session.plugin("field_tools")

    with pytest.raises(QgisSdkBridgeError) as wrong_type:
        handle.run("buffer", distance="far")
    assert "payload.distance" in str(wrong_type.value)

    with pytest.raises(QgisSdkBridgeError) as missing:
        handle.run("buffer")
    assert "payload.distance" in str(missing.value)

    with pytest.raises(QgisSdkBridgeError) as unknown:
        handle.run("buffer", distance=1.0, nope=True)
    assert "payload.nope" in str(unknown.value)


def test_run_refuses_an_unknown_action_naming_the_declared_ids(session: Any) -> None:
    with pytest.raises(QgisSdkConsoleError) as refused:
        session.plugin("field_tools").run("nope")

    assert "buffer, count" in str(refused.value)


def test_run_refuses_an_action_the_runtime_did_not_bind(session: Any) -> None:
    adapter = session.plugin("field_tools")._adapter
    adapter.runtime.unload()

    with pytest.raises(QgisSdkConsoleError) as refused:
        session.plugin("field_tools").run("count")
    assert "no handler bound" in str(refused.value)
    assert "stopped" in str(refused.value)


def test_a_handler_that_raises_keeps_its_own_exception() -> None:
    boom = QgisSdkPlugin(id="boom", title="Boom")

    @boom.action(id="explode", title="Explode")
    def explode(ctx: PluginContext) -> None:
        raise ZeroDivisionError("plugin bug")

    runtime = PluginRuntime(boom, context())
    runtime.start()
    handle = PluginHandle(
        "boom", FakeAdapter(runtime, runtime._context), session=connect()
    )

    with pytest.raises(ZeroDivisionError, match="plugin bug"):
        handle.run("explode")


# -- open --------------------------------------------------------------------------


def test_open_resolves_ids_class_names_and_action_ids(session: Any) -> None:
    handle = session.plugin("field_tools")
    host: FakeSurfaces = handle._adapter.surfaces

    assert handle.open("buffer_dialog") is not None
    assert handle.open("BufferDialog") is not None
    assert handle.open("buffer") is not None
    assert host.opened == [BufferDialog, BufferDialog, BufferDialog]

    assert isinstance(handle.open("layer_panel"), LayerPanel)


def test_open_refuses_an_unknown_target_listing_surfaces_and_actions(
    session: Any,
) -> None:
    with pytest.raises(QgisSdkConsoleError) as refused:
        session.plugin("field_tools").open("nowhere")

    message = str(refused.value)
    assert "buffer_dialog, layer_panel" in message
    assert "buffer, count" in message


def test_open_refuses_a_host_that_cannot_show_surfaces() -> None:
    adapter, _runtime = started()
    adapter.surfaces = None
    handle = PluginHandle("field_tools", adapter, session=connect())

    with pytest.raises(QgisSdkConsoleError) as refused:
        handle.open("buffer_dialog")
    assert "opened no surfaces" in str(refused.value)


# -- reload ------------------------------------------------------------------------


def test_dev_session_reads_the_request_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DEV_REQUEST_ENV, raising=False)
    assert dev_session() is False

    monkeypatch.setenv(DEV_REQUEST_ENV, "/tmp/request.json")
    assert dev_session() is True


def test_reload_is_refused_outside_a_dev_session(
    monkeypatch: pytest.MonkeyPatch, session: Any
) -> None:
    monkeypatch.delenv(DEV_REQUEST_ENV, raising=False)

    with pytest.raises(QgisSdkConsoleError) as refused:
        session.plugin("field_tools").reload()
    assert "QGIS_SDK_DEV_REQUEST" in str(refused.value)


@dataclass
class FakeUtils:
    calls: list[str] = field(default_factory=list)
    unload: bool = True
    load: bool = True

    def unloadPlugin(self, name: str) -> bool:
        self.calls.append(f"unload:{name}")
        return self.unload

    def loadPlugin(self, name: str) -> bool:
        self.calls.append(f"load:{name}")
        return self.load

    def startPlugin(self, name: str) -> bool:
        self.calls.append(f"start:{name}")
        return True


def qgis_with(utils: FakeUtils) -> types.ModuleType:
    """A stand-in ``qgis``/``qgis.utils`` pair for the reload path."""
    package = types.ModuleType("qgis")
    package.utils = utils  # type: ignore[attr-defined]
    return package


def test_reload_unloads_and_loads_again_in_a_dev_session(
    monkeypatch: pytest.MonkeyPatch, session: Any
) -> None:
    monkeypatch.setenv(DEV_REQUEST_ENV, "/tmp/request.json")
    utils = FakeUtils()
    monkeypatch.setitem(sys.modules, "qgis", qgis_with(utils))
    monkeypatch.setitem(sys.modules, "qgis.utils", utils)  # type: ignore[arg-type]

    assert session.plugin("field_tools").reload() == "field_tools reloaded"
    assert utils.calls == [
        "unload:field_tools",
        "load:field_tools",
        "start:field_tools",
    ]


def test_reload_leaves_a_working_plugin_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """decision-15: quiesce first, and a refusal is not a reload."""
    monkeypatch.setenv(DEV_REQUEST_ENV, "/tmp/request.json")
    utils = FakeUtils()
    monkeypatch.setitem(sys.modules, "qgis", qgis_with(utils))
    monkeypatch.setitem(sys.modules, "qgis.utils", utils)  # type: ignore[arg-type]

    @dataclass
    class Busy:
        description: Any = field(default_factory=lambda: describe(tools))
        actions: dict[str, Any] = field(default_factory=dict)
        state: str = "running"
        algorithms: tuple[str, ...] = ()

        def quiesce(self) -> object:
            return types.SimpleNamespace(refused=True, blockers=("a running job",))

    handle = PluginHandle(
        "busy", types.SimpleNamespace(runtime=Busy()), session=connect()
    )

    with pytest.raises(QgisSdkConsoleError) as refused:
        handle.reload()
    assert "a running job" in str(refused.value)
    assert utils.calls == []


def test_a_reload_qgis_refuses_reports_which_step_failed(
    monkeypatch: pytest.MonkeyPatch, session: Any
) -> None:
    monkeypatch.setenv(DEV_REQUEST_ENV, "/tmp/request.json")
    utils = FakeUtils(load=False)
    monkeypatch.setitem(sys.modules, "qgis", qgis_with(utils))
    monkeypatch.setitem(sys.modules, "qgis.utils", utils)  # type: ignore[arg-type]

    with pytest.raises(QgisSdkConsoleError) as refused:
        session.plugin("field_tools").reload()
    assert "could not load it again" in str(refused.value)


def test_console_errors_are_sdk_errors_with_their_own_code() -> None:
    error = QgisSdkConsoleError("no")

    assert isinstance(error, QgisSdkError)
    assert error.code == "console_refused"
