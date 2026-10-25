"""The checked-in bridge cases, read as scenarios (TASK-7 AC 3).

The steps and the ``contract_host`` fixture live in :mod:`bridge_steps`, a
plugin ``tests/conftest.py`` loads for the whole suite, so the same host and the
same replay serve both this feature and the ordinary tests next door.
"""

from pytest_bdd import scenarios

scenarios("features/bridge_contract.feature")
