"""UI001, UI003 and ICON001: native UI ``check`` refuses before QGIS does (TASK-67/68)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from qgis_sdk_tools.check import check_project
from qgis_sdk_tools.check.ui import check_bindings


def findings(source: str, *, icons: tuple[str, ...] = (), tmp_path: Path) -> list[str]:
    package = tmp_path / "pkg"
    (package / "icons").mkdir(parents=True, exist_ok=True)
    for icon in icons:
        (package / "icons" / icon).write_text("<svg/>", encoding="utf-8")
    return [
        f"{d.rule}:{d.line}:{d.message}"
        for d in check_bindings(
            textwrap.dedent(source),
            path=Path("pkg/plugin.py"),
            package_directory=package,
        )
    ]


def test_a_bound_typed_action_is_ui003_whatever_the_stacking_order(
    tmp_path: Path,
) -> None:
    source = """
        from qgis_sdk import action, menu, plugin, shortcut, toolbar


        @plugin(id="x", title="X")
        class X:
            @toolbar
            @action
            def typed(self, distance: float, note: str = "") -> None: ...

            @action
            @menu("Vector/X")
            @shortcut("F9")
            def below(self, *, layer_id: str) -> None: ...

            @toolbar
            @action
            def plain(self) -> None: ...

            @action
            def unbound(self, value: int) -> int: ...
        """
    typed = (
        "UI003:9:typed is bound to the Desktop (@toolbar) but takes inputs "
        "(distance, note); nothing collects them"
    )
    below = (
        "UI003:14:below is bound to the Desktop (@menu, @shortcut) but takes "
        "inputs (layer_id); nothing collects them"
    )
    assert findings(source, tmp_path=tmp_path) == [typed, below]


def test_aliases_and_module_imports_are_recognised(tmp_path: Path) -> None:
    source = """
        import qgis_sdk as sdk
        from qgis_sdk.bindings import toolbar as button


        class X:
            @button
            @sdk.action
            def one(self, a: int) -> None: ...

            @sdk.menu("Plugins/X")
            @sdk.action
            def two(self, b: int) -> None: ...
        """
    assert [f.split(":")[1] for f in findings(source, tmp_path=tmp_path)] == ["9", "13"]


def test_a_binding_from_elsewhere_is_not_ours(tmp_path: Path) -> None:
    source = """
        from somewhere import action, toolbar


        class X:
            @toolbar
            @action
            def typed(self, distance: float) -> None: ...
        """
    assert findings(source, tmp_path=tmp_path) == []


def test_a_missing_icon_is_icon001_on_actions_and_surfaces(tmp_path: Path) -> None:
    source = """
        from qgis_sdk import action, toolbar
        from qgis_sdk.ui import Dialog


        @toolbar(icon="present.svg")
        class Present(Dialog): ...


        @toolbar(icon="missing.svg")
        class Missing(Dialog): ...


        class X:
            @toolbar(icon="../escape.svg", text="Run")
            @action
            def run(self) -> None: ...

            @toolbar(text="No icon")
            @action
            def plain(self) -> None: ...
        """
    assert findings(source, icons=("present.svg",), tmp_path=tmp_path) == [
        "ICON001:10:@toolbar icon 'missing.svg' is not a file under pkg/icons/",
        "ICON001:15:@toolbar icon '../escape.svg' is not a file under pkg/icons/",
    ]


def test_an_unnamed_interactive_widget_in_a_surface_is_ui001(tmp_path: Path) -> None:
    source = """
        from qgis_sdk.ui import Dialog as Window, Form


        class Buffer(Window):
            def build(self):
                from qgis.PyQt.QtWidgets import QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget

                widget = QWidget()
                layout = QVBoxLayout(widget)
                self.name = QLineEdit(widget)
                self.name.setObjectName("form/name")
                count = QSpinBox(widget)
                layout.addWidget(QLabel("Count"))
                layout.addWidget(count)
                layout.addWidget(QPushButton("Run", widget))
                self.form = Form.for_action(self.ctx, "buffer")
                return widget

            def helper(self):
                from qgis import gui

                picker = gui.QgsMapLayerComboBox()
                picker.setObjectName("form/layer")
                return picker


        class NotASurface:
            def build(self):
                from qgis.PyQt.QtWidgets import QSpinBox

                return QSpinBox()
        """
    assert findings(source, tmp_path=tmp_path) == [
        "UI001:13:count (QSpinBox) in Buffer.build() has no objectName",
        "UI001:16:an unassigned QPushButton in Buffer.build() has no objectName",
    ]


def test_check_project_reports_both_rules_with_remediation(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "field-tools"
            version = "0.1.0"
            description = "Field tools"
            authors = [{name = "A", email = "a@example.invalid"}]
            dependencies = ["qgis-sdk-runtime>=0.6,<0.7"]

            [tool.qgis-sdk]
            plugin = "field_tools.plugin:FieldTools"
            qgis-minimum-version = "4.0"
            """
        ),
        encoding="utf-8",
    )
    package = tmp_path / "field_tools"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "plugin.py").write_text(
        textwrap.dedent(
            """
            from qgis_sdk import action, plugin, toolbar
            from qgis_sdk.core import PluginContext


            @plugin(id="field_tools", title="Field tools")
            class FieldTools:
                ctx: PluginContext

                @toolbar(icon="buffer.svg")
                @action
                def buffer(self, distance: float) -> None: ...
            """
        ),
        encoding="utf-8",
    )

    report = check_project(tmp_path)

    by_rule = {d.rule: d for d in report.diagnostics}
    assert "UI003" in by_rule and "ICON001" in by_rule
    assert by_rule["UI003"].path == Path("field_tools/plugin.py")
    assert "self.ctx.actions.buffer(" in by_rule["UI003"].remediation
    assert "field_tools/icons/buffer.svg" in by_rule["ICON001"].remediation
    rendered = by_rule["ICON001"].render()
    assert rendered.startswith("field_tools/plugin.py:10:")
