from __future__ import annotations

import ast
from collections.abc import Iterator

from qgis_sdk_tools.check.diagnostics import Diagnostic

from ._contexts import COMPOUND, MISSING, CheckContext, DeclaredSite
from ._functions import Names, bound_attributes


def _custom_diagnostic(
    attribute: str, value: ast.expr | None, site: DeclaredSite
) -> Diagnostic | None:
    """UI005 for a ``Custom`` holding a widget built at class definition time."""
    if not isinstance(value, ast.Call) or callee_name(value) != "Custom":
        return None
    widget = _custom_widget(value)
    if not isinstance(widget, ast.Call):
        return None
    return Diagnostic(
        rule="UI005",
        path=site.path,
        line=value.lineno,
        column=value.col_offset + 1,
        message=(
            f"{site.node.name}.{attribute} = Custom({callee_name(widget)}"
            "(...)): a widget built when the class is defined cannot "
            "be copied for each window"
        ),
        remediation=(
            "Pass Custom the widget class or a factory "
            "(Custom(widget=QLabel), Custom(lambda parent: ...)); it "
            "runs once per opening, when the tree is mounted."
        ),
    )


def _literal_on_diagnostic(name: str, kind: str, site: DeclaredSite) -> tuple[str, str]:
    """The UI005 wording for a class attribute that is a literal, not a component."""
    return (
        f"@on({name}) in {site.node.name}: {name!r} is {kind}, not a component",
        (
            f"Assign a catalogue component to the class attribute "
            f"({name} = Button(text=...)) and wire @on({name}), or pass "
            f"the widget's objectName as a string: @on({name!r})."
        ),
    )


def _missing_on_diagnostic(name: str, site: DeclaredSite) -> tuple[str, str]:
    """The UI005 wording for an ``@on`` name the class never declares."""
    return (
        (
            f"@on({name}) in {site.node.name}: the class declares no component "
            f"named {name!r}"
        ),
        (
            f"Declare the component as a class attribute ({name} = "
            f"Button(text=...)) above the method, or pass the widget's "
            f"objectName as a string: @on({name!r})."
        ),
    )


def _on_diagnostic(
    decorator: ast.expr, name: str, site: DeclaredSite
) -> Diagnostic | None:
    """UI005 for an ``@on(NAME)`` that resolves to no component."""
    value = site.bound.get(name, MISSING)
    if value is not MISSING:
        kind = _literal_kind(value)  # type: ignore[arg-type]
        if kind is None:
            return None  # a call, a name, an attribute: the host resolves it
        message, remediation = _literal_on_diagnostic(name, kind, site)
    elif name in site.names.module_names:
        return None  # a module-level component or import: the host decides
    else:
        message, remediation = _missing_on_diagnostic(name, site)
    return Diagnostic(
        rule="UI005",
        path=site.path,
        line=decorator.lineno,
        column=decorator.col_offset + 1,
        message=message,
        remediation=remediation,
    )


def check_declared(node: ast.ClassDef, context: CheckContext) -> Iterator[Diagnostic]:
    """Yield UI005 for the declarative form, as far as the source shows it."""
    bound = bound_attributes(node)
    site = DeclaredSite(node, context.names, bound, context.path)
    for attribute, value in bound.items():
        diagnostic = _custom_diagnostic(attribute, value, site)
        if diagnostic is not None:
            yield diagnostic
    for method in node.body:
        if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in method.decorator_list:
            target = site.names.on_target(decorator)
            if not isinstance(target, ast.Name) or target.id in site.names.constants:
                continue
            diagnostic = _on_diagnostic(decorator, target.id, site)
            if diagnostic is not None:
                yield diagnostic


def _custom_widget(call: ast.Call) -> ast.expr | None:
    """The ``widget`` argument of a ``Custom(...)`` call, however it is passed."""
    for keyword in call.keywords:
        if keyword.arg == "widget":
            return keyword.value
    positional = list(call.args)
    if positional and isinstance(positional[0], ast.Constant):
        positional = positional[1:]  # Custom("name", widget)
    return positional[0] if positional else None


def _literal_kind(value: ast.expr | None) -> str | None:
    """``"a str"``/``"an int"``/``"a list"`` for a literal, ``None`` for the rest."""
    if isinstance(value, ast.Constant):
        name = type(value.value).__name__
    elif isinstance(value, ast.List | ast.Tuple | ast.Dict | ast.Set):
        name = type(value).__name__.lower()
    else:
        return None
    article = "an" if name[0] in "aeiou" else "a"
    return f"{article} {name}"


def _child_statements(statement: ast.stmt) -> Iterator[ast.stmt]:
    """The nested statements a compound statement may bind names in."""
    for child in ast.iter_child_nodes(statement):
        if isinstance(child, ast.stmt):
            yield child


def bound_names(statement: ast.stmt) -> Iterator[str]:
    """The names a statement binds in its scope, as far as a checker needs."""
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        yield statement.name
        return
    if isinstance(statement, ast.Import | ast.ImportFrom):
        for alias in statement.names:
            yield alias.asname or alias.name.split(".")[0]
        return
    if isinstance(statement, ast.Assign):
        for target in statement.targets:
            yield from _names_in(target)
        return
    if isinstance(statement, ast.AnnAssign | ast.AugAssign):
        yield from _names_in(statement.target)
        return
    if isinstance(statement, COMPOUND):
        for child in _child_statements(statement):
            yield from bound_names(child)
        if isinstance(statement, ast.For):
            yield from _names_in(statement.target)


def _names_in(target: ast.expr) -> Iterator[str]:
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            yield from _names_in(element)


def literal_name(target: ast.expr | None, names: Names) -> str | None:
    """The node name an ``@on`` target spells, when the checker can read it.

    A string literal, or a module-level ``NAME = "literal"``; a component
    declared on the class (``@on(clear)``) or anything else is left to the
    host, which resolves it when the surface opens.
    """
    if isinstance(target, ast.Constant) and isinstance(target.value, str):
        return target.value
    if isinstance(target, ast.Name):
        return names.constants.get(target.id)
    return None


def class_constant(node: ast.ClassDef, name: str) -> object:
    for statement in node.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
            value = statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets = [statement.target]
            value = statement.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return value.value if isinstance(value, ast.Constant) else None
    return None


def callee_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""
