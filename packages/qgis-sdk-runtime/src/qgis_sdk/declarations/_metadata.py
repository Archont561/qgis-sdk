"""Metadata: ids and titles, derived or given, and how a class or function carries them."""

import hashlib
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import (
    Any,
    TypeVar,
)

from qgis_sdk.declarations._contract import QgisSdkDeclarationError

T = TypeVar("T")


@dataclass(frozen=True)
class Metadata:
    """What every declaration decorator records: a validated id and a title."""

    id: str
    title: str


def metadata(id: str, title: str) -> Metadata:
    """Validate the id and title every ``@plugin``/``@job``/``@provider.algorithm`` takes."""
    _validate_id(id)
    _validate_title(id, title)
    return Metadata(id, title)


def _validate_id(id: Any) -> None:
    if not isinstance(id, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]*", id):
        raise QgisSdkDeclarationError(
            f"Invalid declaration id {id!r}: use a letter followed by letters, digits, _, . or -"
        )


def _validate_title(id: Any, title: Any) -> None:
    if not isinstance(title, str) or not title.strip():
        raise QgisSdkDeclarationError(f"{id}: title must be a nonempty string")


_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _words(name: str) -> list[str]:
    """Split ``FieldTools``, ``HTTPServer`` or ``list_layers`` into its words."""
    spaced = _WORD_BOUNDARY.sub(" ", name.replace("_", " "))
    return spaced.split()


def derive_id(name: str) -> str:
    """The snake_case id a declaration gets from its Python name.

    ``FieldTools`` becomes ``field_tools`` and ``HTTPServer`` becomes
    ``http_server``; a snake_case method name is kept as it is, minus any
    leading underscores (an id starts with a letter).
    """
    id = "_".join(word.lower() for word in _words(name))
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", id):
        raise QgisSdkDeclarationError(
            f"Cannot derive a declaration id from {name!r}; pass id= explicitly"
        )
    return id


def derive_title(name: str) -> str:
    """The readable title a declaration gets from its Python name.

    A CamelCase name keeps its word casing (``FieldTools`` -> ``Field Tools``,
    ``HTTPServer`` -> ``HTTP Server``); a snake_case name reads as a sentence
    (``list_layers`` -> ``List layers``). Either way a title starts with a
    capital (``fieldTools`` -> ``Field Tools``).
    """
    words = _words(name)
    if not words:
        raise QgisSdkDeclarationError(
            f"Cannot derive a declaration title from {name!r}; pass title= explicitly"
        )
    if any(word[:1].isupper() for word in words):
        return " ".join([words[0][:1].upper() + words[0][1:], *words[1:]])
    return " ".join([words[0].capitalize(), *words[1:]])


def _class_id_suffix(cls: type) -> str:
    """Six hex digits hashed from the class's module and qualified name.

    The suffix is what keeps two plugins, algorithms or jobs that share a class
    name apart without making the id random: the same class in the same place
    derives the same id on every import, so a generated client and a
    fingerprint stay valid until the class itself moves.
    """
    qualified = f"{cls.__module__}.{cls.__qualname__}"
    return hashlib.sha256(qualified.encode()).hexdigest()[:6]


def _declared_metadata(
    target: Any, id: str | None, title: str | None, *, suffixed: bool
) -> Metadata:
    """Complete a declaration from ``target``'s name where the author left gaps."""
    name = getattr(target, "__name__", None)
    if id is None:
        if not isinstance(name, str):
            raise QgisSdkDeclarationError(
                "cannot derive an id without a name; pass id= explicitly"
            )
        id = derive_id(name)
        if suffixed:
            id = f"{id}_{_class_id_suffix(target)}"
    if title is None:
        if not isinstance(name, str):
            raise QgisSdkDeclarationError(
                f"{id}: cannot derive a title without a name; pass title= explicitly"
            )
        title = derive_title(name)
    return metadata(id, title)


def validate_given(id: str | None, title: str | None) -> None:
    """Refuse a bad explicit id or title at decoration time, before any class exists."""
    if id is not None:
        _validate_id(id)
    if title is not None:
        _validate_title(id if id is not None else "declaration", title)


def class_metadata(cls: type, id: str | None, title: str | None) -> Metadata:
    """The metadata a class declaration carries: given values, or derived ones.

    A derived class id is the snake_case class name plus the module/qualname
    hash suffix; a derived title is the class name spaced into words.
    """
    return _declared_metadata(cls, id, title, suffixed=True)


