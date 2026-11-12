"""Module __init__."""

from __future__ import annotations

from qgis_sdk_tools.bundle.vendor import rewrite_imports

from ._build import (
    build_plugin,
)
from ._build import (
    build_web as _build_web,  # noqa: F401 - re-exported for `bundle.app`
)
from ._build import (
    imports_optional as _imports_optional,  # noqa: F401 - re-exported for `bundle.app`
)
from ._build import (
    plugin_sources as _plugin_sources,  # noqa: F401 - re-exported for `bundle.app`
)
from ._build import (
    read_vendored as _read_vendored,  # noqa: F401 - re-exported for `bundle.app`
)
from ._build import (
    stage_plugin as _stage_plugin,  # noqa: F401 - re-exported for `bundle.app`
)
from ._errors import (
    OUTPUT_DIRECTORY,
    VENDOR_PACKAGE,
    BuildResult,
    QgisSdkBuildError,
    QgisSdkBuildRefusedError,
    RunProcess,
    WebOutcome,
)
from ._staging import (
    stage_runtime as _stage_runtime,  # noqa: F401 - re-exported for `bundle.app`
)

__all__ = [
    "OUTPUT_DIRECTORY",
    "VENDOR_PACKAGE",
    "BuildResult",
    "QgisSdkBuildError",
    "QgisSdkBuildRefusedError",
    "RunProcess",
    "WebOutcome",
    "build_plugin",
    "rewrite_imports",
]
