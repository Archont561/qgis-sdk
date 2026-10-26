"""``ctx.files``: plugin code turns a ``FileRef`` into a path, and nothing else does.

A handler declared ``source: FileInput()`` and received a ref (TASK-68). The
ref is authority, not a path (decision-20), so the one way from it to the
filesystem is the plugin's ``files`` service, which asks the host authority
the ref was minted by. The same service mints refs for the catalogue's
``FileInput``/``DirectoryInput`` components, so a form, a toolbox run and a
page all hand a handler refs that resolve through one door.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.core import PluginContext, ResourceScope, UiContext
from qgis_sdk.files import FilesService
from qgis_sdk.models import (
    FileRef,
    QgisSdkGrantRefusedError,
    QgisSdkScopeClosedError,
    QgisSdkUnknownHandleError,
    QgisSdkUnsupportedCapabilityError,
)
from qgis_sdk.testing import FakeFiles, FakeViewControl, RecordingNotifications


@pytest.fixture()
def dataset(tmp_path: Path) -> Path:
    path = tmp_path / "sites.gpkg"
    path.write_bytes(b"x")
    return path


def test_a_granted_file_resolves_back_to_its_canonical_path(dataset: Path) -> None:
    scope = ResourceScope()
    files = FilesService(HostAuthority(), scope, owner="plugin:demo")

    ref = files.grant_file(dataset)

    assert isinstance(ref, FileRef)
    assert (ref.kind, ref.name, ref.operations) == ("file", "sites.gpkg", ("read",))
    assert files.resolve(ref) == dataset.resolve()


def test_a_directory_ref_resolves_and_a_file_ref_is_not_a_directory(
    dataset: Path, tmp_path: Path
) -> None:
    files = FilesService(HostAuthority(), ResourceScope(), owner="plugin:demo")

    folder = files.grant_directory(tmp_path)
    file = files.grant_file(dataset)

    assert folder.kind == "directory"
    assert files.resolve(folder) == tmp_path.resolve()
    assert files.resolve(file).parent == files.resolve(folder)


def test_a_write_grant_is_asked_for_and_read_is_refused_on_it(tmp_path: Path) -> None:
    files = FilesService(HostAuthority(), ResourceScope(), owner="plugin:demo")

    out = files.grant_file(tmp_path / "out.gpkg", operations=("write",))

    assert files.resolve(out, operation="write") == (tmp_path / "out.gpkg").resolve()
    with pytest.raises(QgisSdkGrantRefusedError):
        files.resolve(out)


def test_a_ref_minted_for_another_owner_is_unknown_here(dataset: Path) -> None:
    """Two views of one authority never see each other's refs; neither does a plugin."""
    authority = HostAuthority()
    mine = FilesService(authority, ResourceScope(), owner="plugin:demo")
    theirs = FilesService(authority, ResourceScope(), owner="view:page#1")

    ref = theirs.grant_file(dataset)

    with pytest.raises(QgisSdkUnknownHandleError):
        mine.resolve(ref)


def test_a_forged_ref_is_unknown(dataset: Path) -> None:
    files = FilesService(HostAuthority(), ResourceScope(), owner="plugin:demo")
    files.grant_file(dataset)

    with pytest.raises(QgisSdkUnknownHandleError):
        files.resolve(FileRef(id="b" * 16, name="sites.gpkg", operations=("read",)))


def test_the_wire_shape_of_a_ref_resolves_too(dataset: Path) -> None:
    """A handler may forward what a page sent before the dispatcher rebuilt it."""
    files = FilesService(HostAuthority(), ResourceScope(), owner="plugin:demo")
    ref = files.grant_file(dataset)

    assert files.resolve(ref.to_wire()) == dataset.resolve()


def test_closing_the_scope_revokes_what_the_service_minted(dataset: Path) -> None:
    authority = HostAuthority()
    scope = ResourceScope()
    files = FilesService(authority, scope, owner="plugin:demo")
    ref = files.grant_file(dataset)

    scope.close()

    with pytest.raises(QgisSdkScopeClosedError):
        files.grant_file(dataset)
    with pytest.raises(QgisSdkScopeClosedError):
        files.resolve(ref)
    assert authority.refs(files.binding) == ()


def test_the_service_exposes_the_authority_so_a_host_shares_one(dataset: Path) -> None:
    """Processing, the page host and the forms mint through the plugin's authority."""
    authority = HostAuthority()
    files = FilesService(authority, ResourceScope(), owner="plugin:demo")

    assert files.authority is authority


def test_files_is_a_plugin_and_a_view_capability(dataset: Path) -> None:
    scope = ResourceScope()
    files = FakeFiles(scope)
    notifications = RecordingNotifications(scope)

    plugin = PluginContext(notifications=notifications, scope=scope, files=files)
    view = UiContext(notifications, FakeViewControl(), scope, files=files)
    bare = PluginContext(notifications=notifications, scope=scope)

    ref = view.files.grant_file(dataset)
    assert plugin.files.resolve(ref) == dataset.resolve()
    assert plugin.has("files") and view.has("files")
    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="files"):
        _ = bare.files


def test_the_fake_is_the_real_rule_over_a_private_authority(dataset: Path) -> None:
    """``FakeFiles`` refuses exactly what the host refuses: it *is* the service."""
    files = FakeFiles(ResourceScope())

    with pytest.raises(QgisSdkUnknownHandleError):
        files.resolve(FileRef(id="c" * 16, name="x", operations=("read",)))
    assert files.grant_directory(dataset.parent).kind == "directory"
    assert files.granted == (files.granted[0],)
