#!/usr/bin/python
# -*- coding: utf-8 -*-

"""functionality for operating, populating and reading from the mutmut test
and mutation cache"""

import hashlib
import os
from difflib import unified_diff
from functools import wraps
from io import open

from pony.orm import Database, Required, db_session, Set, Optional, PrimaryKey

from mutmut.mutators import MutationContext, mutate

db = Database()

UNTESTED = "UNTESTED"
OK_SUSPICIOUS = "OK_SUSPICIOUS"
OK_KILLED = "OK_KILLED"
BAD_SURVIVED = "BAD_SURVIVED"
BAD_TIMEOUT = "BAD_TIMEOUT"


class MiscData(db.Entity):
    key = PrimaryKey(str, auto=True)
    value = Optional(str, autostrip=False)


class SourceFile(db.Entity):
    filename = Required(str, autostrip=False)
    lines = Set('Line')


class Line(db.Entity):
    sourcefile = Required(SourceFile)
    line = Required(str, autostrip=False)
    mutants = Set('Mutant')


class Mutant(db.Entity):
    line = Required(Line)
    index = Required(int)
    tested_against_hash = Optional(str, autostrip=False)
    status = Required(str, autostrip=False)


def init_db(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if db.provider is None:
            db.bind(provider='sqlite', filename=os.path.join(os.getcwd(), '.mutmut-cache'), create_db=True)
            db.generate_mapping(create_tables=True)

        return f(*args, **kwargs)
    return wrapper


def hash_of(filename):
    """

    :param filename:
    :type filename: str
    :return:
    """
    with open(filename, 'rb') as f:
        m = hashlib.sha256()
        m.update(f.read())
        return m.hexdigest()


def hash_of_tests(tests_dirs):
    """

    :param tests_dirs:
    :type tests_dirs: list[str]
    :return:
    """
    m = hashlib.sha256()
    for tests_dir in tests_dirs:
        for root, dirs, files in os.walk(tests_dir):
            for filename in files:
                with open(os.path.join(root, filename), 'rb') as f:
                    m.update(f.read())
    return m.hexdigest()


def get_apply_line(mutant):
    apply_line = 'mutmut apply %s' % mutant.id
    return apply_line


def get_or_create(model, defaults=None, **params):
    if defaults is None:
        defaults = {}
    obj = model.get(**params)
    if obj is None:
        params = params.copy()
        for k, v in defaults.items():
            if k not in params:
                params[k] = v
        return model(**params)
    else:
        return obj


@init_db
@db_session
def register_mutants(mutations_by_file):
    """

    :param mutations_by_file:
    :type mutations_by_file: dict[str, list[tuple[str, int]]]

    :return:
    """
    for filename, mutation_ids in mutations_by_file.items():
        sourcefile = get_or_create(SourceFile, filename=filename)
        lines_to_be_removed = {x.id: x for x in sourcefile.lines}
        for mutation_id in mutation_ids:
            line = get_or_create(Line, sourcefile=sourcefile, line=mutation_id[0])
            get_or_create(Mutant, line=line, index=mutation_id[1], defaults=dict(status=UNTESTED))
            if line.id in lines_to_be_removed:
                del lines_to_be_removed[line.id]

        # These lines no longer exists in the code, clean them out
        for line in lines_to_be_removed.values():
            line.delete()


@init_db
@db_session
def update_mutant_status(file_to_mutate, mutation_id, status, tests_hash):
    """Update the status of the mutation test run within the database

    :param file_to_mutate:
    :type file_to_mutate: str

    :param mutation_id:
    :type mutation_id: tuple[str, int]

    :param status:
    :type status: str

    :param tests_hash:
    :type tests_hash: str
    """
    sourcefile = SourceFile.get(filename=file_to_mutate)
    line = Line.get(sourcefile=sourcefile, line=mutation_id[0])
    mutant = Mutant.get(line=line, index=mutation_id[1])
    mutant.status = status
    mutant.tested_against_hash = tests_hash


def get_mutation_diff(filename, mutation_id):
    """Get the difference between source file and the source file mutated by
    the mutation noted by ``mutation_id``

    :param filename: thw source file's name
    :type filename: str

    :param mutation_id: id of the mutation on the source file
    :type mutation_id: tuple[str, int]

    :return: TODO: type
    """
    with open(filename) as f:
        source = f.read()
    context = MutationContext(
        source=source,
        filename=filename,
        mutate_id=mutation_id,
    )
    mutated_source, number_of_mutations_performed = mutate(context)
    return unified_diff(source.splitlines(keepends=True),
                        mutated_source.splitlines(keepends=True),
                        fromfile=filename, tofile=filename)


@init_db
@db_session
def get_cached_mutation_status(filename, mutation_id, hash_of_tests):
    """Get the status of a mutation test run from the cache.

    :param filename:
    :type filename: str

    :param mutation_id:
    :type mutation_id: tuple[str, int]

    :param hash_of_tests:
    :type hash_of_tests: str

    :return: the status of the cached mutation test run
    :rtype: str
    """
    sourcefile = SourceFile.get(filename=filename)
    line = Line.get(sourcefile=sourcefile, line=mutation_id[0])
    mutant = Mutant.get(line=line, index=mutation_id[1])
    if mutant.status == OK_KILLED:
        # We assume that if a mutant was killed, a change to the test
        # suite will mean it's still killed
        return OK_KILLED

    if mutant.tested_against_hash != hash_of_tests:
        return UNTESTED

    return mutant.status


@init_db
@db_session
def mutation_id_from_pk(pk):
    mutant = Mutant.get(id=pk)
    return mutant.line.line, mutant.index


@init_db
@db_session
def filename_and_mutation_id_from_pk(pk):
    mutant = Mutant.get(id=pk)
    return mutant.line.sourcefile.filename, mutation_id_from_pk(pk)


@init_db
@db_session
def get_cached_test_time():
    """Get the baseline tests (tests without mutations) execution time

    :return: execution time of the baseline tests
    :rtype: float or None
    """
    d = MiscData.get(key='baseline_time_elapsed')
    return float(d.value) if d else None


@init_db
@db_session
def set_cached_test_time(baseline_time_elapsed):
    """Set the baseline tests (tests without mutations) execution time
    within the database.

    :param baseline_time_elapsed:
    :type baseline_time_elapsed: float
    """
    get_or_create(MiscData, key='baseline_time_elapsed').value = str(baseline_time_elapsed)
