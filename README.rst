Mutmut
======

Mutmut is a mutation testing library/tool. It aims to be usable as a program directly, but also to have an easy to use API.


Install
-------

.. code-block::

    pip install mutmut


Usage
-----

.. code-block::

    mutmut path/to/directory/you/want/to/mutate

This will by default run py.test on tests in the "tests" folder. Run

.. code-block::

    mutmut --help

for the available flags to use other runners, etc.

The output of the mutation tests (if you have surviving mutants) looks like:

.. code-block::

    FAILED: mutmut path/filename.py --mutation 10 --apply

I've made is to you can just copy paste everything after "FAILED:" and run it directly and you'll get the
mutant on disk. You should REALLY have the file you mutate under source code control and committed before you mutate it!

You should start from the bottom of the list, because if you start from the top, the indexes of the mutations change.

You can mark lines like this:

.. code-block:: python

    some_code_here()  # pragma: no mutate

to stop mutation on those lines. Some cases we've found where you need to whitelist lines are:

- The version string on your library. You really shouldn't have a test for this :P
- Optimizing break instead of continue. The code runs fine when mutating break to continue, but it's slower.


Example mutations
-----------------

- Integer literals are changed by adding 1. So 0 becomes 1, 5 becomes 6, etc.
- < is changed to <=
- break is changed to continue and vice versa

In general the idea is that the mutations should be as subtle as possible.


Future plan
-----------

- Custom importer that will mutate the code on the way in
- Plug in to py.test (and nose, etc?) to make it use the importer
- Optimization: Keep a cache of hashes to know which files have changed since they were tested, so we can skip testing files which are already done
- Optimization: Use testmon to know which tests to rerun for each mutation
- Speed up: Make the runner itself a part of py.test so we can use py.test test parallelization/distribution
