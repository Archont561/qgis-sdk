"""Ids and titles default from the decorated name; an explicit value still wins.

A class id carries a short deterministic suffix hashed from the class's module
and qualified name, so two plugins (or algorithms, or jobs) that happen to share
a class name do not collide, while the same class always derives the same id.
A method id is the plain method name: it is already unique inside its class,
and the bridge client spells it as a property, so it stays a plain identifier.
"""

import hashlib
from dataclasses import dataclass

import pytest
from qgis_sdk import QgisSdkDeclarationError, action, describe_plugin, plugin, stream
from qgis_sdk.algorithms import algorithm, describe_algorithm
from qgis_sdk.declarations import derive_id, derive_title
from qgis_sdk.jobs import describe_job, job
from qgis_sdk.providers import Provider


@dataclass
class Inputs:
    count: int


def suffix(cls: type) -> str:
    return hashlib.sha256(f"{cls.__module__}.{cls.__qualname__}".encode()).hexdigest()[
        :6
    ]


def test_a_bare_plugin_decorator_derives_the_id_and_title_from_the_class() -> None:
    @plugin
    class FieldTools:
        @action
        def list_layers(self) -> list[str]:
            raise AssertionError("inspection must not dispatch")

    description = describe_plugin(FieldTools)

    assert description.id == f"field_tools_{suffix(FieldTools)}"
    assert description.title == "Field Tools"
    assert description.actions[0].id == "list_layers"
    assert description.actions[0].title == "List layers"
    assert description.actions[0].handler == "list_layers"


def test_the_derived_class_id_is_stable_and_differs_between_classes() -> None:
    def first() -> type:
        @plugin()
        class Tools:
            pass

        return Tools

    def second() -> type:
        @plugin()
        class Tools:
            pass

        return Tools

    assert describe_plugin(first()).id == describe_plugin(first()).id
    assert describe_plugin(first()).id != describe_plugin(second()).id
    assert describe_plugin(first()).id.startswith("tools_")


def test_an_explicit_id_or_title_overrides_the_derived_one() -> None:
    @plugin(id="example.tools")
    class FieldTools:
        @action(title="Layers")
        def list_layers(self) -> list[str]:
            raise AssertionError("inspection must not dispatch")

        @action(id="layers.count")
        def count_layers(self) -> int:
            raise AssertionError("inspection must not dispatch")

    description = describe_plugin(FieldTools)

    assert (description.id, description.title) == ("example.tools", "Field Tools")
    assert [(item.id, item.title) for item in description.actions] == [
        ("layers.count", "Count layers"),
        ("list_layers", "Layers"),
    ]


def test_a_stream_without_an_id_is_named_after_its_method() -> None:
    @plugin
    class Tools:
        @stream(events={"data": int})
        def tick(self) -> None:
            raise AssertionError("inspection must not dispatch")

    description = describe_plugin(Tools)

    assert description.streams[0].id == "tick"
    assert description.streams[0].title == "Tick"


def test_algorithms_and_jobs_derive_their_ids_the_same_way() -> None:
    @algorithm
    class SmoothGeometries:
        def run(self, inputs: int) -> int:
            return inputs

    @job(title="Sum")
    class AddNumbers:
        def run(self, inputs: int) -> int:
            return inputs

    smooth = describe_algorithm(SmoothGeometries)
    add = describe_job(AddNumbers)

    assert smooth.id == f"smooth_geometries_{suffix(SmoothGeometries)}"
    assert smooth.title == "Smooth Geometries"
    assert add.id == f"add_numbers_{suffix(AddNumbers)}"
    assert add.title == "Sum"


def test_a_provider_algorithm_derives_its_id_from_the_class() -> None:
    mine = Provider(id="mine", title="Mine")

    @mine.algorithm
    class Smooth:
        def run(self, inputs: Inputs) -> int:
            return inputs.count

    @mine.algorithm(group="Geometry")
    class Buffer:
        def run(self, inputs: Inputs) -> int:
            return inputs.count

    ids = {describe_algorithm(cls).id for cls in mine.algorithms}

    assert ids == {f"smooth_{suffix(Smooth)}", f"buffer_{suffix(Buffer)}"}
    assert mine.class_for(f"buffer_{suffix(Buffer)}") is Buffer


def test_an_explicit_invalid_id_is_still_refused_before_the_class_exists() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="Invalid declaration id"):
        plugin(id="9bad")
    with pytest.raises(QgisSdkDeclarationError, match="title must be a nonempty"):
        action(title="  ")


@pytest.mark.parametrize(
    ("name", "id", "title"),
    [
        ("FieldTools", "field_tools", "Field Tools"),
        ("HTTPServer", "http_server", "HTTP Server"),
        ("list_layers", "list_layers", "List layers"),
        ("_private_helper", "private_helper", "Private helper"),
        ("Version2Check", "version2_check", "Version2 Check"),
        ("run", "run", "Run"),
    ],
)
def test_names_turn_into_snake_case_ids_and_readable_titles(
    name: str, id: str, title: str
) -> None:
    assert derive_id(name) == id
    assert derive_title(name) == title
