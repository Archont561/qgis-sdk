#!/usr/bin/env python3
"""Write the checked-in TypeScript client the bridge tests compile and run.

The artifact is one generated module for the sample plugin in
``tests/contract_sample/bridge_plugin.py``. It exists to keep two promises
honest (TASK-17):

* the generator is deterministic, so CI can regenerate the file and fail when
  the checked-in copy differs;
* the output really is a usable client, so a test imports it, calls it against a
  scripted transport and type-checks it with the same options as ``src``.

Regenerate with:

    python packages/qgis-sdk/scripts/generate_bridge_client.py

Add ``--check`` to report drift without writing, which is what CI runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
CLIENT_PATH = (
    REPOSITORY_ROOT
    / "packages"
    / "qgis-sdk-bridge"
    / "tests"
    / "contracts"
    / "generated"
    / "clients"
    / "sites.ts"
)

sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from contract_sample.bridge_plugin import SitesPlugin
from qgis_sdk.bridge.generate import check_generated, write_generated
from qgis_sdk.declarations import describe_plugin


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    description = describe_plugin(SitesPlugin).to_dict()
    if "--check" in arguments:
        message = check_generated(CLIENT_PATH, description)
        if message is not None:
            print(message, file=sys.stderr)
            return 1
        print(f"{CLIENT_PATH} is up to date")
        return 0
    changed = write_generated(CLIENT_PATH, description)
    print(f"{'wrote' if changed else 'unchanged'} {CLIENT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
