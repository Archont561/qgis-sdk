"""Bind actions and surfaces to the Desktop: ``@toolbar``, ``@menu``, ``@shortcut``.

decision-45 and decision-55: a binding says *where QGIS shows a way to
trigger something*, and nothing else. The decorators stack in any order::

    @toolbar(icon="buffer.svg")
    @menu("Vector/Field tools")
    @shortcut("Ctrl+Alt+B")
    @app.action(id="buffer_selection", title="Buffer selection")
    def buffer_selection(ctx: PluginContext) -> None: ...

    @menu("Plugins/Field tools")
    class BufferDialog(Dialog): ...  # a surface, placed the same way

They mark and add a ``describe()`` convenience without wrapping, on an action
function or a ``Dialog``/``Dock`` subclass. Bindings are host metadata, omitted
from the serialized bridge schema and the host fingerprint: a toolbar button
does not move the wire.

Bindings refuse jobs, streams and tools; bind an application action that
submits the job, opens a surface for the stream or calls ``start`` on the tool.
A plain unregistered function cannot be placed. Per decision-55, an action with
no inputs runs on the GUI thread, one returning a job handle reports through the
message bar, and a *typed* action bound without a surface is a ``UI003`` finding.
"""

from __future__ import annotations

from ._bindings import (
    BINDINGS_ATTRIBUTE,
    SURFACES_ATTRIBUTE,
    Binding,
    BindingsDescription,
    BoundAction,
    BoundSurface,
    MenuBinding,
    ShortcutBinding,
    ToolbarBinding,
    bindings_of,
    describe_bindings,
    menu,
    shortcut,
    toolbar,
)
from ._bindings import (
    _describe_lowered_bindings as _describe_lowered_bindings,
)

__stability__ = "stable"

__all__ = [
    "BINDINGS_ATTRIBUTE",
    "SURFACES_ATTRIBUTE",
    "Binding",
    "BindingsDescription",
    "BoundAction",
    "BoundSurface",
    "MenuBinding",
    "ShortcutBinding",
    "ToolbarBinding",
    "bindings_of",
    "describe_bindings",
    "menu",
    "shortcut",
    "toolbar",
]
