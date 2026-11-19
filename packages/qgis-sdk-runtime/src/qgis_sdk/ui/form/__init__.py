"""``Form``: an action's inputs as catalogue components (decision-55 point 4).

A form is a helper, not a popup. ``Form.for_action(ctx, "buffer",
initial={...})`` builds one input per field of the declared action, from the
same ``form_fields`` rule a page's schema and the 0.5 declared dialogs used;
``Form.from_schema(schema)`` does the same from a request schema and
``Form(fields=[...])`` from components an author placed by hand. All three
produce the same tree: ``values()`` reads every field as a model,
``changed(listener)`` reports ``(name, value)``, ``submit()`` dispatches
through ``ctx.actions`` with the view's authority. Mounted, a form is a
``QWidget`` with a ``QFormLayout`` of labelled rows and no buttons - place
a :class:`~qgis_sdk.ui.components.Button` next to it.
"""

from __future__ import annotations

from ._form import Form
from ._inputs import input_for

__all__ = ["Form", "input_for"]
