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
    vendor = ["shapely"]          # pure-Python distributions, copied into _vendor/

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

from qgis_sdk.bridge.host import host_grant_names, host_operation_ids
from qgis_sdk.core.host import Host
from qgis_sdk.models import QgisSdkError

from qgis_sdk_tools.check.diagnostics import Diagnostic
from qgis_sdk_tools.manifest import read_pyproject, table


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


def _plugin_spec_finding(value: object) -> Diagnostic:
    """The one diagnostic for a missing or malformed ``plugin`` entry."""
    if value is None:
        return _missing_plugin("[tool.qgis-sdk] plugin is not set")
    return _config(
        f"[tool.qgis-sdk] plugin must be 'pkg.module:app', got {value!r}",
        'plugin = "field_tools.plugin:app"',
    )


def _read_project_fields(facts: _ProjectFacts, project: Mapping[str, object]) -> None:
    """Read the ``[project]`` values metadata.txt needs, in that order."""
    facts.version = _required_text(project, "version", facts.findings, "version")
    facts.description = _required_text(
        project, "description", facts.findings, "description"
    )
    facts.author, facts.email = _first_author(project, facts.findings)


def _minimum_version(tool: Mapping[str, object], findings: list[Diagnostic]) -> str:
    minimum = tool.get("qgis-minimum-version")
    if minimum is None:
        findings.append(
            _missing_key("[tool.qgis-sdk] qgis-minimum-version", "qgisMinimumVersion")
        )
        return ""
    if not isinstance(minimum, str) or not minimum.strip():
        findings.append(
            _config(
                "[tool.qgis-sdk] qgis-minimum-version must be a version string",
                'qgis-minimum-version = "4.0"',
            )
        )
        return ""
    return minimum


def _experimental_flag(tool: Mapping[str, object], findings: list[Diagnostic]) -> bool:
    experimental = tool.get("experimental", True)
    if not isinstance(experimental, bool):
        findings.append(
            _config(
                "[tool.qgis-sdk] experimental must be true or false",
                "experimental = true",
            )
        )
        return True
    return experimental


def _read_tool_fields(facts: _ProjectFacts) -> None:
    """Read the ``[tool.qgis-sdk]`` values that are not the plugin spec."""
    facts.minimum = _minimum_version(facts.tool, facts.findings)
    facts.experimental = _experimental_flag(facts.tool, facts.findings)
    facts.metadata = _passthrough(facts.tool.get("metadata"), facts.findings)
    facts.hosts = _hosts(facts.tool.get("hosts"), facts.findings)


def _config_from_facts(
    facts: _ProjectFacts,
) -> tuple[ProjectConfig, tuple[Diagnostic, ...]]:
    """Derive the host artifacts and close the record into a configuration."""
    web = _web(facts.tool.get("web"), facts.findings)
    console = _console(facts.tool.get("console"), facts.findings)
    build = _build(facts.tool.get("build"), facts.findings)
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


#: The two optional texts of an ``external`` table: what the diagnostic says
#: and the line it suggests. A dispatch table keeps the validator to one shape.
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
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        description, example = _EXTERNAL_TEXTS[key]
        findings.append(
            _config(
                f"[tool.qgis-sdk.build] external `{name}` {key} {description}",
                example,
            )
        )
        return None
    return value.strip()


