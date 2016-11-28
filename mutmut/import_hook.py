# from __future__ import print_function
# # based off of https://pymotw.com/2/sys/imports.html
# import os
#
# try:
#     from importlib.abc import SourceLoader, FileLoader, PathEntryFinder
# except ImportError:
#     from importlib2.abc import SourceLoader, FileLoader, PathEntryFinder
#
#
# def should_mutate_file(fullname):
#     return fullname == MutateFinder.file_to_mutate
#
#
# class MutateFinder(PathEntryFinder):
#     path = ''
#     file_to_mutate = ''
#     mutation_number = None
#     was_mutated = False
#
#     def find_module(self, fullname, path=None):
#         return MutateLoader(fullname, path)
#
#
# class MutateLoader(SourceLoader, FileLoader):
#     def get_source(self, fullname):
#         print('!!!!!!!')
#         return super(MutateLoader, self).get_source(fullname)