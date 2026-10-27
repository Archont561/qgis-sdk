"""The shipped Processing snapshot: every core provider module imports and
agrees with ``catalogue.json`` (TASK-109, decision-64).

The modules are generated and never edited; this is the one place that reads
all five against the catalogue they came from, so a regeneration that drops a
provider or renames a request class fails here rather than in a plugin.
"""

from __future__ import annotations

import importlib

import pytest
from qgis_sdk.models import TypedRun
from qgis_sdk.processing import snapshot
from qgis_sdk.processing.codegen import _module_name, class_name


# The ids say "provider-native", not "native": a bare ``[native]`` suffix is
# how the pure selection recognises a native service backend.
@pytest.mark.parametrize(
    "provider",
    snapshot.CORE_PROVIDERS,
    ids=[f"provider-{p}" for p in snapshot.CORE_PROVIDERS],
)
def test_each_core_provider_module_matches_the_catalogue(provider: str) -> None:
    catalogue = snapshot.core_catalogue()
    module = importlib.import_module(f"qgis_sdk.processing.{_module_name(provider)}")
    algorithms = [a for a in catalogue.algorithms if a.provider == provider]

    assert module.PROVIDER == provider
    assert module.ALGORITHM_IDS == tuple(a.id for a in algorithms)
    assert set(module.REGISTRY) == {a.id for a in algorithms}
    taken: set[str] = set()
    for algorithm in algorithms:
        name = class_name(algorithm, taken)
        taken.add(name)
        request = module.REGISTRY[algorithm.id]
        assert request is getattr(module, name)
        assert issubclass(request, TypedRun)
        assert request.algorithm == algorithm.id
        assert name in module.__all__
        assert f"{name}Params" in module.__all__


def test_the_snapshot_covers_the_core_providers_once() -> None:
    catalogue = snapshot.core_catalogue()

    assert sorted(p.id for p in catalogue.providers) == sorted(snapshot.CORE_PROVIDERS)
    assert len({a.id for a in catalogue.algorithms}) == len(catalogue.algorithms)
