"""Ids and titles default from the decorated name; an explicit value still wins.

A class id carries a short deterministic suffix hashed from the class's module
and qualified name, so two plugins (or algorithms, or jobs) that happen to share
a class name do not collide, while the same class always derives the same id.
A method id is the plain method name: it is already unique inside its class,
and the bridge client spells it as a property, so it stays a plain identifier.
"""

import hashlib
import re
from typing import Any

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from qgis_sdk import QgisSdkDeclarationError, action, describe_plugin, plugin, stream
from qgis_sdk.algorithms import describe_algorithm
from qgis_sdk.core import AlgorithmContext, JobContext
from qgis_sdk.declarations import derive_id, derive_title
from qgis_sdk.jobs import describe_job, job
from qgis_sdk.models import VectorLayerInfo
from qgis_sdk.providers import Provider


def suffix(cls: Any) -> str:
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


def test_jobs_derive_their_ids_with_a_suffix_and_provider_algorithms_without() -> None:
    mine = Provider(id="mine", title="Mine")

    @mine.algorithm
    def smooth_geometries(ctx: AlgorithmContext) -> VectorLayerInfo:
        raise AssertionError("never run")

    @mine.algorithm(group="Geometry")
    def buffer(ctx: AlgorithmContext) -> VectorLayerInfo:
        raise AssertionError("never run")

    @job(title="Sum")
    def add_numbers(ctx: JobContext, value: int) -> int:
        return value

    smooth = describe_algorithm(smooth_geometries)
    add = describe_job(add_numbers)

    # A job id must stay unique across modules, so it carries the hash suffix;
    # a provider algorithm is namespaced by its provider and keeps the plain
    # name, which is what the toolbox shows as ``mine:buffer``.
    assert (smooth.id, smooth.title) == ("smooth_geometries", "Smooth geometries")
    assert describe_algorithm(buffer).qualified_id == "mine:buffer"
    assert mine.function_for("buffer") is buffer
    assert add.id == f"add_numbers_{suffix(add_numbers)}"
    assert add.title == "Sum"


def test_an_explicit_invalid_id_is_still_refused_before_the_class_exists() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="Invalid declaration id"):
        plugin(id="9bad")
    with pytest.raises(QgisSdkDeclarationError, match="title must be a nonempty"):
        action(title="  ")


#: Python names a decorator sees: CamelCase, snake_case, digits, a leading
#: underscore; short, so a shrunk counterexample reads at a glance.
python_names = st.from_regex(r"\A_{0,2}[A-Za-z][A-Za-z0-9_]{0,11}\Z")


@given(name=python_names)
@settings(max_examples=60, deadline=None, derandomize=True)
@example(name="FieldTools")
@example(name="HTTPServer")
@example(name="_private_helper")
@example(name="Version2Check")
def test_a_derived_id_is_a_lower_snake_case_identifier_and_a_fixed_point(
    name: str,
) -> None:
    derived = derive_id(name)
    assert re.fullmatch(r"[a-z][a-z0-9_]*", derived), derived
    assert derive_id(derived) == derived  # deriving again changes nothing
    # Every letter and digit of the name survives, in order; only case and
    # underscores move.
    assert derived.replace("_", "") == name.replace("_", "").lower()


@given(name=python_names)
@settings(max_examples=60, deadline=None, derandomize=True)
@example(name="list_layers")
@example(name="run")
def test_a_derived_title_keeps_camel_case_words_and_sentences_snake_case(
    name: str,
) -> None:
    title = derive_title(name)
    words = title.split(" ")
    assert words and all(words)
    assert title[0].isupper() or title[0].isdigit()
    assert "_" not in title
    if any(char.isupper() for char in name):
        # CamelCase keeps its casing: the words of the title are the words of the id
        assert [w.lower() for w in words] == derive_id(name).split("_")
    else:
        assert words[1:] == derive_id(name).split("_")[1:]


@pytest.mark.parametrize(
    ("name", "id", "title"),
    [
        ("HTTPServer", "http_server", "HTTP Server"),
        ("Version2Check", "version2_check", "Version2 Check"),
    ],
)
def test_the_word_boundary_rule_on_its_two_hard_cases(
    name: str, id: str, title: str
) -> None:
    assert derive_id(name) == id
    assert derive_title(name) == title
