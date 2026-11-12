"""Module dispatch."""

from __future__ import annotations

from ._description import _ref_inputs as _ref_inputs
from ._dispatcher import (
    Authorizer,
    BoundHandler,
    BoundStreamSource,
    Dispatcher,
    DispatchSetup,
    Handler,
    ThemeProvider,
    ViewBinding,
    Waker,
)
from ._dispatcher import (
    _wire_result as _wire_result,
)

__all__ = [
    "Authorizer",
    "BoundHandler",
    "BoundStreamSource",
    "DispatchSetup",
    "Dispatcher",
    "Handler",
    "ThemeProvider",
    "ViewBinding",
    "Waker",
]
