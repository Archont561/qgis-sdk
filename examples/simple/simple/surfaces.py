"""The native window for ``buffer``: a ``Form`` over the action, plus one button.

``Form.for_action`` builds the inputs the action declares - a layer picker, a
distance in metres and a CRS picker - from the same request schema the page's
generated client is typed against, so the dialog can never drift from the
handler. The dialog adds nothing but a ``Button`` that submits; the form
dispatches through ``ctx.actions``, the very entry the page calls. No Qt is
imported here: a ``Column`` of catalogue components is what the host mounts.
"""

from __future__ import annotations

from qgis_sdk import menu
from qgis_sdk.models import QgisSdkError
from qgis_sdk.ui import Button, Column, Dialog, Form


@menu("Plugins/Simple")
class BufferDialog(Dialog):
    """Buffer a layer in a projected CRS, from a window instead of the page."""

    title = "Buffer in a projected CRS"

    def build(self) -> Column:
        self.form = Form.for_action(self.ctx, "buffer", initial=self.initial)
        run = Button("run", "Buffer")
        run.clicked(self.run)
        return Column("buffer_dialog", [self.form, run])

    def run(self) -> None:
        """Submit the form; a refusal becomes a warning, a result closes the window."""
        try:
            output = self.form.submit()
        except QgisSdkError as error:
            self.ctx.notifications.warning(str(error))
            return
        self.ctx.notifications.success(f"Buffered into {output.name}")
        self.ctx.view.request_close()


surfaces = (BufferDialog,)
