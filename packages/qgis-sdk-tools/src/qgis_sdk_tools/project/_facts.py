"""``[tool.qgis-sdk]`` and ``[project]``: the one description of a plugin project.

decision-43: an author's project holds no ``metadata.txt``, no ``classFactory``
and no ``webview.py``. ``pyproject.toml`` names the plugin application and the
few QGIS-only facts, and ``build`` and ``dev`` derive the host artifacts from
it. This module reads that configuration and reports what is missing or
malformed, with the same :class:`Diagnostic` shape ``check`` prints; it
imports nothing of the project.

::

    [project]
    name = "field-tools"
    version = "0.1.0"
    description = "One line QGIS shows in the plugin manager."
    authors = [{ name = "Ada", email = "ada@example.org" }]
    dependencies = ["qgis-sdk-runtime>=0.6,<0.7"]

    [tool.qgis-sdk]
    plugin = "field_tools.plugin:app"
    qgis-minimum-version = "4.0"
    experimental = true

    [tool.qgis-sdk.metadata]      # passed through to metadata.txt as written
    homepage = "https://example.org/field-tools"
    tags = "vector, survey"

    [tool.qgis-sdk.web]           # only with a page
    placement = "dock"            # or "dialog"
    grants = ["layers.read"]      # host grants or operation ids the page may use

    [tool.qgis-sdk.build]         # what the ZIP may assume and what it carries
    external = ["pandas", { import = "numpy", requirement = "numpy>=1.26" }]
    vendor = ["shapely"]          # pure-Python distributions, copied into vendor/

Rules reported here:

``PROJECT002``
    ``[tool.qgis-sdk] plugin`` is not set, so nothing can tell which class
    the plugin is. A project scaffolded before decision-43 sees this once,
    beside ``META001``/``ENTRY002`` for the files it still carries.
``CONFIG001``
    an entry has the wrong shape (``plugin`` not ``pkg.module:app``, a
    placement that is neither ``dock`` nor ``dialog``, grants that are not
    a list of strings, a passthrough key that is not a string, ...).
``META002``
    a value ``metadata.txt`` needs is missing from ``pyproject.toml``:
    ``[project] version``, ``description``, the first author's ``name`` and
    ``email``, ``[tool.qgis-sdk] qgis-minimum-version``.
``GRANT001``
    ``[tool.qgis-sdk.web] grants`` names something that is neither a host
    grant (``layers.read``) nor a host operation id (``project.layer_ids``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from qgis_sdk.models import QgisSdkError

from qgis_sdk_tools.check.diagnostics import Diagnostic


@dataclass(slots=True)
class _ProjectFacts:
    """The fields one ``pyproject.toml`` contributes to a :class:`ProjectConfig`.

    Validation fills this record in place and appends diagnostics as it goes,
    so the configuration is assembled from one value rather than a long
    argument list (decision-81).
    """

    root: Path
    spec: str
    tool: Mapping[str, object]
    findings: list[Diagnostic] = field(default_factory=list)
    version: str = ""
    description: str = ""
    author: str = ""
    email: str = ""
    minimum: str = ""
    experimental: bool = True
    metadata: dict[str, str] = field(default_factory=dict)
    hosts: tuple[str, ...] = ()


def plugin_spec_finding(value: object) -> Diagnostic:
    """The one diagnostic for a missing or malformed ``plugin`` entry."""
    from ._externals import config, missing_plugin

    if value is None:
        return missing_plugin("[tool.qgis-sdk] plugin is not set")
    return config(
        f"[tool.qgis-sdk] plugin must be 'pkg.module:app', got {value!r}",
        'plugin = "field_tools.plugin:app"',
    )


def read_project_fields(facts: _ProjectFacts, project: Mapping[str, object]) -> None:
    """Read the ``[project]`` values metadata.txt needs, in that order."""
    from ._fields import first_author

    facts.version = _required_text(project, "version", facts.findings, "version")
    facts.description = _required_text(
        project, "description", facts.findings, "description"
    )
    facts.author, facts.email = first_author(project, facts.findings)


def _minimum_version(tool: Mapping[str, object], findings: list[Diagnostic]) -> str:
    from ._externals import config, missing_key

    minimum = tool.get("qgis-minimum-version")
    if minimum is None:
        findings.append(
            missing_key("[tool.qgis-sdk] qgis-minimum-version", "qgisMinimumVersion")
        )
        return ""
    if not isinstance(minimum, str) or not minimum.strip():
        findings.append(
            config(
                "[tool.qgis-sdk] qgis-minimum-version must be a version string",
                'qgis-minimum-version = "4.0"',
            )
        )
        return ""
    return minimum


def _experimental_flag(tool: Mapping[str, object], findings: list[Diagnostic]) -> bool:
    from ._externals import config

    experimental = tool.get("experimental", True)
    if not isinstance(experimental, bool):
        findings.append(
            config(
                "[tool.qgis-sdk] experimental must be true or false",
                "experimental = true",
            )
        )
        return True
    return experimental


def read_tool_fields(facts: _ProjectFacts) -> None:
    """Read the ``[tool.qgis-sdk]`` values that are not the plugin spec."""
    from ._fields import hosts, passthrough

    facts.minimum = _minimum_version(facts.tool, facts.findings)
    facts.experimental = _experimental_flag(facts.tool, facts.findings)
    facts.metadata = passthrough(facts.tool.get("metadata"), facts.findings)
    facts.hosts = hosts(facts.tool.get("hosts"), facts.findings)


def config_from_facts(
    facts: _ProjectFacts,
) -> tuple[ProjectConfig, tuple[Diagnostic, ...]]:
    """Derive the host artifacts and close the record into a configuration."""
    from ._fields import build, console, web

    web = web(facts.tool.get("web"), facts.findings)
    console = console(facts.tool.get("console"), facts.findings)
    build = build(facts.tool.get("build"), facts.findings)
    config = ProjectConfig(
        root=facts.root,
        spec=facts.spec,
        version=str(facts.version),
        description=facts.description,
        author=facts.author,
        email=facts.email,
        qgis_minimum_version=facts.minimum.strip(),
        experimental=facts.experimental,
        metadata=facts.metadata,
        web=web,
        console=console,
        build=build,
        hosts=facts.hosts,
    )
    return config, tuple(facts.findings)


_EXTERNAL_TEXTS: dict[str, tuple[str, str]] = {
    "requirement": (
        "must be a requirement string",
        'requirement = "pandas>=2"',
    ),
    "reason": (
        "must be a sentence",
        'reason = "reads spreadsheets"',
    ),
}


def _external_text(
    item: Mapping[str, object], key: str, name: str, findings: list[Diagnostic]
) -> str | None:
    """One optional text of an ``external`` entry, or ``None`` when invalid."""
    from ._externals import config

    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        description, example = _EXTERNAL_TEXTS[key]
        findings.append(
            config(
                f"[tool.qgis-sdk.build] external `{name}` {key} {description}",
                example,
            )
        )
        return None
    return value.strip()


def external_details(
    item: Mapping[str, object],
    name: str,
    package: ExternalPackage,
    findings: list[Diagnostic],
) -> ExternalPackage:
    """Add the optional requirement and reason to a validated import root."""
    return ExternalPackage(
        import_name=package.import_name,
        requirement=_external_text(item, "requirement", name, findings),
        reason=_external_text(item, "reason", name, findings),
    )


PYPROJECT: Final = "pyproject.toml"
PLACEMENTS: Final = ("dock", "dialog")
DEFAULT_PLACEMENT: Final = "dialog"
GENERATED_METADATA_KEYS: Final = frozenset(
    {
        "name",
        "description",
        "version",
        "qgisMinimumVersion",
        "author",
        "email",
        "experimental",
        "hasProcessingProvider",
    }
)
_PLUGIN_SPEC = re.compile(
    r"^(?P<module>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
    r":(?P<attribute>[A-Za-z_][A-Za-z0-9_]*)$"
)
PATH: Final = Path(PYPROJECT)


class QgisSdkProjectError(QgisSdkError):
    """A command needs the project configuration and it is missing or malformed."""

    code = "project_invalid"

    def __init__(self, diagnostics: tuple[Diagnostic, ...], root: Path) -> None:
        self.diagnostics = diagnostics
        self.root = root
        first = diagnostics[0]
        more = f" (+{len(diagnostics) - 1} more)" if len(diagnostics) > 1 else ""
        super().__init__(
            f"{root / first.path}: {first.rule} {first.message}{more}\n"
            f"    {first.remediation}"
        )


@dataclass(frozen=True, slots=True)
class WebConfig:
    """``[tool.qgis-sdk.web]``: the page and what it may call on the host."""

    placement: str = DEFAULT_PLACEMENT
    grants: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConsoleConfig:
    """``[tool.qgis-sdk.console]``: what the developer's console may reach.

    Unset means every operation. The console is the plugin's own developer
    looking at a running plugin (decision-48), so "call anything" has to stay
    the default; a ``grants`` list narrows it with the same names a page uses
    (decision-54, amended: the agent dialect this used to name was withdrawn
    with decision-49, and the plugin HTTP allowlist names actions, not
    operations).
    """

    grants: tuple[str, ...] = ()

    @property
    def unrestricted(self) -> bool:
        """True when the console reaches every declared operation."""
        return not self.grants


@dataclass(frozen=True, slots=True)
class ExternalPackage:
    """One ``[tool.qgis-sdk.build] external`` entry (decision-50 point 1).

    ``import_name`` is the root the plugin imports (``pandas``);
    ``requirement`` is what the user has to install (``pandas>=2``), defaulting
    to the root; ``reason`` is the sentence the startup probe shows beside it.
    """

    import_name: str
    requirement: str | None = None
    reason: str | None = None

    @property
    def install_requirement(self) -> str:
        """What an install command on the user's machine has to name."""
        return self.requirement or self.import_name


