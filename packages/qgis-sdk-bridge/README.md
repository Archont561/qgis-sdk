# @archont561/qgis-sdk-bridge

**TypeScript contract, wire-limit, and error primitives for QGIS `QWebEngineView` plugin interfaces.**

`@archont561/qgis-sdk-bridge` is the TypeScript companion package to [`qgis-sdk`](https://pypi.org/project/qgis-sdk/) in the [QGIS SDK workspace](https://github.com/Archont561/qgis-sdk).

> **Status (`0.1.0` experimental):** Exposes the version 1 plugin/action declaration parser (`parsePluginDescription`, `PluginDescription`, `ActionDescription`), JavaScript-safe integer wire bounds (`MAX_SAFE_INTEGER`, `MIN_SAFE_INTEGER`, `isSafeJsonInteger`), and the `QgisSdk*`-prefixed error hierarchy (`QgisSdkError`, `QgisSdkScopeClosedError`, `QgisSdkUnsupportedCapabilityError`, `QgisSdkDeclarationError`, `QgisSdkContractValidationError`, `QgisSdkValidationIssue`). `QWebChannel` transport bindings, generated operation clients, and React hooks are scheduled for subsequent `0.x` milestones.

## Exports

```ts
import {
	MAX_SAFE_INTEGER,
	MIN_SAFE_INTEGER,
	PLUGIN_DESCRIPTION_SCHEMA_VERSION,
	QgisSdkContractValidationError,
	QgisSdkDeclarationError,
	QgisSdkError,
	QgisSdkScopeClosedError,
	QgisSdkUnsupportedCapabilityError,
	QgisSdkValidationIssue,
	isSafeJsonInteger,
	parsePluginDescription,
} from "@archont561/qgis-sdk-bridge";
```

- **Safe integer bounds:** `MAX_SAFE_INTEGER` (`9007199254740991`), `MIN_SAFE_INTEGER` (`-9007199254740991`), and `isSafeJsonInteger(value)` mirror `qgis_sdk.models.MAX_SAFE_INTEGER` and `SafeJsonInteger`.
- **Version 1 plugin descriptions:** `parsePluginDescription(raw)` validates and freezes `PluginDescription` payloads (`schema_version: 1`) produced by Python's `describe_plugin(cls).to_json()`.
- **Structured SDK errors:** Every SDK exception class begins with `QgisSdk` and carries a stable wire `code` property (`"sdk_error"`, `"scope_closed"`, `"unsupported_capability"`, `"invalid_declaration"`, `"contract_validation_failed"`).

## License

MIT
