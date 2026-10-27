#!/usr/bin/env python3
"""Regenerate the Processing snapshot the runtime ships (decision-64).

``qgis_sdk/processing/catalogue.json`` and the provider modules next to it
(``native.py``, ``qgis.py``, ``gdal.py``, ``p3d.py``, ``pdal.py``) are
generated from the QGIS the Pixi environment pins, by the same reader and
emitters ``qgis-sdk processing generate`` uses in a project. Nothing there is
edited by hand; CI runs this with ``--check`` and fails on drift.

Regenerate with:

    pixi run -e default python packages/qgis-sdk-python/scripts/generate_processing_snapshot.py

Add ``--check`` to report drift without writing. ``--qgis-prefix`` names a
QGIS install other than the current environment's.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
RUNTIME_SRC = PROJECT_ROOT.parent / "qgis-sdk-runtime" / "src"
SNAPSHOT_DIR = RUNTIME_SRC / "qgis_sdk" / "processing"

sys.path.insert(0, str(PROJECT_ROOT.parent / "qgis-sdk-tools" / "src"))
sys.path.insert(0, str(RUNTIME_SRC))

from qgis_sdk.processing.snapshot import CORE_PROVIDERS
from qgis_sdk_tools.devtools import find_qgis_install
from qgis_sdk_tools.processing import (
    check_files,
    read_host_catalogue,
    render_files,
    write_files,
)


def _run(argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None) -> int:
    return subprocess.run(list(argv), cwd=cwd, env=env, check=False).returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="report drift, write nothing"
    )
    parser.add_argument("--qgis-prefix", type=Path, default=None)
    args = parser.parse_args(argv)
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    install = find_qgis_install(env, prefix=args.qgis_prefix)
    print(f"reading the Processing registry of {install.prefix} ({install.source})")
    catalogue = read_host_catalogue(
        install, env, _run, cwd=REPOSITORY_ROOT, providers=CORE_PROVIDERS
    )
    present = tuple(
        p for p in CORE_PROVIDERS if any(q.id == p for q in catalogue.providers)
    )
    if present != CORE_PROVIDERS:
        missing = sorted(set(CORE_PROVIDERS) - set(present))
        print(f"error: this QGIS lacks the core providers {', '.join(missing)}")
        return 2
    generated = render_files(
        catalogue, out=SNAPSHOT_DIR, web_out=None, providers=CORE_PROVIDERS, init=False
    )
    if args.check:
        messages = check_files(generated)
        for message in messages:
            print(message)
        if messages:
            print(
                "run `pixi run -e default python "
                "packages/qgis-sdk-python/scripts/generate_processing_snapshot.py`"
            )
            return 1
        print(
            f"{len(generated.files)} snapshot files are up to date ({catalogue.qgis_version})"
        )
        return 0
    changed = write_files(generated)
    for path in changed:
        print(f"wrote {path.relative_to(REPOSITORY_ROOT)}")
    print(
        f"{len(catalogue.algorithms)} algorithms from {len(catalogue.providers)} providers "
        f"({catalogue.qgis_version}); {len(changed)} of {len(generated.files)} files changed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
