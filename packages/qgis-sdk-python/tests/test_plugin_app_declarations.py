"""Application authoring, dispatch, composition and description contracts."""

import pytest
from qgis_sdk import QgisSdkDeclarationError, QgisSdkPlugin
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.declarations import describe
from qgis_sdk.declarations._describe import describe_plugin
from qgis_sdk.declarations._plugin import action, plugin
from qgis_sdk.testing import RecordingNotifications
from qgis_sdk_tools.generate import generate_schema_typescript


def test_registered_action_preserves_identity_and_matches_class_contract() -> None:
    @plugin(id="survey.plugin", title="Survey")
    class ClassPlugin:
        @action(id="double", title="Double")
        def double(self, value: int) -> int:
            return value * 2

    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    def double(ctx: PluginContext, value: int) -> int:
        return value * 2

    original = double
    double = app.action(id="double", title="Double")(double)
    assert double is original
    generated = app
    expected = describe_plugin(ClassPlugin).to_dict()
    actual = describe(generated).to_dict()
    assert actual == expected
    assert "ctx" not in actual["actions"][0]["request"]["properties"]
    assert generate_schema_typescript(actual) == generate_schema_typescript(expected)
    scope = ResourceScope()
    context = PluginContext(notifications=RecordingNotifications(scope), scope=scope)
    runtime = PluginRuntime(generated, context)
    runtime.start()
    assert runtime.actions["double"](value=21) == 42
    runtime.unload()
    assert context.scope.closed


def test_explicit_group_inclusion_is_isolated_and_rejects_duplicates_atomically() -> (
    None
):
    group = QgisSdkPlugin()

    @group.action(id="alpha", title="Alpha")
    def alpha(ctx: PluginContext, value: int) -> int:
        return value

    one = QgisSdkPlugin(id="survey.one", title="One")
    two = QgisSdkPlugin(id="survey.two", title="Two")
    one.include(group)
    assert [item.id for item in one.describe().actions] == ["alpha"]
    assert list(two.describe().actions) == []
    two.include(group)
    assert [item.id for item in two.describe().actions] == ["alpha"]

    conflicting = QgisSdkPlugin()

    @conflicting.action(id="beta", title="Beta")
    def beta(ctx: PluginContext, value: int) -> int:
        return value

    @conflicting.action(id="alpha", title="Duplicate")
    def duplicate(ctx: PluginContext, value: int) -> int:
        return value

    with pytest.raises(QgisSdkDeclarationError, match="duplicate"):
        one.include(conflicting)
    assert [item.id for item in one.describe().actions] == ["alpha"]
    with pytest.raises(QgisSdkDeclarationError, match="duplicate"):
        one.include(group)


def test_fake_contexts_and_dispatch_preserve_authority_and_validate_inputs() -> None:
    from qgis_sdk.bridge import BRIDGE_PROTOCOL_VERSION, Dispatcher

    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    @app.action(id="notify", title="Notify")
    def notify(ctx: PluginContext, message: str) -> str:
        ctx.notifications.info(message)
        return message

    first_scope, second_scope = ResourceScope(), ResourceScope()
    first, second = (
        RecordingNotifications(first_scope),
        RecordingNotifications(second_scope),
    )
    ctx1 = PluginContext(notifications=first, scope=first_scope)
    ctx2 = PluginContext(notifications=second, scope=second_scope)
    assert notify(ctx1, "direct") == "direct"
    runtime = PluginRuntime(app, ctx2)
    runtime.start()
    dispatcher = Dispatcher.from_runtime(
        runtime, authorize=lambda binding, op: op == "notify"
    )
    binding = dispatcher.bind(view_id="one", origin="qgis://desktop")

    def call(operation, payload):
        return dispatcher.dispatch(
            binding,
            {
                "protocol": BRIDGE_PROTOCOL_VERSION,
                "call_id": "1",
                "operation": operation,
                "payload": payload,
            },
        )

    assert call("notify", {"message": "wire"})["value"] == "wire"
    assert not call("notify", {"message": 42})["ok"]
    assert not call("other", {})["ok"]
    assert first.messages == ["direct"]
    assert second.messages == ["wire"]
    runtime.unload()
    assert ctx2.scope.closed


