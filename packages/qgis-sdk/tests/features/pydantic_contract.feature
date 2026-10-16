Feature: Optional Pydantic controlled-deployment contract
  The adapter is used only when a deployment explicitly provisions Pydantic.

  Scenario: Strict request validation dispatches a typed handler and serializes defaults
    Given the optional Pydantic run contract
    When the shared request "request defaults may be omitted" is dispatched
    Then the typed handler receives a request with mode "safe" and no label
    And the serialized result includes its nullable default
    And the serialized result satisfies the Pydantic writer schema

  Scenario: Invalid request JSON stops before the typed handler
    Given the optional Pydantic run contract
    When the shared request "request rejects a numeric string" is dispatched
    Then Pydantic reports a safe error path "count"
    And the typed handler is not called

  Scenario: Result readers and writers expose different extension policies
    Given the optional Pydantic run contract
    Then the reader schema accepts its named revision extension
    And the writer schema rejects the reader-only revision
    And the writer schema requires its serialized default

  Scenario: Integral JSON numbers match the shared schema contract
    Given the optional Pydantic run contract
    When the shared request "run-request accepts integral floating value" is dispatched
    Then the typed handler receives the normalized integer count 2
