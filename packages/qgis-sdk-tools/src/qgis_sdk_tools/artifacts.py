"""The QGIS host artifacts ``build`` and ``dev`` derive from a clean project.

decision-43: the author's package carries no ``metadata.txt`` and no
``classFactory``. This module renders both from :class:`ProjectConfig` plus
the two facts only the application knows - its ``title`` and whether it
lists ``providers`` - so the two commands agree byte for byte:

* :func:`render_metadata` - the ``metadata.txt`` QGIS reads;
* :func:`class_factory_source` - the lines ``build`` appends to the staged
  ``<plugin>/__init__.py``: ``classFactory = host("pkg.module:app", ...)``;
* :func:`write_dev_host` - the package ``dev`` stages under
  ``.qgis-sdk/dev/host/<plugin>/`` so QGIS loads the sources in place.

:func:`introspect_plugin` imports the application once, isolated, to read
those facts; ``check`` never calls it (decision-8).
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from qgis_sdk.adapters.desktop import QgisSdkHostError, resolve_plugin_spec
from qgis_sdk.declarations import QgisSdkDeclarationError, describe
from qgis_sdk.models import QgisSdkError

from .project import ProjectConfig

__all__ = [
    "DEV_HOST_DIRECTORY",
    "METADATA_FILE",
    "PluginFacts",
    "QgisSdkArtifactError",
    "class_factory_source",
    "introspect_plugin",
    "render_dev_host_init",
    "render_metadata",
    "write_dev_host",
]

METADATA_FILE: Final = "metadata.txt"
#: Under ``<root>/.qgis-sdk``: the ``QGIS_PLUGINPATH`` entry ``dev`` hands QGIS.
DEV_HOST_DIRECTORY: Final = Path("dev") / "host"
RUNTIME_PACKAGE: Final = "qgis_sdk"
LF: Final = "\n"


class QgisSdkArtifactError(QgisSdkError):
    """The application cannot be read: the import or the declaration failed."""

    code = "artifact_invalid"


@dataclass(frozen=True, slots=True)
class PluginFacts:
    """What only the application says and ``metadata.txt`` needs."""

    id: str
    title: str
    has_providers: bool


def introspect_plugin(config: ProjectConfig) -> PluginFacts:
    """Import the application ``config.spec`` names and read its title and providers.

    The project root goes first on ``sys.path`` for the import and leaves
    again; the package's modules are evicted from ``sys.modules`` before and
    after, so two projects sharing a package name never see each other and
    the caller's own modules of that name come back untouched.
    """
    with _isolated(config.root, config.plugin):
        try:
            app = resolve_plugin_spec(config.spec)
            description = describe(app)
        except (QgisSdkHostError, QgisSdkDeclarationError) as error:
            raise QgisSdkArtifactError(
                f"[tool.qgis-sdk] plugin = {config.spec!r}: {error}"
            ) from error
        except Exception as error:
            raise QgisSdkArtifactError(
                f"importing {config.module!r} failed: {type(error).__name__}: {error}"
            ) from error
        providers = app.providers
        try:
            has_providers = len(tuple(providers)) > 0
        except TypeError as error:
            raise QgisSdkArtifactError(
                f"{config.class_name}.providers must be a list of providers"
            ) from error
    return PluginFacts(
        id=description.id, title=description.title, has_providers=has_providers
    )


@contextmanager
def _isolated(root: Path, package: str) -> Iterator[None]:
    def owned(name: str) -> bool:
        return name == package or name.startswith(package + ".")

    saved = {name: module for name, module in sys.modules.items() if owned(name)}
    for name in saved:
        del sys.modules[name]
    entry = str(root)
    sys.path.insert(0, entry)
    importlib.invalidate_caches()
    try:
        yield
    finally:
        try:
            sys.path.remove(entry)
        except ValueError:  # pragma: no cover - author code edited sys.path
            pass
        for name in [name for name in sys.modules if owned(name)]:
            del sys.modules[name]
        sys.modules.update(saved)


def render_metadata(config: ProjectConfig, facts: PluginFacts) -> str:
    """The ``metadata.txt`` for the plugin: every key QGIS requires, then extras.

    ``name`` is the application title, ``about`` the passthrough value or the
    description, ``hasProcessingProvider`` follows ``providers``. Passthrough
    keys follow in the order written; a multi-line value continues indented,
    the way QGIS's parser reads it.
    """
    extra = dict(config.metadata)
    about = extra.pop("about", config.description)
    fields = [
        ("name", facts.title),
        ("description", config.description),
        ("about", about),
        ("version", config.version),
        ("qgisMinimumVersion", config.qgis_minimum_version),
        ("author", config.author),
        ("email", config.email),
        ("experimental", "True" if config.experimental else "False"),
        ("hasProcessingProvider", "yes" if facts.has_providers else "no"),
        *extra.items(),
    ]
    lines = ["[general]"]
    for key, value in fields:
        lines.append(f"{key}={_continued(value)}")
    return LF.join(lines) + LF


def _continued(value: str) -> str:
    return value.strip().replace("\r\n", LF).replace(LF, LF + "    ")


def class_factory_source(
    config: ProjectConfig, *, runtime_package: str = RUNTIME_PACKAGE, by: str
) -> str:
    """The ``classFactory`` binding for ``<plugin>/__init__.py``.

    ``runtime_package`` is where the runtime imports from: ``qgis_sdk`` for
    ``dev``, the vendored path for ``build``. ``by`` names the generator in
    the comment.
    """
    arguments = [repr(config.spec)]
    if config.web is not None:
        arguments.append(f"placement={config.web.placement!r}")
        if config.web.grants:
            arguments.append(f"grants={config.web.grants!r}")
    return (
        f"# Generated by `{by}`; the source has no classFactory (decision-43).{LF}"
        f"from {runtime_package}.adapters.desktop import host{LF}{LF}"
        f"classFactory = host({', '.join(arguments)}){LF}"
    )


def render_dev_host_init(config: ProjectConfig) -> str:
    """The ``__init__.py`` of the dev host package: the sources in place, plus the binding.

    The module extends its own ``__path__`` with the source package, so
    ``<plugin>.plugin`` imports from the project, runs the author's
    ``__init__.py`` in its own namespace (relative imports included) and
    binds ``classFactory``. QGIS sees one plugin directory; the author's
    tree is never copied.
    """
    source = config.package.resolve().as_posix()
    return (
        f'"""Generated by `qgis-sdk dev`: {config.plugin} served from its sources."""{LF}'
        f"{LF}"
        f"from pathlib import Path as _Path{LF}"
        f"{LF}"
        f"_source = _Path({source!r}){LF}"
        f"__path__.append(str(_source))  # modules resolve from the project{LF}"
        f'_init = _source / "__init__.py"{LF}'
        f"if _init.is_file():{LF}"
        f'    exec(compile(_init.read_text(encoding="utf-8"), str(_init), "exec"), globals()){LF}'
        f"del _init{LF}" + class_factory_source(config, by="qgis-sdk dev")
    )


def write_dev_host(config: ProjectConfig, facts: PluginFacts, *, state: Path) -> Path:
    """Write ``<state>/dev/host/<plugin>/{__init__.py,metadata.txt}``; return the host dir.

    Rewritten on every ``dev`` run, so a changed ``pyproject.toml`` lands
    on the next start. The returned directory is what goes on
    ``QGIS_PLUGINPATH``.
    """
    host = Path(state) / DEV_HOST_DIRECTORY
    package = host / config.plugin
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(
        render_dev_host_init(config), encoding="utf-8", newline=LF
    )
    (package / METADATA_FILE).write_text(
        render_metadata(config, facts), encoding="utf-8", newline=LF
    )
    return host
