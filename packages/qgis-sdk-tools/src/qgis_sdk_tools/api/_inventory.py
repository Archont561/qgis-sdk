"""The public API, as data: what this repository promises at a given version.

decision-56 makes a *generated* inventory the contract for 1.0: a JSON document
listing every public name, its signature, the stability tier it belongs to, the
check rules, the host operations and the CLI surface. `qgis-sdk api dump` writes
it, `release verify-api` diffs two of them, and doc-12 renders the tiers from it
- so the promise is read from one place instead of restated by hand.

Three properties the document has to keep, because a gate is only as good as its
reading: it is deterministic (sorted, no timestamps, no paths, so two dumps of
one tree are byte-identical), it is complete for the public modules `qgis_sdk`
exports, and it is cheap enough to run in the release train.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._signatures import enum_members, signature_of

__all__ = [
    "API_VERSION",
    "PUBLIC_MODULES",
    "Inventory",
    "inventory",
    "read",
    "write",
]

API_VERSION = 1
"""The shape of this document; a consumer refuses a number it does not know."""

PUBLIC_MODULES = (
    "qgis_sdk",
    "qgis_sdk.algorithms",
    "qgis_sdk.app",
    "qgis_sdk.batch",
    "qgis_sdk.bindings",
    "qgis_sdk.console",
    "qgis_sdk.core",
    "qgis_sdk.declarations",
    "qgis_sdk.deprecation",
    "qgis_sdk.environment",
    "qgis_sdk.exports",
    "qgis_sdk.files",
    "qgis_sdk.http",
    "qgis_sdk.jobs",
    "qgis_sdk.models",
    "qgis_sdk.network",
    "qgis_sdk.processing",
    "qgis_sdk.providers",
    "qgis_sdk.server",
    "qgis_sdk.services",
    "qgis_sdk.testing",
    "qgis_sdk.ui",
)
"""The modules `qgis_sdk` exports for plugin authors, one tier each.

These are the modules doc-12 documents as importable authoring surface, and all
of them import without QGIS, which is what lets the inventory run on a plain
runner. `qgis_sdk.core` is listed although decision-56 calls `core/` internal:
the decision also makes the context classes and service Protocols *stable*, and
the names a package re-exports are the only ones this document reads - the
implementations under `core/` stay internal.

`adapters` and `bridge` are absent on purpose: listing them would promise that
their shape survives a release.
"""

INTERNAL_PREFIXES = ("qgis_sdk.adapters", "qgis_sdk.bridge", "qgis_sdk.core")


def _describe(value: Any) -> str:
    """One exported name: its signature, its members, or the type it is."""
    if isinstance(value, enum.EnumMeta):
        return enum_members(value)
    return signature_of(value) if callable(value) else type(value).__name__


def _describe_module(module: Any) -> dict[str, str]:
    """Every name a module exports, mapped to its signature (``""`` if not one)."""
    names = getattr(module, "__all__", None) or [
        name for name in vars(module) if not name.startswith("_")
    ]
    described: dict[str, str] = {}
    for name in sorted(names):
        described[name] = _describe(getattr(module, name, None))
    return described


def _tier(module: Any, name: str) -> str:
    """The declared tier of one module, or `internal` for the excluded trees."""
    declared = getattr(module, "__stability__", None)
    if isinstance(declared, str):
        return declared
    return "internal" if name.startswith(INTERNAL_PREFIXES) else "stable"


def _public_modules() -> dict[str, dict[str, Any]]:
    """The public modules, each with its tier and its exported names."""
    from importlib import import_module

    modules: dict[str, dict[str, Any]] = {}
    for name in PUBLIC_MODULES:
        module = import_module(name)
        modules[name] = {
            "tier": _tier(module, name),
            "names": _describe_module(module),
        }
    return modules


RULE = 'rule="'
"""How the check package names a rule: ``Diagnostic(rule="JOB002", ...)``."""


def _rule_ids(source: Path) -> set[str]:
    """Every ``rule="..."`` literal under one directory, including subpackages."""
    found: set[str] = set()
    for path in sorted(source.rglob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            start = line.find(RULE)
            if start == -1:
                continue
            rest = line[start + len(RULE) :]
            found.add(rest[: rest.find('"')])
    return found


def _check_rules() -> list[str]:
    """The check rule ids the shipped tooling can report."""
    from qgis_sdk_tools import check

    return sorted(_rule_ids(Path(check.__file__).resolve().parent))


def _host_operations() -> list[str]:
    """The host operation ids the manifest declares."""
    from qgis_sdk.bridge.host.handlers import HANDLERS

    return sorted(HANDLERS)


def _cli_commands() -> list[str]:
    """Every command and every flag it takes, as ``"group command --flag"``.

    decision-56 makes CLI commands *and flags* stable, so both are entries: a
    dropped flag then reads as a breaking change on its own, instead of hiding
    inside the command that kept its name.
    """
    from typer.main import get_command

    from qgis_sdk_tools._commands import app

    return sorted(_cli_surface(get_command(app), ""))


def _is_option(parameter: Any) -> bool:
    """Whether one parameter is a flag rather than a positional argument."""
    return getattr(parameter, "param_type_name", "") == "option"


def _flags(command: Any) -> Iterable[str]:
    """Every spelling of every flag one command accepts."""
    for parameter in getattr(command, "params", ()):
        if _is_option(parameter):
            yield from getattr(parameter, "opts", ())


def _cli_surface(command: Any, prefix: str) -> Iterable[str]:
    """One command's path and flags, recursing into the sub-commands of a group."""
    children = getattr(command, "commands", None)
    if children:
        for name in sorted(children):
            yield from _cli_surface(children[name], f"{prefix}{name} ")
        return
    path = prefix.strip()
    yield path
    for flag in _flags(command):
        yield f"{path} {flag}"


