Feature: Cooperative step scheduling for plugin work
  The scheduler advances author coroutines one bounded step per tick on the host's
  own thread, honours cancellation cooperatively, and refuses an in-process
  replacement while a worker has not acknowledged a stop request. Control flow the
  host raises through author code is returned to the host, and once disposal has
  settled a job that settlement is final.

  Scenario: A job runs only when the host drives a tick
    Given a job that yields once before it returns a value
    When the host advances the scheduler twice
    Then the job body ran exactly twice
    And the job completed with its returned value

  Scenario: Cancellation is delivered at the next suspension point
    Given a job that cleans up in a finally block while awaiting a yield
    When the job is cancelled and the host advances the scheduler
    Then the author cleanup ran once
    And the job is cancelled

  Scenario: Unacknowledged worker work refuses replacement
    Given a job still waiting on an unresolved worker handoff
    When the host asks the scheduler to quiesce
    Then the replacement is refused with that job named
    And the job is still waiting rather than disposed

  Scenario: Disposal drops a late worker report
    Given a job still waiting on an unresolved worker handoff
    When the owning scope is disposed and the worker reports afterwards
    Then the late report is counted as dropped
    And the job body never resumes

  Scenario: A host interrupt is returned to the host rather than absorbed as a job failure
    Given a job that raises a host interrupt while it is stepped
    When the host advances the scheduler and control flow escapes
    Then the interrupt reaches the caller of the tick
    And the job reports that interrupt as its error
    And the scheduler holds no active jobs

  Scenario: Disposal settles a job even when its own author code finishes afterwards
    Given a job that disposes its scope and then returns a value
    When the host advances the scheduler
    Then the job is failed by the closed scope
    And the scheduler holds no active jobs
