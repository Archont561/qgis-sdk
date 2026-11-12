"""The file plan for one plugin project, and the only writer that touches disk."""

from __future__ import annotations

from typing import Final


def plan_scaffold_facts11(options, values):
    from ._plan import algorithms_module
    from ._templates import GeneratedFile

    if options.algorithm:
        values.append(
            GeneratedFile(f"{options.plugin}/algorithms.py", algorithms_module(options))
        )
    return _plan_scaffold_facts1(options, values)


def _plan_scaffold_facts1(options, values):
    from ._templates import GeneratedFile

    if options.ui == "native":
        values.append(
            GeneratedFile(
                f"{options.plugin}/ui.py", UI_MODULE.format(title=options.title)
            )
        )
    return tuple(sorted(values, key=lambda file: file.path))


def starter_test_facts1(action_ids, options):
    from ._plan import class_name

    return STARTER_TEST.format(
        title=options.title,
        plugin=options.plugin,
        action_ids=", ".join(f'"{identifier}"' for identifier in action_ids),
        algorithm_test=(
            ALGORITHM_TEST.format(plugin=options.plugin) if options.algorithm else ""
        ),
        ui_test=(
            UI_TEST.format(plugin=options.plugin, class_name=class_name(options.plugin))
            if options.ui
            else ""
        ),
        class_name=class_name(options.plugin),
        host_arguments=(
            "" if options.web is None else f', placement="{options.web.placement}"'
        ),
    )


