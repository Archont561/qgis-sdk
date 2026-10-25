---
id: doc-5
title: TASK-12 validation backend spike evidence
type: other
created_date: '2026-10-16 14:05'
---

# TASK-12 — archived backend evidence and direct-generator review

**Status (2026-10-16):** No production validation or TypeScript generation backend has been selected. At the user's request, the entire experimental `packages/qgis-sdk-python/tests/spikes/` tree (DTO fixtures, Python tests, JSON Schema snapshots, JS harness, and its test-only dependency manifests) was removed from the checkout. The old apischema/TypeAdapter and direct-generator observations below remain **historical results**, not checks a fresh checkout can rerun. A separate, durable **test-only** mashumaro → JSON Schema → `json2ts`/Ajv contract example was subsequently added (see below); its development dependencies are now pinned in the Pixi/Bun locks, but no candidate was added to SDK **runtime** dependencies. The QGIS-free `ResourceScope` Hypothesis and BDD tests also remain in the normal test suite.

## The SDK requirements

[ADR-10](../../decisions/decision-10%20-%20Use-dataclass-authoring-and-schema-driven-TypeScript-generation.md) proposes ordinary stdlib dataclasses, separate request/result-reader/result-writer schemas, generated TS **and** runtime validators, deterministic checked bindings, and a pure-Python-first packaging policy. [ADR-22](../../decisions/decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md) rejects unknown request fields and implicit coercion; defaulted, nullable, and required fields must retain their distinct meanings. A TS `interface` alone does not validate JSON or enforce protocol compatibility.

The retired experiment used a tagged `RunRequest | CancelRequest` union, an integer count, defaulted mode, nullable/defaulted label, a result with defaulted/nullable `note`, a recursive dataclass, and an independently specified set of **25** valid/invalid JSON examples (13 requests, 7 result readers, 5 serialized results). These examples are described here for context, **not retained as runnable test assets**.

## Earlier apischema / TypeAdapter experiment (archived)

| Probe run before removing the harness | Observed outcome |
| :-- | :-- |
| Isolated Python 3.14.8, apischema 0.19.0 and Pydantic TypeAdapter 2.14.1 | **16 passed, 1 strict expected failure**: apischema cannot deserialize a Python 3.14 eager-annotation dataclass (`KeyError('count')`). Dataclasses using future/string annotations passed the chosen probes. |
| Supplemental Python 3.11.2 | **17 passed**. An explicitly installed apischema universal wheel ran its subset (**9 passed; 8 Pydantic-only skips**); default 3.11 pip resolution selected a compiled apischema wheel instead. |
| Separate Python and frontend checks | Both candidates passed the strict/default/nullable/union/result-schema examples and backend-specific constraint and recursive probes. Ajv 8.20.0 agreed with all **25 fixed cases per backend**; `json-schema-to-typescript` 16.0.0 generated deterministic TypeScript that passed a TypeScript 7 static check. The JS check did not exercise the Hypothesis-generated Python cases. |
| QGIS 4.2.3 / Qt 6.11.2, Linux Python 3.14.8 | Both candidates co-imported with PyQGIS and performed sample decoding/schema generation in one process. This is not QGIS Desktop, Windows, WebEngine, or installer qualification. |

Pydantic's tested strict dataclass path used `with_config(ConfigDict(strict=True, extra='forbid', json_schema_serialization_defaults_required=True))` and `TypeAdapter(...).validate_json(...)`; `validate_python(dict)` was not an equivalent strict transport entry point. Input schemas allowed defaulted fields to be omitted, whereas output schemas required values serialized with defaults. Pydantic's mandatory `pydantic-core` **2.50.1** is native; selecting it as runtime would require explicit reconsideration of pure-Python-first packaging. Apischema has a pure wheel, but the Python 3.14 eager-annotation defect, wheel-resolution behavior, and maintenance need resolution. Neither was selected. The complete original harness and schema snapshots are **not present** after the requested cleanup, so these historical numbers are not a current regression gate.

The previous root suite before cleanup had 23 Python passes plus 17 intentional optional-candidate skips, 2 bridge passes, and 100% Python/bridge coverage. After cleanup, the fresh root suite has **23 Python passes, no candidate skips, and 2 bridge passes** (the bridge test task replayed its cached output); a fresh coverage run reported **100%** Python and bridge. Ruff, Biome, bridge typecheck, and Python wheel/sdist/Twine checks also passed. These present checks **do not** exercise either validation backend. The full Conda package build was previously blocked by unavailable conda-forge repodata in this sandbox; it was not retried for this cleanup, so no Conda package qualification is claimed. The restored sandbox's integrity could not be independently verified.

## Live checked contract example (added after spike removal)

