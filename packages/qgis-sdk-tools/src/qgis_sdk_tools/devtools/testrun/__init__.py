"""The plan behind ``qgis-sdk test``: one target, one process, pytest's own verdict.

The command is a thin runner (decision-8). It decides *where* pytest runs -
this interpreter, the QGIS install's interpreter, or inside the QGIS Desktop
binary - and *what* it selects, then forwards the user's arguments, output and
exit code untouched. Nothing is installed; a target whose runtime is missing
raises before anything runs, so a required gate never passes by skipping.

Targets:

``pure``
    this interpreter; tests not marked ``qgis``/``desktop``; native imports
    refused by the plugin's guard;
``qgis``
    the install's interpreter with PyQGIS importable; tests marked ``qgis``;
    ``qgis_app`` is a headless ``QgsApplication``;
``desktop``
    pytest inside the QGIS Desktop binary against a throwaway profile; tests
    marked ``desktop``; ``qgis_iface`` is the real interface, and the
    project's plugin is loadable by name through the same generated host
    package ``qgis-sdk dev`` stages (decision-43);
``server``
    the install's interpreter with QGIS Server bindings importable; tests
    marked ``server``; ``qgis_app`` is a headless ``QgsApplication`` and
    ``qgis.server`` is what they need. A QGIS built without ``WITH_SERVER``
    cannot run this target and the run says so instead of skipping
    (decision-52);
``web``
    the project's Vitest through the manager its lockfile names.
"""

from __future__ import annotations

from collections.abc import Sequence as _Sequence
from pathlib import Path as _Path
from typing import TYPE_CHECKING
from typing import Unpack as _Unpack

from ..installs import wants_headless as _wants_headless
from ._constants import (
    DESKTOP_PROBE,
    NATIVE_TARGETS,
    PLUGIN,
    PROFILE_NAME,
    REQUEST_ENV,
    SELECTION,
    TARGETS,
)
from ._plans import package_manager_for
from ._plans import target_planners as _target_planners
from ._plans import validate_plan as _validate_plan
from ._types import QgisSdkTestRunError, TestPlan

if TYPE_CHECKING:
    from ._types import PlanOptions1

__all__ = [
    "DESKTOP_PROBE",
    "NATIVE_TARGETS",
    "PLUGIN",
    "PROFILE_NAME",
    "REQUEST_ENV",
    "SELECTION",
    "TARGETS",
    "QgisSdkTestRunError",
    "TestPlan",
    "package_manager_for",
    "plan_tests",
]


def plan_tests(
    root: _Path,
    target: str,
    pytest_args: _Sequence[str],
    **options: _Unpack[PlanOptions1],
) -> TestPlan:
    """Return the process for ``target`` at ``root``; raise when it cannot run.

    ``install`` is required for the native targets and ignored otherwise.
    ``workspace`` is the throwaway directory the ``desktop`` target writes its
    probe and profile into; the caller owns and removes it.
    """
    from ._types import PlanValues1, TestFacts

    values = PlanValues1(**options)
    root = _Path(root).resolve()
    _validate_plan(root, target, values)
    facts = TestFacts(
        root=root,
        args=pytest_args,
        env=values.env,
        install=values.install,
        headless=_wants_headless(values.env, platform=values.platform),
        workspace=values.workspace,
    )
    return _target_planners()[target](facts)
