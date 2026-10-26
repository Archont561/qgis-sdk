"""``[tool.qgis-sdk]`` and ``[project]``: the one description of a plugin project.

decision-43: an author's project holds no ``metadata.txt``, no ``classFactory``
and no ``webview.py``. ``pyproject.toml`` names the plugin class and the
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
    plugin = "field_tools.plugin:FieldTools"
    qgis-minimum-version = "4.0"
    experimental = true

    [tool.qgis-sdk.metadata]      # passed through to metadata.txt as written
    homepage = "https://example.org/field-tools"
    tags = "vector, survey"

    [tool.qgis-sdk.web]           # only with a page
    placement = "dock"            # or "dialog"
    grants = ["layers.read"]      # host grants or operation ids the page may use

Rules reported here:

``PROJECT002``
    ``[tool.qgis-sdk] plugin`` is not set, so nothing can tell which class
    the plugin is. A project scaffolded before decision-43 sees this once,
    beside ``META001``/``ENTRY002`` for the files it still carries.
``CONFIG001``
    an entry has the wrong shape (``plugin`` not ``pkg.module:Class``, a
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
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from qgis_sdk.bridge.host import HOST_OPERATIONS
from qgis_sdk.models import QgisSdkError

from qgis_sdk_tools.check.diagnostics import Diagnostic

__all__ = [
    "GENERATED_METADATA_KEYS",
    "PLACEMENTS",
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

    @property
    def module(self) -> str:
        """The module half of ``spec``."""
        return self.spec.partition(":")[0]

    @property
    def class_name(self) -> str:
        """The class half of ``spec``."""
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
    pyproject = root / PYPROJECT
    if not pyproject.is_file():
        return None, (_missing_plugin(f"{root} has no {PYPROJECT}"),)
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return None, ()  # CONFIG001 from check_project already names the parse error
    tool = _table(data, "tool", "qgis-sdk")
    if tool is None:
        return None, (_missing_plugin("[tool.qgis-sdk] plugin is not set"),)
    findings: list[Diagnostic] = []
    spec = tool.get("plugin")
    if spec is None:
        return None, (_missing_plugin("[tool.qgis-sdk] plugin is not set"),)
    if not isinstance(spec, str) or _PLUGIN_SPEC.match(spec) is None:
        return None, (
            _config(
                f"[tool.qgis-sdk] plugin must be 'pkg.module:Class', got {spec!r}",
                'plugin = "field_tools.plugin:FieldTools"',
            ),
        )

    project = _table(data, "project") or {}
    version = _required_text(project, "version", findings, "version")
    description = _required_text(project, "description", findings, "description")
    author, email = _first_author(project, findings)
    minimum = tool.get("qgis-minimum-version")
    if minimum is None:
        findings.append(
            _missing_key("[tool.qgis-sdk] qgis-minimum-version", "qgisMinimumVersion")
        )
        minimum = ""
    elif not isinstance(minimum, str) or not minimum.strip():
        findings.append(
            _config(
                "[tool.qgis-sdk] qgis-minimum-version must be a version string",
                'qgis-minimum-version = "4.0"',
            )
        )
        minimum = ""
    experimental = tool.get("experimental", True)
    if not isinstance(experimental, bool):
        findings.append(
            _config(
                "[tool.qgis-sdk] experimental must be true or false",
                "experimental = true",
            )
        )
        experimental = True
    metadata = _passthrough(tool.get("metadata"), findings)
    web = _web(tool.get("web"), findings)
    config = ProjectConfig(
        root=root,
        spec=spec,
        version=str(version),
        description=description,
        author=author,
        email=email,
        qgis_minimum_version=minimum.strip(),
        experimental=experimental,
        metadata=metadata,
        web=web,
    )
    return config, tuple(findings)


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


def _table(data: object, *keys: str) -> dict[str, object] | None:
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data if isinstance(data, dict) else None


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
        if key in GENERATED_METADATA_KEYS:
            findings.append(
                _config(
                    f"[tool.qgis-sdk.metadata] {key} is derived from [project] and "
                    "[tool.qgis-sdk]; it cannot be set here",
                    "Delete the key; `build` and `dev` write it.",
                )
            )
            continue
        if isinstance(item, bool):
            kept[key] = "True" if item else "False"
        elif isinstance(item, int | float | str):
            kept[key] = str(item)
        else:
            findings.append(
                _config(
                    f"[tool.qgis-sdk.metadata] {key} must be a string",
                    f'{key} = "..."',
                )
            )
    return kept


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
    grants = value.get("grants", [])
    if not isinstance(grants, list) or not all(isinstance(g, str) for g in grants):
        findings.append(
            _config(
                "[tool.qgis-sdk.web] grants must be a list of host grants or operation ids",
                'grants = ["layers.read", "project.layer_ids"]',
            )
        )
        grants = []
    known_grants = sorted({operation.grant for operation in HOST_OPERATIONS})
    known_ids = [operation.id for operation in HOST_OPERATIONS]
    for grant in sorted(set(grants) - set(known_grants) - set(known_ids)):
        findings.append(
            Diagnostic(
                rule="GRANT001",
                path=_PATH,
                line=0,
                column=0,
                message=(
                    f"[tool.qgis-sdk.web] grants names `{grant}`, neither a host "
                    "grant nor a host operation"
                ),
                remediation=(
                    "The grants are "
                    + ", ".join(known_grants)
                    + "; the operation ids are "
                    + ", ".join(known_ids)
                    + ". Remove the entry or fix the name."
                ),
            )
        )
    return WebConfig(placement=placement, grants=tuple(dict.fromkeys(grants)))


def _missing_plugin(message: str) -> Diagnostic:
    return Diagnostic(
        rule="PROJECT002",
        path=_PATH,
        line=0,
        column=0,
        message=message,
        remediation=(
            "Name the plugin class in pyproject.toml: `[tool.qgis-sdk] plugin = "
            '"<package>.plugin:<Class>"`. `build` and `dev` derive metadata.txt '
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
