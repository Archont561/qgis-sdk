"""Release planning and publishing CLI for the QGIS SDK workspace.

Stdlib-only on purpose: the tool runs inside the workspace's Pixi ``build``
environment without adding a single locked dependency. Extraction into a
standalone checksum-pinned repository is tracked as TASK-36.
"""

from .errors import QgisSdkReleaseError, QgisSdkReleaseVersionError

__all__ = [
    "QgisSdkReleaseError",
    "QgisSdkReleaseVersionError",
    "__version__",
]

__version__ = "0.1.0"
