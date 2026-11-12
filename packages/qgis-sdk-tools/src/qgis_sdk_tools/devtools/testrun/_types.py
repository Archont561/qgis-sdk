"""The test runner's vocabulary: the error, the plan, the facts."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from qgis_sdk.models import QgisSdkError

from ..installs import QgisInstall

__all__ = ["QgisSdkTestRunError", "TestPlan"]


class QgisSdkTestRunError(QgisSdkError):
    """The run cannot start: wrong target, no project, or the runtime is missing."""


@dataclass(frozen=True, slots=True)
class TestPlan:
    """What to run: the process, where, with which environment."""

    target: str
    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    notes: tuple[str, ...]
    workspace: Path | None = None


@dataclass(frozen=True, slots=True)
class TestFacts:
    """Everything one target's planner needs, resolved once."""

    root: Path
    args: Sequence[str]
    env: Mapping[str, str]
    install: QgisInstall | None
    headless: bool
    workspace: Path | None


class PlanOptions1(TypedDict, total=False):
    env: Mapping[str, str]
    install: QgisInstall | None
    workspace: Path | None
    python: str
    platform: str


@dataclass(frozen=True, slots=True)
class PlanValues1:
    env: Mapping[str, str]
    install: QgisInstall | None = None
    workspace: Path | None = None
    python: str = sys.executable
    platform: str = sys.platform