The new, persistent `packages/qgis-sdk-python/tests/contract_sample/` example is **not** the retired spike recreated under another name: it has only one ordinary dataclass request/result pair, no production public DTOs or Python decoder, and does not rerun the apischema/TypeAdapter comparison. Its `generate_contract.py` entry point is invoked by the root `sdk:generate` package script in a QGIS-free Python build environment. Mashumaro **3.23** emits Draft 2020-12 schemas for the request and the separately authored result reader. For the writer, the example requires all fields that its default-including serializer emits; the reader accepts only an explicitly declared `revision` extension, not arbitrary extra properties. Three generated schemas and `json-schema-to-typescript` **16.0.0** declarations are checked in under `packages/qgis-sdk-typescript/tests/contracts/generated/`. Biome excludes generated artifacts so its formatter cannot silently change codegen output.

The Python tests compare a fresh export byte-for-byte to the checked schemas, use **test-only** `jsonschema` **4.26.0**'s Draft 2020-12 validator on **24 independently specified JSON cases**, exercise result serialization with Hypothesis, and include five pytest-bdd scenarios. Bridge tests use Ajv2020 **8.20.0** with `coerceTypes: false`, `useDefaults: false`, `removeAdditional: false` on the **same 24 cases**, verify that validation does not mutate payloads, and compare the checked TS byte-for-byte to `compileFromFile`; TypeScript 7 checks required/nullable/defaulted distinctions. On Linux/Python 3.14.8, the current root coverage run passed **55 Python tests and 30 bridge tests**, with **100% measured production-source coverage** for each package. Ruff, Biome and TS typechecking also passed. An isolated Linux/Python 3.11.2 Mashumaro smoke export reproduced the same three schema files byte-for-byte; this was not a 3.11 test-suite or QGIS run. The Hypothesis-generated Python data are not sent to Ajv; shared cross-language examples are the fixed cases.

Mashumaro is **schema export only** here: its default `JSONDecoder` was separately observed to coerce `"2"`, `true` and `2.5` to integers and ignore extra properties, contrary to its generated schema. The `jsonschema` oracle depends transitively on native `rpds-py` but is **development/test-only**, not a selected plugin runtime validator. A strict Python request decoder still needs a decision and durable end-to-end validation. Also unresolved: unions/recursion/constraints and JS-safe integer limits, a general SDK generator/operation map, separate real client/runtime validators, protocol identity, QGIS WebEngine CSP-safe standalone Ajv compilation and non-Linux qualification. This example proves the small generation and schema-test seam, **not** production wire-contract compatibility.

## Direct Python-to-TypeScript generators proposed by the user

Assessment dated **2026-10-16**, using **isolated, ignored Python 3.14.8 venvs**, a supplemental Python 3.11.2 venv where noted, temporary DTO examples outside the repository, and the TypeScript 7 CLI. All three installed or built as pure Python **generation tools**; none was installed into the SDK or the Pixi/Bun locks. Release dates below refer to releases, not GitHub activity or PyPI metadata's broad compatibility claims.

