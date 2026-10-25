"""``check_project``: walk one plugin project and report, mutating nothing.

Decision-8 fixes the boundaries: no imports of the project, no installs, no
handler execution, no rewrites. ``build`` reuses this function rather than
shelling out to the command.
"""

from __future__ import annotations

import configparser
import os
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path

from .diagnostics import CheckReport, Diagnostic, QgisSdkCheckError
from .imports import check_source
from .versions import check_generated_clients, check_runtime_pins

__all__ = ["EXCLUDED_DIRECTORIES", "REQUIRED_METADATA_KEYS", "check_project"]

# Tooling and dependency trees are never the author's plugin code.
EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".venv",
        "venv",
        "node_modules",
        ".pixi",
        "__pycache__",
        "build",
        "dist",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)
# QGIS refuses to load a plugin whose metadata.txt lacks any of these.
REQUIRED_METADATA_KEYS = (
    "name",
    "description",
    "about",
    "version",
    "qgisMinimumVersion",
    "author",
    "email",
)
_CONFIG_TABLE = ("tool", "qgis-sdk", "check")


def check_project(root: Path, *, native_modules: Sequence[str] = ()) -> CheckReport:
    """Check the project at ``root`` and return every finding.

    ``native_modules`` adds to the globs configured under
    ``[tool.qgis-sdk.check] native-modules`` in the project's ``pyproject.toml``.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise QgisSdkCheckError(
            f"{root} is not a directory; give a plugin project root"
        )
    diagnostics: list[Diagnostic] = []
    configured, config_diagnostics = _configured_native_modules(root)
    diagnostics.extend(config_diagnostics)
    native = (*configured, *native_modules)

    diagnostics.extend(_check_packages(root))
    # What the project pins against what this release supports (decision-35).
    diagnostics.extend(check_runtime_pins(root))
    diagnostics.extend(check_generated_clients(root))

    files = 0
    for path in _python_files(root):
        files += 1
        relative = path.relative_to(root)
        source = path.read_text(encoding="utf-8")
        diagnostics.extend(check_source(source, path=relative, native_modules=native))

    diagnostics.sort(key=lambda d: (d.path.as_posix(), d.line, d.column, d.rule))
    return CheckReport(root=root, diagnostics=tuple(diagnostics), files_checked=files)


def _python_files(root: Path) -> Iterator[Path]:
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRECTORIES)
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield Path(directory) / filename


def _check_packages(root: Path) -> Iterator[Diagnostic]:
    packages = sorted(
        child
        for child in root.iterdir()
        if child.is_dir()
        and child.name not in EXCLUDED_DIRECTORIES
        and child.name != "tests"
        and (child / "__init__.py").is_file()
    )
    if not packages:
        yield Diagnostic(
            rule="PROJECT001",
            path=Path("."),
            line=0,
            column=0,
            message=f"no plugin package (a directory with __init__.py) under {root}",
            remediation=(
                "Run from the project root `qgis-sdk new` created, or pass its path."
            ),
        )
        return
    for package in packages:
        yield from _check_metadata(root, package)


def _check_metadata(root: Path, package: Path) -> Iterator[Diagnostic]:
    metadata = package / "metadata.txt"
    relative = metadata.relative_to(root)
    if not metadata.is_file():
        yield Diagnostic(
            rule="META001",
            path=relative,
            line=0,
            column=0,
            message=f"`{package.name}` has no metadata.txt, so QGIS will not list it",
            remediation=(
                "Add metadata.txt with a [general] section; `qgis-sdk new` writes "
                "one with every required key."
            ),
        )
        return
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # type: ignore[assignment]  # QGIS keys are case-sensitive
    try:
        parser.read_string(metadata.read_text(encoding="utf-8"), source=str(relative))
    except configparser.Error as error:
        yield Diagnostic(
            rule="META003",
            path=relative,
            line=0,
            column=0,
            message=f"metadata.txt has no [general] section ({error.__class__.__name__})",
            remediation="Start the file with `[general]`; QGIS reads keys from that section only.",
        )
        return
    if not parser.has_section("general"):
        yield Diagnostic(
            rule="META003",
            path=relative,
            line=0,
            column=0,
            message="metadata.txt has no [general] section",
            remediation="Start the file with `[general]`; QGIS reads keys from that section only.",
        )
        return
    for key in REQUIRED_METADATA_KEYS:
        if not parser.get("general", key, fallback="").strip():
            yield Diagnostic(
                rule="META002",
                path=relative,
                line=0,
                column=0,
                message=f"metadata.txt lacks the required key `{key}`",
                remediation=(
                    "QGIS refuses to load a plugin without it; add the key under "
                    "[general] (`qgis-sdk new` writes all required keys)."
                ),
            )


def _configured_native_modules(root: Path) -> tuple[tuple[str, ...], list[Diagnostic]]:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return (), []
    relative = Path("pyproject.toml")
    try:
        data: object = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        return (), [
            _config_diagnostic(relative, f"pyproject.toml does not parse: {error}")
        ]
    for key in _CONFIG_TABLE:
        if not isinstance(data, dict):
            return (), []
        data = data.get(key)
        if data is None:
            return (), []
    if not isinstance(data, dict):
        return (), [
            _config_diagnostic(relative, "[tool.qgis-sdk.check] must be a table")
        ]
    globs = data.get("native-modules", [])
    if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs):
        return (), [
            _config_diagnostic(
                relative,
                "[tool.qgis-sdk.check] native-modules must be a list of module globs",
            )
        ]
    return tuple(globs), []


def _config_diagnostic(path: Path, message: str) -> Diagnostic:
    return Diagnostic(
        rule="CONFIG001",
        path=path,
        line=0,
        column=0,
        message=message,
        remediation=(
            'Write it as `native-modules = ["my_plugin.native", "my_plugin.views.*"]`.'
        ),
    )
