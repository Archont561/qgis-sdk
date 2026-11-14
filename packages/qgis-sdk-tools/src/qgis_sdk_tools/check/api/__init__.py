"""``API001``: a plugin that imports a name the SDK has marked for removal.

decision-56 point 3 gives a deprecated symbol a window - no removal earlier than
the next major after 1.0, or the second following minor before it - and a mark
that carries both the replacement and the removal version. This rule is the half
that tells the *plugin author*: the name still works, here is what to use
instead, and here is when it stops working.

Severity is ``warning``. A deprecated name is not a broken build today, and a
``check`` that failed on one would be turned off in the week it shipped.

What it reads is imports: ``from qgis_sdk.ui import OldPanel``, and
``qgis_sdk.models.Legacy`` reached through a module imported by name. A name
re-exported by the plugin, passed around as a value, or reached through
``getattr`` is outside source reading; the warning the mark raises when the
symbol is called is what covers those.
"""

from __future__ import annotations

import ast as _ast
from pathlib import Path as _Path

from ..diagnostics import Diagnostic as _Diagnostic
from ._diagnostics import deprecated_diagnostic as _deprecated_diagnostic
from ._table import Marks, deprecated_names
from ._usage import deprecated_uses as _deprecated_uses

__all__ = ["Marks", "check_deprecated_usage", "deprecated_names"]


def check_deprecated_usage(
    source: str, *, path: _Path, deprecations: Marks
) -> list[_Diagnostic]:
    """Report every import of a name the SDK marks for removal."""
    try:
        tree = _ast.parse(source)
    except SyntaxError:
        # A file that cannot be parsed is SYNTAX001's finding, not this rule's.
        return []
    return [
        _deprecated_diagnostic(
            module=module, name=name, mark=mark, node=node, path=path
        )
        for module, name, node, mark in _deprecated_uses(tree, deprecations)
    ]
