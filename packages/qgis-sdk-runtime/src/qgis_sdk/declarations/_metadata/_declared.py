"""Reading the metadata a declaration recorded on a class or a function."""

from __future__ import annotations

import inspect
from typing import Any

from qgis_sdk.declarations._contract import QgisSdkDeclarationError

from ._metadata import Metadata

__all__ = ["declared_metadata"]


def declared_metadata(
    cls: Any, attribute: str, describer: str, decorator: str
) -> Metadata:
    """Return the class's own marker, or refuse with the describer's message.

    Args:
        cls: The class a describer was asked to describe.
        attribute: The attribute the marker is recorded under.
        describer: The describer's name, for the error.
        decorator: The decorator it requires, for the error.

    Raises:
        QgisSdkDeclarationError: The target is not a marked class.
    """
    if not inspect.isclass(cls) or attribute not in vars(cls):
        raise QgisSdkDeclarationError(f"{describer} requires a class with {decorator}")
    declared = vars(cls)[attribute]
    if not isinstance(declared, Metadata):
        raise QgisSdkDeclarationError(f"{describer} requires a class with {decorator}")
    return declared