def _external_details(
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


__all__ = [
    "GENERATED_METADATA_KEYS",
    "PLACEMENTS",
    "BuildConfig",
    "ExternalPackage",
    "ProjectConfig",
    "QgisSdkProjectError",
    "WebConfig",
    "load_project",
    "require_project",
]

PYPROJECT: Final = "pyproject.toml"
PLACEMENTS: Final = ("dock", "dialog")
DEFAULT_PLACEMENT: Final = "dialog"
#: Keys ``build``/``dev`` derive; a passthrough entry may not set them.
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
_PATH: Final = Path(PYPROJECT)


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


def load_project(root: Path) -> tuple[ProjectConfig | None, tuple[Diagnostic, ...]]:
    """Read the configuration at ``root``; ``None`` plus findings when unusable.

    Findings that do not stop the configuration from being used (a missing
    ``[project] description``, say) come back beside a config; ``check``
    prints them all, ``build`` refuses on the errors.
    """
    root = Path(root)
    data, malformed = read_pyproject(root / PYPROJECT)
    if data is None:
        if malformed is not None:
            return (
                None,
                (),
            )  # CONFIG001 from check_project already names the parse error
        return None, (_missing_plugin(f"{root} has no {PYPROJECT}"),)
    tool = table(data, "tool", "qgis-sdk") or {}
    spec = tool.get("plugin")
    if not isinstance(spec, str) or _PLUGIN_SPEC.match(spec) is None:
        return None, (_plugin_spec_finding(spec),)
    facts = _ProjectFacts(root, spec, tool)
    _read_project_fields(facts, table(data, "project") or {})
    _read_tool_fields(facts)
    return _config_from_facts(facts)


def require_project(root: Path) -> ProjectConfig:
    """The configuration, or :class:`QgisSdkProjectError` naming what is wrong."""
    config, findings = load_project(root)
    errors = tuple(d for d in findings if d.severity == "error")
    if config is None:
        if not errors:
            errors = (_config(f"{PYPROJECT} does not parse", "Fix the TOML first."),)
        raise QgisSdkProjectError(errors, Path(root))
    if errors:
        raise QgisSdkProjectError(errors, Path(root))
    return config


# -- pieces ---------------------------------------------------------------------


def _required_text(
    table: Mapping[str, object], key: str, findings: list[Diagnostic], target: str
) -> str:
    value = table.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        findings.append(_missing_key(f"[project] {key}", target))
        return ""
    if not isinstance(value, str):
        findings.append(_config(f"[project] {key} must be a string", f'{key} = "..."'))
        return ""
    return value.strip()


def _first_author(
    project: Mapping[str, object], findings: list[Diagnostic]
) -> tuple[str, str]:
    authors = project.get("authors")
    first: object = None
    if isinstance(authors, list) and authors:
        first = authors[0]
    if not isinstance(first, dict):
        findings.append(
            _missing_key("[project] authors (a name and an email)", "author")
        )
        return "", ""
    name = first.get("name")
    email = first.get("email")
    if not isinstance(name, str) or not name.strip():
        findings.append(_missing_key("[project] authors[0].name", "author"))
        name = ""
    if not isinstance(email, str) or not email.strip():
        findings.append(_missing_key("[project] authors[0].email", "email"))
        email = ""
    return name.strip(), email.strip()


def _metadata_value(
    key: object, item: object, findings: list[Diagnostic]
) -> str | None:
    """One metadata value, or ``None`` when the key is derived or malformed."""
    if key in GENERATED_METADATA_KEYS:
        findings.append(
            _config(
                f"[tool.qgis-sdk.metadata] {key} is derived from [project] and "
                "[tool.qgis-sdk]; it cannot be set here",
                "Delete the key; `build` and `dev` write it.",
            )
        )
        return None
    if isinstance(item, bool):
        return "True" if item else "False"
    if isinstance(item, int | float | str):
        return str(item)
    findings.append(
        _config(
            f"[tool.qgis-sdk.metadata] {key} must be a string",
            f'{key} = "..."',
        )
    )
    return None


def _passthrough(value: object, findings: list[Diagnostic]) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        findings.append(
            _config(
                "[tool.qgis-sdk.metadata] must be a table of strings",
                '[tool.qgis-sdk.metadata]\nhomepage = "https://..."',
            )
        )
        return {}
    kept: dict[str, str] = {}
    for key, item in value.items():
        text = _metadata_value(key, item, findings)
        if text is not None:
            kept[key] = text
    return kept


def _host_name(
    name: object, known: list[str], findings: list[Diagnostic]
) -> str | None:
    """One declared host name, or ``None`` when it is not a host at all."""
    if not isinstance(name, str) or name not in known:
        findings.append(
            _config(
                f"[tool.qgis-sdk] hosts names {name!r}, which is not one of "
                f"{', '.join(known)}",
                'hosts = ["desktop", "server"]',
            )
        )
        return None
    return name


def _hosts(value: object, findings: list[Diagnostic]) -> tuple[str, ...]:
    """``[tool.qgis-sdk] hosts``: the declared hosts, or the Desktop default.

    One plugin class, a declared host set (decision-52 point 1). A name outside
    :class:`~qgis_sdk.core.host.Host` is a ``CONFIG001`` rather than a silent
    default, because a misspelt host is exactly the mistake that would otherwise
    surface as a plugin that refuses every capability on the host it does run on.
    """
    if value is None:
        return (Host.DESKTOP.value,)
    if not isinstance(value, (list, tuple)) or not value:
        findings.append(
            _config(
                "[tool.qgis-sdk] hosts must be a list of host names",
                'hosts = ["desktop", "server"]',
            )
        )
        return (Host.DESKTOP.value,)
    known = [host.value for host in Host]
    declared: list[str] = []
    for name in value:
        host = _host_name(name, known, findings)
        if host is not None and host not in declared:
            declared.append(host)
    return tuple(declared) or (Host.DESKTOP.value,)


def _web(value: object, findings: list[Diagnostic]) -> WebConfig | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        findings.append(
            _config(
                "[tool.qgis-sdk.web] must be a table",
                '[tool.qgis-sdk.web]\nplacement = "dock"',
            )
        )
        return None
    placement = value.get("placement", DEFAULT_PLACEMENT)
    if not isinstance(placement, str) or placement not in PLACEMENTS:
        findings.append(
            _config(
                "[tool.qgis-sdk.web] placement must be "
                f"{' or '.join(repr(p) for p in PLACEMENTS)}, got {placement!r}",
                'placement = "dock"',
            )
        )
        placement = DEFAULT_PLACEMENT
    return WebConfig(
        placement=placement,
        grants=_grants("[tool.qgis-sdk.web]", value.get("grants"), findings),
    )


def _console(value: object, findings: list[Diagnostic]) -> ConsoleConfig:
    """``[tool.qgis-sdk.console]``: the developer's console, unrestricted by default."""
    if value is None:
        return ConsoleConfig()
    if not isinstance(value, dict):
        findings.append(
            _config(
                "[tool.qgis-sdk.console] must be a table",
                '[tool.qgis-sdk.console]\ngrants = ["layers.read"]',
            )
        )
        return ConsoleConfig()
    for key in sorted(set(value) - {"grants"}):
        findings.append(
            _config(
                f"[tool.qgis-sdk.console] has no key `{key}` (only grants)",
                '[tool.qgis-sdk.console]\ngrants = ["layers.read"]',
            )
        )
    return ConsoleConfig(
        grants=_grants("[tool.qgis-sdk.console]", value.get("grants"), findings)
    )


def _grants_shape_finding(section: str) -> Diagnostic:
    return _config(
        f"{section} grants must be a list of host grants or operation ids",
        'grants = ["layers.read", "project.layer_ids"]',
    )


def _unknown_grant_finding(
    section: str,
    grant: str,
    known_grants: tuple[str, ...] | list[str],
    known_ids: tuple[str, ...] | list[str],
) -> Diagnostic:
    return Diagnostic(
        rule="GRANT001",
        path=_PATH,
        line=0,
        column=0,
        message=(
            f"{section} grants names `{grant}`, neither a host grant "
            "nor a host operation"
        ),
        remediation=(
            "The grants are "
            + ", ".join(known_grants)
            + "; the operation ids are "
            + ", ".join(known_ids)
            + ". Remove the entry or fix the name."
        ),
    )


def _grants(section: str, value: object, findings: list[Diagnostic]) -> tuple[str, ...]:
    """Read one ``grants`` list: the same names and the same finding everywhere.

    ``value`` is the raw entry under ``grants``, so ``None`` and a wrong type are
    told apart: a missing list is an empty one, while a string where a list
    belongs is a malformed table and gets ``CONFIG001``. An unknown name is
    ``GRANT001`` in whichever section it appears, with the one remediation
    listing the vocabulary (decision-54 point 2).
    """
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(entry, str) for entry in value
    ):
        findings.append(_grants_shape_finding(section))
        return ()
    known_grants = host_grant_names()
    known_ids = host_operation_ids()
    for grant in sorted(set(value) - set(known_grants) - set(known_ids)):
        findings.append(_unknown_grant_finding(section, grant, known_grants, known_ids))
    return tuple(dict.fromkeys(value))


