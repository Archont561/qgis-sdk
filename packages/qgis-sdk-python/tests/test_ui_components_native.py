"""The same component contract against the mounted QGIS widgets (TASK-68 AC 2).

Skips unless the QGIS bindings are importable. Every contract test of
:mod:`ui_component_contract` runs here with ``mount()`` called after
``attach()``, so each assertion is also made against the real widget; the
tests below cover what only a widget can show - the ``objectName``, a user's
edit reaching the state, the QGIS widget classes behind the pickers.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.qgis

try:
    from qgis.core import QgsProject
    from qgis.gui import (
        QgsFieldComboBox,
        QgsFileWidget,
        QgsMapLayerComboBox,
        QgsProjectionSelectionWidget,
    )
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtWidgets import QCheckBox, QLineEdit
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"native components need QGIS: {error}", allow_module_level=True)

from qgis_sdk.ui import (
    Choice,
    Colour,
    CrsPicker,
    DirectoryInput,
    FieldPicker,
    FileInput,
    LayerPicker,
    Number,
    Text,
    Toggle,
)
from ui_component_contract import *
from ui_component_contract import Rendering, make_rendering


@pytest.fixture
def rendering(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Rendering]:
    """The native rendering: attached to the QGIS services and mounted."""
    yield from make_rendering(request, tmp_path, "native")


def test_native_widgets_carry_the_object_name_and_mirror_the_state(
    rendering: Rendering,
) -> None:
    text = rendering.attach(Text("note"))
    toggle = rendering.attach(Toggle("enabled"))

    assert isinstance(text.widget, QLineEdit)
    assert text.widget.objectName() == "form/note"
    assert isinstance(toggle.widget, QCheckBox)
    assert text.mount() is text.widget

    text.set_value("typed")
    toggle.set_value(True)
    assert text.widget.text() == "typed"
    assert toggle.widget.isChecked() is True


def test_native_edits_by_the_user_reach_the_state_and_its_listeners(
    rendering: Rendering, tmp_path: Path
) -> None:
    seen: list[object] = []
    text = rendering.attach(Text("note"))
    number = rendering.attach(Number("count", range=(0, 10)))
    choice = rendering.attach(Choice("mode", options=("fast", "safe")))
    colour = rendering.attach(Colour("fill"))
    source = tmp_path / "a.csv"
    source.write_text("", encoding="utf-8")
    file = rendering.attach(FileInput("source"))
    for component in (text, number, choice, colour, file):
        component.changed(seen.append)

    text.widget.setText("by hand")
    number.widget.setValue(4)
    choice.widget.setCurrentIndex(1)
    colour.widget.setColor(QColor(255, 0, 0, 128))
    file.widget.setFilePath(str(source))

    assert text.value() == "by hand"
    assert number.value() == 4
    assert choice.value() == "safe"
    assert colour.value() == "#ff000080"
    assert file.value().name == "a.csv"
    assert rendering.ctx.files.resolve(file.value()) == source.resolve()
    assert [type(item).__name__ for item in seen] == [
        "str",
        "int",
        "str",
        "str",
        "FileRef",
    ]


def test_native_pickers_are_the_qgis_widgets(rendering: Rendering) -> None:
    layer = rendering.attach(LayerPicker("layer"))
    field = rendering.attach(FieldPicker("attribute", of=layer))
    crs = rendering.attach(CrsPicker("crs"))
    folder = rendering.attach(DirectoryInput("folder"))

    assert isinstance(layer.widget, QgsMapLayerComboBox)
    assert isinstance(field.widget, QgsFieldComboBox)
    assert isinstance(crs.widget, QgsProjectionSelectionWidget)
    assert isinstance(folder.widget, QgsFileWidget)
    assert folder.widget.storageMode() == QgsFileWidget.StorageMode.GetDirectory

    layer_id = rendering.add_layer()
    layer.widget.setLayer(QgsProject.instance().mapLayer(layer_id))
    assert layer.value() == layer_id
    assert field.widget.layer() is QgsProject.instance().mapLayer(layer_id)
    field.widget.setField("kind")
    assert field.value() == "kind"
    crs.set_value("EPSG:4326")
    assert crs.widget.crs().authid() == "EPSG:4326"
