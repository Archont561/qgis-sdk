"""The support matrix: where the kit is qualified, as one machine-readable source.

A *target* is an OS, architecture and interpreter, with or without a QGIS
installation on top. ``qualified`` means the workspace demonstrated the kit
there and the record says how; ``unqualified`` means the combination is
reachable but not demonstrated, with the blocker named. Rows match on the
series a user can read off their installation (QGIS ``4.2``, Qt ``6.11``,
Chromium ``140``), not on the patch level the locked environment happened to
carry.

The same tuple renders the table in the Python guide (``render_markdown``),
answers ``qgis-sdk targets`` and is pinned by the native suite: the host CI
runs on must be a qualified row, so the matrix cannot drift from what the
locked environment proves.
"""

from __future__ import annotations

import importlib
import platform
import sys
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, NamedTuple

Status = Literal["qualified", "unqualified"]


@dataclass(frozen=True)
class Target:
    """One row of the matrix. ``qgis`` ``None`` is the QGIS-free kit (``pip``
    install, scaffold, check, bridge generation) with no QGIS on the host.

    ``chromium`` ``None`` on a row with a QGIS means the row did not exercise
    the WebEngine layer, so nothing is claimed about a page running there - the
    hosts (Desktop, server) may still be qualified.
    """

    os: str
    arch: str
    python: str
    qgis: str | None
    qt: str | None
    chromium: str | None
    status: Status
    evidence: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)


class Host(NamedTuple):
    """What ``describe_host`` read off this process, in the matrix's units."""

    os: str
    arch: str
    python: str
    qgis: str | None
    qt: str | None
    chromium: str | None

    def to_json(self) -> dict[str, object]:
        return dict(self._asdict())

    def describe(self) -> str:
        parts = [f"{self.os} {self.arch}", f"Python {self.python}"]
        if self.qgis is None:
            parts.append("no QGIS")
        else:
            parts.append(f"QGIS {self.qgis}")
            parts.append(f"Qt {self.qt or '?'}")
            parts.append(f"Chromium {self.chromium or '?'}")
        return ", ".join(parts)


SUPPORT_MATRIX: tuple[Target, ...] = (
    Target(
        "linux",
        "x86-64",
        "3.14",
        "4.2",
        "6.11",
        "140",
        "qualified",
        "the locked Pixi environment (QGIS 4.2.3, Qt 6.11.2, Chromium 140, "
        "CPython 3.14): native suite, headless Desktop harnesses, the reference "
        "plugin through the toolchain and the release gate (workspace guide)",
    ),
    Target(
        "linux",
        "x86-64",
        "3.12",
        "3.44",
        "5.15",
        None,
        "qualified",
        "ci.yml `QGIS 3.44 LTS`: qgis.org apt `qgis` + `qgis-server` + "
        "`python3-qgis` (QGIS 3.44, PyQt5, Qt 5.15), the plugin host offscreen "
        "and the server layer on the same build; the WebEngine layer is not "
        "run on this row",
    ),
    Target(
        "linux",
        "x86-64",
        "3.11",
        None,
        None,
        None,
        "qualified",
        "the QGIS-free suite on CPython 3.11.2, the `requires-python` floor",
    ),
    Target(
        "windows",
        "x86-64",
        "3.14",
        None,
        None,
        None,
        "qualified",
        "ci.yml `cross-platform (windows-latest)`: `pip install` of the kit and "
        "the QGIS-free suite",
    ),
    Target(
        "macos",
        "arm64",
        "3.14",
        None,
        None,
        None,
        "qualified",
        "ci.yml `cross-platform (macos-latest)`: `pip install` of the kit and the "
        "QGIS-free suite",
    ),
    Target(
        "windows",
        "x86-64",
        "3.14",
        "4.2",
        None,
        None,
        "unqualified",
        "no Windows QGIS 4 installation in CI or the sandbox",
    ),
    Target(
        "macos",
        "arm64",
        "3.14",
        "4.2",
        None,
        None,
        "unqualified",
        "no macOS QGIS 4 installation in CI or the sandbox",
    ),
)

_SYSTEMS = {"linux": "linux", "windows": "windows", "darwin": "macos"}
_MACHINES = {
    "x86_64": "x86-64",
    "amd64": "x86-64",
    "arm64": "arm64",
    "aarch64": "arm64",
}