@dataclass(frozen=True, slots=True)
class BuildConfig:
    """``[tool.qgis-sdk.build]``: declared externals and vendored distributions."""

    external: tuple[ExternalPackage, ...] = ()
    vendor: tuple[str, ...] = ()

    @property
    def external_roots(self) -> tuple[str, ...]:
        """The import roots the build may leave to the target QGIS."""
        return tuple(item.import_name for item in self.external)


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """What ``pyproject.toml`` says about the plugin, validated."""

    root: Path
    spec: str
    version: str
    description: str
    author: str
    email: str
    qgis_minimum_version: str
    experimental: bool = True
    metadata: Mapping[str, str] = field(default_factory=dict)
    web: WebConfig | None = None
    console: ConsoleConfig = field(default_factory=ConsoleConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    #: ``[tool.qgis-sdk] hosts``: which hosts this plugin runs on (decision-52).
    hosts: tuple[str, ...] = ("desktop",)

    @property
    def module(self) -> str:
        """The module half of ``spec``."""
        return self.spec.partition(":")[0]

    @property
    def class_name(self) -> str:
        """The attribute half of ``spec``."""
        return self.spec.partition(":")[2]

    @property
    def plugin(self) -> str:
        """The plugin package: the first segment of the module, QGIS's plugin name."""
        return self.module.split(".", 1)[0]

    @property
    def package(self) -> Path:
        return self.root / self.plugin


def _required_text(
    table: Mapping[str, object], key: str, findings: list[Diagnostic], target: str
) -> str:
    from ._externals import config, missing_key

    value = table.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        findings.append(missing_key(f"[project] {key}", target))
        return ""
    if not isinstance(value, str):
        findings.append(config(f"[project] {key} must be a string", f'{key} = "..."'))
        return ""
    return value.strip()
