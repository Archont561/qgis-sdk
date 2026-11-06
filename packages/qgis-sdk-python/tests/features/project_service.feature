Feature: The project is a service, not a document a plugin rewrites
  A plugin reads and edits the project through one service: its CRS, its
  variables and custom properties, its bookmarks and the layer tree the layers
  hang off. The tree is edited node by node - a layer added into a group, moved,
  hidden, removed - and every edit emits a frame on the change stream, so a view
  redraws what moved instead of re-reading a document.

  Two shapes are deliberate here. The tree is asserted as a tree rather than as
  a list of names, so a backend that answered the right names in the wrong
  nesting would fail. The change stream is asserted as an order, so a backend
  that coalesced or reordered the frames would fail too.

  Scenario: The project's CRS is read back normalised
    Given a project with no CRS
    When the project's CRS is set to "EPSG:3857"
    Then the project reports "EPSG:3857"

  Scenario: A nested group structure round-trips through the project file
    Given a project with the nested group "Elevation" holding "Detail"
    When the project is written to its file and read back
    Then the tree is the one that was written, nesting and order included

  Scenario: Visibility is the node's own
    Given a project with the nested group "Elevation" holding "Detail"
    When the group "Detail" is hidden
    Then "Detail" is not visible and "Elevation" still is

  Scenario: A layer is added into the deepest group
    Given a project with the nested group "Elevation" holding "Detail"
    And a vector layer the runtime owns
    When that layer is added into the group "Detail"
    Then the tree holds the layer inside "Detail"

  Scenario: A variable and a custom property are set and unset
    Given a project with no CRS
    When the variable "project_author" is set to "Ada"
    Then the variables report "project_author" as "Ada"
    When the variable "project_author" is unset
    Then the variables name no entry
    When the custom property "sdk.reference" is set to "yes"
    Then the custom properties report "sdk.reference" as "yes"

  Scenario: A bookmark is added and read back
    Given a project with no CRS
    When the bookmark "home" is added over 21.0, 52.0, 21.3, 52.2
    Then the bookmark "home" covers that box

  Scenario: An unknown bookmark is refused by name
    Given a project with no CRS
    When the bookmark "absent" is read
    Then the SDK refuses it as a missing bookmark

  Scenario: The change stream delivers ordered frames
    Given a project with the nested group "Elevation" holding "Detail"
    And the project's changes are being watched
    When the variable "sdk.reference" is set to "yes"
    And the project's CRS is set to "EPSG:3857"
    Then the stream delivered variables then crs
