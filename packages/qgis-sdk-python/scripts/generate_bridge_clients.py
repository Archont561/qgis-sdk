#!/usr/bin/env python3
"""Write the checked-in TypeScript the bridge package compiles, runs and ships.

Two artifacts, one command:

* the **plugin client** the tests exercise - generated from the sample plugin in
  ``tests/contract_sample/bridge_plugin.py``, checked in under ``tests`` because a
  real plugin generates its own into its own frontend;
* the **host client** - generated from the curated manifest in
  ``qgis_sdk.bridge.host`` and checked in under ``src/generated`` because it ships
  inside ``@archont561/qgis-sdk``, versioned with it (decision-27).

Both exist to keep two promises honest (TASK-17): the generator is deterministic,
so CI can regenerate these files and fail when a checked-in copy differs; and the
output is a real client, so tests import it, call it against a scripted transport
and type-check it with the same options as ``src``.

Regenerate with:

    python packages/qgis-sdk-python/scripts/generate_bridge_clients.py

Add ``--check`` to report drift without writing, which is what CI does.
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
HOST_CLIENT_PATH = BRIDGE_PACKAGE / "src" / "generated" / "host.ts"

sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from contract_sample.bridge_plugin import SitesPlugin
from qgis_sdk.bridge.host import host_description
from qgis_sdk.declarations import describe_plugin
from qgis_sdk_tools.generate import (
    check_generated,
    generate_host_typescript,
    generate_typescript,
    write_generated,
)


def artifacts() -> list[tuple[Path, dict, object]]:
    """Return each artifact with the description and renderer that produce it."""
    return [
        (
            PLUGIN_CLIENT_PATH,
            describe_plugin(SitesPlugin).to_dict(),
            generate_typescript,
        ),
        (HOST_CLIENT_PATH, host_description(), generate_host_typescript),
    ]


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    check = "--check" in arguments
    status = 0
    for path, description, generator in artifacts():
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
    return status


if __name__ == "__main__":
    raise SystemExit(main())
