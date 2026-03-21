mutmut - python mutation tester
===============================

.. image:: https://github.com/boxed/mutmut/actions/workflows/tests.yml/badge.svg
    :target: https://github.com/boxed/mutmut/actions/workflows/tests.yml

.. image:: https://readthedocs.org/projects/mutmut/badge/?version=latest
    :target: https://mutmut.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status


Mutmut is a mutation testing system for Python, with a strong focus on ease
of use. If you don't know what mutation testing is try starting with
`this article <https://kodare.net/2016/12/01/mutmut-a-python-mutation-testing-system.html>`_.

Some highlight features:

- Found mutants can be applied on disk with a simple command making it very
  easy to work with the results
- Remembers work that has been done, so you can work incrementally
- Knows which tests to execute, speeding up mutation testing
- Interactive terminal based UI
- Parallel and fast execution
- Configurable process isolation for compatibility with gevent, grpc, torch

.. image:: browse_screenshot.png


If you want to mutate code outside of functions, you can try using mutmut 2,
which has a different execution model than mutmut 3+.


Requirements
------------

Mutmut must be run on a system with `fork` support. This means that if you want
to run on windows, you must run inside WSL.



Install and run
---------------

You can get started with a simple:

.. code-block:: console

    pip install mutmut
    mutmut run

This will by run pytest on tests in the "tests" or "test" folder and
it will try to figure out where the code to mutate is.



You can stop the mutation run at any time and mutmut will restart where you
left off.

To work with the results, use `mutmut browse` where you can see the mutants,
retest them when you've updated your tests.

You can also write a mutant to disk from the `browse` interface, or via
`mutmut apply <mutant>`. You should **REALLY** have the file you mutate under
source code control and committed before you apply a mutant!


