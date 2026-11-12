"""``check_project``: walk one plugin project and report, mutating nothing.

Decision-8 fixes the boundaries: no imports of the project, no installs, no
handler execution, no rewrites. ``build`` reuses this function rather than
shelling out to the command.

Rules owned here: ``PROJECT001`` (no package), ``META001`` (a hand-written
``metadata.txt``; ``build``/``dev`` generate it), ``ENTRY002`` (a
hand-written ``classFactory``; ``host()`` binds it), ``CONFIG001`` for
``[tool.qgis-sdk.check]``. The ``pyproject.toml`` rules live in
:mod:`qgis_sdk_tools.project`, the version rules in :mod:`.versions`, the
native UI rules (``UI001``-``UI003``, ``UI005``, ``ICON001``) in :mod:`.ui`,
and the worker-safety rules for jobs (``JOB001``-``JOB003``) in :mod:`.jobs`.
"""

from __future__ import annotations

from pathlib import Path as _Path
from typing import TYPE_CHECKING

from ..diagnostics import CheckReport as _CheckReport
from ..diagnostics import QgisSdkCheckError as _QgisSdkCheckError
from ..hosts import check_declared_hosts as _check_declared_hosts
from ..versions import check_generated_clients as _check_generated_clients
from ..versions import check_runtime_pins as _check_runtime_pins
from ..versions import check_runtime_requirement as _check_runtime_requirement
from ._config import configured_native_modules as _configured_native_modules
from ._constants import EXCLUDED_DIRECTORIES, REQUIRED_METADATA_KEYS
from ._packages import check_packages as _check_packages
from ._sources import source_diagnostics as _source_diagnostics
from ._vendor import buckets as _buckets

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..buckets import BucketReport
    from ..diagnostics import Diagnostic

__all__ = ["EXCLUDED_DIRECTORIES", "REQUIRED_METADATA_KEYS", "check_project"]


def check_project(root: _Path, *, native_modules: Sequence[str] = ()) -> _CheckReport:
    """Check the project at ``root`` and return every finding.

    ``native_modules`` adds to the globs configured under
    ``[tool.qgis-sdk.check] native-modules`` in the project's ``pyproject.toml``.
    """
    root = _Path(root).resolve()
    if not root.is_dir():
        raise _QgisSdkCheckError(
            f"{root} is not a directory; give a plugin project root"
        )
    diagnostics: list[Diagnostic] = []
    configured, config_diagnostics = _configured_native_modules(root)
    diagnostics.extend(config_diagnostics)
    native = (*configured, *native_modules)
    packages = list(_check_packages(root))
    diagnostics.extend(packages)
    imports, declared_hosts = _project_declarations(root, diagnostics, packages)
    _static_diagnostics(root, diagnostics)
    files = _source_diagnostics(root, diagnostics, native, declared_hosts)
    diagnostics.sort(key=lambda d: (d.path.as_posix(), d.line, d.column, d.rule))
    return _CheckReport(
        root=root,
        diagnostics=tuple(diagnostics),
        files_checked=files,
        imports=imports,
    )


def _static_diagnostics(root: _Path, diagnostics: list[Diagnostic]) -> None:
    """Rules that read files only, independent of the plugin's declarations."""
    # What the project pins against what this release supports (decision-35),
    # and whether the runtime this interpreter would ship is one it declares.
    diagnostics.extend(_check_runtime_pins(root))
    diagnostics.extend(_check_runtime_requirement(root))
    diagnostics.extend(_check_generated_clients(root))


def _project_declarations(
    root: _Path, diagnostics: list[Diagnostic], packages: Sequence[Diagnostic]
) -> tuple[BucketReport | None, tuple[str, ...] | None]:
    """Read the declarations only when the project has a plugin package."""
    imports = None
    declared_hosts = None
    if not any(d.rule == "PROJECT001" for d in packages):
        # The plugin application, the metadata.txt values and the page (decision-43).
        from qgis_sdk_tools.project import load_project

        config, findings = load_project(root)
        diagnostics.extend(findings)
        if config is not None:
            imports, bucket_findings = _buckets(root, config)
            diagnostics.extend(bucket_findings)
            # Which hosts the project declares, and whether this QGIS has them
            # (decision-52 point 1; TASK-80).
            declared_hosts = config.hosts
            diagnostics.extend(_check_declared_hosts(config))
    return imports, declared_hosts
