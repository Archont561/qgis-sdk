"""Artifact building and checksum helpers."""

import hashlib

import pytest
from qgis_sdk_release.artifacts import (
    build_wheel,
    checksums,
    twine_check,
    write_checksums,
)
from qgis_sdk_release.errors import QgisSdkReleaseError


def test_build_wheel_command_shape():
    calls = []
    build_wheel("packages/qgis-sdk", "dist/pypi", runner=calls.append)
    (command,) = calls
    assert list(command[1:]) == [
        "-m",
        "build",
        "--wheel",
        "--no-isolation",
        "--outdir",
        "dist/pypi",
        "packages/qgis-sdk",
    ]
    assert command[0].endswith("python") or "python" in command[0]


def test_twine_check_lists_every_wheel():
    calls = []
    twine_check(["a.whl", "b.whl"], runner=calls.append)
    assert calls == [["twine", "check", "a.whl", "b.whl"]]


def test_twine_check_needs_a_wheel():
    with pytest.raises(QgisSdkReleaseError):
        twine_check([])


def test_checksums_are_sorted_and_sha256(tmp_path):
    second = tmp_path / "b.whl"
    first = tmp_path / "a.whl"
    first.write_bytes(b"hello\n")
    second.write_bytes(b"world\n")
    entries = checksums([second, first])
    assert [name for name, _ in entries] == ["a.whl", "b.whl"]
    assert entries[0][1] == hashlib.sha256(b"hello\n").hexdigest()


def test_checksums_reject_missing_files(tmp_path):
    with pytest.raises(QgisSdkReleaseError):
        checksums([tmp_path / "nope.whl"])


def test_write_checksums_is_sha256sum_compatible(tmp_path):
    target = tmp_path / "SHA256SUMS"
    write_checksums(target, [("a.whl", "aa" * 32), ("b.tgz", "bb" * 32)])
    assert target.read_text() == f"{'aa' * 32}  a.whl\n{'bb' * 32}  b.tgz\n"
