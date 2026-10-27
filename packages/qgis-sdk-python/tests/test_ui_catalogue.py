"""Containers, feedback, buttons and ``Custom`` under the fake rendering (TASK-96 AC 2).

The contract tests come from :mod:`ui_catalogue_contract`;
``test_ui_catalogue_native.py`` runs the same ones against the mounted
widgets. The tests below cover what only the fake can show: a surface built
with :func:`qgis_sdk.testing.build_surface`, snapshotted without Qt.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.testing import RecordingLog, build_surface, fake_ui_context
from qgis_sdk.ui import (
    AcceptCancel,
    Column,
    Dialog,
    Dock,
    JobProgress,
    LogView,
    Number,
    Panel,
    RunButton,
    Text,
    describe_surface,
    is_surface_class,
    is_widget_surface,
    snapshot_names,
    ui_snapshot,
)
from ui_catalogue_contract import *
from ui_component_contract import Rendering, make_rendering


@pytest.fixture
def rendering(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Rendering]:
    """The fake rendering: attached to the fakes, never mounted."""
    yield from make_rendering(request, tmp_path, "fake")


class ResultsPanel(Dialog):
    title = "Results"

    def build(self) -> Column:
        self.progress = JobProgress("job")
        return Panel(
            "root",
            [
                Column("inputs", [Number("distance"), Text("note")]),
                RunButton("run", "buffer", progress=self.progress),
                self.progress,
                LogView("log"),
                AcceptCancel(),
            ],
        )

    def on_close(self) -> None:
        self.closed = True


def test_a_surface_builds_under_the_fake_and_its_snapshot_needs_no_qt() -> None:
    scope = ResourceScope()
    log = RecordingLog(scope, "field_tools")
    ctx = fake_ui_context(scope, log=log)

    built = build_surface(ResultsPanel, ctx, initial={"distance": 3})

    assert built.surface.initial == {"distance": 3}
    assert built.root.attached is True
    assert built.find("distance").value() == 0.0
    assert built.find("root") is built.root
    log.info("ready")
    assert built.find("log").lines() == ("[info] ready",)
    assert snapshot_names(ui_snapshot(built)) == (
        "root",
        "inputs",
        "form/distance",
        "form/note",
        "buttons/run",
        "feedback/job",
        "feedback/log",
        "buttons/dialog_buttons",
    )
    assert ui_snapshot(built.root) == ui_snapshot(built)

    built.close()
    assert built.surface.closed is True
    assert scope.closed is True
    assert built.root.attached is False
    with pytest.raises(QgisSdkUiError, match="no child named 'other'"):
        built.find("other")


def test_fake_ui_context_defaults_and_refusals() -> None:
    ctx = fake_ui_context()
    assert ctx.capabilities == frozenset({"log"})
    assert ctx.log.plugin == "test"
    assert ctx.has("actions") is False

    scope = ResourceScope()
    with pytest.raises(QgisSdkUiError, match="not both"):
        fake_ui_context(scope, runtime=object(), actions=object())
    with pytest.raises(QgisSdkUiError, match="not a Dialog/Dock"):
        build_surface(object, fake_ui_context(scope))  # type: ignore[arg-type]


def test_ui_snapshot_refuses_what_is_neither_component_nor_widget() -> None:
    with pytest.raises(QgisSdkUiError, match="takes a component"):
        ui_snapshot(42)


class LegacyPanel:
    """The widget form: no SDK base, a declared kind, ``__init__(ctx)``."""

    kind = "dock"
    area = "left"
    title = "Legacy"

    def __init__(self, ctx: object) -> None:
        self.ctx = ctx


class LegacyDialog:
    kind = "dialog"
    modal = True

    def __init__(self, ctx: object) -> None:
        self.ctx = ctx


def test_a_widget_class_declaring_its_kind_is_accepted_as_a_surface() -> None:
    assert is_surface_class(LegacyPanel) is True
    assert is_widget_surface(LegacyPanel) is True
    assert is_widget_surface(ResultsPanel) is False
    assert is_surface_class(Dock) is False

    described = describe_surface(LegacyPanel)
    assert (described.id, described.title, described.kind, described.area) == (
        "legacy_panel",
        "Legacy",
        "dock",
        "left",
    )
    assert describe_surface(LegacyDialog).modal is True

    with pytest.raises(QgisSdkUiError, match="widget surface"):
        build_surface(LegacyPanel, fake_ui_context())
