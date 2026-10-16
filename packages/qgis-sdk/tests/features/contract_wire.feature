Feature: QGIS-free request and result example
  The generated JSON schemas distinguish wire validation directions.
  These checks use a test-only JSON Schema validator, not a chosen SDK decoder.

  Scenario: A request may omit its defaulted fields
    Given the generated sample wire schemas
    When the shared payload "request defaults may be omitted" is validated
    Then the schema accepts it

  Scenario: A request cannot coerce a numeric string
    Given the generated sample wire schemas
    When the shared payload "request rejects a numeric string" is validated
    Then the schema rejects it

  Scenario: A result reader recognizes an explicit compatible revision
    Given the generated sample wire schemas
    When the shared payload "reader accepts the explicitly supported revision" is validated
    Then the schema accepts it

  Scenario: A result reader does not permit arbitrary additions
    Given the generated sample wire schemas
    When the shared payload "reader rejects arbitrary new fields" is validated
    Then the schema rejects it

  Scenario: A serialized result includes defaulted fields
    Given the generated sample wire schemas
    When the shared payload "writer requires a serialized default" is validated
    Then the schema rejects it

  Scenario Outline: Default decoding is not strict request validation
    Given the generated sample wire schemas
    When the shared payload "<payload>" is validated
    Then the schema rejects it
    When the same shared payload "<payload>" is decoded without validation
    Then the default decoder nevertheless constructs a request with count 2

    Examples:
      | payload                              |
      | request rejects a numeric string     |
      | request rejects an unknown field     |
      | request rejects a fractional integer |

  Scenario: A JSON integer value need not use an integer token
    Given the generated sample wire schemas
    When the shared payload "run-request accepts integral floating value" is validated
    Then the schema accepts it

  Scenario: A request integer must be exactly interoperable with JavaScript
    Given the generated sample wire schemas
    When the shared payload "request rejects an unsafe integer" is validated
    Then the schema rejects it