def _deprecations() -> list[dict[str, str]]:
    """Every public name carrying a `@deprecated` mark, with its window.

    decision-56 point 3: the mark is the promise, and this is where the promise
    is recorded - one entry per name, naming the replacement and the version the
    name may be removed in. `release.py verify-api` refuses a removal before
    that version, and `check` reports a use of one as ``API001``.
    """
    from importlib import import_module

    from qgis_sdk.deprecation import deprecation_of

    entries: list[dict[str, str]] = []
    for name in PUBLIC_MODULES:
        module = import_module(name)
        for exported in getattr(module, "__all__", ()):
            mark = deprecation_of(getattr(module, exported, None))
            if mark is not None:
                entries.append({"module": name, "name": exported, **mark.to_json()})
    return sorted(entries, key=lambda entry: (entry["module"], entry["name"]))


@dataclass(frozen=True, slots=True)
class Inventory:
    """The public API of one tree: the four surfaces decision-56 names."""

    modules: Mapping[str, Mapping[str, Any]]
    rules: Sequence[str]
    operations: Sequence[str]
    cli: Sequence[str]
    deprecations: Sequence[Mapping[str, str]] = ()

    def document(self) -> dict[str, Any]:
        """The JSON-ready document, every collection sorted."""
        return {
            "api_version": API_VERSION,
            "modules": {
                name: {
                    "tier": entry["tier"],
                    "names": dict(sorted(entry["names"].items())),
                }
                for name, entry in sorted(self.modules.items())
            },
            "rules": sorted(self.rules),
            "host_operations": sorted(self.operations),
            "cli": sorted(self.cli),
            "deprecations": sorted(
                self.deprecations, key=lambda entry: (entry["module"], entry["name"])
            ),
        }


def inventory() -> Inventory:
    """Read the public API out of the installed packages."""
    return Inventory(
        modules=_public_modules(),
        rules=_check_rules(),
        operations=_host_operations(),
        cli=_cli_commands(),
        deprecations=_deprecations(),
    )


def write(document: Mapping[str, Any], path: Path) -> None:
    """Write one inventory as stable JSON: two spaces, sorted keys, one newline."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read(path: Path) -> dict[str, Any]:
    """Read one inventory, refusing a document shape this tool does not know."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    version = document.get("api_version")
    if version != API_VERSION:
        raise ValueError(
            f"{path} is api_version {version}; this tool reads {API_VERSION}"
        )
    return document
