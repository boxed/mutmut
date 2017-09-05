.. image:: https://travis-ci.org/boxed/mutmut.svg?branch=master
    :target: https://travis-ci.org/boxed/mutmut

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

    mutmut

This will by default run py.test on tests in the "tests" folder and it will try to figure out where the code to mutate lies. Run

.. code-block::

    mutmut --help

for the available flags to use other runners, etc. The recommended way to use mutmut if 
the defaults aren't working for you is to add a block in `setup.cfg`. Then when you 
come back to mutmut weeks later you don't have to figure out the flags again, just run 
`mutmut` and it works. Like this:

.. code-block::

    [mutmut]
    paths_to_mutate=src/
    backup=False
    runner=python -m pytest
    tests_dir=tests/
    dict_synonyms=Struct, NamedStruct

The output of the mutation tests (if you have surviving mutants) looks like:

.. code-block::

    FAILED: mutmut path/filename.py --mutation 10 --apply

I've made is to you can just copy paste everything after "FAILED:" and run it directly and you'll get the
mutant on disk. You should REALLY have the file you mutate under source code control and committed before you mutate it!

You should start from the bottom of the list, because if you start from the top, the indexes of the mutations change.

Whitelisting
------------

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
