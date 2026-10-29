"""Isolated helpers for the explicitly selected real-QGIS smoke tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_isolated_smoke(
    module: str, *, timeout: int = 180, prefix: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one native probe in a fresh process so QGIS/Qt teardown is isolated."""
    code = (
        "import importlib, json, sys; from pathlib import Path; "
        "module = importlib.import_module(sys.argv[1]); "
        "report = module.run_smoke(prefix=Path(sys.argv[2])) if len(sys.argv) > 2 else module.run_smoke(); "
        "payload = report if isinstance(report, dict) else "
        "(report.to_payload() if hasattr(report, 'to_payload') else report.to_dict()); "
        "print(json.dumps(payload))"
    )
    args = [sys.executable, "-c", code, f"smoke_support.{module}"]
    if prefix is not None:
        args.append(str(prefix))
    tests = str(Path(__file__).resolve().parents[1])
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([tests, os.environ.get("PYTHONPATH", "")]),
    }
    result = subprocess.run(
        args, env=env, capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result
