mutmut
======

Mutmut aims to be several independent parts that together create a mutation testing library.

Master plan:
    - DONE: Mutator that given a file can give you the number of available mutations, and given an index can perform the mutation corresponing to that index.
    - DONE: Runner that runs py.test (or tox?) for each mutation. For now mutate files on disk.

    - Custom importer that will mutate the code on the way in
    - Plug in to py.test to make it use the importer
    - Optimization: Keep a cache of hashes to know which files have changed since they were tested, so we can skip testing files which are already done
    - Optimization: Use pymon to know which tests to rerun for each mutation
    - Speed up: Make the runner itself a part of py.test so we can use py.test test parallelization/distribution