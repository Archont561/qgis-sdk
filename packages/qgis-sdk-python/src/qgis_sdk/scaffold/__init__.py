"""Generate a minimal, loadable QGIS plugin project from validated choices.

This layer is QGIS-free on purpose: it writes source files, imports no Qt or QGIS
module and needs no display. ``qgis_sdk.__main__`` is the caller that turns these
functions into a command, and the generated project's own entry point reaches the
SDK through :func:`qgis_sdk.adapters.desktop.create_class_factory`.
"""

from .generate import GeneratedFile, plan_scaffold, write_scaffold
from .options import QgisSdkScaffoldError, ScaffoldOptions, WebOptions

__all__ = [
    "GeneratedFile",
    "QgisSdkScaffoldError",
    "ScaffoldOptions",
    "WebOptions",
    "plan_scaffold",
    "write_scaffold",
]
