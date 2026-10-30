"""Non-mutating project checks: read the source, report, change nothing.

``check_project`` is the library entry point the ``qgis-sdk check`` command and
``qgis-sdk build`` both call (decision-8); ``check_source`` and ``check_jobs``
are the per-file rules (imports, then worker safety) for callers that already
hold the text.
"""

from .diagnostics import CheckReport, Diagnostic, QgisSdkCheckError, Severity
from .imports import NATIVE_ADAPTER_PACKAGE, NATIVE_ROOTS, check_source, module_name
from .jobs import GUI_CLASSES, GUI_ONLY_PATHS, WORKER_SAFE_ATTRIBUTES, check_jobs
from .project import EXCLUDED_DIRECTORIES, REQUIRED_METADATA_KEYS, check_project
from .versions import RuntimeRange, requirement_admits_range, supported_runtime_range

__all__ = [
    "EXCLUDED_DIRECTORIES",
    "GUI_CLASSES",
    "GUI_ONLY_PATHS",
    "NATIVE_ADAPTER_PACKAGE",
    "NATIVE_ROOTS",
    "REQUIRED_METADATA_KEYS",
    "WORKER_SAFE_ATTRIBUTES",
    "CheckReport",
    "Diagnostic",
    "QgisSdkCheckError",
    "RuntimeRange",
    "Severity",
    "check_jobs",
    "check_project",
    "check_source",
    "module_name",
    "requirement_admits_range",
    "supported_runtime_range",
]
