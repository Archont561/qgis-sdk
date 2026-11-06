"""Contract: the project as a CRS, entries, bookmarks, a tree and a file.

Everything here runs against both backends unchanged. Two shapes are deliberate.

*The tree is asserted as a tree, not as a string.* A nested group structure is
declared, the layer is placed inside the deepest group, and the assertions read
:meth:`~qgis_sdk.models.project.LayerTree.children_of` - so a backend that
returned the right names in the wrong nesting would fail rather than look right.

*The change stream is asserted as an order.* A subscription records every frame
and the test compares the kinds it received with the order the calls were made
in; a backend that coalesced or reordered them would be caught.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import conftest
import pytest
from qgis_sdk.models import (
    Bookmark,
    CanvasExtent,
    LayerTree,
    ProjectChange,
    QgisSdkBookmarkNotFoundError,
    QgisSdkLayerNotFoundError,
    QgisSdkProjectFileError,
)

if TYPE_CHECKING:
    Services = conftest.Services

pytestmark = pytest.mark.usefixtures("services")

WORKING_CRS = "EPSG:3857"


def _directory(services: Services) -> Path:
    assert services.project_directory is not None
    return services.project_directory()


def _groups(services: Services) -> tuple[str, str]:
    """Declare the nested groups and answer the ids the backend reported."""
    assert services.declare_groups is not None
    return services.declare_groups()


def test_project_starts_without_layers(services: Services) -> None:
    assert services.project.layer_ids() == ()


def test_added_layer_appears_on_the_project(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    services.project.add_layer(info.id)

    assert info.id in services.project.layer_ids()


def test_adding_the_same_layer_twice_keeps_one_entry(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    services.project.add_layer(info.id)
    services.project.add_layer(info.id)

    assert services.project.layer_ids() == (info.id,)


def test_project_refuses_a_layer_the_runtime_does_not_own(
    services: Services,
) -> None:
    with pytest.raises(QgisSdkLayerNotFoundError) as error:
        services.project.add_layer("no-such-layer")

    assert error.value.identifier == "no-such-layer"


# -- the tree ---------------------------------------------------------------


def test_a_layer_can_be_added_into_a_nested_group(services: Services) -> None:
    root_group, child_group = _groups(services)
    info = services.layers.open_vector(services.dataset)

    tree = services.project.add_layer(info.id, group=child_group)

    assert isinstance(tree, LayerTree)
    assert tree.node(info.id).parent == child_group
    assert tree.layer_ids() == (info.id,)
    assert tree.group_ids() == (root_group, child_group)
    # The nested view a UI draws comes back from the flat model.
    assert [node.name for node in services.project.layer_tree().children_of()] == [
        conftest.ROOT_GROUP
    ]


def test_a_layer_moves_between_groups(services: Services) -> None:
    root_group, child_group = _groups(services)
    info = services.layers.open_vector(services.dataset)
    services.project.add_layer(info.id, group=child_group)

    tree = services.project.move_layer(info.id, group=root_group)

    assert tree.node(info.id).parent == root_group
    assert [node.id for node in tree.children_of(root_group)] == [
        child_group,
        info.id,
    ]


def test_an_unknown_group_is_refused_by_name(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)

    with pytest.raises(QgisSdkLayerNotFoundError):
        services.project.add_layer(info.id, group="group:absent")


def test_visibility_is_the_node_s_own(services: Services) -> None:
    _, child_group = _groups(services)
    info = services.layers.open_vector(services.dataset)
    services.project.add_layer(info.id, group=child_group)

    tree = services.project.set_visible(child_group, False)

    assert tree.node(child_group).visible is False
    # Hiding a group hides what it holds without rewriting every child.
    assert tree.node(info.id).visible is True
    assert services.project.set_visible(child_group, True).node(child_group).visible


def test_removing_a_layer_keeps_it_open(services: Services) -> None:
    info = services.layers.open_vector(services.dataset)
    services.project.add_layer(info.id)

    tree = services.project.remove_layer(info.id)

    assert tree.layer_ids() == ()
    # The project forgot it; the layer service still owns it.
    assert services.layers.layer(info.id).id == info.id


# -- CRS, variables and properties ------------------------------------------


def test_the_project_crs_can_be_set_and_read(services: Services) -> None:
    services.project.set_crs(WORKING_CRS)

    assert services.project.crs() == WORKING_CRS


def test_a_crs_that_cannot_be_resolved_is_refused(services: Services) -> None:
    from qgis_sdk.models import QgisSdkUnsupportedCapabilityError

    with pytest.raises(QgisSdkUnsupportedCapabilityError):
        services.project.set_crs("EPSG:not-a-number")


def test_a_variable_is_set_and_removed(services: Services) -> None:
    entries = services.project.set_variable("project_author", "Ada")

    assert {entry.key: entry.value for entry in entries} == {"project_author": "Ada"}
    assert services.project.unset_variable("project_author") == ()
    # Removing an absent name is a no-op, not an error.
    assert services.project.unset_variable("project_author") == ()


def test_a_custom_property_is_set_and_removed(services: Services) -> None:
    entries = services.project.set_custom_property("sdk.reference", "yes")

    assert {entry.key: entry.value for entry in entries} == {"sdk.reference": "yes"}
    assert services.project.unset_custom_property("sdk.reference") == ()


# -- bookmarks --------------------------------------------------------------


def test_a_bookmark_is_added_read_and_removed(services: Services) -> None:
    extent = CanvasExtent(x_min=21.0, y_min=52.0, x_max=21.2, y_max=52.2)

    listed = services.project.add_bookmark("home", extent)

    assert "home" in {bookmark.name for bookmark in listed}
    assert isinstance(services.project.bookmark("home"), Bookmark)
    assert services.project.bookmark("home").extent == extent

    remaining = services.project.remove_bookmark("home")
    assert "home" not in {bookmark.name for bookmark in remaining}


def test_an_unknown_bookmark_is_refused_by_name(services: Services) -> None:
    with pytest.raises(QgisSdkBookmarkNotFoundError) as error:
        services.project.bookmark("nowhere")

    assert error.value.name == "nowhere"
    with pytest.raises(QgisSdkBookmarkNotFoundError):
        services.project.remove_bookmark("nowhere")


# -- the file ---------------------------------------------------------------


def test_a_project_round_trips_through_its_file(services: Services) -> None:
    """The defined tree comes back as the tree that was written."""
    _, child_group = _groups(services)
    info = services.layers.open_vector(services.dataset)
    services.project.add_layer(info.id, group=child_group)
    services.project.set_crs(WORKING_CRS)
    services.project.set_variable("project_author", "Ada")
    extent = CanvasExtent(x_min=21.0, y_min=52.0, x_max=21.2, y_max=52.2)
    services.project.add_bookmark("home", extent)
    destination = _directory(services) / "round-trip.qgs"

    written = services.project.write(destination)

    assert written.path == str(destination)
    with pytest.raises(QgisSdkProjectFileError):
        # An existing project file is replaced only when asked.
        services.project.write(destination)

    read = services.project.read(destination)

    assert read == services.project.layer_tree()
    assert services.project.crs() == WORKING_CRS
    assert {entry.key: entry.value for entry in services.project.variables()} == {
        "project_author": "Ada"
    }
    assert services.project.bookmark("home").extent == extent
    assert services.project.save().path == str(destination)


def test_a_project_without_a_file_cannot_be_saved(services: Services) -> None:
    with pytest.raises(QgisSdkProjectFileError):
        services.project.save()


def test_a_file_that_is_not_a_project_is_refused(services: Services) -> None:
    absent = _directory(services) / "absent.qgs"

    with pytest.raises(QgisSdkProjectFileError):
        services.project.read(absent)


# -- the change stream ------------------------------------------------------


def test_the_change_stream_delivers_ordered_frames(services: Services) -> None:
    frames: list[ProjectChange] = []
    cancel = services.project.watch_changes(frames.append)
    try:
        services.project.set_crs(WORKING_CRS)
        info = services.layers.open_vector(services.dataset)
        services.project.add_layer(info.id)
        services.project.set_variable("project_author", "Ada")
        services.project.add_bookmark("home", CanvasExtent(0, 0, 1, 1))
        services.project.remove_layer(info.id)
    finally:
        cancel()

    assert [frame.kind for frame in frames] == [
        "crs",
        "layers",
        "variables",
        "bookmarks",
        "layers",
    ]
    assert frames[1].layer_ids == (info.id,)


def test_a_cancelled_subscription_stops_receiving_frames(services: Services) -> None:
    frames: list[ProjectChange] = []
    cancel = services.project.watch_changes(frames.append)
    cancel()

    services.project.set_crs(WORKING_CRS)

    assert frames == []
