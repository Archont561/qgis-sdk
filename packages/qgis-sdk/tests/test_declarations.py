"""Public declaration and generated-description contract, without a host runtime."""

import json

import pytest
from qgis_sdk import QgisSdkDeclarationError, action, describe_plugin, plugin
from qgis_sdk.declarations import _schema


def test_plain_plugin_is_inspected_without_constructing_or_running_it():
    @plugin(id="example.tools", title="Example")
    class Tools:
        def __init__(self, ctx):
            raise AssertionError("inspection must not construct")

        @action(id="hello", title="Say hello")
        def hello(self) -> str:
            raise AssertionError("inspection must not dispatch")

    description = describe_plugin(Tools)
    assert json.loads(description.to_json()) == {
        "schema_version": 1,
        "id": "example.tools",
        "title": "Example",
        "actions": [
            {
                "id": "hello",
                "title": "Say hello",
                "handler": "hello",
                "request": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "result": {"type": "string"},
            }
        ],
    }


def test_dataclass_request_and_result_preserve_required_nullable_and_safe_integers():
    from dataclasses import dataclass, field

    @dataclass
    class Request:
        count: int
        label: str | None = None
        tags: list[str] = field(
            default_factory=lambda: (_ for _ in ()).throw(AssertionError())
        )

    @plugin(id="sample", title="Sample")
    class Sample:
        @action(id="run", title="Run")
        def run(self, request: Request) -> Request:
            pass

    description = describe_plugin(Sample).to_dict()["actions"][0]
    assert description["request"] == {
        "type": "object",
        "properties": {
            "request": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "minimum": -9007199254740991,
                        "maximum": 9007199254740991,
                    },
                    "label": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["count"],
                "additionalProperties": False,
            }
        },
        "required": ["request"],
        "additionalProperties": False,
    }
    assert description["result"]["required"] == ["count", "label", "tags"]


def test_inherited_actions_are_sorted_and_overrides_follow_python_lookup():
    class Base:
        @action(id="z", title="Z")
        def last(self) -> None:
            pass

        @action(id="removed", title="Removed")
        def removed(self) -> None:
            pass

    @plugin(id="example", title="Example")
    class Example(Base):
        removed = None

        @property
        def native(self):
            raise AssertionError("do not evaluate descriptors")

        @action(id="a", title="A")
        def first(self, *, enabled: bool = False) -> float:
            return 1.0

    description = describe_plugin(Example)
    assert [item.id for item in description.actions] == ["a", "z"]
    assert description.actions[0].request == {
        "type": "object",
        "properties": {"enabled": {"type": "boolean"}},
        "additionalProperties": False,
    }
    assert description.actions[0].result == {"type": "number"}
    assert description.actions[1].result == {"type": "null"}
    assert description.to_json() == describe_plugin(Example).to_json()
    value = description.to_dict()
    value["actions"][0]["request"].clear()
    assert description.actions[0].request["type"] == "object"


def test_literal_values_and_resolvable_forward_references():
    from typing import Literal

    @plugin(id="example", title="Example")
    class Example:
        @action(id="choose", title="Choose")
        def choose(self, mode: Literal["fast", "safe"]) -> "str":
            return mode

    assert describe_plugin(Example).actions[0].request["properties"] == {
        "mode": {"enum": ["fast", "safe"]}
    }


@pytest.mark.parametrize("decorator", [plugin, action])
@pytest.mark.parametrize(
    "metadata",
    [
        {"id": "", "title": "Title"},
        {"id": "has space", "title": "Title"},
        {"id": "valid", "title": " "},
    ],
)
def test_invalid_metadata_is_actionable(decorator, metadata):
    with pytest.raises(QgisSdkDeclarationError, match="id|title"):
        decorator(**metadata)


@pytest.mark.parametrize("value", [None, object, object()])
def test_inspection_requires_explicit_plugin_metadata(value):
    with pytest.raises(QgisSdkDeclarationError, match="@plugin"):
        describe_plugin(value)


def test_duplicate_decorators_and_wrong_targets_are_rejected():
    with pytest.raises(QgisSdkDeclarationError, match="class"):
        plugin(id="p", title="P")(lambda: None)
    with pytest.raises(QgisSdkDeclarationError, match="instance method"):
        action(id="a", title="A")(object)

    @plugin(id="p", title="P")
    class Plugin:
        pass

    with pytest.raises(QgisSdkDeclarationError, match="duplicate @plugin"):
        plugin(id="p", title="P")(Plugin)

    @action(id="a", title="A")
    def handler(self) -> None:
        pass

    with pytest.raises(QgisSdkDeclarationError, match="duplicate @action"):
        action(id="b", title="B")(handler)