If during the installation you get an error for the `libcst` dependency mentioning the lack of a rust compiler on your system, it is because your architecture does not have a prebuilt binary for `libcst` and it requires both `rustc` and `cargo` from the [rust toolchain](https://www.rust-lang.org/tools/install) to be built. This is known for at least the `x86_64-darwin` architecture.
left off.


Incremental Testing
~~~~~~~~~~~~~~~~~~~

Mutmut is designed for incremental workflows. It remembers which mutants have
been tested and their results, so subsequent runs skip already-tested mutants.

**Function-level change detection:** Mutmut computes a hash of each function's
source code. When you modify a function, mutmut detects the change and
automatically re-tests all mutants in that function. Unchanged functions keep
their previous results.

**Dependency tracking:** Mutmut tracks which functions call which other functions
during stats collection. When a function changes, mutmut automatically invalidates
and re-tests mutants in all functions that depend on it (transitively). For example,
if function A calls B which calls C, and you modify C, mutants in A, B, and C are
all re-tested.

This means you can:

- Run ``mutmut run``, stop partway through, and continue later
- Modify your source code and re-run - only changed functions are re-tested
- Update shared utilities and have dependent functions automatically re-tested
- Update your tests and use ``mutmut browse`` to selectively re-test mutants

The mutation data is stored in the ``mutants/`` directory. Delete this
directory to start completely fresh.


Wildcards for testing mutants
-----------------------------

Unix filename pattern matching style on mutants is supported. Example:

.. code-block:: console

    mutmut run "my_module*"
    mutmut run "my_module.my_function*"

In the `browse` TUI you can press `f` to retest a function, and `m` to retest
an entire module.


Configuration
-------------

In `setup.cfg` in the root of your project you can configure mutmut if you need to:

.. code-block:: ini

    [mutmut]
    source_paths=src/
    pytest_add_cli_args_test_selection=tests/

If you use `pyproject.toml`, you must specify the paths as array in a `tool.mutmut` section:

.. code-block:: toml

    [tool.mutmut]
    source_paths = [ "src/" ]
    pytest_add_cli_args_test_selection= [ "tests/" ]

See below for more options for configuring mutmut.


"also copy" files
~~~~~~~~~~~~~~~~~

To run the full test suite some files are often needed above the tests and the
source. You can configure to copy extra files that you need by adding
directories and files to `also_copy` in your `setup.cfg`:

.. code-block:: ini

    also_copy=
        iommi/snapshots/
        conftest.py


Limit stack depth
~~~~~~~~~~~~~~~~~

In big code bases some functions are called incidentally by huge swaths of the
codebase, but you really don't want tests that hit those executions to count
for mutation testing purposes. Incidentally tested functions lead to slow
mutation testing as hundreds of tests can be checked for things that should
have clean and fast unit tests, and it leads to bad test suites as any
introduced bug in those base functions will lead to many tests that fail which
are hard to understand how they relate to the function with the change.

You can configure mutmut to only count a test as being relevant for a function
if the stack depth from the test to the function is below some limit. In your
`setup.cfg` add:

.. code-block:: ini

    max_stack_depth=8

A lower value will increase mutation speed and lead to more localized tests,
but will also lead to more surviving mutants that would otherwise have been
caught.


Dependency tracking
~~~~~~~~~~~~~~~~~~~

Mutmut automatically tracks function call dependencies during stats collection.
When a function's code changes, all functions that depend on it (transitively)
are also invalidated and re-tested. This is enabled by default.

To disable dependency tracking:

.. code-block:: toml

    [tool.mutmut]
    track_dependencies = false

You can also limit the depth of dependency tracking (defaults to ``max_stack_depth``):

.. code-block:: toml

    [tool.mutmut]
    dependency_tracking_depth = 5

The dependency graph is stored in ``mutants/mutmut-stats.json`` under the
``function_dependencies`` key.

**Config change detection:**

Mutmut automatically detects when dependency tracking configuration changes
between runs. If you enable/disable tracking or change the depth, mutmut will
re-collect stats to ensure the dependency graph matches your current settings.
This avoids both missed invalidations (too few edges) and unnecessary test runs
(too many edges).

**Performance considerations:**

For large codebases, be aware of the overhead at each phase:

- **Mutant generation:** The BFS expansion runs once per ``mutmut run`` when
  changes are detected. Complexity is O(changed + edges), typically milliseconds
  even for graphs with 10,000+ functions.

- **Stats collection:** Adds ~1-5% overhead. Each function call records a single
  edge (caller → callee) via a ContextVar lookup and set insertion—both O(1).
  The depth check is a simple integer comparison.

- **Storage:** The dependency graph adds to ``mutmut-stats.json``. A codebase
  with 10,000 functions and 50,000 call edges adds roughly 1-2 MB.

- **Memory:** The in-memory graph uses ~100 bytes per edge. 50,000 edges ≈ 5 MB.

If you experience issues in very large monorepos, you can limit tracking depth
with ``dependency_tracking_depth`` or disable entirely with ``track_dependencies = false``.


Exclude files from mutation
~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default mutmut mutates all python files in `source_paths`.
You can exclude files from mutation in `setup.cfg`:

.. code-block::

    only_mutate=
        src/api/*
        src/services/*
    do_not_mutate=
        *__tests.py


Enable coverage.py filtering of lines to mutate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, mutmut will mutate only functions that are called. But, if you would like a finer grained (line-level)
check for coverage, mutmut can use coverage.py to do that.

If you only want to mutate lines that are called (according to coverage.py), you can set
`mutate_only_covered_lines` to `true` in your configuration. The default value is `false`.


.. code-block::

    mutate_only_covered_lines=true


Filter generated mutants with type checker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When your project is type checked using `mypy` or `pyrefly`, you can also use it to filter out invalid mutants.
For instance, mutmut mutates `x: str = 'foo'` to `x: str = None` which can easily caught by type checkers.

Using this filter can improve performance and reduce noise, however it can also hide a few relevant mutations:

1. `x: str = None` may not be valid, but if your tests do not detect such a change it indicates that
    the value of `x` is not properly tested (even if your type checker would catch this particular modification)
2. In some edge cases with class properties (usually in the `__init__` method), the way `mypy` and `pyrefly` infer types does not work well
    with the way mutmut mutates code. Some valid mutations like changing `self.x = 123` to `self.x = None` can
    be filtered out, even though the may be valid.

To enable this filtering, configure the `type_check_command` to output json results as follows:

.. code-block::

    # for pyrefly
    type_check_command = ['pyrefly', 'check', '--output-format=json']
    # for mypy
    type_check_command = ['mypy', 'your_source_dir', '--output', 'json', '--disable-error-code', 'unused-ignore']

Currently, only `pyrefly` and `mypy` are supported.
With `pyright` and `ty`, mutating a class method `Foo.bar()` can break the types of all methods of `Foo`,
and therefore mutmut cannot match the type error with the mutant that caused the type error.


Enable debug output (increase verbosity)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, mutmut "swallows" all the test output etc. so that you get a nice clean output.

If you want to see all the detail to aid with debugging, you can set `debug` to `true` in your configuration.
Note that not all displayed errors are necessarily bad. In particular test runs of the mutated code will lead
to failing tests.

.. code-block::

    debug=true


Disable setproctitle (macOS)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Mutmut uses ``setproctitle`` to show the current mutant name in the process
list, which is helpful for monitoring long runs. However, ``setproctitle``
uses CoreFoundation APIs on macOS that are not fork-safe, causing segfaults
in child processes.

By default, mutmut automatically disables ``setproctitle`` on macOS and
enables it on other platforms. If you need to override this (e.g. to enable it on
macOS at your own risk, or to disable it on other platforms), set ``use_setproctitle``:

.. code-block:: toml

    # pyproject.toml
    [tool.mutmut]
    use_setproctitle = false


Debug file logging
~~~~~~~~~~~~~~~~~~

For debugging child processes (which can't easily log to the console), you can
enable file-based logging:

.. code-block:: toml

    [tool.mutmut]
    log_to_file = true
    log_file_path = "mutants/mutmut-debug.log"  # default path

Logs are written as a rotating file (10 MB max, 3 backups). This is useful for
diagnosing issues with forked worker processes.



Process Isolation Mode
~~~~~~~~~~~~~~~~~~~~~~

By default, mutmut uses ``fork`` for fast worker spawning. However, certain libraries
don't survive fork correctly and will cause segfaults:

- **gevent** - Event loop and hub state becomes corrupted after fork
- **grpc** - Thread state, signal handlers, and connections break
- **torch/tensorflow** - GPU handles and thread pools corrupt

If you see segfaults during mutation testing (exit code -11), you can switch to
``hot-fork`` mode which adopts a safer forking strategy to prevent corruption of
state in fork-unsafe libraries.

.. code-block:: toml

    [tool.mutmut]
    process_isolation = "hot-fork"

Or in `setup.cfg`:

.. code-block:: ini

    [mutmut]
    process_isolation=hot-fork

**How it works:**

- ``fork`` mode: The main mutmut process forks directly for each mutant. Fast but
  inherits any fork-unsafe library state from the parent.
- ``hot-fork`` mode: Mutmut spawns a fresh orchestrator subprocess that imports
  pytest/tests, then forks from there for each mutant. The orchestrator has clean
  library state, avoiding fork corruption issues.

Both modes use ``os.fork()`` internally—the difference is *what* gets forked.
Hot-fork mode is nearly as fast as fork mode since the orchestrator only starts once
and subsequent forks are cheap.

See `ARCHITECTURE.rst <ARCHITECTURE.rst>`_ for detailed diagrams of each isolation model.

**Crash recovery (hot-fork only):**

If the orchestrator crashes, mutmut automatically restarts it and re-submits any
pending mutants. By default, it will retry up to 3 times. You can configure this:

.. code-block:: toml

    [tool.mutmut]
    process_isolation = "hot-fork"
    max_orchestrator_restarts = 5  # default: 3


Hot-Fork Warmup Strategies
~~~~~~~~~~~~~~~~~~~~~~~~~~

When using ``hot-fork`` mode, the orchestrator can "warm up" before forking
grandchildren to significantly improve performance. The warmup strategy controls
what happens in the orchestrator before it starts forking workers.

.. code-block:: toml

    [tool.mutmut]
    process_isolation = "hot-fork"
    hot_fork_warmup = "collect"  # default

**Available strategies:**

- ``collect`` (default, recommended): Runs ``pytest --collect-only`` in the
  orchestrator to pre-load pytest, your conftest.py, and all test infrastructure.
  This is then inherited by all forked grandchildren, avoiding redundant imports.

- ``import``: Imports specific modules from a file. Use this when test collection
  has side effects that cause issues (e.g., starting servers, connecting to
  databases).

- ``none``: Only imports pytest itself. Use this for maximum compatibility or
  when debugging warmup-related issues.

**Performance comparison:**

Benchmarking performed with the `/mutmut/e2e_projects/benchmark_1k` project
(1000 mutants, 143 tests, 10 workers).

Syntetic import, collection, and test delays were added to help illustrate
the performance impact of each warmup strategy. Real-world results will vary
greatly but the trends should hold.

_Note:_ preformance impact is most felt on the initial mutation testing run. Subsequent
runs benefit from selective execution of the mutants based on code changes, greatly reducing
the number of tests run per mutant, with larger projects seeing the most benefits.

The warmup strategy has a dramatic impact on throughput. Benchmarks on a 1000-mutant
project with simulated import delays (100ms pytest import, 100ms conftest):

================================================================================
RESULTS SUMMARY
================================================================================

--- Delay: import=0.1s, conftest=0.1s ---
Strategy       Avg. Mut/s   % of Max   Mut Test  Wall Time
------------------------------------------------------------
fork              105.7/s       100%      9.5s     26.0s
collect            92.0/s        87%     10.9s     28.8s
import             45.0/s        43%     22.2s     39.9s
none               30.6/s        29%     32.7s     50.6s

--- Delay: import=0.5s, conftest=0.5s ---
Strategy       Avg. Mut/s   % of Max   Mut Test  Wall Time
------------------------------------------------------------
fork              106.5/s       100%      9.4s     27.3s
collect            86.8/s        81%     11.5s     31.8s
import             14.8/s        14%     67.5s     87.7s
none                7.9/s         7%    127.0s    147.4s

--- Delay: import=1.0s, conftest=1.0s ---
Strategy       Avg. Mut/s   % of Max   Mut Test  Wall Time
------------------------------------------------------------
fork              106.6/s       100%      9.4s     28.4s
collect            79.8/s        75%     12.5s     35.8s
import              8.3/s         8%    119.8s    142.9s
none                4.1/s         4%    242.1s    265.5s

================================================================================
MUTATION THROUGHPUT COMPARISON ACROSS ALL DELAY CONFIGS
================================================================================

Strategy       0.1s delay     0.5s delay     1.0s delay
---------------------------------------------------------
fork              105.7/s        106.5/s        106.6/s
collect            92.0/s         86.8/s         79.8/s
import             45.0/s         14.8/s          8.3/s
none               30.6/s          7.9/s          4.1/s


For comparison, ``fork`` mode achieves ~105 mut/s but requires libraries and
test suites that can be run multiple times from within the same process.

The ``collect`` strategy provides the comparable performance (~75-90% of fork mode
in synthetic tests) while being compatible with most libraries due to the preservation
of a clean parent process state.

In real-world applications where each tests's runtime is greater (>500ms), the
the fork vs hot-fork with collect difference becomes negligible since the
overhead is amortized over the longer test execution time.

Without warmup, each grandchild must re-import pytest and load conftest.py,
which dominates test runtime for most unit tests, though providing
the highest level of isolation and compatibility.

**Using the import strategy:**

If your conftest.py has side effects that cause problems during collection,
you can use the ``import`` strategy with a custom module list:

.. code-block:: toml

    [tool.mutmut]
    process_isolation = "hot-fork"
    hot_fork_warmup = "import"
    preload_modules_file = "mutmut_preload.txt"

The file supports pip requirements format, so you can reuse existing requirements
files or use version specifiers (which are stripped when importing):

.. code-block:: text

    # Simple module names
    pytest
    gevent.monkey
    grpc

    # pip requirements format also works (versions stripped)
    flask>=2.0
    requests[security]==2.28.0
    sqlalchemy~=2.0

This gives you control over exactly what gets loaded, avoiding problematic
imports while still benefiting from pre-warming.

**Note:** Package names with dashes are converted to underscores for import
(e.g., ``google-auth`` becomes ``google_auth``). Some packages have different
import names than their pip names - in those cases, use the import name directly.

**Troubleshooting warmup issues:**

If you experience crashes or hangs with the default ``collect`` strategy:

1. Try ``hot_fork_warmup = "none"`` to verify the issue is warmup-related
2. Check your conftest.py for operations at module level that may corrupt the state if forked
3. Use ``import`` with a minimal module list and gradually add modules
4. Enable debug mode to see detailed logs: ``debug = true``


Whitelisting
~~~~~~~~~~~~

You can mark lines like this:

.. code-block:: python

    some_code_here()  # pragma: no mutate

to stop mutation on those lines. Some cases we've found where you need to
whitelist lines are:

- The version string on your library. You really shouldn't have a test for this :P
- Optimizing break instead of continue. The code runs fine when mutating break
  to continue, but it's slower.


Skipping Code Blocks
~~~~~~~~~~~~~~~~~~~~

You can skip an entire indentation block from mutation using
``# pragma: no mutate block``. This works on any compound statement --
functions, classes, ``if``/``elif``/``else``, loops, context managers, etc.

Both syntax styles are supported:

- ``# pragma: no mutate block``
- ``# pragma: no mutate: block``

**Skipping an entire function or class** -- place the pragma inline on the
definition line. The entire node (including all children) is skipped and no
trampoline is generated:

.. code-block:: python

    def complex_algorithm():  # pragma: no mutate block
        return some_complex_calculation()

    class MySettings:  # pragma: no mutate block
        DEBUG = True
        MAX_RETRIES = 3

**Skipping only the body of a function** -- place the pragma on its own line
inside the function. The function definition (including default arguments) is
still mutable, but the body is suppressed:

.. code-block:: python

    def foo(val=1):
        # pragma: no mutate block
        x = 1
        y = complex_calculation()
        z = x + y

    def bar():
        # this function is still mutated normally
        return 42

**Skipping an ``if`` branch without affecting ``elif``/``else``** -- place
the pragma inline on the ``if``. Only the ``if`` condition and its indented
body are suppressed; sibling branches (``elif``, ``else``) remain mutable
because they exit the original indentation scope:

.. code-block:: python

    if error_condition:  # pragma: no mutate block
        log_error()
        send_alert()
    elif other_condition:
        # still mutated -- this branch is outside the block scope
        handle_other()
    else:
        # still mutated
        handle_success()

The same principle applies to ``for``/``else``, ``while``/``else``,
``try``/``except``/``finally``, and ``match``/``case``.

This is useful for:

- Functions or classes that should be excluded from mutation entirely
- Error-handling branches that are hard to unit test in isolation
- Logging or telemetry blocks that don't affect program correctness
- Generated or boilerplate code within an otherwise mutable function


Skipping Code Regions
~~~~~~~~~~~~~~~~~~~~~

For suppressing mutations across a range of lines regardless of indentation,
use ``# pragma: no mutate start`` and ``# pragma: no mutate end``:

.. code-block:: python

    a = mutate_this()

    # pragma: no mutate start
    b = skip_this()
    c = skip_this_too()
    # pragma: no mutate end

    d = mutate_this_too()

Every line between the markers (inclusive) is suppressed. This works inside
functions, classes, or at module level, and ignores indentation entirely.

An unmatched ``# pragma: no mutate end`` without a preceding ``start`` raises
a ``PragmaParseError`` at parse time.  An unclosed ``# pragma: no mutate start``
(no matching ``end`` before end-of-file) raises a ``PragmaParseError``.
Both errors include the filename and line number.

**Nesting restriction:** opening a new ``block`` or ``start`` context while
another context is already active is not allowed and raises a
``PragmaParseError``.  The error message includes both the offending line and
the line where the existing context was opened.  Close the current context
first (dedent for ``block``, or ``# pragma: no mutate end`` for ``start``)
before opening a new one.


Modifying pytest arguments
~~~~~~~~~~~~~~~~~~~~~~~~~~

You can add and override pytest arguments:

.. code-block:: python

    # for CLI args that select or deselect tests, use `pytest_add_cli_args_test_selection`
    pytest_add_cli_args_test_selection = ["-m", "not fail", "-k", "test_include"]

    # for other CLI args, use `pytest_add_cli_args`
    pytest_add_cli_args = ["-p", "no:some_plugin"] # disable a plugin
    pytest_add_cli_args = ["-o", "xfail_strict=False"] # overrides xfail_strict from your normal config

    # if you want to ignore the normal pytest configuration
    # you can specify a diferent pytest ini file to be used
    pytest_add_cli_args = ["-c", "mutmut_pytest.ini"]
    also_copy = ["mutmut_pytest.ini"]


Unstable configs
~~~~~~~~~~~~~~~~

Following configurations exist, but may be changed in any minor version.
If you use them, expect that a new version could change or break this feature.


.. code-block:: toml

    # Configure how long mutmut waits before killing a slow mutation
    # Currently calculated as (duration_of_original_tests + timeout_constant) * timeout_multiplier seconds
    timeout_constant = 1.0
    timeout_multiplier = 15.0


Example mutations
-----------------

- Integer literals are changed by adding 1. So 0 becomes 1, 5 becomes 6, etc.
- `<` is changed to `<=`
- break is changed to continue and vice versa

In general the idea is that the mutations should be as subtle as possible.
See `node_mutation.py` for the full list and `test_mutation.py` for tests describing them.


Workflow
--------

This section describes how to work with mutmut to enhance your test suite.

1. Run mutmut with `mutmut run`. A full run is preferred but if you're just
   getting started you can exit in the middle and start working with what you
   have found so far.
2. Show the mutants with `mutmut browse`
3. Find a mutant you want to work on and write a test to try to kill it.
4. Press `r` to rerun the mutant and see if you successfully managed to kill it.

Mutmut keeps the data of what it has done and the mutants in the `mutants/`
directory.If  you want to make sure you run a full mutmut run you can delete
this directory to start from scratch.

Contributing to Mutmut
----------------------

If you wish to contribute to Mutmut, please see our `contributing guide <CONTRIBUTING.rst>`_.