def test_stacked_desktop_bindings_survive_lowering_without_wire_changes() -> None:
    from qgis_sdk.bindings import menu, shortcut, toolbar

    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    @menu("Plugins/Survey")
    @toolbar(icon="survey.svg")
    @shortcut("Ctrl+Alt+S")
    @app.action(id="run", title="Run")
    def run(ctx: PluginContext) -> None:
        pass

    lowered = app
    described = describe(lowered)
    kinds = {binding.kind for binding in described.actions[0].bindings}
    assert kinds == {"menu", "toolbar", "shortcut"}
    assert "bindings" not in described.to_dict()["actions"][0]


def test_discovery_accepts_app_and_rejects_missing_targets(
    tmp_path, monkeypatch
) -> None:
    from qgis_sdk.models import QgisSdkBridgeError
    from qgis_sdk_tools.generate import describe_plugin_spec

    (tmp_path / "app_project.py").write_text(
        "from qgis_sdk import QgisSdkPlugin\n"
        'app = QgisSdkPlugin(id="survey.plugin", title="Survey")\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert describe_plugin_spec("app_project:app")["id"] == "survey.plugin"
    with pytest.raises(QgisSdkBridgeError, match="has no attribute"):
        describe_plugin_spec("app_project:missing")
    with pytest.raises(QgisSdkBridgeError, match="cannot import"):
        describe_plugin_spec("no_such_application:app")


def test_duplicate_handler_names_are_refused_without_partial_registration() -> None:
    group = QgisSdkPlugin()

    def handler(ctx: PluginContext, value: int) -> int:
        return value

    group.action(id="first", title="First")(handler)
    with pytest.raises(QgisSdkDeclarationError, match="duplicate"):
        group.action(id="second", title="Second")(handler)
    app = QgisSdkPlugin(id="survey.plugin", title="Survey")
    app.include(group)
    assert [action.id for action in app.describe().actions] == ["first"]


def test_context_is_required_at_lowering() -> None:
    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    @app.action(id="bad", title="Bad")
    def bad(value: int) -> int:
        return value

    with pytest.raises(QgisSdkDeclarationError, match="PluginContext"):
        app.describe()


def test_input_named_function_does_not_replace_the_registered_handler() -> None:
    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    @app.action(id="run", title="Run")
    def run(ctx: PluginContext, _function: int) -> int:
        return _function + 1

    scope = ResourceScope()
    ctx = PluginContext(notifications=RecordingNotifications(scope), scope=scope)
    runtime = PluginRuntime(app, ctx)
    runtime.start()
    assert runtime.actions["run"](_function=41) == 42
    runtime.unload()


def test_keyword_only_injected_context_is_refused_instead_of_misdispatching() -> None:
    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    @app.action(id="bad", title="Bad")
    def bad(*, ctx: PluginContext, value: int) -> int:
        return value

    with pytest.raises(QgisSdkDeclarationError, match="positional"):
        app.describe()


def test_two_live_applications_have_independent_contexts_and_unload() -> None:
    group = QgisSdkPlugin()

    @group.action(id="speak", title="Speak")
    def speak(ctx: PluginContext, message: str) -> str:
        ctx.notifications.info(message)
        return message

    one = QgisSdkPlugin(id="survey.one", title="One")
    two = QgisSdkPlugin(id="survey.two", title="Two")
    one.include(group)
    two.include(group)
    scope1, scope2 = ResourceScope(), ResourceScope()
    notifications1, notifications2 = (
        RecordingNotifications(scope1),
        RecordingNotifications(scope2),
    )
    first = PluginRuntime(
        one, PluginContext(notifications=notifications1, scope=scope1)
    )
    second = PluginRuntime(
        two, PluginContext(notifications=notifications2, scope=scope2)
    )
    first.start()
    second.start()
    first.actions["speak"](message="one")
    second.actions["speak"](message="two")
    first.unload()
    second.actions["speak"](message="still alive")
    assert notifications1.messages == ["one"]
    assert notifications2.messages == ["two", "still alive"]
    assert scope1.closed and not scope2.closed
    second.unload()


def test_group_membership_is_a_snapshot_and_description_order_is_deterministic() -> (
    None
):
    group = QgisSdkPlugin()

    @group.action(id="zulu", title="Zulu")
    def zulu(ctx: PluginContext) -> int:
        return 1

    app = QgisSdkPlugin(id="survey.plugin", title="Survey")
    app.include(group)

    @group.action(id="alpha", title="Alpha")
    def alpha(ctx: PluginContext) -> int:
        return 2

    assert [item.id for item in app.describe().actions] == ["zulu"]
    other = QgisSdkPlugin(id="survey.other", title="Other")
    other.include(group)
    assert [item.id for item in other.describe().actions] == ["alpha", "zulu"]


def test_multi_module_groups_require_explicit_inclusion(tmp_path, monkeypatch) -> None:
    import importlib

    package = tmp_path / "application_survey"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "actions.py").write_text(
        "from qgis_sdk.core import PluginContext\n"
        "from qgis_sdk import QgisSdkPlugin\n"
        "reports = QgisSdkPlugin()\n"
        "@reports.action(id='double', title='Double')\n"
        "def double(ctx: PluginContext, value: int) -> int:\n"
        "    return value * 2\n",
        encoding="utf-8",
    )
    (package / "plugin.py").write_text(
        "from qgis_sdk import QgisSdkPlugin\n"
        "from .actions import reports\n"
        "app = QgisSdkPlugin(id='survey.plugin', title='Survey')\n"
        "app.include(reports)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module("application_survey.plugin")
    assert [item.id for item in describe(module.app).actions] == ["double"]
    scope = ResourceScope()
    ctx = PluginContext(notifications=RecordingNotifications(scope), scope=scope)
    runtime = PluginRuntime(module.app, ctx)
    runtime.start()
    assert runtime.actions["double"](value=21) == 42
    runtime.unload()


def test_unsupported_async_and_generator_handlers_fail_closed() -> None:
    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    @app.action(id="async_action", title="Async")
    async def async_action(ctx: PluginContext) -> int:
        return 1

    with pytest.raises(QgisSdkDeclarationError, match="synchronous"):
        app.describe()

    group = QgisSdkPlugin(id="survey.other", title="Other")

    @group.action(id="generator", title="Generator")
    def generator(ctx: PluginContext):
        yield 1

    with pytest.raises(QgisSdkDeclarationError, match="synchronous"):
        group.describe()


def test_explicit_surface_and_provider_are_owned_by_the_lowered_runtime() -> None:
    from qgis_sdk.bindings import menu
    from qgis_sdk.providers import Provider
    from qgis_sdk.testing import FakeProcessing
    from qgis_sdk.ui import Dialog

    @menu("Plugins/Survey")
    class ReportDialog(Dialog):
        title = "Report"

        def build(self) -> object:
            return object()

    app = QgisSdkPlugin(id="survey.plugin", title="Survey")
    app.add_surface(ReportDialog)
    app.add_provider(Provider(id="survey", title="Survey"))
    generated = app
    assert [s.id for s in describe(generated).bindings.surfaces] == ["report_dialog"]
    scope = ResourceScope()
    processing = FakeProcessing(scope)
    ctx = PluginContext(
        notifications=RecordingNotifications(scope), scope=scope, processing=processing
    )
    runtime = PluginRuntime(generated, ctx)
    runtime.start()
    assert runtime.registered_providers == ("survey",)
    runtime.unload()
    assert runtime.registered_providers == ()


def test_group_stream_lowers_to_sdk_stream_and_shares_action_namespace() -> None:
    from collections.abc import Iterator

    group = QgisSdkPlugin()

    @group.stream(id="ticks", title="Ticks", events={"data": int})
    def ticks(ctx: PluginContext, count: int) -> Iterator[dict]:
        for index in range(count):
            yield {"kind": "data", "payload": index}

    app = QgisSdkPlugin(id="survey.plugin", title="Survey")
    app.include(group)
    description = app.describe()
    assert [item.id for item in description.streams] == ["ticks"]
    assert "ctx" not in description.streams[0].request["properties"]
    scope = ResourceScope()
    runtime = PluginRuntime(
        app,
        PluginContext(notifications=RecordingNotifications(scope), scope=scope),
    )
    runtime.start()
    assert list(runtime.streams["ticks"](count=2)) == [
        {"kind": "data", "payload": 0},
        {"kind": "data", "payload": 1},
    ]
    runtime.unload()

    with pytest.raises(QgisSdkDeclarationError, match="duplicate"):
        app.action(id="ticks", title="Duplicate")(lambda ctx: None)


def test_equivalent_stream_bridge_descriptions_and_generated_schema_match() -> None:
    from collections.abc import Iterator

    from qgis_sdk.declarations._plugin import stream

    @plugin(id="survey.plugin", title="Survey")
    class Existing:
        @stream(id="ticks", title="Ticks", events={"data": int})
        def ticks(self, count: int) -> Iterator[dict]:
            yield {"kind": "data", "payload": count}

    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    @app.stream(id="ticks", title="Ticks", events={"data": int})
    def ticks(ctx: PluginContext, count: int) -> Iterator[dict]:
        yield {"kind": "data", "payload": count}

    expected = describe_plugin(Existing).to_dict()
    actual = app.describe().to_dict()
    assert actual == expected
    assert generate_schema_typescript(actual) == generate_schema_typescript(expected)


def test_lifecycle_member_names_cannot_overwrite_owned_declarations() -> None:
    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    @app.action(id="show", title="Show")
    def surfaces(ctx: PluginContext) -> int:
        return 1

    with pytest.raises(QgisSdkDeclarationError, match="reserved"):
        app.describe()


def test_unified_describe_handles_app_and_original_action_with_ui_metadata() -> None:
    from qgis_sdk import menu
    from qgis_sdk.ui import on

    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    @menu("Plugins/Survey")
    @on("button").clicked
    @app.action(id="count", title="Count")
    def count(ctx: PluginContext, value: int) -> int:
        return value

    expected = app.describe()
    assert describe(app).to_dict() == expected.to_dict()
    action_description = describe(count)
    assert count.describe() == action_description
    assert action_description.id == "count"
    assert [item.kind for item in action_description.bindings] == ["menu"]
    assert [item.kind for item in action_description.wires] == ["on"]
    assert action_description.to_dict() == expected.actions[0].to_dict()
    assert [item.kind for item in expected.actions[0].wires] == ["on"]
    assert "ctx" not in action_description.request["properties"]


def test_function_introspection_works_for_both_stacking_orders_and_streams() -> None:
    from collections.abc import Iterator

    from qgis_sdk import menu
    from qgis_sdk.ui import on

    group = QgisSdkPlugin()

    @group.action(id="first", title="First")
    @on("button").clicked
    @menu("Plugins/Survey")
    def first(ctx: PluginContext) -> int:
        return 1

    @group.stream(id="ticks", title="Ticks", events={"data": int})
    def ticks(ctx: PluginContext, count: int) -> Iterator[dict]:
        yield {"kind": "data", "payload": count}

    first_description = describe(first)
    assert first.describe() == first_description
    assert [binding.kind for binding in first_description.bindings] == ["menu"]
    assert [wire.kind for wire in first_description.wires] == ["on"]
    stream_description = describe(ticks)
    assert ticks.describe() == stream_description
    assert stream_description.id == "ticks"
    assert "ctx" not in stream_description.request["properties"]


def test_describe_name_collision_does_not_partially_register() -> None:
    from qgis_sdk.declarations import QgisSdkDeclarationError

    app = QgisSdkPlugin(id="survey.plugin", title="Survey")

    def count(ctx: PluginContext) -> int:
        return 1

    count.describe = "author-owned"
    with pytest.raises(QgisSdkDeclarationError, match="already defines 'describe'"):
        app.action(id="count", title="Count")(count)
    assert app.describe().actions == ()
    assert count.describe == "author-owned"
