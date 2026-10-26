---
id: decision-51
title: Snapshot the plugin's own surfaces as a structured tree plus screenshot for agents and tests
date: '2026-10-26'
status: accepted
---
## Context

The owner asked for utilities that serialise a plugin's PyQt UI to YAML/JSON
with a PNG screenshot so an agent can work on it. Declared surfaces are
already a serialisation - a `DeclaredForm` is fully described by its action's
input schema, which crosses the wire and will be in `tools/list` - and custom
`dialog=`/`dock=` surfaces are plain Qt classes by decision-45. A YAML UI
authoring format would be a second widget system, which decision-46 ruled out.
What is missing is an *inspection* format: a deterministic tree of what a
surface shows, with stable ids, and a screenshot to go with it, available to
the `dev.*` agent namespace of decision-49 and to tests.

## Decision

1. **A UI snapshot is JSON plus PNG, taken on the GUI thread** of one surface
   the runtime opened (or every open one): `surface`, `kind`, `title`,
   `size`, `palette`, `scale`, `screenshot` (hash; the PNG travels beside
   it), `nodes` and `findings`. Nodes come from `findChildren(QWidget)` with
   a Qt/QGIS class → role table (`QLineEdit` → textbox, `QComboBox` /
   `QgsMapLayerComboBox` / `QgsFieldComboBox` → combobox, spinboxes, checkbox,
   button, label, tab, group…), a per-role value, the associated label
   (`QLabel.buddy()`, `QFormLayout` rows), enabled/visible/focus state,
   geometry in surface coordinates, and `declared` linking a node back to a
   schema field. JSON is canonical (stdlib, sorted keys, stable floats,
   diffable); YAML is an output option of the tools only.
2. **Stable ids.** Generated widgets carry an `objectName` derived from the
   declared field id (`form/distance`, `buttons/ok`); ids survive layout
   changes. A custom widget without an `objectName` gets a positional id and
   a `UI001` finding in the snapshot and in `check` for generated surfaces,
   so the author knows the reference is brittle.
3. **Screenshot** by `QWidget.grab()` → PNG, device pixel ratio recorded,
   works under the offscreen QPA.
4. **Agent tools, developer mode only** (decision-49 `dev.*`): `dev.ui.list`,
   `dev.ui.open(action_id)`, `dev.ui.snapshot(surface, screenshot=)`,
   `dev.ui.act(surface, node_id, verb, value?)` with `click`, `set`,
   `select`, `type`, `focus` through `QTest` and Qt APIs, `dev.ui.diff(a, b)`.
   `act` never ships in user mode; user mode may expose `snapshot` of the
   plugin's own surfaces at most, behind its own grant, because a screenshot
   can contain data.
5. **Test support.** `ui_snapshot(surface)` fixture in the SDK pytest plugin
   (native tests), `approve()` writing `tests/__snapshots__/<name>.json` and
   `.png`; a structural change fails with the diff, the PNG is for humans and
   agents (hash-compared, no tolerance machinery). `qgis-sdk ui snapshot
   <action>` captures into `.qgis-sdk/ui/` for one-off use.
6. **Boundary.** Only surfaces this plugin's runtime opened (its
   `ResourceScope` knows them). Never a tree-walk of the QGIS main window:
   that would be an `iface` proxy by the back door.

## Consequences

- Agents can open, read, drive and re-read a plugin's native UI in the
  developer loop with the same reload and dispatch machinery; authors get
  snapshot tests of native surfaces without writing Qt introspection.
- Runtime gains the snapshot module (stdlib + Qt, no new dependency); tools
  gain the CLI, the fixture and the YAML option; no bridge change.
- Scheduled as TASK-79 in m-7 after TASK-75; the `objectName` rule is folded
  into TASK-68's generated surfaces so ids are stable from the first release
  of the surfaces.
