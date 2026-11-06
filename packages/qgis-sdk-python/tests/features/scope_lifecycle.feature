Feature: Scope ownership stays local
  Resource scopes release work when their owner closes, not before.

  Background:
    Given a plugin with two views and a job in the first view

  Scenario: Closing a view releases its job but not its sibling or plugin
    When the first view closes
    Then only the first view and its job are released
    And the sibling view and plugin still accept work

  Scenario: Closing a plugin releases descendants before its resources exactly once
    When the plugin closes twice
    Then each cleanup runs once from descendants to plugin
    And the closed plugin rejects new work
