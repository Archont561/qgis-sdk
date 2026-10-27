"""The native windows: a dialog for ``buffer`` and a dock that shows the results.

``BufferDialog`` is a ``Form`` over the action: ``Form.for_action`` builds the
inputs the action declares - a layer picker, a distance in metres and a CRS
picker - from the same request schema the page's generated client is typed
against, so the dialog can never drift from the handler. ``ResultsDock`` is
the plugin's panel: a ``RunButton`` that opens the fixture, a ``ResultTable``
of the layers the plugin produced this session and a ``LogView`` over
``ctx.log``, which is how the dialog's outcomes reach the panel without the
two windows knowing each other.

The two show the two ways of writing a surface. The dialog builds its tree
in ``build()`` because the form depends on ``ctx``; the dock declares its
components as class attributes - each takes the attribute's name, the
default ``build()`` stacks them, and ``@on(component)`` wires the methods -
and every opening gets its own copies. Under the fake (``build_surface``)
the same methods are plain calls. No Qt is imported here: a tree of catalogue
components is what the host mounts, so this module imports in a pure test.
"""

from __future__ import annotations

from qgis_sdk import menu
from qgis_sdk.models import QgisSdkError, VectorLayerInfo
from qgis_sdk.ui import (
    Button,
    Column,
    Dialog,
    Dock,
    Form,
    Group,
    LogView,
    ResultTable,
    Row,
    RunButton,
    on,
)


@menu("Plugins/Simple")
class BufferDialog(Dialog):
    """Buffer a layer in a projected CRS, from a window instead of the page."""

    title = "Buffer in a projected CRS"

    def build(self) -> Column:
        self.form = Form.for_action(self.ctx, "buffer", initial=self.initial)
        return Column("buffer_dialog", [self.form, Button("run", "Buffer")])

    @on("run").clicked
    def run(self) -> None:
        """Submit the form; a refusal becomes a warning, a result closes the window."""
        try:
            output = self.form.submit()
        except QgisSdkError as error:
            self.ctx.notifications.warning(str(error))
            return
        self.ctx.log.info("buffered", layer=output.name, crs=output.crs or "")
        self.ctx.notifications.success(f"Buffered into {output.name}")
        self.ctx.view.request_close()


@menu("Plugins/Simple")
class ResultsDock(Dock, area="right"):
    """What the plugin produced this session, and what it logged while doing so."""

    title = "Simple results"

    fixture = RunButton(action_id="open_fixture", text="Open the fixture")
    clear = Button(text="Clear")
    tools = Row([fixture, clear])
    results = ResultTable(
        columns=[("name", "Layer"), ("geometry_type", "Geometry"), ("crs", "CRS")]
    )
    log = LogView()
    log_group = Group([log], label="Log", collapsible=True)

    @on(fixture).finished
    def opened(self, layer: object) -> None:
        """A finished ``open_fixture`` adds its layer to the table."""
        if isinstance(layer, VectorLayerInfo):
            self.add(layer)

    @on(clear).clicked
    def cleared(self) -> None:
        self.results.set_rows([])

    def add(self, layer: VectorLayerInfo) -> None:
        """Append one produced layer and say so in the log."""
        row = {
            "name": layer.name,
            "geometry_type": layer.geometry_type,
            "crs": layer.crs,
        }
        self.results.set_rows([*self.results.rows(), row])
        self.ctx.log.info("layer ready", layer=layer.name, crs=layer.crs or "")


surfaces = (BufferDialog, ResultsDock)
