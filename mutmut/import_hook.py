from __future__ import print_function
# based off of https://pymotw.com/2/sys/imports.html
import os
import sys
import imp


def should_mutate_file(fullname):
    return fullname == MutateFinder.file_to_mutate


class MutateFinder(object):
    file_to_mutate = ''
    mutation_number = None
    was_mutated = False

    def __init__(self, path):
        self.path = path

    def find_module(self, fullname, path=None):
        full_path = os.path.join(self.path, fullname + '.py')
        if not os.path.exists(full_path):
            print('!#(@*&$(#&$(#*', full_path)
            full_path = os.path.join(self.path, fullname, '__init__.py')
        print('  MutateFinder', self.path, full_path, os.path.exists(full_path))
        if should_mutate_file(full_path):
            return MutateLoader(full_path, path)


class MutateLoader(object):
    def __init__(self, full_path, path):
        self.full_path = full_path
        self.path = path

    def load_module(self, fullname):
        from mutmut import mutate
        source, _ = mutate(open(self.full_path).read(), MutateFinder.mutation_number)
        MutateFinder.was_mutated = True
        if fullname in sys.modules:
            # print 'reusing existing module from previous import of "%s"' % fullname
            mod = sys.modules[fullname]
        else:
            # print 'creating a new module object for "%s"' % fullname
            mod = sys.modules.setdefault(fullname, imp.new_module(fullname))

        # Set a few properties required by PEP 302
        mod.__file__ = self.full_path
        mod.__name__ = fullname
        mod.__path__ = self.path
        mod.__loader__ = self
        mod.__package__ = '.'.join(fullname.split('.')[:-1])

        exec source in mod.__dict__
        return mod
