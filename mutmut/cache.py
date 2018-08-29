import hashlib
import os
import sys
from io import open

from mutmut import parse_mutation_id_str, get_mutation_id_str

if sys.version_info < (3, 0):   # pragma: no cover (python 2 specific)
    # noinspection PyUnresolvedReferences
    text_type = unicode
else:
    text_type = str


def hash_of(filename):
    with open(filename, 'rb') as f:
        m = hashlib.sha256()
        m.update(f.read())
        return m.hexdigest()


def hash_of_tests(tests_dirs):
    m = hashlib.sha256()
    for tests_dir in tests_dirs:
        for root, dirs, files in os.walk(tests_dir):
            for filename in files:
                with open(os.path.join(root, filename), 'rb') as f:
                    m.update(f.read())
    return m.hexdigest()


def update_hash_of_source_file(filename, hash_of_file, hashes):
    hashes[filename] = hash_of_file
    with open('.mutmut-cache/hashes', 'w') as f:
        f.writelines(u':'.join([k, v]) + '\n' for k, v in hashes.items())


def load_hash_of_source_file():
    try:
        with open('.mutmut-cache/hashes') as f:
            # noinspection PyTypeChecker
            return dict(line.strip().split(':') for line in f.readlines())
    except IOError:
        return {}


def write_tests_hash(tests_hash):
    with open('.mutmut-cache/tests-hash', 'w') as f:
        f.write(text_type(tests_hash))


def load_hash_of_tests():
    try:
        with open('.mutmut-cache/tests-hash') as f:
            return f.read()
    except IOError:
        return None


def surviving_mutants_filename(f):
    return '.mutmut-cache/%s-surviving-mutants' % f.replace(os.sep, '__')


def ok_lines_filename(f):
    return '.mutmut-cache/%s-ok-lines' % f.replace(os.sep, '__')


def load_surviving_mutants(filename):
    try:
        with open(surviving_mutants_filename(filename)) as f:
            lines = f.read().splitlines()
            return [parse_mutation_id_str(x) for x in lines]

    except IOError:
        return {}


def load_ok_lines(filename):
    try:
        with open(ok_lines_filename(filename)) as f:
            return f.read().splitlines()
    except IOError:
        return {}


def write_ok_line(filename, line):
    with open(ok_lines_filename(filename), 'a') as f:
        f.write(line + '\n')


def write_surviving_mutant(filename, mutation_id):
    surviving_mutants = load_surviving_mutants(filename)
    if mutation_id in surviving_mutants:
        # Avoid storing the same mutant again
        return

    with open(surviving_mutants_filename(filename), 'a') as f:
        f.write(get_mutation_id_str(mutation_id) + '\n')