| Project | What worked | Blocking observations against this SDK's contract |
| :-- | :-- | :-- |
| [`python-to-typescript-interfaces` 0.2.0](https://pypi.org/project/python-to-typescript-interfaces/) ([source](https://github.com/NalyzeSolutions/python_to_typescript_interfaces), released **2024-07-02**) | Pure wheel, MIT; installs with pure `astroid==3.2.1` on Python 3.14. A subclassed legacy `Optional[str]` field emitted `string | null`. | Requires author DTOs to inherit its `Interface` marker: **ordinary dataclasses yielded no interfaces**. A subclassed `Literal` raised `KeyError('Literal')`; `str | None` emitted the unresolved type `UNKNOWN` (TypeScript 7 rejected it); a field with a default was still required in TS. No separate input/output schemas or runtime JSON validation. PyPI classifiers stop at Python 3.12; a basic 3.14 invocation worked, not full 3.14 compatibility. Its pinned `astroid` is LGPL-2.1-or-later. |
| [`py-to-ts-interfaces` 1.4.0](https://pypi.org/project/py-to-ts-interfaces/) ([source](https://github.com/Syndallic/py-to-ts-interfaces), released **2022-09-03**) | Pure wheel, MIT, no declared runtime dependencies; a restricted, old-style dataclass can emit a TS interface. | Text/line parser restricts what can appear in source files; the ordinary DTO module raised `IndexError`. A standalone modern request emitted `Literal["run"]`, `str | None`, and a Python `= "safe"` initializer into TS; TypeScript 7 reported syntax errors. Its legacy `Optional[str] = None` became `note?: string`, losing JSON `null`. No JSON Schema, validation, or separate input/output modes. |
| [`Latios96/py-typescript-generator` v0.3.1](https://github.com/Latios96/py-typescript-generator) ([release](https://github.com/Latios96/py-typescript-generator/releases/tag/v0.3.1), **2023-06-29**) | MIT, Python `>=3.10`, pure wheel built from the tagged GitHub source with pure dependencies; a plain dataclass containing `int`/`str` produced an interface on Python 3.14. Unlike the first option, it does **not** require a base class. | No PyPI distribution was found; use a pinned Git tag/source build. The full DTO failed at `Literal['run']`, and a PEP 604 union alias was rejected as “not a class.” On Python 3.14 even `Optional[str]` failed (`IsNotAClassException: str | None`); on Python 3.11 it emitted `note?: string` for a nullable field, which TypeScript 7 rejected when assigned `null`, and a nonnullable defaulted field remained required. No separate input/output schemas or runtime validator. GitHub main was pushed in October 2026, but the changes since v0.3.1 concern workflows and the dependency lockfile, not generator source. |

The direct-generator probes above used the **same semantic field shapes** as the retired experiment where supported. TypeScript checks were deliberately strict: the first option's `UNKNOWN` produced TS2304, the second option's emitted syntax produced TS1005/TS1131, and the third option's `note?: string` rejected a valid JSON `note: null` with TS2322. Their ability to install is **not** evidence that generated declarations match wire behavior. None supplies Python request validation, JSON Schema, Ajv-compatible runtime validators, contract/version checks, or a reader/writer asymmetry. The new generators were **not** qualified under a full QGIS lifecycle or on Windows.

### Recommendation

**Do not use any of these three as the SDK's backend or its sole binding generator.** `python-to-typescript-interfaces` may be useful for an opt-in, subclassed legacy DTO project; `py-to-ts-interfaces` is too brittle for this contract; `py-typescript-generator` is the closest *basic dataclass-to-interface* tool on Python 3.11 but fails important Python 3.14 and nullable/union requirements. All would still need an independently chosen strict Python runtime validator and matching frontend runtime schema/validator, plus deterministic cross-language drift tests. Prefer a schema-first generator from a validated description once a Python backend and neutral constraint model are selected. Do not adopt a native runtime indirectly to compensate for these tools.

With the user-requested removal of the spike harness, **there is still no in-repository comparison of production Python request-validation backends**. The live example now covers a narrow subset of strict JSON Schema semantics and generated-TS/Ajv parity, but not a selected Python decoder or actual SDK traffic. Before choosing a production backend or generator, extend persistent contract tests for the remaining unions/recursion, constraints and integer limits, error diagnostics, supported Python/QGIS platforms, and matching Python/runtime/client behavior. The earlier candidate comparisons in this report remain historical evidence, not a substitute for those tests.

## Post-merge verification and strict-validator continuation (2026-10-16)

PR #5 landed as `689b137e9def05a5538df46238a55f4169863599`. GitHub reports
[post-merge CI](https://github.com/Archont561/qgis-sdk/actions/runs/38944159777)
and [sandbox publication](https://github.com/Archont561/qgis-sdk/actions/runs/38944159757)
successful for that exact SHA. CI checks lint/format, TS typechecking and separate
coverage gates; it does **not** build/qualify the Conda package or test WebEngine.
Publication covers the `developer` bundle (`default,build,bun`) on **linux-64 only**.
The published branch snapshot is `86fc5d4`, whose manifest identifies source
`689b137` and lock SHA-256
`1cb256b37e4ae0be61789ac6ae79e4cfca07f350d836306fd332e770a81cb68e`.

### Restore failure investigation

`bash scripts/restore.sh` with pixi-sandbox 0.7.0 verified all **594 transport blobs
(948.5 MiB)**, materialized all three environments, then exited 1 at tree
verification with **nine RECORD integrity mismatches**:

- build: coverage, hypothesis, jsonschema, mako, pytest-bdd;
- default: hypothesis, jsonschema, mako, pytest-bdd;
- bun: zero verification failures.

For example, build Hypothesis RECORD expected
`79bac6198fa593155ddbce97c1b7339b975d0a8c09a13e56ed93edbcd4491119`, got
`84f1e20c2825ca81f7a0eed69a6bc7ad9d5446918c5325adc6b66016f31deceb`.
Inspection of the five affected build distributions against their packed wheels
found no changed rows shared with the wheels' original RECORDs. Added rows describe
installer metadata and generated console entrypoints. The restored build
Hypothesis entrypoint has the local shebang, but its RECORD row records 358 bytes
versus the actual 337 bytes after relocation (the same 21-byte size difference
occurs for the other affected build entrypoints). This points investigation toward
installation/relocation and RECORD normalization, **not a demonstrated transport
corruption**. It does not establish the exact cause of the manifest mismatch:
publisher-side RECORD bytes and the verifier's normalization must still be
compared. Do not “fix” this by dropping integrity checks or accepting new hashes.
`gh run view 38944159757 --log` could not retrieve the Actions log archive (EOF
from the results-receiver host); job/step conclusions were available through the
API. The restore work directory remains ignored under `.pixi/.restore-work`.

The user authorized qualified local checks with `PIXI_FROZEN=true` and
`PIXI_NO_INSTALL=true`; those results **do not repair or verify the restore**.
The frozen Bun install succeeded without dependency-file changes.

### Current decision and durable evidence

The agreed test seam remains ordinary dataclass DTOs → decoding/schema → checked
TS/Ajv. New normal-suite tests in `tests/test_request_validation.py` and three
additional BDD examples characterize the **existing default decoder**, not a new
SDK entrypoint:

- Hypothesis generates numeric strings that schema validation rejects but default
  mashumaro decoding converts to integers, and unknown fields that the schema
  rejects but decoding silently discards (80 examples/property).
- Fixed counterexamples also show `true → 1`, `false → 0`, and `2.5 → 2`.
- A valid-request property checks defaults/nullability and nonmutation by the
  schema oracle. Construction supplies defaults separately from validation.
- JSON Schema accepts `2.0` as an integer value. A strict Python token-type rule
  is **not** equivalent to JSON Schema's numeric semantics or JavaScript numbers.
  This characterization is not an SDK policy decision.

**Decision boundary:** reject mashumaro's default decoder as the strict request
validator. Retain its checked schema/serialization example strictly as test tooling.
Schema-first prevalidation is worth evaluating, but do not promote the current
`jsonschema` oracle to runtime: its dependency graph includes native `rpds-py`.
Pydantic remains a native-policy exception, not an implicit fallback. Pure-wheel
apischema is still a candidate for a focused, durable evaluation, conditional on
resolving its historical Python 3.14 eager-annotation failure and verifying actual
pure-wheel resolution. No production backend is selected, and no runtime
requirements, dependency locks, generated bindings or removed spike files change.
Avoid a broad hand-written validator/converter merely to bypass these blockers.

Before selecting a backend, agree JSON integer/safe-number limits (including
integral floating values), nonfinite numbers and duplicate-key handling at the
raw-JSON boundary; then extend the durable seam for nested/tagged unions,
recursion, constraints, missing/null/default behavior, structured path diagnostics,
nonmutation and Python/client parity. Current generated Hypothesis cases run only
in Python; cross-language coverage remains the 24 shared fixed cases. Production
handler dispatch, authorization and version compatibility remain downstream.

### Qualification still missing

- **Conda:** publication of development environments is not an SDK recipe build,
  install or smoke-test qualification. The prior repodata-access failure remains
  unresolved; no new Conda package success is claimed.
- **WebEngine/Desktop:** no real request/handler bridge, browser lifecycle,
  reconnect/cancellation or Qt/WebEngine qualification. Historical PyQGIS co-import
  is not a substitute.
- **Platforms:** this session's checks use Linux/Python 3.14.8 in an unverified
  restore. There is no current full Python 3.11+ matrix, Windows/QGIS installer or
  macOS qualification, nor a clean-prefix verified sandbox restore.

TASK-11 can close against landed contracts and green post-merge CI. TASK-12 stays
In Progress: its checked historical comparison criteria do not mean production
selection or platform qualification is complete. This continuation is local until
separately reviewed and landed.

Qualified local validation for this continuation: root `bun run test` passed
**65 Python / 30 bridge** tests (no Turbo replay); root `bun run coverage` passed
both separate 90% gates with **100% measured production-source coverage** (fresh,
also rerun after the final test assertion). Commands ran through Pixi's Bun
environment. Ruff lint/format, Biome, bridge typecheck, Python wheel/sdist + Twine,
bridge build and `git diff --check` passed. The full root build/Conda build was not
rerun. No tracked lock/dependency files changed. Test coverage percentages do not
measure completeness of the still-unimplemented production validator.

## Pydantic binary-wheel build/install probe (2026-10-16)

The user requested a build spike and selected **binary-wheel deployment**, not a
Rust source build or Conda recipe build. This is an exception for isolated
**evaluation only**, not a runtime selection or a change to ADR-3. All temporary
consumer sources, venv, wheelhouse and probe tests live under ignored
`.pixi/pydantic-wheel-probe/`; the removed `tests/spikes` tree is not restored.
The ordinary durable contract tests remain unchanged by this probe.

### Built and installed

- Host: Linux x86-64, Pixi Python **3.14.8**, using the previously authorized
  partially restored environment with `PIXI_FROZEN=true PIXI_NO_INSTALL=true`.
  The restore integrity failure remains unresolved.
- Created a fresh venv with `pixi run -e build python -m venv
  .pixi/pydantic-wheel-probe/venv`. The base build environment has no pip;
  venv/ensurepip supplied pip **26.2.1** without modifying the base environment.
- Built a temporary `qgis-sdk-pydantic-probe==0.0.0` stdlib-dataclass consumer via
  Hatchling **1.32.4**, with `requires-python >=3.11` and runtime requirement
  `pydantic==2.14.1`. This is **not** a new build of the SDK with Pydantic enabled.
  `python -m build --no-isolation` built its sdist and
  `qgis_sdk_pydantic_probe-0.0.0-py3-none-any.whl`.
- Downloaded with pip `--only-binary=:all:`: Pydantic **2.14.1**, native
  pydantic-core **2.50.1**, annotated-types **0.8.0**, typing-extensions **4.16.0**,
  typing-inspection **0.4.4**. The core artifact selected was
  `pydantic_core-2.50.1-cp314-cp314-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`.
  No Rust/compiler invocation or dependency source build was needed.
- Installed the consumer and dependencies with `--no-index --find-links` from the
  downloaded wheelhouse. `pip check`: **No broken requirements found**. Consumer
  and core imports resolve inside the isolated venv, not the temporary source tree.
  Resolved versions and wheel SHA-256 values are saved locally in `resolved.txt`
  and `SHA256SUMS`. These are diagnostic artifacts, not a committed release lock.

### Validation after installation

The consumer copies the existing sample `RunRequest` stdlib dataclass and applies:

```python
from pydantic import ConfigDict, TypeAdapter, with_config

with_config(ConfigDict(strict=True, extra="forbid"))(RunRequest)
request_adapter = TypeAdapter(RunRequest)
# JSON transport entrypoint, not validate_python(dict):
request_adapter.validate_json('{"kind":"run","count":2}')
```

Installed-wheel checks ran with the venv's `python -I -m pytest`:
**19 passed** — 12 existing shared request cases, two Hypothesis properties
(80 examples each: defaults/numeric-string rejection and unknown-field rejection),
four strict integer counterexamples (`true`, `false`, `2.5`, `2.0`), and one BDD
scenario for omitted defaults. Unknown fields report
`unexpected_keyword_argument`; integer errors locate `count`. Test tools were
pytest **9.1.1**, Hypothesis **6.169.4**, pytest-bdd **9.0.0**. These scratch checks
are not an added persistent production-validator regression gate.

The normal Pixi activation's project `PYTHONPATH` did not expose `qgis` initially
(`ModuleNotFoundError`). Adding `<default-prefix>/share/qgis/python` and the
isolated venv site-packages explicitly to the **default environment's** `sys.path`
allowed **QGIS 4.2.3**, Pydantic and the native core to co-import and decode the
sample request in one process. The core loaded a
`_pydantic_core.cpython-314-x86_64-linux-gnu.so` from the venv. No installation into
QGIS's shared environment occurred. This is a co-import/decoding smoke, not a QGIS
Desktop, application lifecycle or WebEngine test.

### Conclusion and remaining gates

**Binary-wheel deployment is feasible for this Linux/Python target:** the consumer
stays a universal Python wheel while its dependency supplies the native extension.
It does not prove Windows/macOS or other QGIS Python versions, source-build
support, Conda packaging, plugin ZIP assembly, plugin-private import isolation,
shared-plugin dependency compatibility or a safe end-user installer.

A concrete semantic gap remains: strict Pydantic JSON decoding rejects `2.0` for
`int`, whereas JSON Schema accepts integral numeric values and JavaScript does not
preserve the integer/floating token distinction. The 12 fixed request cases agree,
but this probe does **not** establish general Python/Ajv parity. Resolve numeric
policy and add durable cross-language tests before selection. Result-reader/writer
schemas, unions/recursion and constraints are outside this build probe.

No SDK runtime requirements, Pixi/Bun locks, production sources or checked generated
contracts changed. No dependency installer was implemented. TASK-12 stays open and
pure-Python-first remains the accepted default; using Pydantic as a mandatory
runtime still needs explicit packaging-policy approval.

## Numeric policy and bounded pure-Python comparison (2026-10-16)

The user requested execution of the proposed next steps. ADR-22 now specifies
finite integral JSON-number values within ±9007199254740991 inclusive. Integral
`2.0` is accepted; strings, booleans, fractions, nonfinite values and out-of-range
numbers are rejected. This is decoded-number semantics, not arbitrary-precision
validation of original JSON numeric lexemes.

### Durable sample contract changes

Added an independently specified unsafe-number request case first; its Python
schema test failed because the unbounded schema accepted it. Then added test-only
Mashumaro `Minimum`/`Maximum` annotations to request/result integer fields and
regenerated the three schemas through `sdk:generate`. The failing test passed.
The generated TS declarations remained unchanged (TypeScript number does not
express the bounds).

The shared Python/Ajv corpus now contains **40 cases**, including integral numeric
values, both safe boundaries and both unsafe sides for all three wire directions.
Normal-suite Hypothesis properties exercise safe integers/integral floats and
out-of-range values; fixed tests reject nonfinite numbers. Two additional BDD
scenarios cover integral-float acceptance and unsafe-number rejection. These are
persistent tests at the existing agreed DTO/schema seam, not a restored backend
spike or a public numeric type. Candidate-specific experiments remain temporary.

### Apischema 0.19.0 pure-wheel result

PyPI's current release remains 0.19.0. Explicitly downloaded and installed
`apischema-0.19.0-py3-none-any.whl` with `--no-deps` into a separate venv under
`.pixi/apischema-probe`. SHA-256:
`25e253ecb860bebbb4f4f5ed2896b4d69d49c86754c83795eb2ec1ec5c1ed62b`.
`pip check` passed; no unconditional runtime requirements and no installed `.so`
modules. Metadata license: MIT. This verifies this artifact, not default resolver
behavior (other wheel variants can exist).

- The same eager-annotation request shape on Python 3.14.8 still fails:
  `KeyError('kind')`; a minimal one-field dataclass similarly raises
  `KeyError('count')`.
- A module using `from __future__ import annotations` with bounded
  `Annotated[int, schema(min=..., max=...)]` works, defaults correctly and emits
  integer/minimum/maximum schema constraints.
- With `coerce=False, additional_properties=False`, **17/18 shared request cases
  pass**. The mismatch is integral `2.0`, rejected as “expected type integer,
  found number.” Inputs were not mutated. Unknown fields report a structured
  location and “unexpected property.”
- `coerce=True` accepts `"2"` as integer 2, so blanket coercion violates the
  agreed policy.
- Supplemental future-annotation checks: **7 passed** (two 80-example Hypothesis
  properties covering defaults/numeric strings and unknown fields; five fixed
  invalid-number cases). This successful subset does not mask the two blockers.

Minimal eager-annotation reproduction in that environment:

```python
from dataclasses import dataclass
from apischema import deserialize

@dataclass
class Request:
    count: int

deserialize(Request, {"count": 2}, coerce=False, additional_properties=False)
# Python 3.14.8 / apischema 0.19.0 pure wheel: KeyError('count')
```

**Outcome:** do not select apischema from this evaluation. Requiring future
annotations and an additional numeric adapter would change the authoring/support
contract; neither workaround is silently accepted here.

### Explicit Pydantic numeric adapter

Rebuilt and reinstalled the temporary universal consumer wheel using the existing
binary-wheel dependency set. The field-scoped adapter is:

```python
import math
from typing import Annotated
from pydantic import BeforeValidator, Field

def integral_json_number(value):
    if (type(value) is float and math.isfinite(value)
            and value.is_integer() and abs(value) <= 9007199254740991):
        return int(value)
    return value  # strict int still rejects strings, bools and other values

# On the request dataclass; strict=True and extra='forbid' remain enabled.
count: Annotated[
    int,
    Field(ge=-9007199254740991, le=9007199254740991),
    BeforeValidator(integral_json_number),
]
```

**Annotation order mattered in the tested version.** Putting `BeforeValidator`
before `Field` produced `ge`/`le` keys in the emitted count schema; strict Ajv
compilation failed with “unknown keyword: ge”. Placing `Field` before the validator
emitted proper `minimum`/`maximum` keywords and strict Ajv compilation passed.
Do not suppress Ajv strictness or claim the first schema was compatible.

The installed consumer then passed **24 checks**: all 18 shared request cases,
two Hypothesis properties, three invalid-number cases and the existing BDD
scenario. A deterministic Hypothesis run generated **480 numeric cases** from
80 draws (safe integer, safe integral float, numeric string, bool, unsafe integer
and fraction per draw). The installed adapter accepted/rejected all as expected;
Ajv independently checked the same corpus against both the bounded sample schema
and Pydantic's emitted request schema: **480/480 each, no mutation**. Separate raw
`NaN`, `Infinity`, `-Infinity` count tokens were rejected by the adapter.

PyQGIS 4.2.3 co-import and decoding `count: 2.0` to Python integer 2 passed with the
explicit QGIS module path. The probe consumer is still test-only; its rebuilt wheel
supersedes the earlier scratch consumer, not the SDK package. Generated parity data
and candidate tests are ignored local artifacts, not new runtime/codegen tools.
The persistent 40-case corpus and numeric property/BDD tests preserve the agreed
contract independently of candidate experiments.

### Recommendation and qualification boundary

Pydantic is now the leading **controlled-deployment candidate**, not a selected
mandatory runtime. Keep ADR-3 pure-Python-first ordinary plugin distribution intact.
A scoped deployment-policy approval is still needed before implementing Pydantic
as runtime. Do not build an installer or broad custom validator as a workaround.

Real Windows QGIS testing cannot run in this Linux sandbox. No Windows/macOS
installation, clean-QGIS conflict test, actual Desktop/WebEngine run, Conda recipe
build or native source compilation is claimed. These gates cannot close based on
wheel availability or co-import alone. Advanced constraints/unions/recursion and
reader/writer runtime adapters are also outside this bounded comparison.

Final qualified checks for this continuation: root `pixi run -e bun bun run test`
passed **88 Python / 46 bridge** tests without cache replay; root
`pixi run -e bun bun run coverage` freshly passed both 90% gates with **100%
measured production-source coverage**. Ruff lint/format, Biome, bridge typecheck,
both isolated venvs' `pip check` and `git diff --check` passed. Apischema's
future-annotation integer request also co-imported and decoded with PyQGIS 4.2.3;
this does not fix eager annotations or integral-float semantics. All Pixi commands
preserved frozen/non-installing settings in the unverified restore. No new full
SDK/Conda build or clean-target qualification was performed. No commit, push or
merge occurred.

## Optional controlled-deployment Pydantic adapter prototype (2026-10-16)

Implemented the agreed bounded contract slice without reviving the removed spike
harness. `qgis_sdk.adapters.pydantic.PydanticContractAdapter` lazily loads Pydantic
when explicitly constructed, strictly validates request JSON, dispatches a typed
handler, validates/serializes writer results with defaults, and exports separate
request, result-reader, and result-writer schemas. The prototype fails actionably
when Pydantic is missing or is not exactly the tested **2.14.1**. Its optional
`controlled-deployment` extra pins Pydantic 2.14.1; the ordinary package metadata
has no Pydantic base requirement and no startup installer. Pydantic's native
`pydantic-core` remains opt-in. `qgis_sdk.adapters.pydantic_types.SafeJsonInteger`
uses a field-scoped integral-number adapter and bounded `Field` metadata in the
schema-compatible annotation order; integral floats such as `2.0` are accepted,
while booleans, strings, fractions, nonfinite values, and values outside the
inclusive JavaScript safe-integer range are rejected.

The persistent model fixtures and exporter are separate from the Mashumaro sample
under `packages/qgis-sdk-python/tests/contract_sample/pydantic_*`. Checked schemas and
`json2ts` declarations live under
`packages/qgis-sdk-typescript/tests/contracts/pydantic/generated/`. Python's
`jsonschema` oracle and Ajv2020 each validate the same **40 shared examples** for
both schema sets with coercion/default insertion/additional-field removal disabled;
tests also assert payload nonmutation, checked schema/type drift, and TypeScript
required/default/nullable distinctions. Durable Pydantic coverage includes Hypothesis
properties for valid typed dispatch, invalid scalar redaction, and unsafe integers,
plus four pytest-bdd scenarios for defaults, safe error paths, reader/writer
asymmetry, and integral floating JSON numbers. `QgisSdkContractValidationError`
contains only direction, paths, and validator codes, not rejected values.

Validation in this session: **152 Python tests passed**, with **100% measured
production-source coverage**; bridge **90 tests passed**, with **100% measured
source coverage**; Ruff lint/format, Biome, bridge typecheck, `pixi lock --check`,
schema/type regeneration, Python wheel/sdist build and Twine checks passed. The
wheel metadata confirms Pydantic only under optional extras, and a wheel-only smoke
import without Pydantic exercised the actionable inactive-adapter error. The tests
used Pixi's restored Linux/Python **3.14.8** plus an isolated binary-wheel overlay
of Pydantic **2.14.1** / `pydantic-core` **2.50.1** (`pip check` clean); the restored
Pixi prefixes themselves were not modified to add that overlay.

Restore verification remains failed, not repaired: `bash scripts/restore.sh`
verified all **594 transport blobs** but exited 1 on **nine RECORD integrity
mismatches** (build: coverage, hypothesis, jsonschema, mako, pytest-bdd; default:
hypothesis, jsonschema, mako, pytest-bdd; Bun: zero). Checks preserved
`PIXI_FROZEN=true` and `PIXI_NO_INSTALL=true`; an isolated ignored venv supplied the
optional Pydantic wheel. These results are qualified against that **unverified
restore**, not proof of environment integrity. No Windows or clean QGIS installation,
plugin coexistence, Desktop/WebEngine, Conda/package delivery, or full native-runtime
qualification was performed. Pydantic remains an optional prototype and TASK-12
stays **In Progress** pending those deployment gates and an explicit future policy
review; no commit, push, or merge occurred.

## Spike closeout: landed state and remaining gates (2026-10-17)

This section records what actually landed from the work described above, what a
fresh checkout can reproduce today, and which claims stay historical. It does
**not** select a production backend, change runtime requirements or dependency
locks, or claim platform qualification. Checks below ran in this Linux sandbox
with `PIXI_FROZEN=true PIXI_NO_INSTALL=true` against a restore that still fails
integrity verification (transport verified: **603 blobs, 953.9 MiB**; then
**nine** `RECORD` mismatches — build: coverage, hypothesis, jsonschema, mako,
pytest-bdd; default: hypothesis, jsonschema, mako, pytest-bdd; bun: zero).

**Supersedes:** the closing paragraphs of the sections above state that "no
commit, push, or merge occurred". That describes their pre-landing state; the
corresponding content is now in `main` (see the commits below).

### Landed commits and CI

| PR | Merge commit | Content | CI for that commit |
| :-- | :-- | :-- | :-- |
| [#6](https://github.com/Archont561/qgis-sdk/pull/6) | `c37dc73184aadc4f5158bb4e4885e206861da8fd` | ADR-22 JSON integer policy, bounded durable sample schemas, 40-case Python/Ajv corpus | `checks`, `plan`, `publish` success |
| [#7](https://github.com/Archont561/qgis-sdk/pull/7) | `7287a5481034e4e70cf38bc104dc206000a35ebe` | Optional controlled-deployment Pydantic adapter slice (`adapters/pydantic.py`, `adapters/_pydantic_compat.py`, `adapters/pydantic_types.py`), persistent Python/BDD/Hypothesis/generation tests, checked Pydantic schemas and `json2ts` declarations | `checks`, `plan`, `publish` success |
| [#8](https://github.com/Archont561/qgis-sdk/pull/8) | `ae361d058455b2ad781fb0053e46895bae842d94` | Optional WebEngine host adapter and the `pyqt6-webengine` pin (TASK-23 work; changes the dev environment, not this spike's deliverables) | `checks`, `plan`, `publish` success |

### Current-checkout verification (2026-10-17)

Environment: Linux x86_64, Pixi `default` environment Python **3.14.8**, QGIS
**4.2.3-Belém do Pará**, Qt **6.11.2**.

- `pixi run -e bun bun run test` at `ae361d0`: **181 Python passed, 1 skipped**;
  **90 bridge tests passed**. The single skip is
  `tests/test_webengine_availability.py::test_create_webengine_view_raises_when_unavailable`
  ("Qt WebEngine bindings are installed in this environment"): the unavailable-
  binding branch no longer runs in this environment because PR #8 pinned
  `pyqt6-webengine` **6.11.0**.
- Focused contract/Pydantic selection (7 files: `test_pydantic_adapter.py`,
  `test_pydantic_contract_bdd.py`, `test_pydantic_contract_generation.py`,
  `test_pydantic_optional_boundary.py`, `test_request_validation.py`,
  `test_contract_bdd.py`, `test_contract_generation.py`): **129 passed**.
- Pydantic **2.14.1** / `pydantic-core` **2.50.1** now come from the Pixi
  `python` feature's PyPI pins in `pixi.toml`, **not** from the ignored isolated
  wheel overlay that earlier sessions needed. No Pixi prefix was extended for
  these checks.
- Packaging re-check: Hatchling **1.32.4** wheel/sdist build and `twine check`
  passed. Wheel metadata shows `Provides-Extra: controlled-deployment` and
  `Requires-Dist: pydantic==2.14.1; extra == 'controlled-deployment'`, with no
  unconditional Pydantic requirement; the wheel ships the adapter modules.
- **Conda is still blocked, not qualified:** `pixi build --path
  packages/qgis-sdk-python/recipe.yaml` fails with `failed to query the conda gateway`
  → `Request failed after 3 retries` →
  `https://conda.anaconda.org/conda-forge/linux-64/repodata_shards.msgpack.zst`
  → `tls handshake eof`. Network access to conda-forge is unavailable here.

### Historical versus reproducible evidence

| Evidence | Status in a fresh checkout |
| :-- | :-- |
| apischema 0.19.0 vs Pydantic TypeAdapter 2.14.1 comparison, 25-case corpus, Ajv 8.20.0 parity, `json-schema-to-typescript` 16.0.0 generation | **Historical.** The harness was removed on 2026-10-16 at the user's request; reproducing it means rebuilding the harness, not running a test. |
| Direct Python-to-TS generator assessment (three projects) | **Historical** install/probe observations; none of the tools is installed or locked. |
| Pydantic binary-wheel build/install probe and PyQGIS co-import smoke | **Historical**, and now superseded for environment purposes: Pydantic comes from the Pixi pins. |
| Durable mashumaro → JSON Schema → `json2ts`/Ajv sample: 40 shared cases, schema/type drift checks, Hypothesis serialization, BDD | **Reproducible:** `tests/contract_sample/`, `tests/test_contract_*.py`, bridge `contracts.test.ts`. |
| Durable Pydantic slice: strict request validation, typed handler dispatch, result serialization, `SafeJsonInteger` bounds, missing/unqualified-dependency errors, BDD/Hypothesis, generated-schema/Ajv parity | **Reproducible:** `tests/test_pydantic_*.py`, `tests/contract_sample/pydantic_*`, bridge Pydantic schema/type tests. |
| QGIS Desktop lifecycle, WebEngine, Windows/macOS, clean-prefix plugin coexistence, Conda delivery | **Not performed.** Still open (see below). |

### Outcome recorded by the spike

Pure-Python-first ordinary plugin distribution ([ADR-3](../../decisions/decision-3%20-%20Development-and-distribution-artifacts-are-separate.md))
is unchanged, and **no mandatory runtime backend is selected**. Pydantic
**2.14.1** remains the leading **controlled-deployment candidate**, reachable
only through the explicit `controlled-deployment` extra and never installed at
startup. apischema **0.19.0** is not selected (Python 3.14 eager-annotation
failure and rejection of integral `2.0`). Mashumaro's default decoder is ruled
out as the strict request validator; its schema export stays test-only. The
`jsonschema` oracle also stays test-only because it pulls native `rpds-py`.
No dependency installer, startup download or plugin-ZIP change is authorized by
this closeout.

### Gates that remain before any production backend selection

These are **not** TASK-12 acceptance criteria; they are prerequisites for
turning the prototype into a mandatory runtime, and they are owned elsewhere.

- Tagged unions, recursion and advanced constraints at the durable contract seam
  (future backend-selection decision, ahead of TASK-2/TASK-17).
- Clean supported Windows and Linux QGIS installations, native imports, and
  coexistence with another Pydantic-using plugin (**TASK-23** for toolchain
  qualification).
- Desktop/WebEngine lifecycle tests of the bridge and adapter
  (**TASK-4**, **TASK-17**).
- Conda/package delivery and plugin ZIP qualification (**TASK-8**), including
  the repodata blocker recorded above.
- An explicit deployment-scope policy review before a native validator can
  become mandatory for ordinary plugin distribution (**ADR-3**).
