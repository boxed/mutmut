Architecture
======================

This document gives an overview on how Mutmut works internally.

Phases of ``mutmut run``
------------------------

Generating mutants
^^^^^^^^^^^^^^^^^^

This phase creates a ``./mutants/`` directory, which will be used by all following phases.

We start by copying ``source_paths`` to ``mutants/`` and then mutate the ``*.py`` files in there. Finally, we also copy ``also_copy`` paths to ``mutants/``, including the (guessed) test directories and some project files.

The mutated files contains the original code and the mutants. With the ``MUTANT_UNDER_TEST`` environment variable, we can specify (among other things) which mutant should be enabled. If a mutant is not enabled, it will run the original code.


Collecting tests and stats
^^^^^^^^^^^^^^^^^^^^^^^^^^

We collect a list of all tests and execute them. In this test run, we track which tests would execute which mutants, and how long they take. We also track function call dependencies (which functions call which other functions) for cascading invalidation when code changes. We use these stats for performance optimizations later on. The results are stored in ``mutants/mutmut-stats.json`` and global variables.


Collecting mutation results
^^^^^^^^^^^^^^^^^^^^^^^^^^^

We load mutation results from previous runs. Mutation results are loaded from ``.meta`` files next to the mutated code. For instance, the results of ``mutants/foo/bar.py`` will be loaded from ``mutants/foo/bar.py.meta``.


Running clean tests
^^^^^^^^^^^^^^^^^^^

This step verifies that the test setup works. We disable all mutants and run all tests. As the tests use the original versions, this *should* succeed.


Running forced fail test
^^^^^^^^^^^^^^^^^^^^^^^^

Here, we verify that the mutation setup works. We tell all mutants that they should raise an Exception, when being executed, and run all tests. We verify that at least one test failed, to ensure that enabling mutants works, and the tests run on mutated code.


Running mutation testing
^^^^^^^^^^^^^^^^^^^^^^^^

We finally check, which mutations are caught by the test suite.

For each mutant, we execute the test suite. If any of the tests fails, we successfully killed the mutant. To optimize performance, we only execute the tests that could cover the mutant and sort them by mutation time. We also skip mutants, which already have a result from a previous run.

The results are stored in the ``.meta`` files.


Process Isolation Models
------------------------

Mutmut supports two process isolation strategies for running mutation tests.
The choice affects compatibility with fork-unsafe libraries (gevent, grpc, torch)
and crash recovery behavior.


ForkRunner (default)
^^^^^^^^^^^^^^^^^^^^

::

    ┌─────────────────────────────────────────────────────────┐
    │                    MutMut Process                       │
    │  (imports pytest, loads conftest.py, runs stats)        │
    └─────────────────────────┬───────────────────────────────┘
                              │ os.fork() per mutant
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ Child 1  │    │ Child 2  │    │ Child N  │
        │ mutant_1 │    │ mutant_2 │    │ mutant_N │
        └──────────┘    └──────────┘    └──────────┘

1. Parent process imports pytest and runs stats collection
2. For each mutant, parent calls ``os.fork()`` to create a child
3. Child inherits parent's memory (copy-on-write) and runs tests
4. Child exits with test result code
5. Parent reaps child and records result

**Pros:**

- Fastest startup and per-mutant execution
- Memory efficient via copy-on-write sharing
- Simple architecture

**Cons:**

- Fork-unsafe libraries (gevent, grpc, torch) may cause segfaults
- No automatic crash recovery


HotForkRunner
^^^^^^^^^^^^^

::

    ┌─────────────────────────────────────────────────────────┐
    │                 MutMut Process (Clean)                  │
    │       (never imports pytest - stays fork-safe)          │
    └─────────────────────────┬───────────────────────────────┘
                              │ os.fork() for each phase
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌─────────────────────┐
        │  Stats   │    │  Clean   │    │    Orchestrator     │
        │ (fork)   │    │  (fork)  │    │  (imports pytest)   │
        └──────────┘    └──────────┘    └──────────┬──────────┘
                                                   │ os.fork() per mutant
                                   ┌───────────────┼───────────────┐
                                   ▼               ▼               ▼
                             ┌──────────┐    ┌──────────┐    ┌──────────┐
                             │Grandchild│    │Grandchild│    │Grandchild│
                             │ mutant_1 │    │ mutant_2 │    │ mutant_N │
                             └──────────┘    └──────────┘    └──────────┘

1. Stats collection runs in a forked child (isolated from parent)
2. Clean test and forced fail run in forked children (parent stays clean)
3. Parent forks a **orchestrator** process that imports pytest
4. Parent sends work via pipe, orchestrator forks grandchildren per mutant
5. Grandchildren run tests and exit (inherit orchestrator's memory via COW)
6. Orchestrator sends results back to parent via pipe
7. If orchestrator crashes, parent restarts it and re-submits pending work

**Pros:**

- Fully fork-safe-parent never imports pytest
- Nearly as fast as ForkRunner (2 additional pytest imports)
- Automatic crash recovery with orchestrator restart

**Cons:**

- More complex three-level process architecture
- Slight memory overhead due to orchestrator process
- Requires pipe-based IPC between parent and orchestrator
- Requires pytest environment to be re-imported by Stats/Clean/Orchestrator processes (import time heavy projects may see slower startup)

**Why hot-fork?**

The orchestrator process is "hot" (performed all imports) before forking
grandchildren.

Choosing a Runner
^^^^^^^^^^^^^^^^^
"fork" is the default and fastest option. If you experience instability, state corruption,
or segfaults during mutation testing, consider switching to "hot-fork" mode.

Configure in ``pyproject.toml``:

.. code-block:: toml

    [tool.mutmut]
    process_isolation = "hot-fork"  # or "fork" (default)
