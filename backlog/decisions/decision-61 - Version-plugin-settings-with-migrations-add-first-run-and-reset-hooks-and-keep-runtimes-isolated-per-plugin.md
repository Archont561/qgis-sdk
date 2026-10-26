---
id: decision-61
title: Version plugin settings with migrations, add first-run and reset hooks, and keep runtimes isolated per plugin
date: '2026-10-26'
status: accepted
---
## Context

`ctx.settings` is a prefixed key/value store with no notion of version;
nothing runs on first install; QGIS has no uninstall hook, so plugin data
outlives the plugin; profiles are implicit. Two plugins built with different
SDK versions coexist today because `build` vendors the runtime under each
plugin with an import rewrite (decision-50, plugin-coexistence harness),
which is the right answer and should be written down rather than
rediscovered.

## Decision

1. **Settings carry a schema version.** `settings_version: int = 1` on the
   plugin class; `@migration(from_version, to_version)` functions on the
   plugin receive a `SettingsMigration` (read/write/remove on the plugin's
   prefix) and run in order on start before the plugin constructs; a
   failed migration refuses the start with a named error and leaves the
   stored version untouched. Settings are per QGIS profile because
   `QgsSettings` is.
2. **Lifecycle hooks are optional methods.** `on_first_run(self)` runs once
   per profile and plugin version series; `on_upgrade(self, previous)` runs
   when the stored version differs; `on_reset(self)` backs the standard
   "Reset plugin data" surface the catalogue offers (`ResetAction`), which
   clears the prefix, owned temporary outputs and the first-run marker.
   Uninstall cleanup is documented as unavailable from QGIS; reset is the
   mechanism offered to users.
3. **Runtimes are isolated per plugin.** The vendored runtime under
   `<plugin>/_vendor/` with the rewritten import root is the only supported
   way to install a built plugin; two plugins on different SDK versions
   never share modules, and the coexistence harness is the proof. The
   console's `connect()` targets one plugin's runtime at a time.
4. **Owned temporary outputs are registered** in the plugin prefix so
   reset and `on_upgrade` can remove them; `FileRef` already names them.

## Consequences

- `describe_plugin` gains `settings_version`; migrations are pure functions
  testable with the settings fake.
- Tasks: TASK-104 in m-11.
