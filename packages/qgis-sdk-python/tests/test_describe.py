"""The shared describer surface behind ``@plugin``, ``@job`` and ``@provider.algorithm`` (TASK-49).

Author classes stay plain (decision-6, decision-10): nothing here adds a base
class or a method to them. What is shared lives on the declaration side - one
``describe()`` entry point, one ``Description`` protocol the description objects
satisfy, one canonical JSON form, and one marker-decorator builder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from qgis_sdk.algorithms import AlgorithmDescription, describe_algorithm
from qgis_sdk.core import AlgorithmContext, JobContext
from qgis_sdk.declarations import (
    Description,
    PluginDescription,
    QgisSdkDeclarationError,
    action,
    canonical_json,
    declare_class,
    describe,
    describe_plugin,
    plugin,
)
from qgis_sdk.jobs import JobDescription, describe_job, job
from qgis_sdk.models import VectorLayerInfo
from qgis_sdk.providers import Provider, ProviderDescription


@dataclass(frozen=True)
class Inputs:
    value: int


@dataclass(frozen=True)
class Result:
    value: int


@plugin(id="describe.plugin", title="A plugin")
class Plugin:
    @action(id="echo", title="Echo")
    def echo(self, value: int) -> int:
        return value


@job(id="describe.job", title="A job")
async def echo_job(ctx: JobContext, value: int) -> Result:
    return Result(value)


provider = Provider(id="describe.provider", title="A provider")


@provider.algorithm(id="registered", title="Registered")
def registered(ctx: AlgorithmContext, value: int) -> VectorLayerInfo:
    raise AssertionError("describe must not call an algorithm")


# -- describe(): one entry point, dispatching on the decorator marker ---------------


@pytest.mark.parametrize(
    ("cls", "expected_type", "narrow"),
    [
        pytest.param(Plugin, PluginDescription, describe_plugin, id="plugin"),
        pytest.param(
            registered, AlgorithmDescription, describe_algorithm, id="algorithm"
        ),
        pytest.param(echo_job, JobDescription, describe_job, id="job"),
    ],
)
def test_describe_dispatches_to_the_narrow_describer(
    cls, expected_type, narrow
) -> None:
    described = describe(cls)
    assert isinstance(described, expected_type)
    assert described == narrow(cls)
    assert isinstance(described, Description)


def test_describe_refuses_an_undecorated_class_a_function_and_a_non_class() -> None:
    with pytest.raises(QgisSdkDeclarationError, match="class declared with @plugin"):
        describe(Inputs)
    with pytest.raises(QgisSdkDeclarationError, match="@job or @provider.algorithm"):
        describe(lambda ctx: None)
    with pytest.raises(QgisSdkDeclarationError, match="requires a class or a function"):
        describe(object())  # type: ignore[arg-type]


# -- Description: the protocol every description object satisfies -----------------


@pytest.mark.parametrize(
    "described",
    [
        pytest.param(describe_plugin(Plugin), id="plugin"),
        pytest.param(describe_algorithm(registered), id="algorithm"),
        pytest.param(describe_job(echo_job), id="job"),
        pytest.param(provider.describe(), id="provider"),
    ],
)
def test_every_description_serialises_the_same_way(described: Description) -> None:
    assert isinstance(described, Description)
    assert isinstance(described.id, str) and described.id
    assert isinstance(described.title, str) and described.title
    assert described.schema_version == 1
    payload = described.to_dict()
    assert payload["schema_version"] == 1
    assert payload["id"] == described.id
    # One canonical form: sorted keys, compact separators, no NaN, independent
    # of the object's own key order.
    text = described.to_json()
    assert text == canonical_json(payload)
    assert json.loads(text) == payload
    assert text == json.dumps(payload, sort_keys=True, separators=(",", ":"))


def test_provider_description_is_a_description() -> None:
    assert isinstance(provider.describe(), ProviderDescription)
    assert isinstance(provider.describe(), Description)


def test_canonical_json_refuses_nonfinite_numbers() -> None:
    with pytest.raises(ValueError):
        canonical_json({"value": float("nan")})


# -- declare_class: the one marker pattern the class decorators share ---------------


def test_declare_class_attaches_metadata_once_and_only_to_classes() -> None:
    marker = "__qgis_sdk_test_marker__"
    decorate = declare_class(marker, "@thing", id="describe.thing", title="Thing")

    class Thing:
        pass

    assert decorate(Thing) is Thing
    assert vars(Thing)[marker].id == "describe.thing"
    with pytest.raises(QgisSdkDeclarationError, match="duplicate @thing declaration"):
        decorate(Thing)
    with pytest.raises(QgisSdkDeclarationError, match="@thing requires a class"):
        decorate(lambda: None)  # type: ignore[arg-type]
    with pytest.raises(QgisSdkDeclarationError, match="Invalid declaration id"):
        declare_class(marker, "@thing", id="9bad", title="Thing")


def test_a_subclass_does_not_inherit_the_marker_as_its_own_declaration() -> None:
    class Child(Plugin):
        pass

    with pytest.raises(QgisSdkDeclarationError, match="requires a class with @plugin"):
        describe_plugin(Child)
    with pytest.raises(QgisSdkDeclarationError, match="class declared with @plugin"):
        describe(Child)
