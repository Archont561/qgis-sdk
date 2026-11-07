"""The layer-kind checks, read as scenarios (TASK-91).

The steps live in :mod:`layer_kind_steps`, which ``tests/conftest.py`` loads for
the whole suite, so the scenarios here and the ordinary tests next door share one
fake runtime: a kind is arranged once and observed the same way from both.
"""

from pytest_bdd import scenarios

scenarios("features/layer_kinds.feature")
