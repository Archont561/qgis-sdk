"""The declared operation table, the grants that select from it and the description."""

from __future__ import annotations

from ._operations_algorithms import HOST_OPERATIONS_C
from ._operations_canvas import HOST_OPERATIONS_D
from ._operations_connections import HOST_OPERATIONS_B
from ._operations_layers import HOST_OPERATIONS_A
from ._operations_project import HOST_OPERATIONS_E

HOST_OPERATIONS = (
    HOST_OPERATIONS_A
    + HOST_OPERATIONS_B
    + HOST_OPERATIONS_C
    + HOST_OPERATIONS_D
    + HOST_OPERATIONS_E
)
