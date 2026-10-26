"""The provider: declaration is validated where a plugin author can see it fail."""

from __future__ import annotations

from typing import Annotated, Literal

import pytest
from qgis_sdk.algorithms import describe_algorithm, parameter_kind
from qgis_sdk.core import AlgorithmContext, JobContext
from qgis_sdk.declarations import QgisSdkDeclarationError, plugin
from qgis_sdk.models import (
    CrsInput,
    CrsParameter,
    LayerInput,
    LayerParameter,
    Metres,
    MetresParameter,
    VectorLayerInfo,
)
from qgis_sdk.providers import Provider, ProviderDescription, declared_providers
from sample_algorithms import buffer_layer, sample_provider


def _provider() -> Provider:
    return Provider(id="test", title="Test provider")


def _buffer(
    ctx: AlgorithmContext, layer_id: LayerInput, distance: Metres, note: str = "n"
) -> VectorLayerInfo:
    raise AssertionError("declaration must not run anything")


# -- what a declaration records ------------------------------------------------------


def test_a_provider_describes_its_algorithms_with_qualified_ids() -> None:
    provider = _provider()
    provider.algorithm(id="buffer", title="Buffer", group="Geometry")(_buffer)

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


def test_declaration_attaches_the_metadata_describe_needs() -> None:
    provider = _provider()

    @provider.algorithm(id="plain", title="Plain")
    def plain(ctx: AlgorithmContext) -> VectorLayerInfo: ...

    assert describe_algorithm(plain).id == "plain"
    assert describe_algorithm(plain).provider_id == "test"
    assert provider.algorithms == (plain,)
    assert provider.function_for("plain") is plain
    assert repr(provider) == "Provider(id='test', title='Test provider')"


def test_the_derived_id_is_the_plain_function_name() -> None:
    provider = _provider()

    @provider.algorithm
    def smooth_geometries(ctx: AlgorithmContext) -> VectorLayerInfo: ...

    @provider.algorithm(group="Geometry")
    def buffer(ctx: AlgorithmContext) -> VectorLayerInfo: ...

    described = [describe_algorithm(function) for function in provider.algorithms]

    # The provider is the namespace, so the toolbox shows ``test:buffer`` and
    # not a hashed suffix the way a cross-module ``@job`` id needs one.
    assert [item.id for item in described] == ["smooth_geometries", "buffer"]
    assert [item.title for item in described] == ["Smooth geometries", "Buffer"]
    assert [item.qualified_id for item in described] == [
        "test:smooth_geometries",
        "test:buffer",
    ]


def test_a_duplicate_id_is_refused() -> None:
    provider = _provider()

    @provider.algorithm(id="once", title="Once")
    def once(ctx: AlgorithmContext) -> VectorLayerInfo: ...

    with pytest.raises(QgisSdkDeclarationError, match="duplicate algorithm id"):

        @provider.algorithm(id="once", title="Again")
        def again(ctx: AlgorithmContext) -> VectorLayerInfo: ...

    assert provider.algorithms == (once,)


def test_a_function_cannot_be_declared_on_two_providers() -> None:
    provider = _provider()

    @provider.algorithm(id="mine", title="Mine")
    def mine(ctx: AlgorithmContext) -> VectorLayerInfo: ...

    with pytest.raises(QgisSdkDeclarationError, match="already declared"):
        _provider().algorithm(id="mine", title="Mine")(mine)


def test_the_class_form_is_refused_with_the_way_forward() -> None:
    class Buffer:
        def run(self, inputs: object) -> VectorLayerInfo: ...

    with pytest.raises(QgisSdkDeclarationError, match="class form was removed"):
        _provider().algorithm(id="buffer", title="Buffer")(Buffer)


def test_decorating_a_non_function_is_refused() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="requires a function"):
        _provider().algorithm(id="obj", title="Obj")(object())  # type: ignore[arg-type]


def test_an_empty_group_is_refused() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="group must be a nonempty"):
        _provider().algorithm(id="g", title="G", group=" ")


@pytest.mark.parametrize("bad_id", ["1abc", "has space", ""])
def test_the_provider_uses_the_shared_id_grammar(bad_id: str) -> None:
    with pytest.raises(QgisSdkDeclarationError, match="Invalid declaration id"):
        Provider(id=bad_id, title="Bad")


def test_an_explicit_bad_id_is_refused_before_the_function_exists() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="Invalid declaration id"):
        _provider().algorithm(id="9bad")


# -- the shape a declaration must have -----------------------------------------------


def test_a_missing_leading_context_parameter_is_refused() -> None:
    provider = _provider()

    with pytest.raises(QgisSdkDeclarationError, match="first parameter must be the"):

        @provider.algorithm
        def no_context(layer_id: LayerInput) -> VectorLayerInfo: ...

    with pytest.raises(QgisSdkDeclarationError, match="first parameter must be the"):

        @provider.algorithm
        def wrong_context(ctx: JobContext, layer_id: LayerInput) -> VectorLayerInfo: ...

    with pytest.raises(QgisSdkDeclarationError, match="first parameter must be the"):

        @provider.algorithm
        def nothing() -> VectorLayerInfo: ...

    assert provider.algorithms == ()


