"""What a snapshot approval must fail on, and what it must forgive."""

from __future__ import annotations

import copy

from qgis_sdk_tools.ui_diff import diff_snapshots, structural_change


def surface(**overrides):
    """A small approved-shape snapshot; overrides make the second capture."""
    tree = {
        "surface": "buffer",
        "kind": "dialog",
        "title": "Buffer",
        "size": {"width": 320, "height": 200},
        "scale": 1.0,
        "screenshot": "sha256:aaaa",
        "nodes": [
            {
                "id": "root",
                "role": "container",
                "type": "QWidget",
                "value": None,
                "label": None,
                "state": {"enabled": True, "visible": True, "focus": False},
                "geometry": {"x": 0, "y": 0, "width": 320, "height": 200},
                "declared": None,
                "children": [
                    {
                        "id": "form/distance",
                        "role": "spinbox",
                        "type": "QgsDoubleSpinBox",
                        "value": 0.0,
                        "label": "Distance",
                        "state": {"enabled": True, "visible": True, "focus": False},
                        "geometry": {"x": 0, "y": 0, "width": 100, "height": 20},
                        "declared": {"field": "distance"},
                    },
                    {
                        "id": "buttons/run",
                        "role": "button",
                        "type": "QPushButton",
                        "value": "Run",
                        "label": None,
                        "state": {"enabled": True, "visible": True, "focus": False},
                        "geometry": {"x": 0, "y": 24, "width": 80, "height": 24},
                        "declared": {"button": "run"},
                    },
                ],
            }
        ],
        "findings": [],
    }
    tree.update(overrides)
    return tree


def _node(tree, node_id):
    def walk(nodes):
        for node in nodes:
            if node["id"] == node_id:
                return node
            found = walk(node.get("children", ()))
            if found is not None:
                return found
        return None

    return walk(tree["nodes"])


def test_an_unchanged_surface_has_no_differences():
    diff = diff_snapshots(surface(), surface())
    assert diff.identical
    assert not diff
    assert diff.render() == "no differences"


def test_a_value_change_is_structural_and_names_the_node():
    after = copy.deepcopy(surface())
    _node(after, "form/distance")["value"] = 12.5
    diff = diff_snapshots(surface(), after)
    assert bool(diff)
    assert [(change.where, change.field) for change in diff.changes] == [
        ("form/distance", "value")
    ]
    assert "form/distance: value 0.0 -> 12.5" in diff.render()


def test_a_pixel_only_change_does_not_fail_an_approval():
    after = surface(screenshot="sha256:bbbb")
    diff = diff_snapshots(surface(), after)
    assert not structural_change(surface(), after)
    assert not diff
    assert diff.identical is False
    assert "the structure did not" in diff.render()


def test_a_state_change_is_structural():
    after = copy.deepcopy(surface())
    _node(after, "buttons/run")["state"] = {
        "enabled": False,
        "visible": True,
        "focus": False,
    }
    diff = diff_snapshots(surface(), after)
    assert [(change.field) for change in diff.changes] == ["state"]
    assert '"enabled": True' in diff.render() or "enabled" in diff.render()


def test_an_added_and_a_removed_node_are_each_reported():
    after = copy.deepcopy(surface())
    _node(after, "root")["children"] = [
        node for node in _node(after, "root")["children"] if node["id"] != "buttons/run"
    ]
    _node(after, "root")["children"].append(
        {
            "id": "form/name",
            "role": "textbox",
            "type": "QLineEdit",
            "value": "",
            "label": "Name",
            "state": {"enabled": True, "visible": True, "focus": False},
            "geometry": {"x": 0, "y": 0, "width": 100, "height": 20},
            "declared": {"field": "name"},
        }
    )
    diff = diff_snapshots(surface(), after)
    fields = {(change.where, change.field) for change in diff.changes}
    assert ("buttons/run", "node") in fields
    assert ("form/name", "node") in fields
    assert structural_change(surface(), after)


def test_reordering_the_same_nodes_is_structural():
    after = copy.deepcopy(surface())
    children = _node(after, "root")["children"]
    children.reverse()
    diff = diff_snapshots(surface(), after)
    assert [change.field for change in diff.changes] == ["child order"]
    assert structural_change(surface(), after)


def test_a_new_ui001_finding_is_structural():
    after = surface(
        findings=[
            {
                "rule": "UI001",
                "node": "#3",
                "message": "QPushButton has no objectName",
            }
        ]
    )
    diff = diff_snapshots(surface(), after)
    assert [change.field for change in diff.changes] == ["findings"]
    assert "UI001" in diff.render()


def test_a_capture_without_a_screenshot_differs_only_in_pixels():
    after = surface(screenshot=None)
    diff = diff_snapshots(surface(), after)
    assert not diff
    assert "screenshot" in diff.render()


def test_the_report_is_bounded_and_says_how_many_were_hidden():
    after = copy.deepcopy(surface())
    for node in _node(after, "root")["children"]:
        node["state"] = {"enabled": False, "visible": False, "focus": True}
        node["geometry"] = {"x": 1, "y": 1, "width": 1, "height": 1}
    diff = diff_snapshots(surface(), after)
    rendered = diff.render(limit=3)
    assert len(rendered.splitlines()) == 4
    assert rendered.splitlines()[-1].startswith("... ")
    assert "more difference(s)" in rendered


def test_a_different_surface_is_reported_by_name():
    after = surface(surface="other", kind="dock", title="Other")
    diff = diff_snapshots(surface(), after)
    fields = [change.field for change in diff.changes]
    assert fields[:3] == ["surface", "kind", "title"]
    assert structural_change(surface(), after)
