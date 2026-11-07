"""The connections checks, read as scenarios (TASK-92).

The steps live in :mod:`connections_steps`, which ``tests/conftest.py`` loads
for the whole suite, so the scenarios here and the ordinary tests next door
share one fake registry: a connection is arranged once and observed the same
way from both.
"""

from pytest_bdd import scenarios

scenarios("features/connections.feature")
