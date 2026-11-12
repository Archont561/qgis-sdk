"""Vendored distributions: what is declared, and what is missing."""

from __future__ import annotations

import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from qgis_sdk_tools.distributions import (
    Distribution,
    QGisSdkDistributionError,
    normalize,
    read_distribution,
)
from qgis_sdk_tools.paths import walk_files

from ..buckets import HOST_ROOTS, BucketReport, bucket_imports, import_findings
from ..diagnostics import Diagnostic
from ._constants import EXCLUDED_DIRECTORIES

if TYPE_CHECKING:  # imported by the caller: this module is imported by it
    from qgis_sdk_tools.project import ProjectConfig

__all__ = ["buckets"]


def buckets(
    root: Path, config: ProjectConfig
) -> tuple[BucketReport | None, tuple[Diagnostic, ...]]:
    """Sort the plugin's imports; declared vendored distributions must be there.

    A declared ``vendor`` distribution that is not installed cannot have its
    import roots read, and a compiled one cannot be vendored at all, so both
    are reported here rather than when the build first copies files
    (``DEP004`` names the missing one, ``DEP003`` the compiled one).
    """
    package = root / config.plugin
    if not package.is_dir():
        return None, ()
    vendored: list[str] = []
    distributions: list[Distribution] = []
    findings: list[Diagnostic] = []
    for name in config.build.vendor:
        _read_vendor(name, distributions, vendored, findings)
    findings.extend(_requirement_findings(distributions, config))
    report = bucket_imports(
        root,
        config.plugin,
        tuple(python_files(package)),
        external=config.build.external_roots,
        vendored=vendored,
    )
    findings.extend(import_findings(report))
    return report, tuple(findings)


def python_files(root: Path) -> Iterator[Path]:
    return walk_files(root, skip=EXCLUDED_DIRECTORIES, suffix=".py")


def _read_vendor(
    name: str,
    distributions: list[Distribution],
    vendored: list[str],
    findings: list[Diagnostic],
) -> None:
    """Read one declared vendored distribution, reporting a missing or compiled one."""
    try:
        distribution = read_distribution(name)
    except QGisSdkDistributionError as error:
        findings.append(_declared("DEP004", str(error), name, vendored=False))
        return
    distributions.append(distribution)
    if not distribution.is_pure:
        findings.append(
            _declared(
                "DEP003",
                f"`{distribution.name}` ships compiled extensions "
                f"(`{distribution.compiled[0].as_posix()}` is one); it "
                "cannot be vendored",
                name,
                vendored=True,
            )
        )
    vendored.extend(distribution.roots)


def _available_roots(
    distributions: Sequence[Distribution], config: ProjectConfig
) -> set[str]:
    """Every root a vendored package may import without another declaration."""
    available = {normalize(item.name) for item in distributions}
    available.update(normalize(root) for root in config.build.external_roots)
    available.update(normalize(name) for name in HOST_ROOTS)
    available.update(names for names in sys.stdlib_module_names)
    return available


def _missing_requirement(distribution: Distribution, requirement: str) -> Diagnostic:
    """``DEP004`` for one vendored requirement nothing declares."""
    return Diagnostic(
        rule="DEP004",
        path=Path("pyproject.toml"),
        line=0,
        column=0,
        message=(
            f"vendored `{distribution.name}` requires "
            f"`{requirement}`, which is neither vendored nor "
            "declared external"
        ),
        remediation=(
            f"Add `{requirement}` to `[tool.qgis-sdk.build] vendor` "
            "when it is pure Python, or to `external` when every "
            "QGIS you target ships it."
        ),
    )


def _requirement_findings(
    distributions: Sequence[Distribution], config: ProjectConfig
) -> tuple[Diagnostic, ...]:
    """``DEP004`` for a vendored requirement that is neither vendored nor external.

    A vendored package carries its dependencies with it or assumes the target
    QGIS has them (decision-50 point 2); anything else fails on a clean QGIS
    with an ``ImportError`` from inside the copy, which is exactly what the
    author has to decide about here.
    """
    available = _available_roots(distributions, config)
    return tuple(
        _missing_requirement(distribution, requirement)
        for distribution in distributions
        for requirement in distribution.requires
        if normalize(requirement) not in available
    )


def _declared(rule: str, message: str, name: str, *, vendored: bool) -> Diagnostic:
    remediation = (
        "Vendor it, or declare it under `[tool.qgis-sdk.build] external` with "
        "the requirement the startup probe shows - a declaration costs a "
        "message bar, never a traceback"
        if not vendored
        else "Declare it external (`pandas`, `scipy`, `shapely` and similar "
        "compiled packages are never vendored); the startup probe explains a "
        "missing one to the user"
    )
    return Diagnostic(
        rule=rule,
        path=Path("pyproject.toml"),
        line=0,
        column=0,
        message=message,
        remediation=remediation,
    )
