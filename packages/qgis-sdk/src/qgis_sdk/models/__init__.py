"""QGIS-free value and error types shared by the SDK layers."""

from .algorithms import AlgorithmRequest, BufferRequest, CentroidRequest
from .errors import (
    QgisSdkAlgorithmCancelledError,
    QgisSdkAlgorithmRejectedError,
    QgisSdkContractValidationError,
    QgisSdkError,
    QgisSdkFormError,
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
from .parameters import CrsInput, LayerInput, Metres
from .styles import StyleSpec

__all__ = [
    "MAX_SAFE_INTEGER",
    "AlgorithmRequest",
    "BufferRequest",
    "CentroidRequest",
    "CrsInput",
    "GeometryType",
    "LayerInput",
    "Metres",
    "QgisSdkAlgorithmCancelledError",
    "QgisSdkAlgorithmRejectedError",
    "QgisSdkContractValidationError",
    "QgisSdkError",
    "QgisSdkFormError",
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
