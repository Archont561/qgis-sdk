"""Authoring: ``@job``, :class:`JobStatus` and the description of a job."""

from __future__ import annotations

import inspect
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from types import UnionType
from typing import Annotated, Any, Literal, TypeVar, Union, get_args, get_origin

from qgis_sdk.core import JobContext
from qgis_sdk.core.scheduling import JobState
from qgis_sdk.declarations import (
    QgisSdkDeclarationError,
    canonical_json,
    declared_function_metadata,
    function_metadata,
    keyword_inputs,
    mark_function,
    object_schema,
    refuse_bindings,
    register_describer,
    resolve_hints,
    schema_for,
    type_name,
    validate_given,
)

T = TypeVar("T")

_JOB_ATTRIBUTE = "__qgis_sdk_job__"

JobEvent = Literal["progress", "success", "failure", "cancelled"]
"""The four things a handle can be subscribed to."""

_EVENTS: tuple[JobEvent, ...] = ("progress", "success", "failure", "cancelled")


def _main_thread() -> bool:
    """The default notion of "the GUI thread": the interpreter's main thread."""
    return threading.current_thread() is threading.main_thread()


# -- authoring --------------------------------------------------------------------


class JobStatus(StrEnum):
    """The observable state of one submitted job (decision-13 names)."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def settled(self) -> bool:
        """Whether the job can no longer change state."""
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


_STATUS_OF_STATE = {
    JobState.QUEUED: JobStatus.QUEUED,
    JobState.RUNNING: JobStatus.RUNNING,
    JobState.WAITING: JobStatus.RUNNING,
    JobState.COMPLETED: JobStatus.SUCCEEDED,
    JobState.FAILED: JobStatus.FAILED,
    JobState.CANCELLED: JobStatus.CANCELLED,
}


def job(
    function: Callable[..., Any] | None = None,
    /,
    *,
    id: str | None = None,
    title: str | None = None,
) -> Any:
    """Attach job metadata to a plain function without wrapping it.

    The function takes the :class:`JobContext` first and its inputs as typed
    keyword parameters, and declares its result::

        @job(id="demo.sum", title="Sum two numbers")
        def sum_numbers(ctx: JobContext, a: int, b: int = 0) -> SumResult: ...

    ``@job`` alone derives the id and title from the function name, the way
    ``@plugin`` does for a class; ``id=`` and ``title=`` override either one.
    Nothing is injected at decoration time: the runtime passes the context
    when it runs the attempt, so a test calls the function directly with a
    fake. ``async def`` is allowed and suspends on the scheduler at each
    ``await``.
    """
    validate_given(id, title)

    def decorate(target: Callable[..., Any]) -> Callable[..., Any]:
        refuse_bindings(target, "@job")
        mark_function(
            target, _JOB_ATTRIBUTE, function_metadata(target, id, title), "@job"
        )
        return target

    if function is None:
        return decorate
    return decorate(function)


@dataclass(frozen=True)
class JobDescription:
    """Inspectable job structure: its keyword inputs, its result, and how it runs.

    ``parameters`` are the input names in signature order and ``required``
    the ones without a default; ``inputs_schema`` is the object schema built
    from them, the same way an action's is. ``asynchronous`` says whether the
    function is a coroutine function. A plain function executes in one
    scheduler step on the driving thread, so it is for short work or work
    that hands itself off through ``ctx.workers``; an ``async def`` suspends
    on the scheduler at every ``await``.
    """

    id: str
    title: str
    parameters: tuple[str, ...]
    required: tuple[str, ...]
    annotations: dict[str, Any] = field(repr=False, compare=False)
    result_type: Any = field(default=None)
    inputs_schema: dict[str, Any] = field(default_factory=dict)
    result_schema: dict[str, Any] = field(default_factory=dict)
    asynchronous: bool = False
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Return the transport representation without live Python types."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "title": self.title,
            "asynchronous": self.asynchronous,
            "inputs": self.inputs_schema,
            "result": {
                "type": type_name(self.result_type),
                "schema": self.result_schema,
            },
        }

    def to_json(self) -> str:
        """The canonical JSON form shared by every description."""
        return canonical_json(self.to_dict())


def describe_job(function: Callable[..., Any]) -> JobDescription:
    """Inspect one decorated function without calling it."""
    declared = declared_function_metadata(
        function, _JOB_ATTRIBUTE, "describe_job", "@job"
    )
    path = f"job {declared.id}"
    if inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function):
        raise QgisSdkDeclarationError(
            f"{path}: a job is a function or coroutine function, not a generator"
        )
    parameters = list(inspect.signature(function).parameters.values())
    hints = resolve_hints(function, path)
    context_first = (
        bool(parameters)
        and parameters[0].kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY)
        and hints.get(parameters[0].name) is JobContext
    )
    if not context_first:
        raise QgisSdkDeclarationError(
            f"{path}: first parameter must be the JobContext the runtime injects "
            "(annotate it `ctx: JobContext`)"
        )
    inputs = parameters[1:]
    properties, required = keyword_inputs(inputs, hints, f"{path}.inputs")
    result_type = hints.get("return", inspect.Signature.empty)
    if result_type is inspect.Signature.empty:
        raise QgisSdkDeclarationError(f"{path}: a job must declare its result")
    return JobDescription(
        id=declared.id,
        title=declared.title,
        parameters=tuple(parameter.name for parameter in inputs),
        required=tuple(required),
        annotations={parameter.name: hints[parameter.name] for parameter in inputs},
        result_type=result_type,
        inputs_schema=object_schema(properties, required),
        result_schema=schema_for(result_type, f"{path}.result", result=True),
        asynchronous=inspect.iscoroutinefunction(function),
    )


register_describer(_JOB_ATTRIBUTE, describe_job)


def _accepts(value: object, annotation: Any) -> bool:
    """Whether ``value`` fits ``annotation`` for the shapes a job may declare.

    The same subset :func:`qgis_sdk.declarations.schema_for` admits, checked
    on Python values: primitives, ``None``, unions, ``Literal``, ``list``,
    ``tuple`` and dataclasses. The check is about the outer shape - a list is
    a list - so a wrong submission is refused before anything is queued while
    the author's function keeps the last word on the values.
    """
    origin = get_origin(annotation)
    if origin is Annotated:
        return _accepts(value, get_args(annotation)[0])
    if annotation is Any:
        return True
    if annotation is None or annotation is type(None):
        return value is None
    if origin in (Union, UnionType):
        return any(_accepts(value, arg) for arg in get_args(annotation))
    if origin is Literal:
        return value in get_args(annotation)
    if origin is not None:
        return isinstance(value, origin)
    if annotation is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if annotation is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, annotation)


def _describe_annotation(annotation: Any) -> str:
    """Spell an annotation the way the author wrote it, for a refusal message."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return _describe_annotation(args[0])
    if origin is Literal:
        return "one of " + ", ".join(repr(arg) for arg in args)
    if origin in (Union, UnionType):
        return " | ".join(_describe_annotation(arg) for arg in args)
    if origin is not None and args:
        inner = ", ".join(_describe_annotation(arg) for arg in args)
        return f"{type_name(origin)}[{inner}]"
    return type_name(annotation)


def _check_arguments(
    description: JobDescription, arguments: dict[str, Any]
) -> list[str]:
    """Name every way ``arguments`` fails the signature, without the values."""
    problems = [
        f"missing {name}" for name in description.required if name not in arguments
    ]
    problems += [
        f"unexpected {name}" for name in arguments if name not in description.parameters
    ]
    for name, value in arguments.items():
        annotation = description.annotations.get(name)
        if name in description.parameters and not _accepts(value, annotation):
            problems.append(
                f"{name} must be {_describe_annotation(annotation)}, "
                f"not {type_name(type(value))}"
            )
    return problems