def test_duplicate_action_ids_identify_the_conflicting_binding():
    @plugin(id="p", title="P")
    class Plugin:
        @action(id="a", title="A")
        def first(self) -> None:
            pass

        @action(id="a", title="A")
        def second(self) -> None:
            pass

    with pytest.raises(QgisSdkDeclarationError, match="a: duplicate id at second"):
        describe_plugin(Plugin)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("def handler(): pass", "first parameter must be self"),
        ("def handler(self, *args) -> None: pass", "variadic"),
        ("def handler(self, x, /) -> None: pass", "positional-only"),
        ("def handler(self, x) -> None: pass", "handler.*x: unsupported annotation"),
        ("def handler(self): pass", "return: unsupported annotation"),
        ("def handler(self, x: object) -> None: pass", "unsupported annotation"),
        (
            "def handler(self, x: 'MissingType') -> None: pass",
            "cannot resolve annotations",
        ),
        ("async def handler(self) -> None: pass", "synchronous instance method"),
        ("def handler(self) -> None: yield None", "synchronous instance method"),
    ],
)
def test_invalid_handler_reports_action_and_location(source, message):
    namespace = {}
    exec(source, namespace)  # noqa: S102 -- fixed test-only signature fixtures
    cls = plugin(id="p", title="P")(
        type(
            "Plugin",
            (),
            {"handler": action(id="run", title="Run")(namespace["handler"])},
        )
    )
    with pytest.raises(QgisSdkDeclarationError, match=message):
        describe_plugin(cls)


@pytest.mark.parametrize("wrapper", [staticmethod, classmethod])
def test_static_and_class_actions_are_rejected(wrapper):
    def handler(self) -> None:
        pass

    cls = plugin(id="p", title="P")(
        type("Plugin", (), {"handler": wrapper(action(id="run", title="Run")(handler))})
    )
    with pytest.raises(QgisSdkDeclarationError, match="synchronous instance method"):
        describe_plugin(cls)


@pytest.mark.parametrize("annotation", [dict[str, str], list, "MissingType"])
def test_unsupported_input_contracts_fail_closed(annotation):
    def handler(self, request) -> None:
        pass

    handler.__annotations__["request"] = annotation
    cls = plugin(id="p", title="P")(
        type("Plugin", (), {"handler": action(id="run", title="Run")(handler)})
    )
    with pytest.raises(
        QgisSdkDeclarationError,
        match="action run.*(unsupported annotation|cannot resolve annotations)",
    ):
        describe_plugin(cls)


def test_recursive_and_unsafe_literal_contracts_are_rejected():
    from dataclasses import make_dataclass
    from typing import Literal

    recursive = make_dataclass("Recursive", [("child", object)])
    recursive.__annotations__["child"] = recursive
    for annotation, message in [
        (recursive, "recursive"),
        (Literal[9007199254740992], "safe-integer"),
        (Literal[1.5], "Literal supports"),
    ]:

        def handler(self, request) -> None:
            pass

        handler.__annotations__["request"] = annotation
        cls = plugin(id="p", title="P")(
            type("Plugin", (), {"handler": action(id="run", title="Run")(handler)})
        )
        with pytest.raises(QgisSdkDeclarationError, match=message):
            describe_plugin(cls)


def test_declaration_errors_share_sdk_error_boundary():
    from qgis_sdk.models import QgisSdkError

    with pytest.raises(QgisSdkError) as error:
        plugin(id="invalid id", title="Example")
    assert error.value.code == "invalid_declaration"


def test_generated_schemas_validate_json_values_independently():
    from jsonschema import Draft202012Validator

    @plugin(id="p", title="P")
    class Plugin:
        @action(id="run", title="Run")
        def run(self, count: int, label: str | None = None) -> list[int]:
            return []

    description = describe_plugin(Plugin).actions[0]
    for schema in (description.request, description.result):
        Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(description.request)
    assert validator.is_valid({"count": 2.0})
    assert validator.is_valid({"count": 9007199254740991, "label": None})
    for value in (
        {},
        {"count": True},
        {"count": "2"},
        {"count": 2.5},
        {"count": 9007199254740992},
        {"count": 2, "extra": 1},
    ):
        assert not validator.is_valid(value)
    result = Draft202012Validator(description.result)
    assert result.is_valid([1, 2])
    assert not result.is_valid([False])


def test_action_hidden_inside_property_is_rejected_not_silently_dropped():
    @plugin(id="p", title="P")
    class Plugin:
        @property
        @action(id="bad", title="Bad")
        def bad(self) -> str:
            raise AssertionError("never evaluate")

    with pytest.raises(
        QgisSdkDeclarationError, match="ordinary synchronous instance method"
    ):
        describe_plugin(Plugin)


