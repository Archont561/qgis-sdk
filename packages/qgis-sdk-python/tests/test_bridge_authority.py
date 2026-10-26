"""Host-minted file references and per-view grants (decision-20, TASK-20).

A view never names a path. It holds a ``FileRef`` the host minted from a native
picker result or an explicit plugin grant, and every use is checked against the
caller's binding: the view it was minted for, the generation it was minted in,
the operations it allows, and whether the path still is what it was.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from qgis_sdk.bridge import Dispatcher
from qgis_sdk.bridge.authority import (
    FILE_REF,
    MAX_FILE_REFS_PER_VIEW,
    FileOperation,
    FileRef,
    HostAuthority,
)
from qgis_sdk.bridge.schema import validate
from qgis_sdk.models import (
    QgisSdkBridgeError,
    QgisSdkGrantRefusedError,
    QgisSdkStaleHandleError,
    QgisSdkUnknownHandleError,
)
from qgis_sdk.network import NetworkGrant

ORIGIN = "qgis://desktop"


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def clock() -> _Clock:
    return _Clock()


@pytest.fixture()
def authority(clock: _Clock) -> HostAuthority:
    return HostAuthority(clock=clock)


@pytest.fixture()
def dispatcher() -> Dispatcher:
    return Dispatcher(
        description={"schema_version": 1, "id": "demo.plugin", "title": "Demo"},
        authorize=lambda binding, operation: True,
    )


@pytest.fixture()
def dataset(tmp_path: Path) -> Path:
    path = tmp_path / "sites.geojson"
    path.write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")
    return path


# -- minting ------------------------------------------------------------------


def test_a_picker_result_becomes_an_opaque_ref_the_view_can_show(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    ref = authority.grant_file(binding, dataset, source="picker")

    assert isinstance(ref, FileRef)
    assert ref.kind == "file"
    assert ref.name == "sites.geojson"
    assert ref.operations == ("read",)
    wire = ref.to_wire()
    assert wire == {
        "kind": "file",
        "id": ref.id,
        "name": "sites.geojson",
        "operations": ["read"],
    }
    assert str(dataset) not in str(wire)
    validate({"kind": "file", "id": ref.id}, FILE_REF, path="payload.file")
    assert len(ref.id) >= 16


def test_a_directory_grant_is_a_directory_ref_that_resolves_to_the_directory(
    authority: HostAuthority, dispatcher: Dispatcher, tmp_path: Path, dataset: Path
) -> None:
    """``DirectoryInput()`` hands a handler a ref, never a path (TASK-68)."""
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    ref = authority.grant_directory(binding, tmp_path, source="picker")

    assert ref.kind == "directory"
    assert ref.name == tmp_path.name
    assert ref.operations == ("read",)
    assert (
        authority.resolve_file(binding, ref.to_wire(), FileOperation.READ)
        == tmp_path.resolve()
    )
    # A directory ref is not a file ref: the brand is checked, not just the id.
    with pytest.raises(QgisSdkUnknownHandleError):
        authority.resolve_file(
            binding, {**ref.to_wire(), "kind": "file"}, FileOperation.READ
        )
    with pytest.raises(QgisSdkBridgeError, match="is not a directory that exists"):
        authority.grant_directory(binding, dataset)
    with pytest.raises(QgisSdkBridgeError, match="is not a directory that exists"):
        authority.grant_directory(binding, tmp_path / "missing")


def test_a_directory_ref_goes_stale_when_the_directory_disappears(
    authority: HostAuthority, dispatcher: Dispatcher, tmp_path: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    folder = tmp_path / "data"
    folder.mkdir()
    ref = authority.grant_directory(binding, folder)
    folder.rmdir()

    with pytest.raises(QgisSdkStaleHandleError, match="no longer names the directory"):
        authority.resolve_file(binding, ref.to_wire(), FileOperation.READ)


def test_two_grants_for_the_same_file_are_distinct_refs(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    first = authority.grant_file(binding, dataset)
    second = authority.grant_file(binding, dataset)
    assert first.id != second.id


def test_a_read_grant_needs_an_existing_regular_file(
    authority: HostAuthority, dispatcher: Dispatcher, tmp_path: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    with pytest.raises(QgisSdkBridgeError, match="not a file"):
        authority.grant_file(binding, tmp_path / "missing.gpkg")
    with pytest.raises(QgisSdkBridgeError, match="not a file"):
        authority.grant_file(binding, tmp_path)


def test_a_write_grant_needs_an_existing_parent_directory(
    authority: HostAuthority, dispatcher: Dispatcher, tmp_path: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = authority.grant_file(
        binding, tmp_path / "export.csv", operations=("write",), source="picker"
    )
    assert ref.operations == ("write",)
    with pytest.raises(QgisSdkBridgeError, match="directory"):
        authority.grant_file(
            binding, tmp_path / "nowhere" / "export.csv", operations=("write",)
        )
    with pytest.raises(QgisSdkBridgeError, match="not a file"):
        authority.grant_file(binding, tmp_path, operations=("write",))


def test_a_grant_refuses_unknown_operations_and_sources(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    with pytest.raises(QgisSdkBridgeError, match="read and/or write"):
        authority.grant_file(binding, dataset, operations=("execute",))
    with pytest.raises(QgisSdkBridgeError, match="at least one"):
        authority.grant_file(binding, dataset, operations=())
    with pytest.raises(QgisSdkBridgeError, match="source"):
        authority.grant_file(binding, dataset, source="page")


def test_a_view_holds_a_bounded_number_of_refs(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    for _ in range(MAX_FILE_REFS_PER_VIEW):
        authority.grant_file(binding, dataset)
    with pytest.raises(QgisSdkBridgeError, match="refs"):
        authority.grant_file(binding, dataset)
    other = dispatcher.bind(view_id="view-2", origin=ORIGIN)
    authority.grant_file(other, dataset)  # the ceiling is per view


# -- resolving ----------------------------------------------------------------


def test_the_view_that_was_granted_resolves_the_canonical_path(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = authority.grant_file(binding, dataset)

    resolved = authority.resolve_file(binding, ref.to_wire(), FileOperation.READ)

    assert resolved == dataset.resolve()


def test_a_ref_is_resolved_from_its_id_alone_and_the_rest_is_ignored(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path, tmp_path: Path
) -> None:
    """A page cannot steer the host by editing the display fields."""
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = authority.grant_file(binding, dataset)
    forged = {
        "kind": "file",
        "id": ref.id,
        "name": "../../etc/passwd",
        "operations": ["read", "write"],
    }

    assert authority.resolve_file(binding, forged, FileOperation.READ) == (
        dataset.resolve()
    )
    with pytest.raises(QgisSdkGrantRefusedError, match="write"):
        authority.resolve_file(binding, forged, FileOperation.WRITE)


def test_another_view_cannot_use_the_ref_and_learns_nothing(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path
) -> None:
    owner = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    other = dispatcher.bind(view_id="view-2", origin=ORIGIN)
    ref = authority.grant_file(owner, dataset)

    with pytest.raises(QgisSdkUnknownHandleError) as foreign:
        authority.resolve_file(other, ref.to_wire(), FileOperation.READ)
    with pytest.raises(QgisSdkUnknownHandleError) as never:
        authority.resolve_file(
            other, {"kind": "file", "id": "no-such"}, FileOperation.READ
        )

    # The same message shape for a foreign and a nonexistent ref: no oracle.
    assert str(foreign.value).replace(ref.id, "X") == str(never.value).replace(
        "no-such", "X"
    )
    assert str(dataset) not in str(foreign.value)


def test_a_ref_from_a_replaced_generation_is_stale(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path
) -> None:
    old = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = authority.grant_file(old, dataset)
    dispatcher.advance_generation()
    new = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    with pytest.raises(QgisSdkStaleHandleError, match="generation"):
        authority.resolve_file(new, ref.to_wire(), FileOperation.READ)


def test_a_malformed_ref_is_unknown_not_an_exception(
    authority: HostAuthority, dispatcher: Dispatcher
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    for raw in (None, "f-1", {"kind": "layer", "id": "x"}, {"kind": "file"}, {"id": 3}):
        with pytest.raises(QgisSdkUnknownHandleError):
            authority.resolve_file(binding, raw, FileOperation.READ)


def test_an_expired_ref_is_stale_and_forgotten(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path, clock: _Clock
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = authority.grant_file(binding, dataset, ttl_seconds=60)
    authority.resolve_file(binding, ref.to_wire(), FileOperation.READ)
    clock.now += 61

    with pytest.raises(QgisSdkStaleHandleError, match="expired"):
        authority.resolve_file(binding, ref.to_wire(), FileOperation.READ)
    assert authority.refs(binding) == ()


def test_a_revoked_ref_is_stale_until_the_view_is_released(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = authority.grant_file(binding, dataset)

    assert authority.revoke(ref.id) is True
    assert authority.revoke(ref.id) is False
    with pytest.raises(QgisSdkStaleHandleError, match="revoked"):
        authority.resolve_file(binding, ref.to_wire(), FileOperation.READ)

    authority.release_view(binding)
    with pytest.raises(QgisSdkUnknownHandleError):
        authority.resolve_file(binding, ref.to_wire(), FileOperation.READ)


def test_releasing_a_view_drops_its_refs_and_grants_but_not_the_files(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    other = dispatcher.bind(view_id="view-2", origin=ORIGIN)
    ref = authority.grant_file(binding, dataset)
    kept = authority.grant_file(other, dataset)
    authority.grant_network(binding, NetworkGrant(origins=("https://api.example.org",)))

    released = authority.release_view(binding)

    assert released == 1
    assert dataset.exists()
    assert authority.refs(binding) == ()
    assert authority.network_grant(binding) is None
    with pytest.raises(QgisSdkUnknownHandleError):
        authority.resolve_file(binding, ref.to_wire(), FileOperation.READ)
    assert authority.resolve_file(other, kept.to_wire(), FileOperation.READ)


def test_pruning_a_replaced_generation_forgets_its_refs_and_grants(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path
) -> None:
    old = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    authority.grant_file(old, dataset)
    authority.grant_network(old, NetworkGrant(origins=("https://api.example.org",)))
    dispatcher.advance_generation()
    new = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    kept = authority.grant_file(new, dataset)

    assert authority.prune(new.generation) == 1
    assert authority.prune(new.generation) == 0
    assert authority.network_grant(new) is None
    assert authority.refs(new) == (kept,)
    assert dataset.exists()


def test_a_write_destination_whose_parent_was_replaced_is_stale(
    authority: HostAuthority, dispatcher: Dispatcher, tmp_path: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    folder = tmp_path / "out"
    folder.mkdir()
    ref = authority.grant_file(
        binding, folder / "export.geojson", operations=("write",)
    )

    folder.rename(tmp_path / "elsewhere")
    with pytest.raises(QgisSdkStaleHandleError, match="destination"):
        authority.export_file(binding, ref.to_wire(), "{}")

    (tmp_path / "elsewhere").rename(folder)
    (folder / "export.geojson").mkdir()
    with pytest.raises(QgisSdkStaleHandleError, match="no longer names a file"):
        authority.export_file(binding, ref.to_wire(), "{}")


def test_a_ref_whose_file_moved_or_changed_identity_is_stale(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path, tmp_path: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = authority.grant_file(binding, dataset)
    dataset.rename(tmp_path / "moved.geojson")

    with pytest.raises(QgisSdkStaleHandleError, match="no longer"):
        authority.resolve_file(binding, ref.to_wire(), FileOperation.READ)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_a_symlink_is_granted_as_its_target_and_cannot_be_steered_by_retargeting(
    authority: HostAuthority, dispatcher: Dispatcher, dataset: Path, tmp_path: Path
) -> None:
    """The ref names the canonical file; swapping the link opens nothing new."""
    link = tmp_path / "current.geojson"
    try:
        link.symlink_to(dataset)
    except (OSError, NotImplementedError):  # pragma: no cover - platform policy
        pytest.skip("symlinks are not permitted here")
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = authority.grant_file(binding, link)
    assert authority.resolve_file(binding, ref.to_wire(), FileOperation.READ) == (
        dataset.resolve()
    )

    elsewhere = tmp_path / "secrets.txt"
    elsewhere.write_text("x", encoding="utf-8")
    link.unlink()
    link.symlink_to(elsewhere)

    assert authority.resolve_file(binding, ref.to_wire(), FileOperation.READ) == (
        dataset.resolve()
    )
    assert ref.name == "sites.geojson"

    # And a link put in place of the granted file itself is refused.
    dataset.unlink()
    dataset.symlink_to(elsewhere)
    with pytest.raises(QgisSdkStaleHandleError, match="no longer"):
        authority.resolve_file(binding, ref.to_wire(), FileOperation.READ)


def test_a_write_ref_refuses_to_overwrite_unless_the_grant_said_so(
    authority: HostAuthority, dispatcher: Dispatcher, tmp_path: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    target = tmp_path / "export.csv"
    fresh = authority.grant_file(binding, target, operations=("write",))
    assert authority.resolve_file(binding, fresh.to_wire(), FileOperation.WRITE) == (
        target.resolve()
    )

    target.write_text("existing", encoding="utf-8")
    with pytest.raises(QgisSdkGrantRefusedError, match="overwrit"):
        authority.resolve_file(binding, fresh.to_wire(), FileOperation.WRITE)

    replace = authority.grant_file(
        binding, target, operations=("write",), overwrite=True, source="picker"
    )
    assert authority.resolve_file(binding, replace.to_wire(), FileOperation.WRITE) == (
        target.resolve()
    )
    with pytest.raises(QgisSdkGrantRefusedError, match="read"):
        authority.resolve_file(binding, replace.to_wire(), FileOperation.READ)


# -- exporting ----------------------------------------------------------------


def test_an_export_writes_atomically_and_leaves_nothing_behind_on_failure(
    authority: HostAuthority, dispatcher: Dispatcher, tmp_path: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    target = tmp_path / "export.csv"
    ref = authority.grant_file(binding, target, operations=("write",))

    written = authority.export_file(binding, ref.to_wire(), "a,b\n1,2\n")

    assert written == len(b"a,b\n1,2\n")
    assert target.read_text(encoding="utf-8") == "a,b\n1,2\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["export.csv"]

    # A second export through a non-overwriting grant leaves the file alone.
    with pytest.raises(QgisSdkGrantRefusedError, match="overwrit"):
        authority.export_file(binding, ref.to_wire(), "changed")
    assert target.read_text(encoding="utf-8") == "a,b\n1,2\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["export.csv"]


def test_an_export_that_fails_midway_cleans_its_partial_file(
    authority: HostAuthority, dispatcher: Dispatcher, tmp_path: Path, monkeypatch
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    target = tmp_path / "export.csv"
    ref = authority.grant_file(binding, target, operations=("write",))

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", explode)
    with pytest.raises(QgisSdkBridgeError, match="disk full"):
        authority.export_file(binding, ref.to_wire(), "a,b\n")

    assert list(tmp_path.iterdir()) == []


def test_an_export_is_bounded(
    authority: HostAuthority, dispatcher: Dispatcher, tmp_path: Path
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    ref = authority.grant_file(
        binding, tmp_path / "export.csv", operations=("write",), max_bytes=4
    )
    with pytest.raises(QgisSdkGrantRefusedError, match="4 bytes"):
        authority.export_file(binding, ref.to_wire(), "12345")
    assert list(tmp_path.iterdir()) == []


# -- network grants -----------------------------------------------------------


def test_a_network_grant_is_per_view_and_replaced_not_merged(
    authority: HostAuthority, dispatcher: Dispatcher
) -> None:
    binding = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    other = dispatcher.bind(view_id="view-2", origin=ORIGIN)
    first = NetworkGrant(origins=("https://a.example.org",))
    second = NetworkGrant(origins=("https://b.example.org",))

    assert authority.network_grant(binding) is None
    authority.grant_network(binding, first)
    authority.grant_network(binding, second)

    assert authority.network_grant(binding) is second
    assert authority.network_grant(other) is None
    assert authority.revoke_network(binding) is True
    assert authority.revoke_network(binding) is False
    assert authority.network_grant(binding) is None


def test_a_network_grant_belongs_to_the_generation_it_was_minted_in(
    authority: HostAuthority, dispatcher: Dispatcher
) -> None:
    old = dispatcher.bind(view_id="view-1", origin=ORIGIN)
    authority.grant_network(old, NetworkGrant(origins=("https://a.example.org",)))
    dispatcher.advance_generation()
    new = dispatcher.bind(view_id="view-1", origin=ORIGIN)

    assert authority.network_grant(new) is None
    with pytest.raises(QgisSdkGrantRefusedError, match="network"):
        authority.require_network(new)
