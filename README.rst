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



.. code-block:: ini

    [mutmut]
    paths_to_mutate=src/
    tests_dir=tests/

You can stop the mutation run at any time and mutmut will restart where you
left off. It will continue where it left off, and re-test functions that were
modified since last run.

To work with the results, use `mutmut browse` where you can see the mutants,
retest them when you've updated your tests.

You can also write a mutant to disk from the `browse` interface, or via
`mutmut apply <mutant>`. You should **REALLY** have the file you mutate under
source code control and committed before you apply a mutant!


Wildcards for testing mutants
-----------------------------

Unix filename pattern matching style on mutants is supported. Example:

.. code-block:: console

    mutmut run "my_module*"
    mutmut run "my_module.my_function*"

In the `browse` TUI you can press `f` to retest a function, and `m` to retest
an entire module.


"also copy" files
-----------------

To run the full test suite some files are often needed above the tests and the
source. You can configure to copy extra files that you need by adding
directories and files to `also_copy` in your `setup.cfg`:

.. code-block:: ini

    also_copy=
        iommi/snapshots/
        conftest.py


Limit stack depth
-----------------

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


Exclude files from mutation
---------------------------

You can exclude files from mutation in `setup.cfg`:

.. code-block::

    do_not_mutate=
        *__tests.py


Whitelisting
------------

You can mark lines like this:

.. code-block:: python

    some_code_here()  # pragma: no mutate

to stop mutation on those lines. Some cases we've found where you need to
whitelist lines are:

- The version string on your library. You really shouldn't have a test for this :P
- Optimizing break instead of continue. The code runs fine when mutating break
  to continue, but it's slower.


Example mutations
-----------------

- Integer literals are changed by adding 1. So 0 becomes 1, 5 becomes 6, etc.
- `<` is changed to `<=`
- break is changed to continue and vice versa

In general the idea is that the mutations should be as subtle as possible.
See `__init__.py` for the full list.


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
