"""Ordering and ownership of the workflow class itself, observed on the fakes.

The actions in ``test_workflow_pure.py`` prove what the plugin does; this file
proves *when*: the output is styled before it is presented, and nothing is
presented when the run is refused, cancelled or cannot take the style.
"""

from __future__ import annotations

import pytest
from conftest import WORKING_CRS
from qgis_sdk.core import PluginContext, ResourceScope
from qgis_sdk.models import (
    BufferRequest,
    QgisSdkAlgorithmCancelledError,
    QgisSdkScopeClosedError,
    QgisSdkStyleIncompatibleError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.testing import (
    FakeAlgorithms,
    FakeLayers,
    FakeProject,
    FakeStyles,
    RecordingNotifications,
)
from reference_plugin.plugin import FIXTURE
from reference_plugin.workflow import LocalGisWorkflow


class _Journal:
    """Records the order the workflow drives the services in."""

    def __init__(self) -> None:
        self.events: list[str] = []


def _context(
    journal: _Journal,
    *,
    output_fields: tuple[str, ...] = ("id", "value"),
    algorithms_available: bool = True,
) -> tuple[PluginContext, FakeProject, FakeStyles]:
    scope = ResourceScope()
    layers = FakeLayers(scope)
    layers.register(
        FIXTURE, name="points", geometry_type="point", field_names=("id", "value")
    )
    algorithms = FakeAlgorithms(layers, scope)
    algorithms.declare_output(
        BufferRequest,
        FIXTURE.parent / "buffer.gpkg",
        name="buffer",
        geometry_type="polygon",
        field_names=output_fields,
        crs=WORKING_CRS,
    )
    project = FakeProject(layers, scope)
    styles = FakeStyles(layers, scope)

    original_execute = algorithms.execute
    original_apply = styles.apply_style
    original_add = project.add_layer

    def execute(request: object) -> object:
        journal.events.append("execute")
        return original_execute(request)  # type: ignore[arg-type]

    def apply_style(layer_id: str, style: str) -> None:
        journal.events.append(f"style:{style}")
        original_apply(layer_id, style)

    def add_layer(layer_id: str) -> None:
        journal.events.append(f"add:{layer_id}")
        original_add(layer_id)

    algorithms.execute = execute  # type: ignore[method-assign]
    styles.apply_style = apply_style  # type: ignore[method-assign]
    project.add_layer = add_layer  # type: ignore[method-assign]
    context = PluginContext(
        notifications=RecordingNotifications(scope),
        scope=scope,
        layers=layers,
        project=project,
        styles=styles,
        algorithms=algorithms if algorithms_available else None,
    )
    return context, project, styles


def test_buffer_runs_styles_and_only_then_presents_the_output() -> None:
    journal = _Journal()
    context, _project, styles = _context(journal)
    workflow = LocalGisWorkflow(context)
    source = workflow.open_dataset(FIXTURE)

    output = workflow.buffer(source.id, 500.0, WORKING_CRS)

    assert journal.events == [
        f"add:{source.id}",
        "execute",
        f"style:{LocalGisWorkflow.OUTPUT_STYLE}",
        f"add:{output.id}",
    ]
    assert styles.applied(output.id) == (LocalGisWorkflow.OUTPUT_STYLE,)


def test_an_output_the_style_cannot_express_is_not_presented() -> None:
    journal = _Journal()
    context, project, _styles = _context(journal, output_fields=("fid",))
    workflow = LocalGisWorkflow(context)
    source = workflow.open_dataset(FIXTURE)

    with pytest.raises(QgisSdkStyleIncompatibleError):
        workflow.buffer(source.id, 500.0, WORKING_CRS)

    assert project.layer_ids() == (source.id,)
    assert "execute" in journal.events
    assert not any(event.startswith("add:layer-2") for event in journal.events)


def test_a_cancelled_buffer_is_neither_styled_nor_presented() -> None:
    journal = _Journal()
    context, project, styles = _context(journal)
    workflow = LocalGisWorkflow(context)
    source = workflow.open_dataset(FIXTURE)

    class Cancelled:
        def is_cancelled(self) -> bool:
            return True

    with pytest.raises(QgisSdkAlgorithmCancelledError):
        workflow.buffer(source.id, 500.0, WORKING_CRS, cancellation=Cancelled())

    assert project.layer_ids() == (source.id,)
    assert journal.events == [f"add:{source.id}"]
    assert styles.applied(source.id) == ()


def test_a_host_without_processing_refuses_the_buffer_by_name() -> None:
    journal = _Journal()
    context, project, _styles = _context(journal, algorithms_available=False)
    workflow = LocalGisWorkflow(context)
    source = workflow.open_dataset(FIXTURE)

    with pytest.raises(QgisSdkUnsupportedCapabilityError) as error:
        workflow.buffer(source.id, 500.0, WORKING_CRS)

    assert "algorithms" in str(error.value)
    assert project.layer_ids() == (source.id,)


def test_the_workflow_runs_over_the_plugins_own_scope() -> None:
    journal = _Journal()
    context, _project, _styles = _context(journal)
    workflow = LocalGisWorkflow(context)
    source = workflow.open_dataset(FIXTURE)
    workflow.buffer(source.id, 500.0, WORKING_CRS)

    assert not context.scope.closed
    context.scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        workflow.selected_features(source.id)
