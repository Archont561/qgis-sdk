"""Keep the Python support promise and the matrix that tests it in step.

`requires-python = ">=3.11"` is a claim about interpreters nobody develops on:
the workspace's Pixi environments pin one Python (the newest), and every other
version in the range is only ever exercised by the compatibility matrix. A
manifest that widens the range without a tox environment, or a tox environment
without a workflow entry, would therefore keep the promise on paper only - and
the failure it hides is "the package does not install on 3.11", found by a user.

These tests read the repository as data and import no package code.
"""

from __future__ import annotations

import configparser
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = (
    ROOT / "packages" / "qgis-sdk-python" / "pyproject.toml",
    ROOT / "packages" / "qgis-sdk-runtime" / "pyproject.toml",
    ROOT / "packages" / "qgis-sdk-tools" / "pyproject.toml",
)
TOX = ROOT / "tox.ini"
WORKFLOW = ROOT / ".github" / "workflows" / "compat.yml"
PIXI = ROOT / "pixi.toml"

FLOOR = re.compile(r">=(?P<major>\d+)\.(?P<minor>\d+)")
PINNED = re.compile(r'^python = "==(?P<major>\d+)\.(?P<minor>\d+)\.\d+"$', re.MULTILINE)


def _manifest_floors() -> dict[str, tuple[int, int]]:
    floors: dict[str, tuple[int, int]] = {}
    for path in MANIFESTS:
        declared = tomllib.loads(path.read_text(encoding="utf-8"))["project"][
            "requires-python"
        ]
        match = FLOOR.fullmatch(declared.strip())
        assert match is not None, f"{path.name}: unreadable requires-python {declared}"
        floors[path.parent.name] = (int(match["major"]), int(match["minor"]))
    return floors


def _newest() -> tuple[int, int]:
    """The interpreter the Pixi environments pin: the top of the range."""
    match = PINNED.search(PIXI.read_text(encoding="utf-8"))
    assert match is not None, "pixi.toml: no pinned python dependency"
    return int(match["major"]), int(match["minor"])


def _expected() -> list[str]:
    """Every minor from the declared floor to the pinned interpreter."""
    floor = next(iter(_manifest_floors().values()))
    major, minor = floor
    top_major, top_minor = _newest()
    assert major == top_major, f"the floor ({major}) is ahead of the pin ({top_major})"
    return [f"py{major}{version}" for version in range(minor, top_minor + 1)]


def _tox_environment() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(TOX, encoding="utf-8")
    return parser


def test_every_distribution_promises_the_same_python_floor() -> None:
    floors = _manifest_floors()
    assert len(set(floors.values())) == 1, f"manifests disagree on the floor: {floors}"


def test_tox_tests_every_version_the_manifests_promise() -> None:
    envlist = [
        name.strip()
        for name in _tox_environment()["tox"]["envlist"].split(",")
        if name.strip()
    ]
    assert envlist == _expected(), (
        "tox.ini's envlist and the range the manifests promise have drifted"
    )


def test_tox_refuses_to_skip_a_missing_interpreter() -> None:
    """A matrix that silently drops a version proves nothing about that version."""
    declared = _tox_environment()["tox"].get("skip_missing_interpreters")
    assert declared is not None and declared.strip() == "false"


def test_the_compatibility_workflow_runs_one_job_per_tox_environment() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["compat"]["steps"]
    entries = workflow["jobs"]["compat"]["strategy"]["matrix"]["include"]
    assert [entry["toxenv"] for entry in entries] == _expected()
    for entry in entries:
        env = entry["toxenv"]
        assert entry["python"] == f"{env[2]}.{env[3:]}", (
            f"{env} is set up with Python {entry['python']}"
        )
    tox_calls = [
        step["run"]
        for step in steps
        if step.get("run", "").startswith("python scripts/ci.py")
    ]
    assert any("tox -e" in call and "matrix.toxenv" in call for call in tox_calls), (
        "the workflow never runs the tox environment it configures"
    )
