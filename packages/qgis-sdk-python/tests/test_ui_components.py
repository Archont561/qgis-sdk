"""The catalogue's eleven input components under the fake rendering (TASK-68 AC 2).

A component holds its state without Qt - ``value()``/``set_value()`` speak
models (a layer id, a ``FileRef``, a number, a colour string), never Qt
types - and that state is what a pure test asserts on. The contract tests
come from :mod:`ui_component_contract`; ``test_ui_components_native.py``
runs the same ones against the mounted widgets.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import layers as layer_env
import pytest
from qgis_sdk.core import ResourceScope, UiContext
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.testing import FakeViewControl, RecordingNotifications
from qgis_sdk.ui import (
    Choice,
    Colour,
    Component,
    CrsPicker,
    DirectoryInput,
    Distance,
    FieldPicker,
    FileInput,
    LayerPicker,
    Number,
    Text,
    Toggle,
)
from ui_component_contract import *
from ui_component_contract import Rendering, make_rendering

ELEVEN = (
    LayerPicker,
    FieldPicker,
    CrsPicker,
    FileInput,
    DirectoryInput,
    Distance,
    Number,
    Text,
    Toggle,
    Choice,
    Colour,
)


@pytest.fixture
def rendering(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Rendering]:
    """The fake rendering: attached to in-memory services, never mounted."""
    yield from make_rendering(request, tmp_path, "fake")


def test_qgis_sdk_ui_imports_without_qt() -> None:
    """The catalogue imports lazily: a pure test process never loads Qt."""
    script = (
        "import sys; sys.path[:0] = sys.argv[1:]; import qgis_sdk.ui; "
        "loaded = [m for m in sys.modules if m.startswith(('PyQt', 'qgis.'))]; "
        "assert not loaded, loaded"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, *map(str, layer_env.SOURCE_ROOTS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_every_component_names_its_widget_after_its_field() -> None:
    """The ``objectName`` an agent or a test selects by is the field's path."""
    for cls in ELEVEN:
        component = _make(cls, "my_field")
        assert component.object_name == "form/my_field"
        assert component.snapshot()["objectName"] == "form/my_field"
        assert component.snapshot()["type"] == cls.__name__


def test_mounting_without_qgis_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a machine without Qt the error names the component, not a Qt internal."""
    from qgis_sdk.ui.components import NATIVE_CATALOGUE

    monkeypatch.delitem(sys.modules, NATIVE_CATALOGUE, raising=False)
    for module in ("qgis.PyQt", "qgis.core", "qgis.gui", "PyQt6", "PyQt5"):
        monkeypatch.setitem(sys.modules, module, None)

    with pytest.raises(QgisSdkUiError, match="Text 'note' needs QGIS"):
        Text("note").mount()


def test_the_widget_is_only_there_once_mounted() -> None:
    with pytest.raises(QgisSdkUiError, match="not mounted"):
        _ = Text("note").widget


def test_a_component_attaches_to_one_context_once() -> None:
    """Re-attaching to the same context is a no-op (a container attaches its
    children); a second context is refused."""
    scope = ResourceScope()
    ctx = UiContext(RecordingNotifications(scope), FakeViewControl(), scope)
    other = UiContext(RecordingNotifications(scope), FakeViewControl(), scope)
    component = Text("note").attach(ctx)

    assert component.attach(ctx) is component
    with pytest.raises(QgisSdkUiError, match="already attached"):
        component.attach(other)


def _make(cls: type[Component], name: str = "field") -> Component:
    if cls is Choice:
        return Choice(name, options=("fast", "safe"))
    if cls is FieldPicker:
        return FieldPicker(name, of=LayerPicker("layer"))
    return cls(name)
