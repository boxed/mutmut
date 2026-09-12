Architecture
======================

This document gives an overview on how Mutmut works internally.

Phases of ``mutmut run``
------------------------

Generating mutants
^^^^^^^^^^^^^^^^^^

This phase creates a ``./mutants/`` directory, which will be used by all following phases.

We start by copying ``source_paths`` to ``mutants/`` and then mutate the ``*.py`` files in there. Finally, we also copy ``also_copy`` paths to ``mutants/``, including the (guessed) test directories and some project files.

The mutated files contains the original code and the mutants. The active mutant is stored in process-local state (and mirrored to the ``MUTANT_UNDER_TEST`` environment variable). If a mutant is not enabled, it will run the original code.


Collecting tests and stats
^^^^^^^^^^^^^^^^^^^^^^^^^^

We collect a list of all tests and execute them. In this test run, we track which tests would execute which mutants, and how long they take. We use both stats for performance optimizations later on. The results are stored in ``mutants/mutmut-stats.json`` and global variables.


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

Every mutant is tested in its own process. Which process that one is forked from is
owned by a ``MutantRunner`` (``src/mutmut/workers/isolation.py``), selected by the
``process_isolation`` config. ``ForkRunner`` forks each worker straight from mutmut's
main process, which by this point has imported pytest and run the suite once to collect
stats. ``ForkServerRunner`` instead keeps the main process free of pytest: it forks a
dedicated fork server child, and that child imports pytest once and forks a worker per
mutant, streaming results back over a length-prefixed pipe. That extra generation exists
for test setups that are not fork-safe, where inheriting the main process would hang or
crash the workers.

The runner also owns the surrounding test operations (stats collection, clean tests,
forced fail, test listing) so that, under ``forkserver``, those too can run in short-lived
forks and leave the main process clean.
