"""Generate a typed TypeScript client from one plugin description.

The input is the object ``describe(app)`` produces
([decision-26](../../../../../backlog/decisions/decision-26%20-%20Derive-the-bridge-allowlist-and-the-generated-client-from-one-declared-manifest.md)):
the plugin's id, its actions, and the request/result schemas each action
declares. The output is one module with the value types, a nested operations
map, runtime validators and `createOperations(client)`, so a frontend never
hand-writes a contract or asserts a type at a call site.

Three rules make the output trustworthy:

* **Deterministic.** The same description always produces the same bytes -
  sorted actions, no timestamps, no environment - so a checked-in file can be
  diffed by CI and reviewed like any other source.
* **Closed subset.** The generator speaks exactly the schemas
  :mod:`qgis_sdk.declarations` emits. Anything else raises rather than emitting
  ``any``, because a type that promises nothing is worse than a build failure.
* **Asymmetric.** Input validators reject unknown properties, result validators
  tolerate them: a host may add a field without breaking an older frontend, but
  a misspelled argument never reaches Python (decision-22).

A plugin's generated module imports nothing from the SDK (decision-40): it
must resolve under either npm name of the package and must not pin the page to
the SDK version the generator shipped with. A frontend passes its own
``BridgeClient`` (anything with an ``invoke`` method, plus ``subscribe`` when
the surface declares a stream), which keeps the artifact usable with a scripted
transport in a test. Its contract error therefore extends ``Error`` and carries
the wire ``code`` instead of a class relation. The host module ships inside the
package, so its contract error extends the package's own ``QgisSdkError``;
either way a page matches on ``code``, not on the class name.

Streams (decision-28) share the operations tree with actions. For each declared
stream the module emits one interface and validator per declared event kind, a
discriminated ``{kind, payload}`` union named after the stream, and a member
that opens the stream through the client's ``subscribe``. The frame envelope -
``protocol``, ``subscription_id``, ``seq`` and the ordering check - stays in the
hand-written kernel; the generated module only ever types the payload.
"""

from __future__ import annotations

from qgis_sdk_tools.generate._api import (
    DEFAULT_SCHEMA_PATH,
    DEFAULT_SDK_IMPORT,
    SCHEMA_SUFFIX,
    check_generated,
    generate_host_typescript,
    generate_schema_typescript,
    generate_typescript,
    write_generated,
)
from qgis_sdk_tools.generate._contract import (
    CONTRACT_ERROR_CODE,
    GENERATED_MARKER,
    HOST_SURFACE,
    KIND_KEYWORD,
    PLUGIN_SURFACE,
    contract_fingerprint,
    describe_plugin_spec,
    load_description,
)
from qgis_sdk_tools.generate._names import SDK_MEMBERS

__all__ = [
    "CONTRACT_ERROR_CODE",
    "DEFAULT_SCHEMA_PATH",
    "DEFAULT_SDK_IMPORT",
    "GENERATED_MARKER",
    "HOST_SURFACE",
    "KIND_KEYWORD",
    "PLUGIN_SURFACE",
    "SCHEMA_SUFFIX",
    "SDK_MEMBERS",
    "check_generated",
    "contract_fingerprint",
    "describe_plugin_spec",
    "generate_host_typescript",
    "generate_schema_typescript",
    "generate_typescript",
    "load_description",
    "write_generated",
]
