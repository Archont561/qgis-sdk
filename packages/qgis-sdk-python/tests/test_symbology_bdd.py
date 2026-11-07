"""The symbology checks, read as scenarios (TASK-93).

The steps live in :mod:`symbology_steps`, which ``tests/conftest.py`` loads for
the whole suite, so the scenarios here and the ordinary tests next door share one
fake runtime: a renderer is arranged once and observed the same way from both.
"""

from pytest_bdd import scenarios

scenarios("features/symbology.feature")
