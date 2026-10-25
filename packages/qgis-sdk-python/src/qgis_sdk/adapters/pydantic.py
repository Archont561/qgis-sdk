"""Optional Pydantic adapter for explicitly provisioned deployments.

The module and default SDK imports remain usable without Pydantic. Constructing an
adapter imports the optional validator and reports an actionable SDK error if the
deployment has not provisioned it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generic, Literal, TypeVar

from qgis_sdk.models import (
    QgisSdkContractValidationError,
    QgisSdkOptionalDependencyError,
    QgisSdkValidationIssue,
)

from ._pydantic_compat import (
    OPTIONAL_PYDANTIC_PROVISIONING_HINT,
    SUPPORTED_PYDANTIC_VERSION,
    UNSUPPORTED_PYDANTIC_VERSION_HINT,
)

RequestT = TypeVar("RequestT")
ReaderT = TypeVar("ReaderT")
WriterT = TypeVar("WriterT")


class PydanticContractAdapter(Generic[RequestT, ReaderT, WriterT]):
    """Validate JSON requests, call a typed handler, and serialize its result.

    The supplied dataclasses own their Pydantic ``strict``/``extra`` settings and
    field constraints. Request decoding and result validation are always strict;
    schemas are emitted separately for request, result-reader, and result-writer
    directions. Pydantic is loaded only when this adapter is constructed.
    """

    def __init__(
        self,
        *,
        request_type: type[RequestT],
        result_reader_type: type[ReaderT],
        result_writer_type: type[WriterT],
        handler: Callable[[RequestT], WriterT],
    ) -> None:
        try:
            from pydantic import TypeAdapter, ValidationError, __version__
        except ImportError as error:
            raise QgisSdkOptionalDependencyError(
                "pydantic",
                OPTIONAL_PYDANTIC_PROVISIONING_HINT,
            ) from error

        if __version__ != SUPPORTED_PYDANTIC_VERSION:
            raise QgisSdkOptionalDependencyError(
                "pydantic", UNSUPPORTED_PYDANTIC_VERSION_HINT
            )

        self._validation_error_type = ValidationError
        self._request_adapter = TypeAdapter(request_type)
        self._result_reader_adapter = TypeAdapter(result_reader_type)
        self._result_writer_adapter = TypeAdapter(result_writer_type)
        self._handler = handler

    def validate_request_json(self, payload: str | bytes | bytearray) -> RequestT:
        """Strictly validate JSON and construct the typed request dataclass."""
        try:
            return self._request_adapter.validate_json(payload, strict=True)
        except self._validation_error_type as error:
            raise self._as_sdk_error(error, direction="request") from None

    def serialize_result_json(self, result: WriterT) -> bytes:
        """Strictly validate and serialize a result, including declared defaults."""
        try:
            typed_result = self._result_writer_adapter.validate_python(
                result, strict=True
            )
            return self._result_writer_adapter.dump_json(
                typed_result, exclude_unset=False, warnings="error"
            )
        except self._validation_error_type as error:
            raise self._as_sdk_error(error, direction="result") from None

    def handle_json(self, payload: str | bytes | bytearray) -> bytes:
        """Validate one request, invoke its typed handler, and serialize the result."""
        request = self.validate_request_json(payload)
        result = self._handler(request)
        return self.serialize_result_json(result)

    def request_json_schema(self) -> dict[str, Any]:
        """Return the schema used for incoming request JSON."""
        return self._request_adapter.json_schema(mode="validation")

    def result_reader_json_schema(self) -> dict[str, Any]:
        """Return the schema accepted when reading a compatible result."""
        return self._result_reader_adapter.json_schema(mode="validation")

    def result_writer_json_schema(self) -> dict[str, Any]:
        """Return the schema emitted when serializing a result."""
        return self._result_writer_adapter.json_schema(mode="serialization")

    @staticmethod
    def _as_sdk_error(
        error: Exception, *, direction: Literal["request", "result"]
    ) -> QgisSdkContractValidationError:
        """Keep only field paths and validator codes; never copy rejected values."""
        details = error.errors(
            include_input=False, include_context=False, include_url=False
        )
        issues = []
        for detail in details:
            location = detail.get("loc", ())
            path = tuple(part for part in location if type(part) in (str, int))
            code = detail.get("type")
            issues.append(
                QgisSdkValidationIssue(
                    path=path,
                    code=code if isinstance(code, str) else "validation_error",
                )
            )
        return QgisSdkContractValidationError(direction=direction, issues=issues)
