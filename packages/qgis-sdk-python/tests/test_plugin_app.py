"""Public application authoring contract."""

import pytest
import qgis_sdk
from qgis_sdk import (
    QgisSdkDeclarationError,
    QgisSdkPlugin,
    describe,
    describe_bindings,
    toolbar,
)
from qgis_sdk.core import PluginContext, PluginRuntime, ResourceScope
from qgis_sdk.testing import RecordingNotifications


def test_class_authoring_decorators_are_not_public() -> None:
    from qgis_sdk import core, declarations, providers

    assert not hasattr(core, "PluginFactory")
    assert not hasattr(providers, "declared_providers")
    for name in ("plugin", "action", "stream", "describe_plugin"):
        assert not hasattr(qgis_sdk, name)
        assert not hasattr(declarations, name)


def test_runtime_rejects_former_plugin_classes() -> None:
    from qgis_sdk.declarations._plugin import plugin

    @plugin(id="legacy", title="Legacy")
    class Legacy:
        pass

    scope = ResourceScope()
    context = PluginContext(scope=scope, notifications=RecordingNotifications(scope))
    with pytest.raises(QgisSdkDeclarationError, match="QgisSdkPlugin"):
        PluginRuntime(Legacy, context)


def test_describe_rejects_former_plugin_classes() -> None:
    from qgis_sdk.declarations._plugin import plugin

    @plugin(id="legacy", title="Legacy")
    class Legacy:
        pass

    with pytest.raises(QgisSdkDeclarationError, match="QgisSdkPlugin"):
        describe(Legacy)
    with pytest.raises(QgisSdkDeclarationError, match="QgisSdkPlugin"):
        describe_bindings(Legacy)


def test_app_and_original_handler_share_description_without_context_input() -> None:
    app = QgisSdkPlugin(id="example", title="Example")
    group = QgisSdkPlugin()

    @group.action(id="double", title="Double")
    def double(ctx: PluginContext, value: int) -> int:
        return value * 2

    app.include(group)
    description = describe(app)
    assert app.describe() == description
    assert describe(double) == double.describe() == description.actions[0]
    assert description.actions[0].request["properties"] == {
        "value": {
            "type": "integer",
            "minimum": -9007199254740991,
            "maximum": 9007199254740991,
        }
    }
    scope = ResourceScope()
    context = PluginContext(notifications=RecordingNotifications(scope), scope=scope)
    assert double(context, 21) == 42
    scope.close()


def test_invalid_declarations_fail_at_registration_without_partial_state() -> None:
    with pytest.raises(QgisSdkDeclarationError):
        QgisSdkPlugin(id="", title="Example")
    app = QgisSdkPlugin(id="example", title="Example")
    with pytest.raises(QgisSdkDeclarationError):
        app.action(id="invalid id", title="Invalid")
    assert describe(app).actions == ()


def test_fake_ui_enforces_application_surface_registration() -> None:
    from qgis_sdk.models import QgisSdkUiError
    from qgis_sdk.testing import FakeUi
    from qgis_sdk.ui import Dialog

    class Allowed(Dialog):
        pass

    class NotAllowed(Dialog):
        pass

    app = QgisSdkPlugin(id="example", title="Example")
    app.add_surface(Allowed)
    scope = ResourceScope()
    ui = FakeUi(scope, app=app)
    ui.open(Allowed, initial={"value": 1})
    assert ui.opened[0].surface is Allowed
    with pytest.raises(QgisSdkUiError, match="NotAllowed is not registered"):
        ui.open(NotAllowed)
    scope.close()


def test_application_bindings_are_describable() -> None:
    app = QgisSdkPlugin(id="example", title="Example")

    @toolbar
    @app.action(id="run", title="Run")
    def run(ctx: PluginContext) -> None:
        pass

    assert [entry.id for entry in describe_bindings(app).entries] == ["run"]
    assert describe(app).bindings == describe_bindings(app)


def test_unresolved_action_annotations_raise_declaration_error() -> None:
    app = QgisSdkPlugin(id="example", title="Example")

    @app.action(id="run", title="Run")
    def run(ctx: PluginContext, value: "NotAType") -> str:  # noqa: F821
        return str(value)

    with pytest.raises(QgisSdkDeclarationError, match="cannot resolve annotations"):
        describe(app)


def test_two_runtimes_of_same_app_keep_contexts_isolated() -> None:
    app = QgisSdkPlugin(id="example", title="Example")

    @app.action(id="speak", title="Speak")
    def speak(ctx: PluginContext, message: str) -> None:
        ctx.notifications.info(message)

    first_scope, second_scope = ResourceScope(), ResourceScope()
    first_log = RecordingNotifications(first_scope)
    second_log = RecordingNotifications(second_scope)
    first = PluginRuntime(
        app=app, context=PluginContext(scope=first_scope, notifications=first_log)
    )
    second = PluginRuntime(
        app, PluginContext(scope=second_scope, notifications=second_log)
    )
    first.start()
    second.start()
    try:
        first.actions["speak"](message="one")
        second.actions["speak"](message="two")
        assert first_log.messages == ["one"]
        assert second_log.messages == ["two"]
    finally:
        first.unload()
        second.unload()
