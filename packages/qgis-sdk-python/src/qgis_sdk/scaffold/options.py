"""Validated choices for one generated plugin project."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Final

from qgis_sdk.models import QgisSdkError

DEFAULT_VERSION: Final = "0.1.0"
DEFAULT_QGIS_MINIMUM_VERSION: Final = "4.0"
DEFAULT_AUTHOR: Final = "qgis-sdk scaffold user"
DEFAULT_EMAIL: Final = "someone@example.invalid"

_PACKAGE_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")
_DOT_VERSION = re.compile(r"[0-9]+(\.[0-9]+)*\Z")

# A plugin directory is placed on ``sys.path`` by QGIS, so a package that shares
# an import name with QGIS itself or the standard library would shadow it for
# every other plugin in the profile.
RESERVED_PACKAGE_NAMES: Final = frozenset(
    {"analysis", "core", "gui", "processing", "providers", "qgis", "qgis_sdk", "utils"}
)


class QgisSdkScaffoldError(QgisSdkError):
    """The requested plugin project cannot be generated as specified."""

    code = "scaffold_invalid"


@dataclass(frozen=True, slots=True)
class ScaffoldOptions:
    """The single validated description of what ``plan_scaffold`` emits."""

    plugin: str
    title: str
    version: str
    qgis_minimum_version: str
    author: str
    email: str

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
    ) -> ScaffoldOptions:
        """Check what the caller chose and derive what it left out."""
        return cls(
            plugin=_package_name(plugin),
            title=_title(plugin, title),
            version=_dot_version(version, "version"),
            qgis_minimum_version=_dot_version(
                qgis_minimum_version, "QGIS minimum version"
            ),
            author=_text(author, "author"),
            email=_text(email, "email"),
        )


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
