"""Exercise the repository's actual alint policy against isolated trees."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".alint.yml"


def check(root: Path) -> tuple[int, set[str]]:
    result = subprocess.run(
        ["alint", "check", "--config", str(CONFIG), "--format", "json", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        pytest.fail(f"alint failed to run: {result.stderr}")
    report = json.loads(result.stdout)
    return result.returncode, {
        rule["id"] for rule in report["results"] if not rule["passed"]
    }


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("License\n", encoding="utf-8")
    for scoped, alias, name in (
        ("qgis-sdk-typescript", "qgis-sdk-alias", "qgis-sdk"),
        ("qgis-sdk-ui", "qgis-sdk-ui-alias", "qgis-sdk-ui"),
    ):
        for package in (scoped, alias):
            readme = tmp_path / "packages" / package / "README.md"
            readme.parent.mkdir(parents=True)
            readme.write_text(f"# Package\n\nbun add {name}\n", encoding="utf-8")
    return tmp_path


def test_clean_tree_passes(tree: Path) -> None:
    workflow = tree / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  build:\n    steps:\n"
        "      - uses: actions/checkout@" + "a" * 40 + "\n"
        "      - uses: ./local-action\n",
        encoding="utf-8",
    )
    assert check(tree) == (0, set())


def test_missing_required_root_files_fail_independently(tree: Path) -> None:
    for filename, rule in [("README.md", "root-readme"), ("LICENSE", "root-license")]:
        path = tree / filename
        path.unlink()
        status, violations = check(tree)
        assert status == 1
        assert rule in violations
        path.write_text("restored\n", encoding="utf-8")


def test_unpinned_action_is_rejected(tree: Path) -> None:
    workflow = tree / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n",
        encoding="utf-8",
    )
    status, violations = check(tree)
    assert status == 1
    assert "immutable-actions" in violations


@pytest.mark.parametrize(
    ("content", "rule"),
    [
        (
            "<" * 7 + " HEAD\nchange\n" + "=" * 7 + "\nother\n" + ">" * 7 + " topic\n",
            "no-merge-markers",
        ),
        ("text " + chr(0x202E) + "hidden\n", "no-bidi-controls"),
    ],
)
def test_unsafe_text_is_rejected(tree: Path, content: str, rule: str) -> None:
    (tree / "example.txt").write_text(content, encoding="utf-8")
    status, violations = check(tree)
    assert status == 1
    assert rule in violations


def test_unpinned_nested_composite_action_is_rejected(tree: Path) -> None:
    action = tree / ".github/actions/build/action.yaml"
    action.parent.mkdir(parents=True)
    action.write_text(
        "runs:\n  using: composite\n  steps:\n    - uses: actions/checkout@v4\n",
        encoding="utf-8",
    )
    status, violations = check(tree)
    assert status == 1
    assert "immutable-actions" in violations


def test_ignored_files_are_not_scanned(tree: Path) -> None:
    (tree / ".gitignore").write_text("generated/\n", encoding="utf-8")
    ignored = tree / "generated"
    ignored.mkdir()
    (ignored / "fixture.txt").write_text("text " + chr(0x202E) + "\n", encoding="utf-8")
    assert check(tree) == (0, set())


@pytest.mark.parametrize(
    "reference",
    [
        "owner/repo/.github/workflows/check.yml@main",
        "docker://alpine:latest",
    ],
)
def test_unpinned_reusable_workflow_and_container_are_rejected(
    tree: Path, reference: str
) -> None:
    workflow = tree / ".github/workflows/check.yaml"
    workflow.parent.mkdir(parents=True)
    if reference.startswith("docker://"):
        text = f"jobs:\n  build:\n    steps:\n      - uses: {reference}\n"
    else:
        text = f"jobs:\n  call:\n    uses: {reference}\n"
    workflow.write_text(text, encoding="utf-8")
    status, violations = check(tree)
    assert status == 1
    assert "immutable-actions" in violations


@pytest.mark.parametrize(
    ("scoped", "alias", "rule"),
    [
        ("qgis-sdk-typescript", "qgis-sdk-alias", "bridge-readme-mirror"),
        ("qgis-sdk-ui", "qgis-sdk-ui-alias", "ui-readme-mirror"),
    ],
)
def test_alias_readme_must_match_scoped_package_byte_for_byte(
    tree: Path, scoped: str, alias: str, rule: str
) -> None:
    target = tree / "packages" / alias / "README.md"
    target.write_bytes(target.read_bytes() + b"\n")
    status, violations = check(tree)
    assert status == 1
    assert rule in violations


@pytest.mark.parametrize(
    ("scoped", "alias", "rule"),
    [
        ("qgis-sdk-typescript", "qgis-sdk-alias", "bridge-readme-alias-name"),
        ("qgis-sdk-ui", "qgis-sdk-ui-alias", "ui-readme-alias-name"),
    ],
)
def test_scoped_readme_must_name_its_unscoped_install(
    tree: Path, scoped: str, alias: str, rule: str
) -> None:
    for package in (scoped, alias):
        (tree / "packages" / package / "README.md").write_text(
            "# Package\n", encoding="utf-8"
        )
    status, violations = check(tree)
    assert status == 1
    assert rule in violations


@pytest.mark.parametrize(
    ("missing", "rule"),
    [
        ("qgis-sdk-typescript", "bridge-readme-mirror"),
        ("qgis-sdk-alias", "bridge-readme-mirror"),
        ("qgis-sdk-ui", "ui-readme-mirror"),
        ("qgis-sdk-ui-alias", "ui-readme-mirror"),
    ],
)
def test_readme_mirror_rejects_missing_files(
    tree: Path, missing: str, rule: str
) -> None:
    (tree / "packages" / missing / "README.md").unlink()
    status, violations = check(tree)
    assert status == 1
    assert rule in violations


def test_scoped_readme_alias_requirement_is_not_silenced_by_gitignore(
    tree: Path,
) -> None:
    (tree / ".gitignore").write_text(
        "packages/qgis-sdk-typescript/README.md\n", encoding="utf-8"
    )
    for package in ("qgis-sdk-typescript", "qgis-sdk-alias"):
        (tree / "packages" / package / "README.md").write_text(
            "# Package\n", encoding="utf-8"
        )
    status, violations = check(tree)
    assert status == 1
    assert "bridge-readme-alias-name" in violations


def test_alias_install_text_can_appear_more_than_once(tree: Path) -> None:
    for package in ("qgis-sdk-typescript", "qgis-sdk-alias"):
        (tree / "packages" / package / "README.md").write_text(
            "# Bridge\n\nbun add qgis-sdk\n\nbun add qgis-sdk\n", encoding="utf-8"
        )
    assert check(tree) == (0, set())


def test_mirrored_readme_newline_bytes_must_match(tree: Path) -> None:
    path = tree / "packages/qgis-sdk-alias/README.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    status, violations = check(tree)
    assert status == 1
    assert "bridge-readme-mirror" in violations