_BUILD_KEYS: Final = frozenset({"external", "vendor"})
_EXTERNAL_KEYS: Final = frozenset({"import", "requirement", "reason"})
_IMPORT_ROOT: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DISTRIBUTION_NAME: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _build(value: object, findings: list[Diagnostic]) -> BuildConfig:
    """``[tool.qgis-sdk.build]``; an unknown key is a typed-in-the-wrong-place key."""
    if value is None:
        return BuildConfig()
    if not isinstance(value, dict):
        findings.append(
            _config(
                "[tool.qgis-sdk.build] must be a table",
                '[tool.qgis-sdk.build]\nexternal = ["pandas"]',
            )
        )
        return BuildConfig()
    for key in sorted(set(value) - _BUILD_KEYS):
        findings.append(
            _config(
                f"[tool.qgis-sdk.build] has no key `{key}` (only external, vendor)",
                '[tool.qgis-sdk.build]\nexternal = ["pandas"]',
            )
        )
    return BuildConfig(
        external=_external(value.get("external"), findings),
        vendor=_vendor(value.get("vendor"), findings),
    )


def _duplicate_external_finding(import_name: str) -> Diagnostic:
    return _config(
        f"[tool.qgis-sdk.build] external names `{import_name}` twice",
        "List each import root once.",
    )