def function_metadata(function: Any, id: str | None, title: str | None) -> Metadata:
    """The metadata a module-level ``@job`` function declaration carries.

    Derived the way a class id is - snake_case name plus the module/qualname
    suffix - because a job id has to stay unique across modules the same way
    an algorithm id does, and because the two are documented as one rule.
    """
    return _declared_metadata(function, id, title, suffixed=True)


def mark_function(
    function: Any, attribute: str, declared: Metadata, decorator: str
) -> None:
    """Record ``declared`` on a plain function under ``attribute``.

    The function is left otherwise untouched: not wrapped, not bound, no
    attribute beyond the marker (decision-10 applied to functions). A class
    is refused with the way forward, because ``@job`` used to take one.
    """
    if inspect.isclass(function):
        raise QgisSdkDeclarationError(
            f"{decorator} declares a function, not a class: write "
            f"`{decorator} def name(ctx: JobContext, ...) -> Result` "
            "(the class form was removed; see the 0.6.0 migration notes)"
        )
    if not inspect.isfunction(function):
        raise QgisSdkDeclarationError(f"{decorator} requires a function")
    if attribute in vars(function):
        raise QgisSdkDeclarationError(
            f"{declared.id}: duplicate {decorator} declaration"
        )
    setattr(function, attribute, declared)


def declared_function_metadata(
    function: Any, attribute: str, describer: str, decorator: str
) -> Metadata:
    """Return the function's own marker, or refuse with the describer's message."""
    if not inspect.isfunction(function) or attribute not in vars(function):
        raise QgisSdkDeclarationError(
            f"{describer} requires a function with {decorator}"
        )
    declared = vars(function)[attribute]
    if not isinstance(declared, Metadata):
        raise QgisSdkDeclarationError(
            f"{describer} requires a function with {decorator}"
        )
    return declared


def method_metadata(method: Any, id: str | None, title: str | None) -> Metadata:
    """The metadata a method declaration carries: given values, or derived ones.

    A method id is the plain method name: it is already unique inside its class,
    and the bridge client spells it as a property, so no suffix is added.
    """
    return _declared_metadata(method, id, title, suffixed=False)


def mark_class(cls: Any, attribute: str, declared: Metadata, decorator: str) -> None:
    """Record ``declared`` on ``cls`` under ``attribute`` - the one marker pattern.

    The class is left otherwise untouched: no base class, no injected method
    (decision-6, decision-10). A marker set on a parent is not the child's own
    declaration, which is why every describer reads ``vars(cls)`` and not
    ``getattr``.
    """
    if not inspect.isclass(cls):
        raise QgisSdkDeclarationError(f"{decorator} requires a class")
    if attribute in vars(cls):
        raise QgisSdkDeclarationError(
            f"{declared.id}: duplicate {decorator} declaration"
        )
    setattr(cls, attribute, declared)


def declare_class(
    attribute: str,
    decorator: str,
    *,
    id: str | None = None,
    title: str | None = None,
) -> Callable[[type[T]], type[T]]:
    """Build a marker class decorator of the shape ``@plugin`` has.

    An omitted ``id`` or ``title`` is derived from the class once it is known
    (:func:`class_metadata`); a given one is validated right here.
    """
    validate_given(id, title)

    def decorate(cls: type[T]) -> type[T]:
        if not inspect.isclass(cls):
            raise QgisSdkDeclarationError(f"{decorator} requires a class")
        mark_class(cls, attribute, class_metadata(cls, id, title), decorator)
        return cls

    return decorate


def class_decorator(
    attribute: str,
    decorator: str,
    cls: Any,
    *,
    id: str | None,
    title: str | None,
) -> Any:
    """Serve both ``@plugin`` and ``@plugin(...)`` from one definition.

    Used bare, the decorator receives the class as its only positional
    argument and decorates it at once; called, it returns the decorator.
    """
    decorate = declare_class(attribute, decorator, id=id, title=title)
    if cls is None:
        return decorate
    return decorate(cls)


def declared_metadata(
    cls: Any, attribute: str, describer: str, decorator: str
) -> Metadata:
    """Return the class's own marker, or refuse with the describer's message."""
    if not inspect.isclass(cls) or attribute not in vars(cls):
        raise QgisSdkDeclarationError(f"{describer} requires a class with {decorator}")
    declared = vars(cls)[attribute]
    if not isinstance(declared, Metadata):
        raise QgisSdkDeclarationError(f"{describer} requires a class with {decorator}")
    return declared
