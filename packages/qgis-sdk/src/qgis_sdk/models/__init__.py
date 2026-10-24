"""QGIS-free value and error types shared by the SDK layers."""

from .errors import (
    QgisSdkContractValidationError,
    QgisSdkError,
    QgisSdkJobCancelledError,
    QgisSdkLayerNotFoundError,
    QgisSdkOptionalDependencyError,
    QgisSdkPackagedResourceError,
    QgisSdkSchedulingBlockedError,
    QgisSdkScopeClosedError,
    QgisSdkStyleIncompatibleError,
    QgisSdkStyleNotFoundError,
    QgisSdkUnsupportedCapabilityError,
    QgisSdkValidationIssue,
)
from .layers import GeometryType, VectorLayerInfo
from .limits import MAX_SAFE_INTEGER
from .styles import StyleSpec

__all__ = [
    "MAX_SAFE_INTEGER",
    "GeometryType",
    "QgisSdkContractValidationError",
    "QgisSdkError",
    "QgisSdkJobCancelledError",
    "QgisSdkLayerNotFoundError",
    "QgisSdkOptionalDependencyError",
    "QgisSdkPackagedResourceError",
    "QgisSdkSchedulingBlockedError",
    "QgisSdkScopeClosedError",
    "QgisSdkStyleIncompatibleError",
    "QgisSdkStyleNotFoundError",
    "QgisSdkUnsupportedCapabilityError",
    "QgisSdkValidationIssue",
    "StyleSpec",
    "VectorLayerInfo",
]
