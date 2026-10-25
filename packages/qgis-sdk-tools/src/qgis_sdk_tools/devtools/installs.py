"""Find the QGIS a developer command should use, and how to run under it.

``qgis-sdk test`` and ``qgis-sdk dev`` both need the same answer: where is QGIS,
can its Python bindings be imported, and is there a Desktop binary. The
answer comes from explicit configuration first and discovery second
(decision-14): the ``--qgis-prefix`` option, then ``[tool.qgis-sdk]
qgis-prefix`` in the project's ``pyproject.toml``, then ``QGIS_PREFIX_PATH``,
then a ``qgis`` executable on ``PATH``, then the environment this interpreter
runs in. An explicit answer that does not hold is an error, never a fall
through; nothing here installs anything or guesses at ``sys.path`` beyond the
layouts QGIS itself ships.
"""

from __future__ import annotations

import os
import shutil
import sys
import tomllib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from qgis_sdk.models import QgisSdkError

__all__ = [
    "QgisInstall",
    "QgisSdkQgisNotFoundError",
    "find_qgis_install",
    "wants_headless",
]

#: Where a prefix keeps the ``qgis`` Python package, in the layouts QGIS ships:
#: conda, Linux distributions and the macOS bundle, then OSGeo4W.
BINDINGS_LAYOUTS: Final = (
    Path("share/qgis/python"),
    Path("apps/qgis/python"),
    Path("apps/qgis-ltr/python"),
)
EXECUTABLE_LAYOUTS: Final = (
    Path("bin/qgis"),
    Path("bin/qgis-bin.exe"),
    Path("bin/qgis-ltr-bin.exe"),
    Path("bin/qgis.exe"),
)
PYTHON_LAYOUTS: Final = (
    Path("bin/python"),
    Path("bin/python3"),
    Path("python.exe"),
)

HEADLESS_PLATFORM: Final = "offscreen"
#: QGIS Desktop refuses to start when ``DISPLAY`` is unset, whatever the Qt
#: platform; the offscreen plugin never connects to it, so any value serves.
PLACEHOLDER_DISPLAY: Final = ":99"
#: What an offscreen Chromium needs to come up without a GPU or a display; the
#: flags the SDK's own headless WebEngine harness qualified (TASK-23).
HEADLESS_CHROMIUM_FLAGS: Final = (
    "--no-sandbox --disable-gpu --disable-dev-shm-usage --single-process"
)

Which = Callable[[str, str | None], str | None]
"""``shutil.which``'s shape: a command name and the ``PATH`` to search."""


class QgisSdkQgisNotFoundError(QgisSdkError):
    """No usable QGIS install: the message says where it looked and what to set."""


@dataclass(frozen=True, slots=True)
class QgisInstall:
    """One QGIS install, resolved: what exists there and where the answer came from."""

    prefix: Path
    bindings: Path
    executable: Path | None
    python: Path | None
    source: str
    conda: bool

    def environment(
        self,
        base: Mapping[str, str],
        *,
        extra_paths: Iterable[Path] = (),
        headless: bool = False,
        desktop: bool = False,
    ) -> dict[str, str]:
        """The environment a process needs to import PyQGIS from this install.

        The bindings and ``extra_paths`` go first on ``PYTHONPATH``, ahead of
        whatever the caller already had. ``headless`` selects the offscreen
        Qt platform and the placeholder display unless the caller chose a
        platform. ``desktop`` adds what only the Desktop *binary* needs: a
        conda prefix carries its build-time ``PYTHONHOME`` in the embedded
        interpreter, so a relocated install starts and then cannot import
        ``sys`` until the live prefix is pinned.
        """
        env = dict(base)
        paths = [str(self.bindings), *(str(path) for path in extra_paths)]
        existing = env.get("PYTHONPATH")
        if existing:
            paths.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(paths)
        env["QGIS_PREFIX_PATH"] = str(self.prefix)
        proj = self.prefix / "share" / "proj"
        if proj.is_dir():
            env.setdefault("PROJ_LIB", str(proj))
        if headless:
            env.setdefault("QT_QPA_PLATFORM", HEADLESS_PLATFORM)
            env.setdefault("DISPLAY", PLACEHOLDER_DISPLAY)
            env.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", HEADLESS_CHROMIUM_FLAGS)
        if desktop and self.conda:
            env["PYTHONHOME"] = str(self.prefix)
        return env


def sdk_import_paths() -> tuple[Path, ...]:
    """Where ``qgis_sdk`` and ``qgis_sdk_tools`` import from, for a QGIS process.

    The CLI may run under any interpreter; QGIS runs its own. Putting the
    SDK's own locations on that process's ``PYTHONPATH`` is what lets the
    dev bootstrap and the pytest plugin import there. A source checkout and
    an installed distribution both resolve through the packages' files.
    """
    import qgis_sdk

    import qgis_sdk_tools

    paths: dict[Path, None] = {}
    for package in (qgis_sdk, qgis_sdk_tools):
        location = getattr(package, "__file__", None)
        if location:
            paths[Path(location).resolve().parent.parent] = None
    return tuple(paths)


