#!/usr/bin/env python3
"""Compute the commit range for conventional-commit checking.

Extracted from ci.yml's checks job so the same range selection runs in CI
and can be validated locally:

    python -m automation.commits

Reads BASE_SHA, DEFAULT_BRANCH, and GITHUB_SHA from the environment (all
set by the workflow step) and writes CONVCO_REV or CONVCO_MAX_COUNT to
$GITHUB_ENV so the following `check-commits` step inherits them.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_main_p1(_s):
    _s.base_sha = os.environ.get("BASE_SHA", "").strip()
    _s.default_branch = os.environ.get("DEFAULT_BRANCH", "main").strip()
    _s.github_sha = os.environ.get("GITHUB_SHA", "").strip()
    _s.env_path = os.environ.get("GITHUB_ENV", "")

    def emit(name: str, value: str) -> None:
        print(f"{name}={value}")
        if _s.env_path:
            with Path(_s.env_path).open("a", encoding="utf-8") as handle:
                handle.write(f"{name}={value}\n")

    _s.emit = emit


def _cc_main_p2(_s):

    if _s.base_sha and _s.base_sha.lstrip("0") != "":
        print(f"::notice::convco range: {_s.base_sha}..{_s.github_sha}")
        _s.emit("CONVCO_REV", f"{_s.base_sha}..{_s.github_sha}")
        return _CcReturn(0)


def _cc_main_p3(_s):
    try:
        _s.base = subprocess.check_output(
            ["git", "merge-base", _s.github_sha, f"origin/{_s.default_branch}"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        _s.base = ""
    if _s.base == _s.github_sha or not _s.base:
        print("::notice::convco: single-commit check")
        _s.emit("CONVCO_MAX_COUNT", "1")
        return _CcReturn(0)


def _cc_main_p4(_s):
    print(f"::notice::convco range: {_s.base}..{_s.github_sha}")
    _s.emit("CONVCO_REV", f"{_s.base}..{_s.github_sha}")
    return _CcReturn(0)


# A real PR base or non-zero before SHA: review only new commits.
# New-branch pushes have an all-zero before SHA; manual runs have none.
# Fall back to the merge-base with the default branch.
# Nothing to compare against: check only this commit.
def main() -> int:
    _s = _CcState()
    for _p in (_cc_main_p1, _cc_main_p2, _cc_main_p3, _cc_main_p4):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


if __name__ == "__main__":
    sys.exit(main())
