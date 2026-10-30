"""``check_project``: walk one plugin project and report, mutating nothing.

Decision-8 fixes the boundaries: no imports of the project, no installs, no
handler execution, no rewrites. ``build`` reuses this function rather than
shelling out to the command.

Rules owned here: ``PROJECT001`` (no package), ``META001`` (a hand-written
``metadata.txt``; ``build``/``dev`` generate it), ``ENTRY002`` (a
hand-written ``classFactory``; ``host()`` binds it), ``CONFIG001`` for
``[tool.qgis-sdk.check]``. The ``pyproject.toml`` rules live in
:mod:`qgis_sdk_tools.project`, the version rules in :mod:`.versions`, the
native UI rules (``UI001``-``UI003``, ``UI005``, ``ICON001``) in :mod:`.ui`,
and the worker-safety rules for jobs (``JOB001``-``JOB003``) in :mod:`.jobs`.
"""

from __future__ import annotations

import ast
import os
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
from qgis_sdk_tools.manifest import read_pyproject, table

from .buckets import HOST_ROOTS, BucketReport, bucket_imports, import_findings
from .diagnostics import CheckReport, Diagnostic, QgisSdkCheckError
from .imports import check_source
from .jobs import check_jobs
from .ui import check_bindings
from .versions import (
    check_generated_clients,
    check_runtime_pins,
    check_runtime_requirement,
)

if TYPE_CHECKING:  # imported by the caller: this module is imported by it
    from qgis_sdk_tools.project import ProjectConfig

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
# QGIS refuses to load a plugin whose metadata.txt lacks any of these; ``build``
# and ``dev`` render them all from pyproject.toml (``qgis_sdk_tools.project``).
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

    packages = list(_check_packages(root))
    diagnostics.extend(packages)
    imports = None
    if not any(d.rule == "PROJECT001" for d in packages):
        # The plugin application, the metadata.txt values and the page (decision-43).
        from qgis_sdk_tools.project import load_project

        config, findings = load_project(root)
        diagnostics.extend(findings)
        if config is not None:
            imports, bucket_findings = _buckets(root, config)
            diagnostics.extend(bucket_findings)
    # What the project pins against what this release supports (decision-35),
    # and whether the runtime this interpreter would ship is one it declares.
    diagnostics.extend(check_runtime_pins(root))
    diagnostics.extend(check_runtime_requirement(root))
    diagnostics.extend(check_generated_clients(root))

    files = 0
    for path in _python_files(root):
        files += 1
        relative = path.relative_to(root)
        source = path.read_text(encoding="utf-8")
        diagnostics.extend(check_source(source, path=relative, native_modules=native))
        diagnostics.extend(check_jobs(source, path=relative))
        package = root / relative.parts[0] if len(relative.parts) > 1 else None
        diagnostics.extend(
            check_bindings(
                source,
                path=relative,
                package_directory=package,
                directory=path.parent,
            )
        )

    diagnostics.sort(key=lambda d: (d.path.as_posix(), d.line, d.column, d.rule))
    return CheckReport(
        root=root,
        diagnostics=tuple(diagnostics),
        files_checked=files,
        imports=imports,
    )


def _buckets(
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
    distributions = []
    findings: list[Diagnostic] = []
    for name in config.build.vendor:
        try:
            distribution = read_distribution(name)
        except QGisSdkDistributionError as error:
            findings.append(_declared("DEP004", str(error), name, vendored=False))
            continue
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
    findings.extend(_requirement_findings(distributions, config))
    report = bucket_imports(
        root,
        config.plugin,
        tuple(_python_files(package)),
        external=config.build.external_roots,
        vendored=vendored,
    )
    findings.extend(import_findings(report))
    return report, tuple(findings)


def _requirement_findings(
    distributions: Sequence[Distribution], config: ProjectConfig
) -> tuple[Diagnostic, ...]:
    """``DEP004`` for a vendored requirement that is neither vendored nor external.

    A vendored package carries its dependencies with it or assumes the target
    QGIS has them (decision-50 point 2); anything else fails on a clean QGIS
    with an ``ImportError`` from inside the copy, which is exactly what the
    author has to decide about here.
    """
    available = {normalize(item.name) for item in distributions}
    available.update(normalize(root) for root in config.build.external_roots)
    available.update(normalize(name) for name in HOST_ROOTS)
    available.update(names for names in sys.stdlib_module_names)
    findings: list[Diagnostic] = []
    for distribution in distributions:
        for requirement in distribution.requires:
            if normalize(requirement) in available:
                continue
            findings.append(
                Diagnostic(
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
            )
    return tuple(findings)


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
        yield from _check_host_artifacts(root, package)


def _check_host_artifacts(root: Path, package: Path) -> Iterator[Diagnostic]:
    """``META001``/``ENTRY002``: files ``build`` and ``dev`` generate, authored by hand."""
    metadata = package / "metadata.txt"
    if metadata.is_file():
        yield Diagnostic(
            rule="META001",
            path=metadata.relative_to(root),
            line=0,
            column=0,
            message=(
                f"`{package.name}` carries a hand-written metadata.txt; `build` and "
                "`dev` generate it from pyproject.toml"
            ),
            remediation=(
                "Delete the file. Move `version`, `description` and the author to "
                "[project], `qgisMinimumVersion` to [tool.qgis-sdk] "
                "qgis-minimum-version, and any other key to [tool.qgis-sdk.metadata] "
                "(decision-43)."
            ),
        )
    init = package / "__init__.py"
    try:
        tree = ast.parse(init.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return  # the import rules report the file itself
    bound = _class_factory_binding(tree)
    if bound is not None:
        yield Diagnostic(
            rule="ENTRY002",
            path=init.relative_to(root),
            line=bound.lineno,
            column=bound.col_offset + 1,
            message=(
                "__init__.py binds `classFactory`; `build` and `dev` bind it through "
                "`qgis_sdk.adapters.desktop.host()`"
            ),
            remediation=(
                "Delete the definition or import (and the Desktop wrapper it "
                "points at); name the class in `[tool.qgis-sdk] plugin` instead."
            ),
        )


def _class_factory_binding(tree: ast.Module) -> ast.stmt | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name == "classFactory":
                return node
        elif isinstance(node, ast.ImportFrom):
            if any((a.asname or a.name) == "classFactory" for a in node.names):
                return node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "classFactory":
                    return node
    return None


def _configured_native_modules(root: Path) -> tuple[tuple[str, ...], list[Diagnostic]]:
    relative = Path("pyproject.toml")
    manifest, malformed = read_pyproject(root / relative)
    if malformed is not None:
        return (), [
            _config_diagnostic(relative, f"pyproject.toml does not parse: {malformed}")
        ]
    parent = table(manifest, *_CONFIG_TABLE[:-1])
    if parent is None or _CONFIG_TABLE[-1] not in parent:
        return (), []
    data = parent[_CONFIG_TABLE[-1]]
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
