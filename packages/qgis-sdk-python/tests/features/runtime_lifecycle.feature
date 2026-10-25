Feature: Plain plugin runtime lifecycle
  The runtime constructs a plain author class once, owns its scope and
  disposes every registered resource when the plugin unloads.

  Scenario: Starting injects the runtime context and binds declared actions
    Given a declared plugin that records the context it receives
    When the runtime starts
    Then the plugin receives that same context
    And the declared action is bound to the instance
    And the runtime is running

  Scenario: Partial startup failure releases owned resources before unloading
    Given a plugin that registers owned resources and then fails to construct
    When its runtime start is attempted
    Then the original startup error is raised
    And owned resources are released in reverse order
    And the runtime is failed and unloading it again is safe
    And restarting the failed runtime is rejected

  Scenario: Repeated unload releases owned resources once
    Given a running plugin with two owned resources
    When the runtime unloads three times
    Then each resource is released once and the runtime is stopped
    And the bound actions are cleared
