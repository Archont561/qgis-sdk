"""Module codegen."""

from __future__ import annotations

from ._algorithm import (
    PYTHON_TYPES,
    TYPESCRIPT_TYPES,
    class_name,
    field_name,
    python_type,
    typescript_type,
)
from ._python import (
    emit_python_module,
    emit_python_package,
    emit_python_package_init,
)
from ._typescript import (
    _module_name,  # noqa: F401 - kept for the module-name tests
    emit_typescript_module,
    module_name,
    render_package,
)

__all__ = [
    "PYTHON_TYPES",
    "TYPESCRIPT_TYPES",
    "class_name",
    "emit_python_module",
    "emit_python_package",
    "emit_python_package_init",
    "emit_typescript_module",
    "field_name",
    "module_name",
    "python_type",
    "render_package",
    "typescript_type",
]
