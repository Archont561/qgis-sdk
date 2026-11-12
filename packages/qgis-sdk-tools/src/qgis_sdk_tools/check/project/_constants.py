"""The constants the project check shares between its submodules."""

from __future__ import annotations

__all__ = ["EXCLUDED_DIRECTORIES", "REQUIRED_METADATA_KEYS"]

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
