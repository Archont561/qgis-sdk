"""Validated choices for one generated plugin project."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Final, Literal, get_args

from qgis_sdk.models import QgisSdkError

DEFAULT_VERSION: Final = "0.1.0"
DEFAULT_QGIS_MINIMUM_VERSION: Final = "4.0"
DEFAULT_AUTHOR: Final = "qgis-sdk scaffold user"
DEFAULT_EMAIL: Final = "someone@example.invalid"

_PACKAGE_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")
_DOT_VERSION = re.compile(r"[0-9]+(\.[0-9]+)*\Z")

# A plugin directory is placed on ``sys.path`` by QGIS, so a package that shares
# an import name with QGIS itself or the standard library would shadow it for
# every other plugin in the profile. ``tests`` and ``web`` are the project's own
# top-level directories, so a package of that name would collide with them.
RESERVED_PACKAGE_NAMES: Final = frozenset(
    {
        "analysis",
        "core",
        "gui",
        "processing",
        "providers",
        "qgis",
        "qgis_sdk",
        "qgis_sdk_tools",
        "tests",
        "utils",
        "web",
    }
)

WebFramework = Literal["vanilla", "react"]
WebPlacement = Literal["dialog", "dock"]
PackageManager = Literal["npm", "pnpm", "bun"]

WEB_FRAMEWORKS: Final[tuple[str, ...]] = get_args(WebFramework)
WEB_PLACEMENTS: Final[tuple[str, ...]] = get_args(WebPlacement)
PACKAGE_MANAGERS: Final[tuple[str, ...]] = get_args(PackageManager)
DEFAULT_WEB_PLACEMENT: Final = "dialog"
DEFAULT_PACKAGE_MANAGER: Final = "npm"


class QgisSdkScaffoldError(QgisSdkError):
    """The requested plugin project cannot be generated as specified."""

    code = "scaffold_invalid"


@dataclass(frozen=True, slots=True)
class WebOptions:
    """The web user interface a project carries, once every choice is valid.

    The three axes decision-18 names: the framework the page is written in,
    where QGIS shows it, and which package manager drives Vite and Vitest.
    """

    framework: WebFramework
    placement: WebPlacement = DEFAULT_WEB_PLACEMENT
    package_manager: PackageManager = DEFAULT_PACKAGE_MANAGER
    sdk_dependency: str | None = None
    """What ``web/package.json`` depends on for ``@archont561/qgis-sdk``.

    ``None`` is the exact release this scaffold is pinned to; a string is any
    npm spec - inside this repository, ``file:<path to
    packages/qgis-sdk-typescript>`` so the page runs on the workspace bridge
    (decision-41).
    """


@dataclass(frozen=True, slots=True)
class ScaffoldOptions:
    """The single validated description of what ``plan_scaffold`` emits."""

    plugin: str
    title: str
    version: str
    qgis_minimum_version: str
    author: str
    email: str
    web: WebOptions | None = None
    algorithm: bool = False
    """Whether the project starts with a Processing provider and one algorithm.

    ``--algorithm`` adds ``<plugin>/algorithms.py`` - a ``Provider`` with a
    ``buffer`` function (decision-42) - lists it on the plugin class and
    exposes it as an action, with a starter test over the SDK fakes.
    """
    ui: str | None = None
    """``"native"`` for a bound Dialog in pure PyQt (decision-55), else ``None``.

    ``--ui native`` adds ``<plugin>/ui.py`` with one ``Dialog`` subclass whose
    ``build()`` is plain PyQt, lists it in ``surfaces``, binds it to the
    Plugins menu, binds one no-input action to the toolbar that opens it,
    and adds a starter test over ``FakeUi``.
    """

    @classmethod
    def resolve(
        cls,
        plugin: str,
        *,
        title: str | None = None,
        version: str = DEFAULT_VERSION,
        qgis_minimum_version: str = DEFAULT_QGIS_MINIMUM_VERSION,
        author: str = DEFAULT_AUTHOR,
        email: str = DEFAULT_EMAIL,
        web: str | None = None,
        placement: str | None = None,
        package_manager: str | None = None,
        sdk_dependency: str | None = None,
        algorithm: bool = False,
        ui: str | None = None,
    ) -> ScaffoldOptions:
        """Check what the caller chose and derive what it left out.

        ``web`` names the framework (``vanilla`` or ``react``) or is ``None``
        for a plugin without a page; ``placement``, ``package_manager`` and
        ``sdk_dependency`` refine it and are refused on their own.
        ``algorithm`` adds the Processing starter.
        """
        return cls(
            plugin=_package_name(plugin),
            title=_title(plugin, title),
            version=_dot_version(version, "version"),
            qgis_minimum_version=_dot_version(
                qgis_minimum_version, "QGIS minimum version"
            ),
            author=_text(author, "author"),
            email=_text(email, "email"),
            web=_web(web, placement, package_manager, sdk_dependency),
            algorithm=bool(algorithm),
            ui=_ui(ui),
        )


UI_KINDS = ("native",)


def _ui(ui: str | None) -> str | None:
    if ui is None:
        return None
    if ui not in UI_KINDS:
        raise QgisSdkScaffoldError(
            f"--ui must be one of {', '.join(UI_KINDS)}, got {ui!r} "
            "(a web page is --web <framework>)"
        )
    return ui


def _web(
    framework: str | None,
    placement: str | None,
    package_manager: str | None,
    sdk_dependency: str | None = None,
) -> WebOptions | None:
    if framework is None:
        for label, value in (
            ("placement", placement),
            ("package manager", package_manager),
            ("SDK dependency", sdk_dependency),
        ):
            if value is not None:
                raise QgisSdkScaffoldError(
                    f"A {label} needs a web framework: pass --web vanilla or --web react"
                )
        return None
    return WebOptions(
        framework=_choice(framework, WEB_FRAMEWORKS, "web framework"),  # type: ignore[arg-type]
        placement=_choice(  # type: ignore[arg-type]
            DEFAULT_WEB_PLACEMENT if placement is None else placement,
            WEB_PLACEMENTS,
            "placement",
        ),
        package_manager=_choice(  # type: ignore[arg-type]
            DEFAULT_PACKAGE_MANAGER if package_manager is None else package_manager,
            PACKAGE_MANAGERS,
            "package manager",
        ),
        sdk_dependency=_dependency_spec(sdk_dependency),
    )


def _dependency_spec(value: str | None) -> str | None:
    """A version or any npm spec (``file:``, ``link:``, ``workspace:``, a URL).

    The shape is npm's to judge; here only the obvious mistakes are refused: an
    empty flag and whitespace, which no spec contains.
    """
    if value is None:
        return None
    if not value or value != value.strip() or any(ch.isspace() for ch in value):
        raise QgisSdkScaffoldError(
            "The SDK dependency must be a non-empty npm version or spec "
            "without whitespace"
        )
    return value


def _choice(value: str, choices: tuple[str, ...], label: str) -> str:
    if value not in choices:
        raise QgisSdkScaffoldError(
            f"Invalid {label} {value!r}: choose one of {', '.join(choices)}"
        )
    return value


def _package_name(name: str) -> str:
    if not isinstance(name, str) or not _PACKAGE_NAME.match(name):
        raise QgisSdkScaffoldError(
            f"Invalid plugin package name {name!r}: use a lowercase Python identifier"
        )
    if name in RESERVED_PACKAGE_NAMES or name in sys.stdlib_module_names:
        raise QgisSdkScaffoldError(
            f"Invalid plugin package name {name!r}: QGIS or Python already owns that import name"
        )
    return name


def _title(plugin: str, title: str | None) -> str:
    if title is None:
        return " ".join(word.title() for word in plugin.split("_"))
    if not title.strip():
        raise QgisSdkScaffoldError("Invalid title: use a non-empty string")
    return title.strip()


def _dot_version(value: str, label: str) -> str:
    if not _DOT_VERSION.match(value):
        raise QgisSdkScaffoldError(
            f"Invalid {label} {value!r}: use digits and dots, for example 1.2.3"
        )
    return value


def _text(value: str, label: str) -> str:
    if not value.strip():
        raise QgisSdkScaffoldError(f"Invalid {label}: use a non-empty string")
    return value.strip()
