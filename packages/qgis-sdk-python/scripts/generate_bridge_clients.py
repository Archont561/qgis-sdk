#!/usr/bin/env python3
"""Write the checked-in TypeScript the bridge package compiles, runs and ships.

Three artifacts, one command:

* the **plugin client** the tests exercise - generated from the sample plugin in
  ``tests/contract_sample/bridge_plugin.py``, checked in under ``tests`` because a
  real plugin generates its own into its own frontend;
* the **plugin schema module** (``bridge.schema.ts``, decision-44) from the same
  sample, importing ``defineBridgeSchema`` from the package source so the tests
  can build a ``QgisSdk`` on it without an installed copy;
* the **host client** - generated from the curated manifest in
  ``qgis_sdk.bridge.host`` and checked in under ``src/generated`` because it ships
  inside ``@archont561/qgis-sdk``, versioned with it (decision-27).

Both exist to keep two promises honest (TASK-17): the generator is deterministic,
so CI can regenerate these files and fail when a checked-in copy differs; and the
output is a real client, so tests import it, call it against a scripted transport
and type-check it with the same options as ``src``.

Regenerate with:

    python packages/qgis-sdk-python/scripts/generate_bridge_clients.py

Both modes report orphaned outputs without deleting them. An orphan is a ``.ts``
file under the sample-client or host output directory whose first two lines
identify this generator's sample-plugin or curated-host source, but whose path
is absent from ``artifacts()``. This includes untracked files, but deliberately
excludes files with another source header, files without the generated header,
and files outside those directories. When retiring or renaming an output,
remove the old file explicitly; restore its entry instead if it is still needed.

Add ``--check`` to report byte drift and orphans without writing. CI instead
runs the normal regeneration and checks Git status across the TypeScript package,
then checks the reference plugin's schema separately.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
BRIDGE_PACKAGE = REPOSITORY_ROOT / "packages" / "qgis-sdk-typescript"

PLUGIN_CLIENT_PATH = (
    BRIDGE_PACKAGE / "tests" / "contracts" / "generated" / "clients" / "sites.ts"
)
PLUGIN_SCHEMA_PATH = PLUGIN_CLIENT_PATH.with_name("sites.schema.ts")
#: The package source, relative to ``PLUGIN_SCHEMA_PATH``; the tests compile the
#: schema module against ``src`` rather than against a published build.
PLUGIN_SCHEMA_SDK_IMPORT = "../../../../src/index"
HOST_CLIENT_PATH = BRIDGE_PACKAGE / "src" / "generated" / "host.ts"

sys.path.insert(0, str(PROJECT_ROOT.parent / "qgis-sdk-tools" / "src"))
sys.path.insert(0, str(PROJECT_ROOT.parent / "qgis-sdk-runtime" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from contract_sample.bridge_plugin import app as sites_app
from qgis_sdk import describe
from qgis_sdk.bridge.host import host_description
from qgis_sdk_tools.generate import (
    GENERATED_MARKER,
    check_generated,
    generate_host_typescript,
    generate_schema_typescript,
    generate_typescript,
    write_generated,
)


def generate_sample_schema(description: dict) -> str:
    """Render the sample schema module against the package source."""
    return generate_schema_typescript(description, sdk_import=PLUGIN_SCHEMA_SDK_IMPORT)


def artifacts() -> list[tuple[Path, dict, object]]:
    """Return each artifact with the description and renderer that produce it."""
    return [
        (
            PLUGIN_CLIENT_PATH,
            describe(sites_app).to_dict(),
            generate_typescript,
        ),
        (
            PLUGIN_SCHEMA_PATH,
            describe(sites_app).to_dict(),
            generate_sample_schema,
        ),
        (HOST_CLIENT_PATH, host_description(), generate_host_typescript),
    ]


def orphaned_artifacts(expected: set[Path]) -> list[Path]:
    """Find retired bridge outputs by their generator and source headers.

    Search only the two bridge output directories, and only files carrying the
    specific sample-plugin or host header. This leaves other generators' files
    and hand-written files alone, even when they live in the same directory.
    """
    roots = (
        (
            BRIDGE_PACKAGE / "tests" / "contracts" / "generated" / "clients",
            "// Source: the declarations of org.example.sites.",
        ),
        (
            BRIDGE_PACKAGE / "src" / "generated",
            "// Source: the curated host manifest in qgis_sdk.bridge.host.",
        ),
    )
    orphans = []
    for root, source in roots:
        header = [GENERATED_MARKER.encode(), source.encode()]
        for path in root.rglob("*.ts"):
            if path in expected or not path.is_file():
                continue
            with path.open("rb") as file:
                first_lines = [file.readline().rstrip(b"\r\n") for _ in range(2)]
            if first_lines == header:
                orphans.append(path)
    return sorted(orphans)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    check = "--check" in arguments
    outputs = artifacts()
    status = 0
    for path, description, generator in outputs:
        if check:
            message = check_generated(path, description, generate=generator)
            if message is not None:
                print(message, file=sys.stderr)
                status = 1
            else:
                print(f"{path} is up to date")
            continue
        changed = write_generated(path, description, generate=generator)
        print(f"{'wrote' if changed else 'unchanged'} {path}")
    for path in orphaned_artifacts({path for path, _, _ in outputs}):
        print(
            f"orphaned generated bridge artifact: {path}; "
            "remove it if it is no longer generated, or restore it to artifacts()",
            file=sys.stderr,
        )
        status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
