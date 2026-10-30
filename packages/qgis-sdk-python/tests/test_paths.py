"""``walk_files``: the one directory walk the check, bundle and devtools trees share.

TASK-80's pathlib pass replaced five copies of ``os.walk`` with this helper, so
the tests below hold the two things ``os.walk`` gave those call sites for free:
the order a diagnostic list or a staged archive is built in, and the pruning that
keeps ``web/node_modules`` and ``__pycache__`` from being descended into.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from qgis_sdk_tools.paths import walk_files


def tree(root: Path) -> Path:
    """A package-shaped tree: files and subdirectories at two depths."""
    (root / "web" / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "web" / "node_modules" / "left-pad" / "index.js").write_text("")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "plugin.cpython-312.pyc").write_text("")
    (root / "b_second.py").write_text("")
    (root / "a_first.py").write_text("")
    (root / "notes.txt").write_text("")
    (root / "sub").mkdir()
    (root / "sub" / "inner.py").write_text("")
    return root


def test_files_of_a_directory_come_before_its_subdirectories(tmp_path: Path) -> None:
    root = tree(tmp_path)
    assert [p.relative_to(root) for p in walk_files(root)] == [
        Path("a_first.py"),
        Path("b_second.py"),
        Path("notes.txt"),
        Path("__pycache__/plugin.cpython-312.pyc"),
        Path("sub/inner.py"),
        Path("web/node_modules/left-pad/index.js"),
    ]


def test_a_suffix_keeps_only_that_kind_of_file(tmp_path: Path) -> None:
    root = tree(tmp_path)
    assert [p.relative_to(root) for p in walk_files(root, suffix=".py")] == [
        Path("a_first.py"),
        Path("b_second.py"),
        Path("sub/inner.py"),
    ]


def test_a_skipped_name_is_never_descended_into(tmp_path: Path) -> None:
    root = tree(tmp_path)
    assert [
        p.relative_to(root) for p in walk_files(root, skip=("web", "__pycache__"))
    ] == [
        Path("a_first.py"),
        Path("b_second.py"),
        Path("notes.txt"),
        Path("sub/inner.py"),
    ]


def test_a_pruned_directory_is_never_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not descending is the point of copying ``os.walk``'s ``dirnames[:]`` filter."""
    root = tree(tmp_path)
    real_iterdir = Path.iterdir

    def iterdir(self: Path) -> Iterator[Path]:
        if self.name == "node_modules":
            raise AssertionError("listed a pruned directory")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    assert list(walk_files(root, skip=("web", "__pycache__")))


def test_a_missing_root_yields_nothing(tmp_path: Path) -> None:
    assert list(walk_files(tmp_path / "absent")) == []


def test_a_symlinked_directory_is_not_followed(tmp_path: Path) -> None:
    """``os.walk`` does not follow links, and a link to the parent would never end."""
    root = tree(tmp_path)
    (root / "sub" / "loop").symlink_to(root, target_is_directory=True)
    assert [
        p.relative_to(root) for p in walk_files(root, skip=("web", "__pycache__"))
    ] == [
        Path("a_first.py"),
        Path("b_second.py"),
        Path("notes.txt"),
        Path("sub/inner.py"),
    ]
