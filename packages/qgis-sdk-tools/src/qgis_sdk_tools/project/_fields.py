from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from qgis_sdk.bridge.host import host_grant_names, host_operation_ids
from qgis_sdk.core.host import Host

from qgis_sdk_tools.check.diagnostics import Diagnostic

from ._externals import config, missing_key, named_external, vendor
from ._facts import (
    DEFAULT_PLACEMENT,
    GENERATED_METADATA_KEYS,
    PATH,
    PLACEMENTS,
    BuildConfig,
    ConsoleConfig,
    ExternalPackage,
    WebConfig,
    external_details,
)


def first_author(
    project: Mapping[str, object], findings: list[Diagnostic]
) -> tuple[str, str]:
    authors = project.get("authors")
    first: object = None
    if isinstance(authors, list) and authors:
        first = authors[0]
    if not isinstance(first, dict):
        findings.append(
            missing_key("[project] authors (a name and an email)", "author")
        )
        return "", ""
    name = first.get("name")
    email = first.get("email")
    if not isinstance(name, str) or not name.strip():
        findings.append(missing_key("[project] authors[0].name", "author"))
        name = ""
    if not isinstance(email, str) or not email.strip():
        findings.append(missing_key("[project] authors[0].email", "email"))
        email = ""
    return name.strip(), email.strip()


def _metadata_value(
    key: object, item: object, findings: list[Diagnostic]
) -> str | None:
    """One metadata value, or ``None`` when the key is derived or malformed."""
    if key in GENERATED_METADATA_KEYS:
        findings.append(
            config(
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
        config(
            f"[tool.qgis-sdk.metadata] {key} must be a string",
            f'{key} = "..."',
        )
    )
    return None


def passthrough(value: object, findings: list[Diagnostic]) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        findings.append(
            config(
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
            config(
                f"[tool.qgis-sdk] hosts names {name!r}, which is not one of "
                f"{', '.join(known)}",
                'hosts = ["desktop", "server"]',
            )
        )
        return None
    return name


def hosts(value: object, findings: list[Diagnostic]) -> tuple[str, ...]:
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
            config(
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


def web(value: object, findings: list[Diagnostic]) -> WebConfig | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        findings.append(
            config(
                "[tool.qgis-sdk.web] must be a table",
                '[tool.qgis-sdk.web]\nplacement = "dock"',
            )
        )
        return None
    placement = value.get("placement", DEFAULT_PLACEMENT)
    if not isinstance(placement, str) or placement not in PLACEMENTS:
        findings.append(
            config(
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


def console(value: object, findings: list[Diagnostic]) -> ConsoleConfig:
    """``[tool.qgis-sdk.console]``: the developer's console, unrestricted by default."""
    if value is None:
        return ConsoleConfig()
    if not isinstance(value, dict):
        findings.append(
            config(
                "[tool.qgis-sdk.console] must be a table",
                '[tool.qgis-sdk.console]\ngrants = ["layers.read"]',
            )
        )
        return ConsoleConfig()
    for key in sorted(set(value) - {"grants"}):
        findings.append(
            config(
                f"[tool.qgis-sdk.console] has no key `{key}` (only grants)",
                '[tool.qgis-sdk.console]\ngrants = ["layers.read"]',
            )
        )
    return ConsoleConfig(
        grants=_grants("[tool.qgis-sdk.console]", value.get("grants"), findings)
    )


def _grants_shape_finding(section: str) -> Diagnostic:
    return config(
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
        path=PATH,
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


def build(value: object, findings: list[Diagnostic]) -> BuildConfig:
    """``[tool.qgis-sdk.build]``; an unknown key is a typed-in-the-wrong-place key."""
    if value is None:
        return BuildConfig()
    if not isinstance(value, dict):
        findings.append(
            config(
                "[tool.qgis-sdk.build] must be a table",
                '[tool.qgis-sdk.build]\nexternal = ["pandas"]',
            )
        )
        return BuildConfig()
    for key in sorted(set(value) - _BUILD_KEYS):
        findings.append(
            config(
                f"[tool.qgis-sdk.build] has no key `{key}` (only external, vendor)",
                '[tool.qgis-sdk.build]\nexternal = ["pandas"]',
            )
        )
    return BuildConfig(
        external=_external(value.get("external"), findings),
        vendor=vendor(value.get("vendor"), findings),
    )


def _duplicate_external_finding(import_name: str) -> Diagnostic:
    return config(
        f"[tool.qgis-sdk.build] external names `{import_name}` twice",
        "List each import root once.",
    )


def _external(value: object, findings: list[Diagnostic]) -> tuple[ExternalPackage, ...]:
    """The declared externals: bare import roots, or tables adding detail."""
    if value is None:
        return ()
    if not isinstance(value, list):
        findings.append(
            config(
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
            config(
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
            config(
                "[tool.qgis-sdk.build] external entry needs `import`",
                'external = [{ import = "pandas", requirement = "pandas>=2" }]',
            )
        )
        return None
    return name


def _external_entry(item: object, findings: list[Diagnostic]) -> ExternalPackage | None:
    if isinstance(item, str):
        return named_external(item, findings)
    if not isinstance(item, dict):
        findings.append(
            config(
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
    package = named_external(name, findings)
    if package is None:
        return None
    return external_details(item, name, package, findings)