def wants_headless(env: Mapping[str, str], *, platform: str = sys.platform) -> bool:
    """Whether there is no display to show a window on, so Qt must go offscreen.

    An explicit ``QT_QPA_PLATFORM`` decides on every platform. Without one,
    Linux is headless when neither ``DISPLAY`` nor ``WAYLAND_DISPLAY`` is set;
    macOS and Windows always have a window system.
    """
    chosen = env.get("QT_QPA_PLATFORM")
    if chosen:
        return chosen == HEADLESS_PLATFORM
    if not platform.startswith("linux"):
        return False
    return not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def find_qgis_install(
    env: Mapping[str, str],
    *,
    prefix: Path | None = None,
    project: Path | None = None,
    which: Which | None = None,
    sys_prefix: Path | None = None,
) -> QgisInstall:
    """Resolve the QGIS install the command should use, or say why there is none.

    ``prefix`` is the command-line option; ``project`` is where to read
    ``pyproject.toml``; ``PATH`` is read from ``env``, not the process;
    ``which`` and ``sys_prefix`` exist so a test can own the machine. An explicitly named prefix (option, configuration,
    ``QGIS_PREFIX_PATH``) must hold the bindings or the call fails right
    there: silently moving on would run the tests against a different QGIS
    than the one asked for.
    """
    looked: list[str] = []
    which = _which if which is None else which
    for candidate, source in _explicit_candidates(env, prefix=prefix, project=project):
        install = _resolve(candidate, source)
        if install is None:
            raise QgisSdkQgisNotFoundError(
                f"{source} names {candidate}, which has no QGIS Python bindings "
                f"(none of {_layouts(BINDINGS_LAYOUTS)} under it). Point it at "
                "the QGIS install prefix, or drop it and pass --qgis-prefix."
            )
        return install

    executable = which("qgis", env.get("PATH"))
    if executable is not None:
        found = Path(executable).resolve()
        install = _resolve(found.parent.parent, f"qgis on PATH ({executable})")
        if install is not None:
            return install
        looked.append(f"qgis on PATH ({executable}) has no bindings next to it")
    else:
        looked.append("no qgis executable on PATH")

    current = Path(sys.prefix if sys_prefix is None else sys_prefix)
    install = _resolve(current, "the current Python environment")
    if install is not None:
        return install
    looked.append(f"the current Python environment ({current}) has no bindings")

    tried = "\n".join(f"  - {entry}" for entry in looked)
    raise QgisSdkQgisNotFoundError(
        "no QGIS install found:\n"
        "  - QGIS_PREFIX_PATH is not set\n"
        f"{tried}\n"
        "Pass --qgis-prefix <prefix>, set `[tool.qgis-sdk] qgis-prefix` in "
        "pyproject.toml, or export QGIS_PREFIX_PATH; the prefix must contain "
        f"{_layouts(BINDINGS_LAYOUTS)}."
    )


def _which(name: str, path: str | None) -> str | None:
    return shutil.which(name, path=path)


def _explicit_candidates(
    env: Mapping[str, str], *, prefix: Path | None, project: Path | None
) -> Iterable[tuple[Path, str]]:
    if prefix is not None:
        yield Path(prefix), "the --qgis-prefix option"
    if project is not None:
        configured = _configured_prefix(Path(project))
        if configured is not None:
            yield configured, "pyproject.toml [tool.qgis-sdk] qgis-prefix"
    named = env.get("QGIS_PREFIX_PATH")
    if named:
        yield Path(named), "QGIS_PREFIX_PATH"


def _configured_prefix(project: Path) -> Path | None:
    pyproject = project / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        data: object = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise QgisSdkQgisNotFoundError(
            f"{pyproject} is not valid TOML: {error}"
        ) from error
    tool = data.get("tool", {}) if isinstance(data, dict) else {}
    section = tool.get("qgis-sdk", {}) if isinstance(tool, dict) else {}
    value = section.get("qgis-prefix") if isinstance(section, dict) else None
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise QgisSdkQgisNotFoundError(
            f"{pyproject}: [tool.qgis-sdk] qgis-prefix must be a path string"
        )
    return project / Path(value).expanduser()


def _resolve(prefix: Path, source: str) -> QgisInstall | None:
    prefix = prefix.expanduser().resolve()
    bindings = _first_existing(prefix, BINDINGS_LAYOUTS, directory=True)
    if bindings is None or not (bindings / "qgis" / "__init__.py").is_file():
        return None
    return QgisInstall(
        prefix=prefix,
        bindings=bindings,
        executable=_first_existing(prefix, EXECUTABLE_LAYOUTS),
        python=_first_existing(prefix, PYTHON_LAYOUTS),
        source=source,
        conda=(prefix / "conda-meta").is_dir(),
    )


def _first_existing(
    prefix: Path, layouts: Iterable[Path], *, directory: bool = False
) -> Path | None:
    for layout in layouts:
        candidate = prefix / layout
        if candidate.is_dir() if directory else candidate.is_file():
            return candidate
    return None


def _layouts(layouts: Iterable[Path]) -> str:
    return ", ".join(layout.as_posix() for layout in layouts)
