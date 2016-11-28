# from __future__ import print_function
# import os
#
# from mutmut.import_hook import MutateFinder
# import sys
#
#
# def mutator_hook(path):
#     if path:
#         assert os.path.exists(MutateFinder.file_to_mutate)
#         print('mutator_hook', path, MutateFinder.file_to_mutate.startswith(path))
#         if MutateFinder.file_to_mutate.startswith(path):
#             if not MutateFinder.path:
#                 MutateFinder.path = path
#             return MutateFinder()
#     raise ImportError
#
#
# def pytest_addoption(parser):
#     group = parser.getgroup("mutation testing")
#     group._addoption(
#         '--mutate',
#         dest="mutate",
#         help="run specified mutation on specified file. Format is: /full/path/to/file.py:MUTATION_NUMBER (mutation number is 0 indexed)")
#
#
# def pytest_configure(config):
#     m = config.getvalue("mutate")
#     if m:
#         MutateFinder.file_to_mutate, MutateFinder.mutation_number = m.split(':')
#         MutateFinder.file_to_mutate = os.path.abspath(MutateFinder.file_to_mutate)
#         MutateFinder.mutation_number = int(MutateFinder.mutation_number)
#         assert MutateFinder.mutation_number >= 0
#
#         sys.path_hooks.insert(0, mutator_hook)
#         sys.path_importer_cache.clear()
#
#
# def pytest_unconfigure(config):
#     if MutateFinder.file_to_mutate and not MutateFinder.was_mutated:
#         print("""
#         ERROR: %s was supposed to be mutated but it never was. This can be caused by:
#          - The file is never imported by the tests
#          - The tests imports from an installed egg inside the virtual environment, but you've specified the source location of the same file.
#         """ % MutateFinder.file_to_mutate)
#         exit(-2)