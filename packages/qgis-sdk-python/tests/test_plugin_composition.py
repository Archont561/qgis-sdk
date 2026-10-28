"""Public plugin composition and surface authoring."""


def test_inclusion_rejects_collisions_and_cycles_without_partial_changes() -> None:
    import pytest
    from qgis_sdk import QgisSdkDeclarationError, QgisSdkPlugin
    from qgis_sdk.core import PluginContext
    from qgis_sdk.providers import Provider
    from qgis_sdk.ui import Dialog

    parent = QgisSdkPlugin(id="root", title="Root")
    child = QgisSdkPlugin(id="child", title="Child")

    @parent.action(id="same", title="Same")
    def original(ctx: PluginContext) -> None:
        pass

    @child.action(id="new", title="New")
    def added(ctx: PluginContext) -> None:
        pass

    @child.action(id="same", title="Same")
    def conflicting(ctx: PluginContext) -> None:
        pass

    @child.surface
    class Report(Dialog):
        pass

    child.add_provider(Provider(id="reports", title="Reports"))
    with pytest.raises(QgisSdkDeclarationError, match="duplicate"):
        parent.include(child)
    assert [item.id for item in parent.describe().actions] == ["same"]
    assert parent.surfaces == () and parent.providers == ()

    one = QgisSdkPlugin(id="one", title="One")
    two = QgisSdkPlugin(id="two", title="Two")
    three = QgisSdkPlugin(id="three", title="Three")
    one.include(two)
    two.include(three)
    with pytest.raises(QgisSdkDeclarationError, match="cycle"):
        three.include(one)
    with pytest.raises(QgisSdkDeclarationError, match="cycle"):
        one.include(one)
    with pytest.raises(QgisSdkDeclarationError, match="already included"):
        one.include(two)

    root = QgisSdkPlugin(id="root2")
    branch = QgisSdkPlugin(id="branch")
    leaf = QgisSdkPlugin(id="leaf")
    branch.include(leaf)
    root.include(branch)
    with pytest.raises(QgisSdkDeclarationError, match="already included"):
        root.include(leaf)


def test_inclusion_refuses_conflicting_surfaces_providers_and_context() -> None:
    import pytest
    from qgis_sdk import QgisSdkDeclarationError, QgisSdkPlugin
    from qgis_sdk.providers import Provider
    from qgis_sdk.ui import Dialog

    class Report(Dialog):
        pass

    parent = QgisSdkPlugin(id="root", title="Root")
    parent.add_surface(Report)
    parent.add_provider(Provider(id="reports", title="Reports"))
    duplicate_surface = QgisSdkPlugin(id="one", title="One")
    duplicate_surface.add_surface(Report)
    with pytest.raises(QgisSdkDeclarationError, match="duplicate surface"):
        parent.include(duplicate_surface)
    duplicate_provider = QgisSdkPlugin(id="two", title="Two")
    duplicate_provider.add_provider(Provider(id="reports", title="Other"))
    with pytest.raises(QgisSdkDeclarationError, match="duplicate provider"):
        parent.include(duplicate_provider)
    has_context = QgisSdkPlugin(id="three", title="Three")
    has_context.context_factory = lambda iface: None
    with pytest.raises(QgisSdkDeclarationError, match="context_factory"):
        parent.include(has_context)
    assert parent.surfaces == (Report,)
    assert [provider.id for provider in parent.providers] == ["reports"]


def test_including_plugin_composes_owned_declarations_as_a_snapshot() -> None:
    from collections.abc import Iterator

    from qgis_sdk import QgisSdkPlugin, describe
    from qgis_sdk.core import PluginContext
    from qgis_sdk.providers import Provider
    from qgis_sdk.ui import Dialog

    child = QgisSdkPlugin(id="reports", title="Reports")

    @child.action(id="count", title="Count")
    def count(ctx: PluginContext, value: int) -> int:
        return value

    @child.stream(id="updates", title="Updates", events={"data": int})
    def updates(ctx: PluginContext) -> Iterator[dict]:
        yield {"kind": "data", "payload": 1}

    @child.surface
    class Report(Dialog):
        pass

    provider = Provider(id="reports", title="Reports")
    child.add_provider(provider)
    parent = QgisSdkPlugin(id="root", title="Root")
    parent.include(child)

    @child.action(id="later", title="Later")
    def later(ctx: PluginContext) -> None:
        pass

    description = describe(parent)
    assert description.id == "root"
    assert [item.id for item in description.actions] == ["count"]
    assert [item.id for item in description.streams] == ["updates"]
    assert [item.cls for item in description.bindings.surfaces] == [Report]
    assert parent.providers == (provider,)


def test_surface_decorator_rejects_invalid_classes() -> None:
    import pytest
    from qgis_sdk import QgisSdkDeclarationError, QgisSdkPlugin

    plugin = QgisSdkPlugin(id="invalid.surface")
    with pytest.raises(QgisSdkDeclarationError, match="Dialog/Dock"):
        plugin.surface(object)
    assert plugin.surfaces == ()


def test_surface_decorator_preserves_class_and_both_binding_orders() -> None:
    from qgis_sdk import QgisSdkPlugin, describe, menu
    from qgis_sdk.ui import Dialog, Dock

    plugin = QgisSdkPlugin(id="tools", title="Tools")

    @plugin.surface
    @menu("Plugins/First")
    class First(Dialog):
        pass

    @menu("Plugins/Second")
    @plugin.surface
    class Second(Dock):
        pass

    bindings = describe(plugin).bindings
    assert [item.cls for item in bindings.surfaces] == [First, Second]
    assert [item.bindings[0].path for item in bindings.surfaces] == [
        "Plugins/First",
        "Plugins/Second",
    ]


def test_plugin_defaults_follow_declaring_module(tmp_path, monkeypatch) -> None:
    import importlib

    package = tmp_path / "composition_defaults_fixture"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "reports.py").write_text(
        "from qgis_sdk import QgisSdkPlugin\n"
        "plugin = QgisSdkPlugin()\n"
        "overridden = QgisSdkPlugin(id='cadastral-survey')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module("composition_defaults_fixture.reports")
    assert module.plugin.describe().id == "composition_defaults_fixture.reports"
    assert module.plugin.describe().title == "Reports"
    assert module.overridden.describe().title == "Cadastral survey"

    from types import FunctionType

    import pytest
    import qgis_sdk
    from qgis_sdk import QgisSdkDeclarationError

    # A function with synthetic globals simulates entry points without a module.
    def construct():
        return synthetic_sdk.QgisSdkPlugin()  # noqa: F821

    for name in ("__main__", None):
        globals_ = {"synthetic_sdk": qgis_sdk}
        if name is not None:
            globals_["__name__"] = name
        construct_in_module = FunctionType(construct.__code__, globals_)
        with pytest.raises(QgisSdkDeclarationError, match="pass id="):
            construct_in_module()


def test_plugin_is_the_single_public_authoring_type() -> None:
    import qgis_sdk
    from qgis_sdk import QgisSdkPlugin

    plugin = QgisSdkPlugin(id="field_tools", title="Field Tools")
    assert plugin.describe().id == "field_tools"
    assert not hasattr(qgis_sdk, "PluginApp")
    assert not hasattr(qgis_sdk, "ActionGroup")
