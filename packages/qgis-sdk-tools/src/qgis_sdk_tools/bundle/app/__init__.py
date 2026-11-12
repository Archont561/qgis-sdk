"""Module app."""

from __future__ import annotations

from ._build_app import (
    APP_SUFFIX,
    LAUNCHER_MODULE,
    AppBuildResult,
    build_app,
    launcher_source,
    package_data,
    script_name,
)

__all__ = [
    "APP_SUFFIX",
    "LAUNCHER_MODULE",
    "AppBuildResult",
    "build_app",
    "launcher_source",
    "package_data",
    "script_name",
]