def _external(value: object, findings: list[Diagnostic]) -> tuple[ExternalPackage, ...]:
    """The declared externals: bare import roots, or tables adding detail."""
    if value is None:
        return ()
    if not isinstance(value, list):
        findings.append(
            _config(
                "[tool.qgis-sdk.build] external must be a list of import roots "
                "or tables",
                'external = ["pandas", { import = "numpy", requirement = '
                '"numpy>=1.26", reason = "raster maths" }]',
            )
        )
        return ()
    declared: list[ExternalPackage] = []
    seen: set[str] = set()
    for item in value:
        package = _external_entry(item, findings)
        if package is None:
            continue
        if package.import_name in seen:
            findings.append(_duplicate_external_finding(package.import_name))
            continue
        seen.add(package.import_name)
        declared.append(package)
    return tuple(declared)


def _external_entry_keys(
    item: Mapping[str, object], findings: list[Diagnostic]
) -> None:
    """An ``external`` table names only import, requirement and reason."""
    for key in sorted(set(item) - _EXTERNAL_KEYS):
        findings.append(
            _config(
                f"[tool.qgis-sdk.build] external entry has no key `{key}` "
                "(only import, requirement, reason)",
                '[tool.qgis-sdk.build]\nexternal = [{ import = "pandas" }]',
            )
        )


def _external_entry_name(
    item: Mapping[str, object], findings: list[Diagnostic]
) -> str | None:
    name = item.get("import")
    if not isinstance(name, str):
        findings.append(
            _config(
                "[tool.qgis-sdk.build] external entry needs `import`",
                'external = [{ import = "pandas", requirement = "pandas>=2" }]',
            )
        )
        return None
    return name


def _external_entry(item: object, findings: list[Diagnostic]) -> ExternalPackage | None:
    if isinstance(item, str):
        return _named_external(item, findings)
    if not isinstance(item, dict):
        findings.append(
            _config(
                "[tool.qgis-sdk.build] external entries are import roots or "
                f"tables, got {item!r}",
                'external = [{ import = "pandas", requirement = "pandas>=2" }]',
            )
        )
        return None
    _external_entry_keys(item, findings)
    name = _external_entry_name(item, findings)
    if name is None:
        return None
    package = _named_external(name, findings)
    if package is None:
        return None
    return _external_details(item, name, package, findings)


def _named_external(name: str, findings: list[Diagnostic]) -> ExternalPackage | None:
    if _IMPORT_ROOT.match(name.strip()) is None:
        findings.append(
            _config(
                f"[tool.qgis-sdk.build] external entry {name!r} is not an import "
                "root (one identifier, such as `pandas`)",
                'external = ["pandas"]',
            )
        )
        return None
    return ExternalPackage(import_name=name.strip())


def _vendor_name(name: str, seen: set[str], findings: list[Diagnostic]) -> str | None:
    """One vendored distribution, or ``None`` when malformed or duplicated."""
    if _DISTRIBUTION_NAME.match(name) is None:
        findings.append(
            _config(
                f"[tool.qgis-sdk.build] vendor entry {name!r} is not a "
                "distribution name",
                'vendor = ["shapely"]',
            )
        )
        return None
    if name.lower() in seen:
        findings.append(
            _config(
                f"[tool.qgis-sdk.build] vendor names `{name}` twice",
                "List each distribution once.",
            )
        )
        return None
    return name


def _vendor(value: object, findings: list[Diagnostic]) -> tuple[str, ...]:
    """The distributions the build copies into ``<plugin>/_vendor``."""
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(n, str) for n in value):
        findings.append(
            _config(
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


def _missing_plugin(message: str) -> Diagnostic:
    return Diagnostic(
        rule="PROJECT002",
        path=_PATH,
        line=0,
        column=0,
        message=message,
        remediation=(
            "Name the plugin application in pyproject.toml: `[tool.qgis-sdk] plugin = "
            '"<package>.plugin:app"`. `build` and `dev` derive metadata.txt '
            "and classFactory from it (decision-43)."
        ),
    )


def _missing_key(what: str, target: str) -> Diagnostic:
    return Diagnostic(
        rule="META002",
        path=_PATH,
        line=0,
        column=0,
        message=f"{what} is missing; metadata.txt needs it as `{target}`",
        remediation=(
            "QGIS refuses a plugin whose metadata lacks it; set the value in "
            "pyproject.toml (`qgis-sdk new` writes every required one)."
        ),
    )


def _config(message: str, example: str) -> Diagnostic:
    return Diagnostic(
        rule="CONFIG001",
        path=_PATH,
        line=0,
        column=0,
        message=message,
        remediation=f"Write it as `{example}`.",
    )
