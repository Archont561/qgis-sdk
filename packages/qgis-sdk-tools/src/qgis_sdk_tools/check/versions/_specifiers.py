from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from qgis_sdk_tools.check.diagnostics import Diagnostic
from qgis_sdk_tools.manifest import read_pyproject

from ._ranges import (
    CLAUSE,
    REQUIREMENT,
    RUNTIME_DISTRIBUTION,
    RUNTIME_REQUIREMENT_NAMES,
    eq,
    installed_runtime_version,
    lt,
    next_after_prefix,
    release,
    requirement_strings,
)


def requirement_admits_version(specifier: str, version: str) -> bool:
    """Whether ``version`` satisfies ``specifier`` (release segments only).

    The same arithmetic as :func:`requirement_admits_range`, on a point: an
    unparsable clause counts as satisfied, ``!=`` is honoured here because a
    point can be excluded exactly.
    """
    try:
        point = release(version)
    except ValueError:
        return True
    return _clauses_admit(point, specifier)


def _exact_point(point: tuple[int, ...], wanted: tuple[int, ...]) -> bool:
    return eq(point, wanted)


def _excluded_point(point: tuple[int, ...], wanted: tuple[int, ...]) -> bool:
    return not eq(point, wanted)


def _at_least_point(point: tuple[int, ...], wanted: tuple[int, ...]) -> bool:
    return not lt(point, wanted)


def _more_than_point(point: tuple[int, ...], wanted: tuple[int, ...]) -> bool:
    return lt(wanted, point)


def _at_most_point(point: tuple[int, ...], wanted: tuple[int, ...]) -> bool:
    return not lt(wanted, point)


def _less_than_point(point: tuple[int, ...], wanted: tuple[int, ...]) -> bool:
    return lt(point, wanted)


def _compatible_point(point: tuple[int, ...], wanted: tuple[int, ...]) -> bool:
    return not lt(point, wanted) and (
        len(wanted) < 2 or lt(point, next_after_prefix(wanted[:-1]))
    )


_POINT_CLAUSES: dict[str, Callable[[tuple[int, ...], tuple[int, ...]], bool]] = {
    "==": _exact_point,
    "===": _exact_point,
    "!=": _excluded_point,
    ">=": _at_least_point,
    ">": _more_than_point,
    "<=": _at_most_point,
    "<": _less_than_point,
    "~=": _compatible_point,
}


def _clauses_admit(point: tuple[int, ...], specifier: str) -> bool:
    """Whether every clause of ``specifier`` admits the release ``point``."""
    for raw in specifier.split(","):
        clause = raw.strip()
        if not clause:
            continue
        match = CLAUSE.match(clause)
        if match is None:
            return True
        op, text = match.group("op"), match.group("version")
        try:
            if op in ("==", "===", "!=") and text.endswith(".*"):
                prefix = release(text[:-2])
                same = eq(point[: len(prefix)], prefix)
                if (op == "!=") == same:
                    return False
                continue
            wanted = release(text)
        except ValueError:
            return True
        compare = _POINT_CLAUSES.get(op)
        if compare is None or not compare(point, wanted):
            return False
    return True


@dataclass(frozen=True, slots=True)
class RuntimeResolution:
    """What the project asks of the runtime and what this interpreter has."""

    requirement: str | None
    """The declared requirement (``qgis-sdk-runtime>=0.6,<0.7``), or ``None``."""
    installed: str | None
    """The importable runtime's version, or ``None`` when nothing says."""

    @property
    def specifier(self) -> str:
        if self.requirement is None:
            return ""
        match = REQUIREMENT.match(self.requirement)
        return "" if match is None else match.group("spec")

    @property
    def satisfied(self) -> bool:
        """True unless a declared specifier excludes the installed version."""
        if self.requirement is None or self.installed is None:
            return True
        return requirement_admits_version(self.specifier, self.installed)


def resolve_runtime(root: Path) -> RuntimeResolution:
    """Pair the project's runtime requirement with the installed runtime."""
    requirement = None
    data, _malformed = read_pyproject(Path(root) / "pyproject.toml")
    for candidate in requirement_strings(data):
        match = REQUIREMENT.match(candidate)
        if match is None:
            continue
        name = match.group("name").lower().replace("_", "-")
        if name in RUNTIME_REQUIREMENT_NAMES:
            requirement = candidate.split(";", 1)[0].strip()
            break
    return RuntimeResolution(
        requirement=requirement, installed=installed_runtime_version()
    )


def _missing_runtime_finding(installed: str) -> Diagnostic:
    """VERSION003: the project declares no requirement on the runtime."""
    return Diagnostic(
        rule="VERSION003",
        path=Path("pyproject.toml"),
        line=0,
        column=0,
        severity="warning",
        message=(
            f"declares no requirement on {RUNTIME_DISTRIBUTION}; `build` ships "
            f"whatever this interpreter imports ({installed})"
        ),
        remediation=(
            "Add it to [project] dependencies, for example "
            f'`"{RUNTIME_DISTRIBUTION}>={_minor(installed)},<{_next_minor(installed)}"`, '
            "so the vendored runtime is one the plugin was written for."
        ),
    )


def _unmet_runtime_finding(resolution: RuntimeResolution) -> Diagnostic:
    """VERSION004: the importable runtime is outside the declared specifier."""
    return Diagnostic(
        rule="VERSION004",
        path=Path("pyproject.toml"),
        line=0,
        column=0,
        message=(
            f"declares `{resolution.requirement}` but the importable runtime is "
            f"{resolution.installed}"
        ),
        remediation=(
            f'Install a matching runtime (`pip install "{resolution.requirement}"`) '
            "or move the requirement; qgis-sdk never installs on your behalf."
        ),
    )


def check_runtime_requirement(root: Path) -> Iterator[Diagnostic]:
    """``VERSION003`` without a runtime requirement, ``VERSION004`` when unmet."""
    if not (Path(root) / "pyproject.toml").is_file():
        return
    resolution = resolve_runtime(root)
    if resolution.requirement is None:
        yield _missing_runtime_finding(resolution.installed or "unknown")
        return
    if resolution.satisfied:
        return
    yield _unmet_runtime_finding(resolution)


def _minor(version: str) -> str:
    try:
        parsed = release(version)
    except ValueError:
        return "X.Y"
    return ".".join(str(part) for part in (parsed + (0, 0))[:2])


def _next_minor(version: str) -> str:
    try:
        parsed = release(version)
    except ValueError:
        return "X.Y+1"
    major, minor = (parsed + (0, 0))[:2]
    return f"{major}.{minor + 1}"
