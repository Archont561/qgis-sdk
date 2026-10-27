"""The entry points: generate, check and write a plugin, schema or host module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qgis_sdk_tools.generate._contract import HOST_SURFACE, _as_mapping
from qgis_sdk_tools.generate._generator import _Generator


def generate_typescript(description: Any) -> str:
    """Render a plugin's module for ``description``."""
    described = _as_mapping(description)
    generator = _Generator(described)
    return generator.render()


DEFAULT_SDK_IMPORT = "@archont561/qgis-sdk"
"""Where a generated schema module imports ``defineBridgeSchema`` from."""

SCHEMA_SUFFIX = ".schema.ts"
"""The file name suffix that selects the schema module over the legacy client."""

DEFAULT_SCHEMA_PATH = Path("web/src/bridge.schema.ts")
"""Where ``qgis-sdk bridge generate`` writes when ``--out`` is not given."""


def generate_schema_typescript(
    description: Any, *, sdk_import: str = DEFAULT_SDK_IMPORT
) -> str:
    """Render a plugin's ``bridge.schema.ts`` for ``description`` (decision-44).

    The module carries the declaration and its types and nothing else: no
    validators, no client, one import of ``defineBridgeSchema`` from
    ``sdk_import``. ``QgisSdk.fromBridgeSchema`` validates against the
    declaration at run time, so a page gets both the types and the checks
    from one file that is only ever regenerated.
    """
    described = _as_mapping(description)
    return _Generator(described).render_schema(sdk_import=sdk_import)


def generate_host_typescript(description: Any = None) -> str:
    """Render the curated host module shipped inside the npm package."""
    if description is None:
        from qgis_sdk.bridge.host import host_description

        description = host_description()
    described = _as_mapping(description)
    return _Generator(described, surface=HOST_SURFACE).render()


def check_generated(
    path: Path, description: Any, *, generate: Any = generate_typescript
) -> str | None:
    """Return a message when ``path`` is not what ``description`` generates."""
    expected = generate(description)
    if not path.exists():
        return f"{path} does not exist; run the generator to create it"
    if path.read_text(encoding="utf-8") != expected:
        return (
            f"{path} is out of date; regenerate it from the plugin declarations "
            "and commit the result"
        )
    return None


def write_generated(
    path: Path, description: Any, *, generate: Any = generate_typescript
) -> bool:
    """Write the module, returning whether anything changed."""
    rendered = generate(description)
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return True