LF: Final = "\n"
ENTRY_POINT = ""
PLUGIN_MODULE = '''"""{title}: a minimal qgis-sdk plugin."""

from __future__ import annotations

from qgis_sdk import QgisSdkPlugin{ui_names}
{algorithm_imports}from qgis_sdk.core import PluginContext
{algorithm_models}{ui_imports}

app = QgisSdkPlugin(id="{plugin}", title="{title}")
{algorithm_providers}{ui_surfaces}

@app.action(id="ping", title="Ping")
def ping(ctx: PluginContext, value: int) -> int:
    """Return the value unchanged so a caller can prove the round trip."""
    return value


@app.action(id="project_layers", title="Project layers")
def project_layers(ctx: PluginContext) -> list[str]:
    """The same project service a web view reaches as ``host.project``."""
    return list(ctx.project.layer_ids())
{algorithm_action}{ui_action}'''
UI_IMPORTS = """
from .ui import PingDialog
"""
UI_SURFACES = """
app.add_surface(PingDialog)
"""
UI_ACTION = '''

@toolbar(text="{title}")
@app.action(id="open_ping", title="Open ping")
def open_ping(ctx: PluginContext) -> None:
    """A bound, no-input action: the toolbar button opens the dialog."""
    ctx.ui.open(PingDialog, initial={{"value": 7}})
'''
UI_MODULE = '''"""{title}: native surfaces, plain classes built in pure PyQt (decision-55).

The dialog declares its components as class attributes: each takes the
attribute's name, the default ``build()`` stacks them, ``@on(component)``
wires the method, and every opening gets its own copies seeded from
``initial``. The host constructs a ``Dialog`` per opening, binds ``self.ctx``
(a ``UiContext``: ``actions``, ``view``, ``notifications``, ``log``) and
``self.initial``, shows what ``build()`` returns and disposes the scope -
connections included - when the window closes. Nothing here imports Qt, so
the module stays importable by the pure tests, ``describe_bindings`` and
``qgis-sdk check``; a ``build()`` returning any QWidget is the escape hatch.
"""

from __future__ import annotations

from qgis_sdk import menu
from qgis_sdk.ui import Button, Dialog, Form, LogView, Number, on


@menu("Plugins/{title}")
class PingDialog(Dialog):
    """Ask for a number and show what the ``ping`` action answers."""

    title = "{title}: ping"

    value = Number(integer=True, required=True)  # objectName form/value
    form = Form([value], action_id="ping")  # submits through ctx.actions
    ping = Button(text="Ping")  # objectName buttons/ping
    answers = LogView(label="Answers")  # shows ctx.log as it arrives

    @on(ping).clicked  # connected after build(); gone with the window
    def pinged(self) -> None:
        """Call the plugin's own action through the validated, view-scoped path."""
        answer = self.form.submit()
        self.ctx.log.info("pong", value=answer)
'''
ALGORITHM_IMPORTS = """from qgis_sdk.algorithms import invoke
"""
ALGORITHM_MODELS = """from qgis_sdk.models import CrsInput, LayerInput, Metres, VectorLayerInfo

from . import algorithms
"""
ALGORITHM_PROVIDERS = """
app.add_provider(algorithms.provider)
"""
ALGORITHM_ACTION = '''

@app.action(id="buffer", title="Buffer a layer")
def buffer(
    ctx: PluginContext,
    layer_id: LayerInput,
    distance_metres: Metres,
    working_crs: CrsInput,
) -> VectorLayerInfo:
    """Run the same algorithm the toolbox offers, from a native or web surface."""
    return invoke(
        algorithms.buffer_layer, ctx, layer_id=layer_id,
        distance_metres=distance_metres, working_crs=working_crs,
    )
'''
ALGORITHMS_MODULE = '''"""The Processing algorithms {title} owns (decision-42).

One provider, one function. The function binds typed inputs to the produced
layer through the injected ``ctx.algorithms``; request validation and the
Processing call belong to the SDK, so the same function runs against the
in-memory fake in a QGIS-free test and against Processing inside QGIS.
"""

from __future__ import annotations

from qgis_sdk.core import AlgorithmContext
from qgis_sdk.models import BufferRequest, CrsInput, LayerInput, Metres, VectorLayerInfo
from qgis_sdk.providers import Provider

provider = Provider(id="{plugin}", title="{title}")


@provider.algorithm(id="buffer", title="Buffer a layer in an explicit working CRS")
def buffer_layer(
    ctx: AlgorithmContext,
    layer_id: LayerInput,
    distance_metres: Metres,
    working_crs: CrsInput,
) -> VectorLayerInfo:
    """Buffer ``layer_id`` by ``distance_metres`` inside the projected ``working_crs``."""
    return ctx.algorithms.execute(
        BufferRequest(
            layer_id=layer_id,
            distance_metres=distance_metres,
            working_crs=working_crs,
        )
    )
'''
STARTER_TEST = '''"""Smoke tests for {title}. They need no QGIS install and no display.

``host()`` is what `qgis-sdk build` and `qgis-sdk dev` bind as ``classFactory``;
outside QGIS it gives the plugin a bare context, so these tests run the real
lifecycle against the SDK's own refusals.
"""

import pytest
from qgis_sdk import describe
from qgis_sdk.adapters.desktop import host

from {plugin}.plugin import app

classFactory = host("{plugin}.plugin:app"{host_arguments})


def test_the_plugin_starts_and_unloads_without_a_host() -> None:
    plugin = classFactory(None)
    plugin.initGui()
    try:
        assert plugin.runtime.state.value == "running"
        assert plugin.runtime.actions["ping"](7) == 7
    finally:
        plugin.unload()
    assert plugin.runtime.state.value == "stopped"


def test_declared_actions_are_the_plugins_public_surface() -> None:
    description = describe(app)

    assert [action.id for action in description.actions] == [{action_ids}]


def test_a_service_the_host_did_not_supply_is_refused_by_name() -> None:
    from qgis_sdk.models import QgisSdkUnsupportedCapabilityError

    plugin = classFactory(None)
    plugin.initGui()
    try:
        with pytest.raises(QgisSdkUnsupportedCapabilityError):
            plugin.runtime.actions["project_layers"]()
    finally:
        plugin.unload()
{algorithm_test}{ui_test}'''
UI_TEST = """

def test_the_bound_action_opens_the_dialog_under_the_fake_ui() -> None:
    from qgis_sdk.core import PluginContext, PluginServices, ResourceScope
    from qgis_sdk.testing import FakeUi, RecordingNotifications
    from {plugin}.plugin import open_ping
    from {plugin}.ui import PingDialog

    scope = ResourceScope()
    ui = FakeUi(scope)
    context = PluginContext(
        notifications=RecordingNotifications(scope),
        scope=scope,
        services=PluginServices(ui=ui),
    )
    open_ping(context)
    assert [opened.surface for opened in ui.opened] == [PingDialog]
    assert dict(ui.opened[0].initial) == {{"value": 7}}
    scope.close()
"""
ALGORITHM_TEST = '''

def test_the_buffer_algorithm_asks_processing_for_exactly_the_request(tmp_path) -> None:
    """The SDK fakes stand in for Processing: what was asked, and what came back."""
    from qgis_sdk.algorithms import invoke
    from qgis_sdk.core import PluginContext, PluginServices, ResourceScope
    from qgis_sdk.models import BufferRequest
    from qgis_sdk.testing import (
        DeclaredOutput,
        FakeAlgorithmSetup,
        FakeAlgorithms,
        FakeLayers,
        FakeProject,
        RecordingNotifications,
        VectorLayerDeclaration,
    )

    from {plugin}.algorithms import buffer_layer, provider

    scope = ResourceScope()
    layers = FakeLayers(scope)
    layers.register(
        VectorLayerDeclaration(
            tmp_path / "points.gpkg",
            name="points",
            geometry_type="point",
            field_names=("id",),
        )
    )
    algorithms = FakeAlgorithms(FakeAlgorithmSetup(layers, scope))
    algorithms.declare_output(
        DeclaredOutput(
            BufferRequest,
            tmp_path / "buffer.gpkg",
            name="buffer",
            geometry_type="polygon",
            field_names=("id",),
            crs="EPSG:3857",
        )
    )
    project = FakeProject(layers, scope)
    ctx = PluginContext(
        notifications=RecordingNotifications(scope),
        scope=scope,
        services=PluginServices(layers=layers, project=project, algorithms=algorithms),
    )
    source = layers.open_vector(tmp_path / "points.gpkg")

    output = invoke(
        buffer_layer, ctx, layer_id=source.id, distance_metres=25.0, working_crs="EPSG:3857"
    )

    assert provider.algorithms == (buffer_layer,)
    assert output.name == "buffer" and output.geometry_type == "polygon"
    (request,) = algorithms.requests
    assert request == BufferRequest(
        layer_id=source.id, distance_metres=25.0, working_crs="EPSG:3857"
    )
    assert project.layer_ids() == (output.id,)
    scope.close()
'''
