"""Repository automation: the code behind ``pixi run automation <task>``.

Each module is ordinary Python with a ``main()``/function entry point and no
knowledge of ``doit``: the task registry is ``dodo.py``, and anything here can
be imported by a test or run directly with ``python -m automation.<module>``.

- :mod:`.release` - the stdlib-only release train (plan, stamp, build, publish).
- :mod:`.ci` - the workflow harness: run a gate, capture its log, annotate it.
- :mod:`.pr` - watch a pull request's CI, breaking on the first error.
- :mod:`.tasks` - the automation commands themselves, one function per task.
- :mod:`.commits` - the merge base a pull request is checked against.
- :mod:`.results` - turn an XML/log report into a failure list.
- :mod:`.lib` - helpers shared by the modules above.
"""
