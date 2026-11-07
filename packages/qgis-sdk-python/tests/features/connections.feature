Feature: A connection is a name in a registry, never a credential
  QGIS keeps a registry of data-source connections: a GeoPackage file, a
  PostGIS database, each under a name the user gave it. A plugin that can
  browse the registry and open one of its tables can build a data-source
  picker without reaching into QGIS directly; a page that needs to know which
  authentication configuration a connection spends needs only the id.

  What crosses the boundary is a description: the name, the provider key that
  owns the registry, and the id of the attached authentication configuration.
  A connection's URI - the one place a password lives in plaintext - and the
  decrypted contents of the authentication database are read and dropped
  before a model is built. An unknown provider or connection is refused with
  both names; a database that will not answer is a verdict, not an exception.

  These scenarios run on the fake backend: a plugin author's own pure tests
  arrange the same connections and read the same descriptions.

  Background:
    Given a runtime with connections and auth configurations

  Scenario: The registry lists what the test declared
    When the plugin lists the connections
    Then the registry lists connection "survey" of provider "ogr"
    And the registry lists connection "lagoon" of provider "postgres"

  Scenario: A description carries a name, a provider and an auth config id
    When the plugin describes connection "lagoon" of provider "postgres"
    Then the description names "lagoon" of provider "postgres"
    And its wire shape carries no credential

  Scenario: A GeoPackage browses its tables directly
    When the plugin browses connection "survey" of provider "ogr"
    Then the browse lists table "roads" of kind "vector"

  Scenario: A schema-capable connection browses schemas first
    When the plugin browses connection "lagoon" of provider "postgres"
    Then the browse lists schema "public"
    When the plugin browses schema "public" of connection "lagoon"
    Then the browse lists table "points" of kind "vector"

  Scenario: Opening a table answers a vector layer in the layer list
    When the plugin opens table "roads" of connection "survey"
    Then the opened layer is named "roads"
    And its geometry type is "line"
    And the layer list holds it

  Scenario: A schema is browsed, not opened
    When the plugin opens schema "public" as a table of connection "lagoon"
    Then the SDK refuses it as browsed, not opened

  Scenario: An unreachable connection answers a verdict
    When the plugin tests connection "warehouse" of provider "postgres"
    Then the verdict is invalid and says why

  Scenario: The auth registry lists ids and names only
    When the plugin lists the auth configurations
    Then the configuration named "field crew" is listed
    And its wire shape carries an id and a name only

  Scenario: Attaching swaps the id the description answers
    When the plugin attaches configuration "field crew" to connection "lagoon"
    Then connection "lagoon" of provider "postgres" spends that configuration

  Scenario: A file-based connection cannot carry a configuration
    When the plugin attaches configuration "field crew" to connection "survey"
    Then the SDK refuses it as having none to attach

  Scenario: An unknown connection is refused with both names
    When the plugin describes connection "survey" of provider "postgres"
    Then the SDK refuses it as no such connection
