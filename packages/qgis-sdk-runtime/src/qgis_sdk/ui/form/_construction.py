"""How a ``Form`` is built: from a schema, or for one of the plugin's actions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from qgis_sdk.ui.form_fields import schema_fields

from ._inputs import inputs_for

if TYPE_CHECKING:
    from qgis_sdk.core.contexts import UiContext
    from qgis_sdk.declarations import ActionDescription

from ._form import Form

__all__ = ["for_action", "from_schema"]


def from_schema(
    cls: type[Form],
    schema: Mapping[str, Any] | ActionDescription,
    *,
    name: str = "form",
    action_id: str | None = None,
    initial: Mapping[str, object] | None = None,
) -> Form:
    """Build the inputs a request schema (or an action's description) declares.

    The kind of each field comes from the ``x-qgis-sdk`` annotation the
    describer put on it; a ``FieldInput`` follows the layer field its
    ``of`` names, which must be in the same schema.

    Args:
        schema: The request schema or action description to build from.
        name: The form's name in the surface.
        action_id: The action a submit runs.
        initial: The values the fields start with.
    """
    request = schema if isinstance(schema, Mapping) else schema.request
    if action_id is None and not isinstance(schema, Mapping):
        action_id = schema.id
    owner = f"action {action_id!r}" if action_id else "form"
    specs = schema_fields(request, owner=owner)
    form = cls(inputs_for(specs, owner=owner), name=name, action_id=action_id)
    if initial:
        form.set_values(initial)
    return form


def for_action(
    cls: type[Form],
    ctx: UiContext,
    action_id: str,
    *,
    initial: Mapping[str, object] | None = None,
    name: str = "form",
) -> Form:
    """The form for one of the plugin's actions, attached to ``ctx``.

    ``initial`` sets field values first (a name the action lacks is
    refused), typically the surface's ``self.initial``.

    Args:
        ctx: The context the form is attached to.
        action_id: The action to build the form for.
        initial: The values the fields start with.
        name: The form's name in the surface.
    """
    action = ctx.actions.describe(action_id)
    form = cls.from_schema(action, name=name, action_id=action.id)
    form.attach(ctx)
    if initial:
        form.set_values(initial)
    return form
