"""Native form rendering and handler dispatch (TASK-3, acceptance criteria 1-3).

Skips unless Qt and the QGIS gui bindings are importable, which is the honest
split: the widget mapping itself is pinned by ``test_ui.py`` in the QGIS-free
suite, and this file only proves the mechanical half - a spec becomes a concrete
widget, a submitted value is read back, and the declared handler runs with
coerced arguments.

The imports are guarded rather than left to ``importorskip`` because a *broken*
Qt install raises ``ImportError`` from inside the module (a missing ``libGL`` is
the usual one, and it says so), and a collection error there would take the whole
run down instead of reporting what this machine lacks.

The runtime here is a stub rather than ``PluginRuntime``. The adapter reads
exactly three attributes from it (``description``, ``actions``, ``instance``), so
a stub states that contract instead of hiding it behind a full plugin setup.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# The pixi environment keeps the QGIS bindings in share/qgis/python instead of
# on sys.path, which is how the services contract suite finds them as well.
_BINDINGS = Path(sys.prefix) / "share" / "qgis" / "python"
if _BINDINGS.is_dir() and str(_BINDINGS) not in sys.path:
    sys.path.insert(0, str(_BINDINGS))
os.environ.setdefault("QGIS_PREFIX_PATH", sys.prefix)
os.environ.setdefault("PROJ_LIB", str(Path(sys.prefix) / "share" / "proj"))

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QLineEdit,
        QSpinBox,
    )
    from qgis.gui import QgsMapLayerComboBox, QgsProjectionSelectionWidget
    from qgis_sdk.adapters.qgis import ui as native_ui
    from qgis_sdk.declarations import action, describe_plugin, plugin
    from qgis_sdk.models import CrsInput, LayerInput, Metres, QgisSdkFormError
except ImportError as error:  # pragma: no cover - depends on the host
    pytest.skip(f"native forms need Qt and QGIS: {error}", allow_module_level=True)


@plugin(id="demo.forms", title="Form demo")
class FormDemo:
    """One action per widget family, with the handler recording what it got."""

    def __init__(self, calls):
        self.calls = calls

    @action(id="demo.plain", title="Plain fields")
    def plain(
        self,
        name: str,
        count: int,
        ratio: float,
        enabled: bool,
        mode: Literal["fast", "safe"],
    ) -> str:
        self.calls.append(
            {
                "name": name,
                "count": count,
                "ratio": ratio,
                "enabled": enabled,
                "mode": mode,
            }
        )
        return name

    @action(id="demo.marked", title="Marked fields")
    def marked(
        self,
        layer_id: Annotated[str, LayerInput()],
        working_crs: Annotated[str, CrsInput()],
        distance: Annotated[float, Metres()],
    ) -> str:
        self.calls.append(
            {
                "layer_id": layer_id,
                "working_crs": working_crs,
                "distance": distance,
            }
        )
        return layer_id


@dataclass
class _StubRuntime:
    """The three attributes ``NativeForms`` reads, and nothing else."""

    description: object
    actions: dict = field(default_factory=dict)
    instance: object | None = None


@pytest.fixture(scope="module")
def app():
    """One headless QGIS application, because the pickers need a project.

    ``QgsMapLayerComboBox`` reads ``QgsProject.instance()``, so a bare
    ``QApplication`` is not enough; ``QgsApplication`` is a ``QApplication`` and
    initialises QGIS at the same time. Any application already running - the
    services contract suite starts one - is reused rather than re-initialised.
    """
    from qgis.core import QgsApplication

    existing = QApplication.instance()
    if existing is not None:
        return existing
    prefix = Path(sys.prefix)
    os.environ.setdefault("QGIS_PREFIX_PATH", str(prefix))
    QgsApplication.setPrefixPath(str(prefix), True)
    application = QgsApplication([b"qgis-sdk-native-forms"], True)
    application.initQgis()
    return application


@pytest.fixture()
def forms(app):
    calls: list[dict] = []
    instance = FormDemo(calls)
    runtime = _StubRuntime(
        description=describe_plugin(FormDemo),
        actions={},
        instance=instance,
    )
    runtime.actions = {
        description.id: getattr(instance, description.handler)
        for description in runtime.description.actions
    }
    return native_ui.NativeForms(runtime), calls


def test_each_primitive_family_renders_as_its_own_widget(forms) -> None:
    native, _ = forms

    dialog = native.render("demo.plain")

    assert isinstance(dialog.widget("name"), QLineEdit)
    assert isinstance(dialog.widget("count"), QSpinBox)
    assert isinstance(dialog.widget("ratio"), QDoubleSpinBox)
    assert isinstance(dialog.widget("enabled"), QCheckBox)
    assert isinstance(dialog.widget("mode"), QComboBox)


def test_a_marker_renders_a_qgis_picker_and_a_metre_spin_box(forms) -> None:
    native, _ = forms

    dialog = native.render("demo.marked")

    assert isinstance(dialog.widget("layer_id"), QgsMapLayerComboBox)
    assert isinstance(dialog.widget("working_crs"), QgsProjectionSelectionWidget)
    assert isinstance(dialog.widget("distance"), QDoubleSpinBox)
    assert dialog.widget("distance").suffix() == " m"


def test_submitted_values_are_coerced_and_dispatched_to_the_handler(forms) -> None:
    native, calls = forms
    dialog = native.render("demo.plain")
    dialog.widget("name").setText("  buffer ")
    dialog.widget("count").setValue(3)
    dialog.widget("ratio").setValue(1.5)
    dialog.widget("enabled").setChecked(True)
    dialog.widget("mode").setCurrentIndex(1)

    result = native.dispatch("demo.plain", dialog.values())

    assert result == "buffer"
    assert calls == [
        {"name": "buffer", "count": 3, "ratio": 1.5, "enabled": True, "mode": "safe"}
    ]


def test_run_dispatches_only_when_the_dialog_is_accepted(forms, monkeypatch) -> None:
    native, calls = forms
    dialog = native.render("demo.plain")
    dialog.widget("name").setText("kept")
    dialog.widget("mode").setCurrentIndex(1)
    monkeypatch.setattr(native, "render", lambda action_id: dialog)
    monkeypatch.setattr(
        native_ui.DeclaredFormDialog, "exec", lambda self: QDialog.DialogCode.Rejected
    )

    assert native.run("demo.plain") is None
    assert calls == []

    monkeypatch.setattr(
        native_ui.DeclaredFormDialog, "exec", lambda self: QDialog.DialogCode.Accepted
    )

    assert native.run("demo.plain") == "kept"
    assert calls[-1]["name"] == "kept"


def test_an_unknown_action_is_refused(forms) -> None:
    native, _ = forms

    with pytest.raises(QgisSdkFormError, match="declares no action"):
        native.render("demo.missing")


def test_markers_need_a_running_plugin(forms) -> None:
    native, _ = forms
    native._runtime.instance = None

    with pytest.raises(QgisSdkFormError, match="running plugin"):
        native.fields("demo.marked")