def test_a_coroutine_or_generator_is_refused() -> None:
    provider = _provider()

    with pytest.raises(QgisSdkDeclarationError, match="plain synchronous function"):

        @provider.algorithm
        async def later(ctx: AlgorithmContext) -> VectorLayerInfo: ...

    with pytest.raises(QgisSdkDeclarationError, match="plain synchronous function"):

        @provider.algorithm
        def stream(ctx: AlgorithmContext) -> VectorLayerInfo:
            yield  # type: ignore[misc]


def test_an_unannotated_input_or_result_is_refused() -> None:
    provider = _provider()

    with pytest.raises(QgisSdkDeclarationError, match="every input must be annotated"):

        @provider.algorithm
        def bare(ctx: AlgorithmContext, value) -> VectorLayerInfo: ...

    with pytest.raises(QgisSdkDeclarationError, match="must declare its result"):

        @provider.algorithm
        def silent(ctx: AlgorithmContext, value: str): ...


def test_a_result_that_is_not_the_produced_layer_is_refused() -> None:
    provider = _provider()

    with pytest.raises(QgisSdkDeclarationError, match="returns the VectorLayerInfo"):

        @provider.algorithm
        def count(ctx: AlgorithmContext) -> int: ...


def test_an_input_outside_the_parameter_kinds_is_refused_naming_it() -> None:
    provider = _provider()

    def nested(ctx: AlgorithmContext, inner: list[str]) -> VectorLayerInfo: ...

    with pytest.raises(QgisSdkDeclarationError) as error:
        provider.algorithm(nested)

    assert "algorithm test:nested.inner" in str(error.value)
    assert "use Annotated markers" in str(error.value)
    # The refused function keeps no marker: it neither describes nor registers.
    assert provider.algorithms == ()
    with pytest.raises(QgisSdkDeclarationError, match="requires a function with"):
        describe_algorithm(nested)


def test_a_literal_input_is_refused_rather_than_guessed() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="cannot express"):

        @_provider().algorithm
        def mode(ctx: AlgorithmContext, mode: Literal["a", "b"]) -> VectorLayerInfo: ...


def test_a_variadic_input_is_refused() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="variadic"):

        @_provider().algorithm
        def many(ctx: AlgorithmContext, *values: str) -> VectorLayerInfo: ...


@pytest.mark.parametrize(
    ("annotation", "message"),
    [
        (Annotated[int, LayerParameter()], "must be a str layer id"),
        (Annotated[int, CrsParameter()], "must be a str authority code"),
        (Annotated[str, MetresParameter()], "must be a number"),
        (Annotated[str, "unknown"], "unknown parameter marker"),
    ],
)
def test_a_marker_that_does_not_fit_its_type_is_refused(annotation, message) -> None:
    with pytest.raises(QgisSdkDeclarationError, match=message):
        parameter_kind("test.value", annotation)


def test_primitives_and_aliases_map_to_their_own_kinds() -> None:
    assert [
        parameter_kind("p", annotation)
        for annotation in (str, float, int, bool, LayerInput, CrsInput, Metres)
    ] == ["string", "number", "integer", "boolean", "layer", "crs", "metres"]
    assert parameter_kind("p", Annotated[int, MetresParameter()]) == "metres"


def test_an_annotated_input_still_describes_its_stored_type() -> None:
    schema = describe_algorithm(buffer_layer).inputs_schema

    assert schema["properties"]["layer_id"] == {"type": "string"}
    assert schema["properties"]["distance_metres"] == {"type": "number"}


def test_a_provider_reports_its_own_id_and_title() -> None:
    provider = Provider(id="shown", title="Shown provider")

    assert (provider.id, provider.title) == ("shown", "Shown provider")


def test_asking_for_an_undeclared_algorithm_names_the_provider() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="test: no algorithm 'ghost'"):
        _provider().function_for("ghost")


def test_the_sample_provider_declares_the_workflow_operations() -> None:
    described = sample_provider.describe()

    assert sample_provider.id == "sample"
    assert [item.id for item in described.algorithms] == ["buffer", "centroid"]
    assert sample_provider.algorithms[0] is buffer_layer


# -- providers = [...] on a plugin class ---------------------------------------------


def test_a_plugin_lists_the_providers_it_owns() -> None:
    tools = Provider(id="tools", title="Tools")

    @plugin
    class WithProviders:
        providers = [tools, sample_provider]  # noqa: RUF012 - the list form

    @plugin
    class Without:
        pass

    assert declared_providers(WithProviders) == (tools, sample_provider)
    assert declared_providers(Without) == ()


@pytest.mark.parametrize(
    "listed",
    [sample_provider, "sample", [sample_provider, "tools"], {"a": 1}],
)
def test_anything_but_a_list_of_providers_is_refused_naming_the_class(listed) -> None:
    @plugin
    class Wrong:
        providers = listed

    with pytest.raises(QgisSdkDeclarationError, match="Wrong.providers must be a list"):
        declared_providers(Wrong)


def test_a_provider_listed_twice_is_refused_by_id() -> None:
    @plugin
    class Twice:
        providers = (sample_provider, sample_provider)

    with pytest.raises(QgisSdkDeclarationError, match="'sample' is listed twice"):
        declared_providers(Twice)