def test_bare_generic_and_unhashable_annotation_metadata_fail_actionably():
    from typing import List  # noqa: UP035 -- exercise rejected legacy bare generic

    # A bare generic still has no element type to describe. `Annotated` used to
    # be refused here as well; TASK-39 made it part of the subset (the extras are
    # host hints, the stored type is what the schema describes), so it is no
    # longer in this list.
    for annotation in (List,):  # noqa: UP006

        def handler(self, value) -> None:
            pass

        handler.__annotations__["value"] = annotation
        cls = plugin(id="p", title="P")(
            type("Plugin", (), {"handler": action(id="run", title="Run")(handler)})
        )
        with pytest.raises(
            QgisSdkDeclarationError, match="action run.*unsupported annotation"
        ):
            describe_plugin(cls)


def test_variadic_tuple_generates_the_same_json_array_as_a_list():
    """A tuple is the wire's one array type, so it must not need a second spelling.

    Immutable value DTOs (VectorLayerInfo, StyleSpec and later result handles)
    describe their collections as tuples. Refusing them would force mutable fields
    into frozen dataclasses purely to satisfy the generator.
    """

    @plugin(id="p", title="P")
    class Plugin:
        @action(id="run", title="Run")
        def run(self, tags: tuple[str, ...]) -> tuple[int, ...]:
            return ()

    description = describe_plugin(Plugin).actions[0]

    assert description.request["properties"]["tags"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    # Spelled out, not imported from the constant that produced it.
    assert description.result == {
        "type": "array",
        "items": {
            "type": "integer",
            "minimum": -9007199254740991,
            "maximum": 9007199254740991,
        },
    }


def test_variadic_tuple_of_a_dataclass_describes_the_object_items():
    from dataclasses import dataclass

    @dataclass
    class Item:
        name: str

    @plugin(id="p", title="P")
    class Plugin:
        @action(id="run", title="Run")
        def run(self, items: tuple[Item, ...]) -> None: ...

    request = describe_plugin(Plugin).actions[0].request

    assert request["properties"]["items"]["items"]["properties"] == {
        "name": {"type": "string"}
    }


@pytest.mark.parametrize(
    ("annotation", "message"),
    [
        # Bare `tuple` carries no element type at all: the generic refusal.
        (tuple, "unsupported annotation"),
        # A typed but non-variadic tuple gets the specific refusal.
        (tuple[str], "variadic"),
        (tuple[str, int], "variadic"),
    ],
)
def test_a_tuple_without_one_ellipsis_element_is_rejected(annotation, message):
    """Fixed-length and bare tuples have no JSON Schema counterpart here.

    Accepting them would either lose the length or silently pick a branch, so the
    generator refuses instead of emitting a looser schema than the annotation.
    """
    handler = action(id="run", title="Run")(_handler_annotated(annotation))
    Plugin = plugin(id="p", title="P")(type("Plugin", (), {"run": handler}))

    with pytest.raises(QgisSdkDeclarationError, match=message):
        describe_plugin(Plugin)


def test_a_union_of_variadic_tuples_is_expressible_as_a_branch():
    """Each arm is a legal array, so the union is legal too - no over-refusal."""

    handler = action(id="run", title="Run")(
        _handler_annotated(tuple[str, ...] | tuple[int, ...])
    )
    Plugin = plugin(id="p", title="P")(type("Plugin", (), {"run": handler}))

    request = describe_plugin(Plugin).actions[0].request

    assert [
        branch["items"]["type"] for branch in request["properties"]["value"]["anyOf"]
    ] == [
        "string",
        "integer",
    ]


def _handler_annotated(annotation):
    """Return a plain instance method declaring ``value: annotation``."""

    def handler(self, value): ...

    handler.__annotations__.update({"value": annotation, "return": type(None)})
    return handler


@pytest.mark.parametrize("dto", ["VectorLayerInfo", "StyleSpec"])
def test_bridge_eligible_service_payloads_stay_generatable(dto):
    """The service DTOs are bridge-eligible, so the generator must accept them.

    TASK-17 generates TypeScript from these payloads. Until this rule existed the
    instruction to "use primitives, list, union, Literal or a dataclass" rejected
    their `tuple[str, ...]` fields, so an unsupported annotation could have sat
    unnoticed in an already-qualified service contract.
    """
    from qgis_sdk import models

    schema = _schema(getattr(models, dto), dto, result=False)

    array_properties = {
        name: value
        for name, value in schema["properties"].items()
        if value.get("type") == "array"
    }
    assert array_properties, f"{dto} is expected to expose a collection field"
    assert all(
        value["items"] == {"type": "string"} for value in array_properties.values()
    )
