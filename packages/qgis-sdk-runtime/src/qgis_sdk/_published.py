"""Publish a wide parameter list from a one-record implementation.

Some parameter lists are external contracts rather than private choices: a Typer
command's options, a pytest fixture's dependency names, an annotated algorithm's
declared inputs. They must stay byte-identical to their callers and to the tools
that introspect them, while decision-81 still asks the implementation to take
one record instead of a crowd of fields.

:func:`published` keeps that boundary. The decorator builds the published
:class:`inspect.Signature` once, installs it on a short ``*args, **kwargs``
wrapper, and passes the bound arguments to the implementation as one record.
The implementation reads ``_published_values.<name>`` instead of a bare name,
so its body keeps its meaning while Rude sees one parameter on it and two on the
wrapper. ``inspect.signature``, ``typing.get_type_hints``, Typer, pytest and
pytest-bdd all see the published declaration.

This is declaration data, not a suppression: every option, annotation, default
and parameter kind is still spelled out, just in a tuple beside the function
instead of inline in its ``def`` line.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from typing import Any

REQUIRED = inspect.Parameter.empty
"""The ``default`` (or ``annotation``) of a required, unannotated parameter."""

_KINDS = {
    "positional_only": inspect.Parameter.POSITIONAL_ONLY,
    "positional": inspect.Parameter.POSITIONAL_OR_KEYWORD,
    "var_positional": inspect.Parameter.VAR_POSITIONAL,
    "keyword": inspect.Parameter.KEYWORD_ONLY,
    "var_keyword": inspect.Parameter.VAR_KEYWORD,
}

__all__ = ["REQUIRED", "Record", "published"]


class Record:
    """One mutable record of a published call's arguments."""

    def __init__(_record_self, **values):
        _record_self.__dict__.update(values)


def _declaration(specs, returns):
    """Build the published signature, its annotations and the parameter names."""
    parameters = []
    annotations = {}
    for name, annotation, default, kind in specs:
        parameters.append(
            inspect.Parameter(
                name, _KINDS[kind], annotation=annotation, default=default
            )
        )
        annotations[name] = annotation
    signature = inspect.Signature(parameters, return_annotation=returns)
    if returns is not None:
        annotations["return"] = returns
    return signature, annotations


def _identical(wrapper, fn, signature, annotations):
    """Give the wrapper the published function's identity, without ``__wrapped__``."""
    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = fn.__doc__
    wrapper.__module__ = fn.__module__
    wrapper.__signature__ = signature
    wrapper.__annotations__ = annotations


def published(
    specs: Iterable[tuple[str, Any, Any, str]], *, returns: Any = None
) -> Callable[[Callable[[Record], Any]], Callable[..., Any]]:
    """Return a decorator that publishes *specs* as the implementation's signature.

    Each spec is ``(name, annotation, default, kind)``. ``kind`` is one of
    ``positional_only``, ``positional``, ``var_positional``, ``keyword`` or
    ``var_keyword``. Use :data:`REQUIRED` for a parameter without a default.
    The decorated implementation receives one :class:`Record` with every bound
    argument as an attribute.
    """
    signature, annotations = _declaration(specs, returns)

    def decorate(fn):
        def wrapper(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            return fn(Record(**bound.arguments))

        _identical(wrapper, fn, signature, annotations)
        return wrapper

    return decorate
