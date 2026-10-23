#!/usr/bin/env python3
"""Compute the commit range for conventional-commit checking.

Extracted from ci.yml's checks job so the same range selection runs in CI
and can be validated locally:

    python scripts/compute_commit_base.py

Reads BASE_SHA, DEFAULT_BRANCH, and GITHUB_SHA from the environment (all
set by the workflow step) and writes CONVCO_REV or CONVCO_MAX_COUNT to
$GITHUB_ENV so the following `check-commits` step inherits them.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    base_sha = os.environ.get("BASE_SHA", "").strip()
    default_branch = os.environ.get("DEFAULT_BRANCH", "main").strip()
    github_sha = os.environ.get("GITHUB_SHA", "").strip()

    env_path = os.environ.get("GITHUB_ENV", "")

    def emit(name: str, value: str) -> None:
        print(f"{name}={value}")
        if env_path:
            with open(env_path, "a", encoding="utf-8") as handle:
                handle.write(f"{name}={value}\n")

    if base_sha and base_sha.lstrip("0") != "":
        # A real PR base or non-zero before SHA: review only new commits.
        print(f"::notice::convco range: {base_sha}..{github_sha}")
        emit("CONVCO_REV", f"{base_sha}..{github_sha}")
        return 0

    # New-branch pushes have an all-zero before SHA; manual runs have none.
    # Fall back to the merge-base with the default branch.
    try:
        base = subprocess.check_output(
            ["git", "merge-base", github_sha, f"origin/{default_branch}"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        base = ""

    if base == github_sha or not base:
        # Nothing to compare against: check only this commit.
        print("::notice::convco: single-commit check")
        emit("CONVCO_MAX_COUNT", "1")
        return 0

    print(f"::notice::convco range: {base}..{github_sha}")
    emit("CONVCO_REV", f"{base}..{github_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
