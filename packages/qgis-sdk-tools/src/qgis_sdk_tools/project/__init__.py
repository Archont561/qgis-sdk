"""Module project."""

from __future__ import annotations

from ._facts import (
    GENERATED_METADATA_KEYS,
    PLACEMENTS,
    BuildConfig,
    ExternalPackage,
    ProjectConfig,
    QgisSdkProjectError,
    WebConfig,
)
from ._reading import load_project, require_project

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
