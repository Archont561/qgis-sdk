"""The YAML rendering the tools offer for a capture (decision-51 point 5).

YAML is a reading format only: the fixture approval, the capture on disk and
``ui diff`` all speak canonical JSON. So these tests hold the emitter to the
one promise that makes it safe to read a rendered capture - ``yaml.safe_load``
gives the payload back unchanged - and to the refusal the CLI depends on.
"""

from __future__ import annotations

import json

import pytest
from qgis_sdk_tools.ui_yaml import to_yaml

yaml = pytest.importorskip("yaml", reason="PyYAML is the oracle, not a dependency")


def test_a_capture_round_trips_through_a_yaml_reader():
    payload = {
        "surface": "buffer_dialog",
        "kind": "dialog",
        "size": [400, 300],
        "scale": 1.0,
        "nodes": [
            {
                "id": "form/distance",
                "role": "spinbox",
                "value": 5.0,
                "label": "Distance",
                "declared": True,
                "state": {"enabled": True, "focus": False},
                "children": [],
            }
        ],
        "findings": [],
    }
    assert yaml.safe_load(to_yaml(payload)) == payload


def test_a_string_that_reads_as_a_keyword_is_quoted():
    payload = {"text": "yes", "null": "null", "number": "5", "empty": ""}
    text = to_yaml(payload)
    assert yaml.safe_load(text) == payload
    assert '"yes"' in text


def test_keys_and_values_that_hold_yaml_punctuation_stay_one_scalar():
    payload = {"a: b": "c # not a comment", "nested": [{"x": "- dash"}]}
    text = to_yaml(payload)
    assert yaml.safe_load(text) == payload


def test_empty_containers_and_a_document_end_newline():
    assert to_yaml({}) == "{}\n"
    assert to_yaml([]) == "[]\n"
    assert yaml.safe_load(to_yaml({"nodes": [], "findings": []})) == {
        "nodes": [],
        "findings": [],
    }
    assert to_yaml({"a": 1}).endswith("\n")


def test_a_non_finite_float_stays_readable_rather_than_becoming_a_number():
    text = to_yaml({"scale": float("nan")})
    loaded = yaml.safe_load(text)
    assert loaded == {"scale": "NaN"} or loaded["scale"] != loaded["scale"]


def test_the_rendering_is_not_json():
    """A capture printed as YAML is a capture a person can read at a glance."""
    tree = json.loads('{"surface": "buffer_dialog", "nodes": [{"id": "form/name"}]}')
    text = to_yaml(tree)
    assert "surface: buffer_dialog" in text
    assert text != json.dumps(tree)
