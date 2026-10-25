"""The provider: registration is validated where a plugin author can see it fail."""

from __future__ import annotations

from dataclasses import dataclass, make_dataclass
from typing import Annotated, Literal

import pytest
from qgis_sdk.algorithms import describe_algorithm
from qgis_sdk.declarations import QgisSdkDeclarationError
from qgis_sdk.models import (
    CrsInput,
    LayerInput,
    Metres,
    VectorLayerInfo,
)
from qgis_sdk.providers import Provider, ProviderDescription, parameter_kinds
from qgis_sdk.reference import BufferLayer, reference_provider


@dataclass(frozen=True, slots=True)
class Result:
    output: VectorLayerInfo


@dataclass(frozen=True, slots=True)
class Request:
    layer_id: Annotated[str, LayerInput()]
    distance: Annotated[float, Metres()]
    note: str = "note"


def _provider() -> Provider:
    return Provider(id="test", title="Test provider")


def _run(self, inputs: Request) -> Result:
    raise AssertionError("registration must not run anything")


def test_a_provider_describes_its_algorithms_with_qualified_ids() -> None:
    provider = _provider()

    @provider.algorithm(id="buffer", title="Buffer", group="Geometry")
    class Buffer:
        run = _run

    description = provider.describe()

    assert isinstance(description, ProviderDescription)
    payload = description.to_dict()
    assert (payload["id"], payload["title"]) == ("test", "Test provider")
    assert payload["algorithms"][0]["qualified_id"] == "test:buffer"
    assert payload["algorithms"][0]["group"] == "Geometry"
    assert payload["algorithms"][0]["parameters"] == {
        "layer_id": "layer",
        "distance": "metres",
        "note": "string",
    }


def test_registration_attaches_the_metadata_describe_needs() -> None:
    provider = _provider()

    @provider.algorithm(id="plain", title="Plain")
    class Plain:
        run = _run

    assert describe_algorithm(Plain).id == "plain"
    assert provider.algorithms == (Plain,)
    assert provider.class_for("plain") is Plain


def test_a_duplicate_id_is_refused() -> None:
    provider = _provider()

    @provider.algorithm(id="once", title="Once")
    class Once:
        run = _run

    with pytest.raises(QgisSdkDeclarationError, match="duplicate algorithm id"):

        @provider.algorithm(id="once", title="Again")
        class Again:
            run = _run


def test_a_class_cannot_be_registered_on_two_providers() -> None:
    provider = _provider()

    @provider.algorithm(id="mine", title="Mine")
    class Mine:
        run = _run

    with pytest.raises(QgisSdkDeclarationError, match="already declared"):
        _provider().algorithm(id="mine", title="Mine")(Mine)


def test_decorating_a_non_class_is_refused() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="requires a class"):
        _provider().algorithm(id="fn", title="Fn")(lambda: None)


def test_an_empty_group_is_refused() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="group must be a nonempty"):
        _provider().algorithm(id="g", title="G", group=" ")


@pytest.mark.parametrize("bad_id", ["1abc", "has space", ""])
def test_the_provider_uses_the_shared_id_grammar(bad_id: str) -> None:
    with pytest.raises(QgisSdkDeclarationError, match="Invalid declaration id"):
        Provider(id=bad_id, title="Bad")


def test_a_request_without_run_is_refused_at_registration() -> None:
    provider = _provider()

    with pytest.raises(QgisSdkDeclarationError, match="needs its own run method"):

        @provider.algorithm(id="norun", title="No run")
        class NoRun:
            pass

    assert provider.algorithms == ()


def test_a_refused_registration_leaves_the_class_undeclared() -> None:
    """A half-declared class would describe but never be registered."""
    provider = _provider()
    # The wire schema accepts a variadic tuple; a QGIS parameter list does not,
    # so this refuses one step later - still at registration, never at run time.
    Unrepresentable = make_dataclass("Unrepresentable", [("names", tuple[str, ...])])
    Bad = type(
        "Bad",
        (),
        {"run": lambda self, inputs: Result(output=None), "__annotations__": {}},
    )
    Bad.run.__annotations__ = {"inputs": Unrepresentable, "return": Result}

    with pytest.raises(QgisSdkDeclarationError, match="cannot express"):
        provider.algorithm(id="bad", title="Bad")(Bad)

    assert provider.algorithms == ()
    # The marker was removed again, so a fixed class can still be registered.
    Good = type("Good", (), {"run": _run})
    assert _provider().algorithm(id="good", title="Good")(Good) is Good


def test_an_unrepresentable_field_names_the_field_and_the_markers() -> None:
    @dataclass(frozen=True, slots=True)
    class Nested:
        inner: list[str]

    with pytest.raises(QgisSdkDeclarationError) as error:
        parameter_kinds(Nested)

    assert "Nested.inner" in str(error.value)
    assert "use Annotated markers" in str(error.value)


@pytest.mark.parametrize(
    ("annotation", "message"),
    [
        (Annotated[int, LayerInput()], "must be a str layer id"),
        (Annotated[int, CrsInput()], "must be a str authority code"),
        (Annotated[str, Metres()], "must be a number"),
        (Annotated[str, "unknown"], "unknown parameter marker"),
    ],
)
def test_a_marker_that_does_not_fit_its_type_is_refused(annotation, message) -> None:
    Wrong = make_dataclass("Wrong", [("value", annotation)])

    with pytest.raises(QgisSdkDeclarationError, match=message):
        parameter_kinds(Wrong)


def test_primitives_map_to_their_own_kinds() -> None:
    @dataclass(frozen=True, slots=True)
    class Primitives:
        text: str
        number: float
        count: int
        flag: bool

    assert parameter_kinds(Primitives) == (
        ("text", "string"),
        ("number", "number"),
        ("count", "integer"),
        ("flag", "boolean"),
    )


def test_a_literal_field_is_refused_rather_than_guessed() -> None:
    @dataclass(frozen=True, slots=True)
    class WithLiteral:
        mode: Literal["a", "b"]

    with pytest.raises(QgisSdkDeclarationError, match="cannot express"):
        parameter_kinds(WithLiteral)


def test_an_annotated_field_still_describes_its_stored_type() -> None:
    from qgis_sdk.declarations import _schema

    schema = _schema(Request, "request", result=False)

    assert schema["properties"]["layer_id"] == {"type": "string"}
    assert schema["properties"]["distance"] == {"type": "number"}


def test_parameter_kinds_requires_a_dataclass_type() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="must be a dataclass type"):
        parameter_kinds("not a type")


def test_a_provider_reports_its_own_id_and_title() -> None:
    provider = Provider(id="shown", title="Shown provider")

    assert (provider.id, provider.title) == ("shown", "Shown provider")


def test_asking_for_an_unregistered_algorithm_names_the_provider() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="test: no algorithm 'ghost'"):
        _provider().class_for("ghost")


def test_the_reference_provider_registers_the_workflow_operations() -> None:
    described = reference_provider.describe()

    assert reference_provider.id == "reference"
    assert [item.description.id for item in described.algorithms] == [
        "buffer",
        "centroid",
    ]
    algorithms = reference_provider.algorithms
    assert algorithms[0] is BufferLayer
    assert describe_algorithm(algorithms[1]).inputs_type.__name__ == "CentroidRequest"
