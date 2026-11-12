from __future__ import annotations

import re
from typing import Final

from qgis_sdk_tools.check.diagnostics import Diagnostic

from ._facts import PATH, ExternalPackage


def named_external(name: str, findings: list[Diagnostic]) -> ExternalPackage | None:
    if IMPORT_ROOT.match(name.strip()) is None:
        findings.append(
            config(
                f"[tool.qgis-sdk.build] external entry {name!r} is not an import "
                "root (one identifier, such as `pandas`)",
                'external = ["pandas"]',
            )
        )
        return None
    return ExternalPackage(import_name=name.strip())


def _vendor_name(name: str, seen: set[str], findings: list[Diagnostic]) -> str | None:
    """One vendored distribution, or ``None`` when malformed or duplicated."""
    if DISTRIBUTION_NAME.match(name) is None:
        findings.append(
            config(
                f"[tool.qgis-sdk.build] vendor entry {name!r} is not a "
                "distribution name",
                'vendor = ["shapely"]',
            )
        )
        return None
    if name.lower() in seen:
        findings.append(
            config(
                f"[tool.qgis-sdk.build] vendor names `{name}` twice",
                "List each distribution once.",
            )
        )
        return None
    return name


def vendor(value: object, findings: list[Diagnostic]) -> tuple[str, ...]:
    """The distributions the build copies into ``<plugin>/vendor``."""
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(n, str) for n in value):
        findings.append(
            config(
                "[tool.qgis-sdk.build] vendor must be a list of distribution names",
                'vendor = ["shapely"]',
            )
        )
        return ()
    declared: list[str] = []
    seen: set[str] = set()
    for name in (n.strip() for n in value):
        accepted = _vendor_name(name, seen, findings)
        if accepted is None:
            continue
        seen.add(accepted.lower())
        declared.append(accepted)
    return tuple(declared)


def missing_plugin(message: str) -> Diagnostic:
    return Diagnostic(
        rule="PROJECT002",
        path=PATH,
        line=0,
        column=0,
        message=message,
        remediation=(
            "Name the plugin application in pyproject.toml: `[tool.qgis-sdk] plugin = "
            '"<package>.plugin:app"`. `build` and `dev` derive metadata.txt '
            "and classFactory from it (decision-43)."
        ),
    )


def missing_key(what: str, target: str) -> Diagnostic:
    return Diagnostic(
        rule="META002",
        path=PATH,
        line=0,
        column=0,
        message=f"{what} is missing; metadata.txt needs it as `{target}`",
        remediation=(
            "QGIS refuses a plugin whose metadata lacks it; set the value in "
            "pyproject.toml (`qgis-sdk new` writes every required one)."
        ),
    )


def config(message: str, example: str) -> Diagnostic:
    return Diagnostic(
        rule="CONFIG001",
        path=PATH,
        line=0,
        column=0,
        message=message,
        remediation=f"Write it as `{example}`.",
    )


IMPORT_ROOT: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DISTRIBUTION_NAME: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