def version_prefix(version: str | None, parts: int) -> str | None:
    """``"4.2.3-Belém do Pará"`` → ``"4.2"``; ``None`` when there is nothing to read."""
    if not version:
        return None
    numbers: list[str] = []
    for piece in version.split("."):
        digits = ""
        for char in piece:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        numbers.append(digits)
        if len(numbers) == parts:
            break
    return ".".join(numbers) if numbers else None


_PROBES: dict[str, tuple[tuple[str, str], ...]] = {
    "qgis": (("qgis.core", "Qgis.QGIS_VERSION"),),
    "qt": (
        ("qgis.PyQt.QtCore", "QT_VERSION_STR"),
        ("PyQt6.QtCore", "QT_VERSION_STR"),
        ("PyQt5.QtCore", "QT_VERSION_STR"),
    ),
    "chromium": (
        ("qgis.PyQt.QtWebEngineCore", "qWebEngineChromiumVersion"),
        ("PyQt6.QtWebEngineCore", "qWebEngineChromiumVersion"),
    ),
}


def probe_installed(name: str, *, bindings: Path | None = None) -> str | None:
    """Read the installed ``qgis``, ``qt`` or ``chromium`` version; ``None`` when
    the bindings are not importable here. ``bindings`` is a PyQGIS directory
    to import from when the interpreter does not carry it on ``sys.path``
    (the way ``qgis-sdk test`` found it)."""
    if bindings is not None and str(bindings) not in sys.path:
        sys.path.append(str(bindings))
    for module_name, attribute in _PROBES.get(name, ()):
        try:
            value: object = importlib.import_module(module_name)
        except ImportError:
            continue
        for part in attribute.split("."):
            value = getattr(value, part, None)
        if callable(value):
            value = value()
        if value:
            return str(value)
    return None


def bindings_probe(bindings: Path) -> Callable[[str], str | None]:
    """``probe_installed`` bound to a PyQGIS directory found outside ``sys.path``."""

    def probe(name: str) -> str | None:
        return probe_installed(name, bindings=bindings)

    return probe


def describe_host(probe: Callable[[str], str | None] = probe_installed) -> Host:
    """This process as a matrix row: OS, arch and interpreter from :mod:`platform`,
    QGIS, Qt and Chromium from ``probe`` (installed bindings by default)."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    qgis = version_prefix(probe("qgis"), 2)
    return Host(
        os=_SYSTEMS.get(system, system),
        arch=_MACHINES.get(machine, machine),
        python=version_prefix(platform.python_version(), 2) or "?",
        qgis=qgis,
        qt=version_prefix(probe("qt"), 2) if qgis else None,
        chromium=version_prefix(probe("chromium"), 1) if qgis else None,
    )


def qualified_target(
    host: Host, matrix: Iterable[Target] = SUPPORT_MATRIX
) -> Target | None:
    """The row that speaks for ``host``, or ``None`` when the matrix is silent.

    A host with QGIS needs the row with its QGIS series, and the Qt and
    Chromium a qualified row names. A host without QGIS is covered by the
    QGIS-free row for its interpreter, or failing that by any row that
    qualified the same interpreter with QGIS on top: the QGIS-free suite is
    part of that evidence.
    """
    rows = [
        target
        for target in matrix
        if (target.os, target.arch, target.python) == (host.os, host.arch, host.python)
    ]
    if host.qgis is None:
        for target in rows:
            if target.qgis is None:
                return target
        for target in rows:
            if target.status == "qualified":
                return target
        return None
    for target in rows:
        if target.qgis != host.qgis:
            continue
        if target.qt is not None and target.qt != host.qt:
            continue
        if target.chromium is not None and target.chromium != host.chromium:
            continue
        return target
    return None


def render_markdown(matrix: Iterable[Target] = SUPPORT_MATRIX) -> str:
    """The matrix as the Markdown table the guides carry, ``-`` for *not on the target*."""
    header = "| OS | Arch | Python | QGIS | Qt | Chromium | Status | Evidence |"
    rule = "| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |"
    rows = [
        "| "
        + " | ".join(
            (
                target.os,
                target.arch,
                target.python,
                target.qgis or "-",
                target.qt or "-",
                target.chromium or "-",
                target.status,
                target.evidence,
            )
        )
        + " |"
        for target in matrix
    ]
    return "\n".join([header, rule, *rows])
