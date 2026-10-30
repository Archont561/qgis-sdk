Feature: Scoped local jobs with typed handles
  A job is a decorated function bound to an owner and submitted with delay; the
  handle it returns is typed end to end. Four rules carry the design: a
  submitted body runs in its entirety on a worker, a cancellation request is
  not a state, callbacks run on the host's tick and never from a worker, and
  disposal of the owner beats any delivery. Hiding a view is not disposal,
  plugin-lifetime work is explicit, and nothing retries on its own.

  Scenario: Submitting a job runs no author code until a worker runs it
    Given a plugin with a view and a worker pool
    When the view binds the sum job and delays it with 1 and 2
    Then no author code has run
    And the handle is queued with attempt 1
    When the host ticks once
    Then no author code has run
    And the handle is running with no cancellation requested
    When the worker runs the job and the host ticks once
    Then the handle succeeded with total 3

  Scenario: Cancellation is a request until the job acknowledges it
    Given a plugin with a view and a worker pool
    When the view binds the sum job and delays it with 1 and 2
    And the host ticks once
    And the handle is cancelled
    Then the handle is still running with cancellation requested
    When the worker runs the job and the host ticks once
    Then the handle is cancelled
    And the cancelled subscriber was told exactly once

  Scenario: A body that ignores the request still reports what happened to the job
    Given a plugin with a view and a worker pool
    When the view delays a job that is cancelled while it runs and ignores it
    And the host ticks once
    And the worker runs the job and the host ticks once
    Then the handle is cancelled with cancellation requested

  Scenario: A job cancelled before it ever starts settles as cancelled
    Given a plugin with a view and a worker pool
    When the view binds the sum job and delays it with 1 and 2
    And the handle is cancelled
    And the host ticks once
    Then the handle is cancelled
    And no author code has run

  Scenario: A late subscriber hears the current state once
    Given a plugin with a view and a worker pool
    When the view binds the sum job and delays it with 1 and 2
    And the host ticks once
    And the worker runs the job and the host ticks once
    And a late subscriber attaches to success
    Then the late subscriber heard total 3 exactly once
    And the late subscription is already complete

  Scenario: Disposing the view detaches its callbacks and asks the job to stop
    Given a plugin with a view and a worker pool
    When the view binds the sum job and delays it with 1 and 2
    And the host ticks once
    And the view is disposed
    Then the handle has its owner closed and cancellation requested
    When the worker runs the job and the host ticks once
    Then the handle is cancelled
    And the view's subscribers heard nothing after disposal

  Scenario: Hiding the view is not disposal
    Given a plugin with a view and a worker pool
    When the view binds the sum job and delays it with 1 and 2
    And the host ticks once
    And the view is hidden
    And the worker runs the job and the host ticks once
    Then the handle succeeded with total 3
    And the view's success subscriber heard total 3

  Scenario: Plugin-lifetime work is explicit and outlives the view
    Given a plugin with a view and a worker pool
    When the view delays the sum job through its parent service
    And the host ticks once
    And the view is disposed
    Then the handle has its owner open and no cancellation requested
    When the worker runs the job and the host ticks once
    Then the handle succeeded with total 3

  Scenario: Waiting for a job on the GUI thread is refused
    Given a plugin with a view and a worker pool on the GUI thread
    When the view binds the sum job and delays it with 1 and 2
    Then waiting on the handle is refused with code job_wait_refused

  Scenario: A tick re-entered from worker code is ignored
    Given a plugin with a view and a worker pool
    When the view delays a job that re-enters the tick while it runs
    And the view binds the sum job and delays it with 1 and 2
    And the host ticks once
    And the worker runs the job and the host ticks once
    Then the nested tick returned 0 and the re-entering job succeeded
    And the handle succeeded with total 3
