Feature: The bridge contract vectors hold against a live host
  The cases checked in for the TypeScript client are replayed here through a
  real dispatcher. Every step is shared with the ordinary tests in
  test_bridge_contract_fixtures.py; a scenario adds only the reading.

  Scenario: A page that claims another identity is answered as the view it is
    Given a host with a bound view
    When the page sends the "forged-identity" request
    Then the reply is the one checked in for "forged-identity"
    And the reply names view "view-1" at generation 0

  Scenario: A denied operation is refused without running
    Given a host that authorizes nothing
    When the page sends the "not-authorized" request
    Then the reply is the one checked in for "not-authorized"
    And the operation did not run

  Scenario: A malformed result never reaches the page
    Given a host with a bound view
    When the page sends the "invalid-result" request
    Then the reply is the one checked in for "invalid-result"
    And the reply carries no value

  Scenario: A cancelled call is acknowledged as cancelled
    Given a host with a bound view
    And the call is cancelled before the operation runs
    When the page sends the "cancelled" request
    Then the reply is the one checked in for "cancelled"
    And the operation did not run

  Scenario: An expired file handle no longer opens anything
    Given a host with a bound view
    And the view holds a file grant that has since expired
    When the page sends the "expired-handle" request
    Then the reply is the one checked in for "expired-handle"
    And no layer was opened

  Scenario: Releasing a borrowed handle keeps the host's layer
    Given a host with a bound view
    And the view borrowed the layer "layer-1"
    When the page sends the "release-borrowed" request
    Then the reply is the one checked in for "release-borrowed"
    And the view no longer holds "layer-1"
