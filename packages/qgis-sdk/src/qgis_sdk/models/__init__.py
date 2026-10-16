"""QGIS-free value and error types shared by the SDK layers."""

from .errors import (
    QgisSdkError,
    QgisSdkScopeClosedError,
    QgisSdkUnsupportedCapabilityError,
)

__all__ = [
    "QgisSdkError",
    "QgisSdkScopeClosedError",
    "QgisSdkUnsupportedCapabilityError",
]
