#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Functionality for operating, populating and reading from the mutmut test
and mutation cache"""

import hashlib
import os
import sys
from difflib import SequenceMatcher
from functools import wraps
from io import open

from pony.orm import Database, Required, db_session, Set, Optional, select, \
    PrimaryKey, RowNotFound, ERDiagramError, OperationalError

if sys.version_info < (3, 0):   # pragma: no cover (python 2 specific)
    from itertools import izip_longest, groupby  # pylint: disable=no-name-in-module
    zip_longest = izip_longest
    # noinspection PyUnresolvedReferences
    text_type = unicode  # pylint: disable=undefined-variable
else:
    from itertools import groupby, zip_longest
    text_type = str

DB = Database()

CURRENT_DB_VERSION = 2


class MiscData(DB.Entity):
    key = PrimaryKey(text_type, auto=True)
    value = Optional(text_type, autostrip=False)


class SourceFile(DB.Entity):
    filename = Required(text_type, autostrip=False)
    lines = Set('Line')


class Line(DB.Entity):
    sourcefile = Required(SourceFile)
    line = Optional(text_type, autostrip=False)
    line_number = Required(int)
    mutants = Set('Mutant')


class Mutant(DB.Entity):
    line = Required(Line)
    index = Required(int)
    tested_against_hash = Optional(text_type, autostrip=False)
    status = Required(text_type, autostrip=False)  # really an enum of MUTANT_STATUSES


def init_db(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if DB.provider is None:
            cache_filename = os.path.join(os.getcwd(), '.mutmut-cache')
            DB.bind(provider='sqlite', filename=cache_filename, create_db=True)

            try:
                DB.generate_mapping(create_tables=True)
            except OperationalError:
                pass

            if os.path.exists(cache_filename):
                # If the existing cache file is out of data,
                # delete it and start over
                with db_session:
                    try:
                        v = MiscData.get(key='version')
                        if v is None:
                            existing_db_version = 1
                        else:
                            existing_db_version = int(v.value)
                    except (RowNotFound, ERDiagramError, OperationalError):
                        existing_db_version = 1

                if existing_db_version != CURRENT_DB_VERSION:
                    print('mutmut cache is out of date, clearing it...')
                    DB.drop_all_tables(with_all_data=True)
                    # Set the schema to None otherwise Pony thinks we've
                    # already created the tables
                    DB.schema = None
                    DB.generate_mapping(create_tables=True)

            with db_session:
                v = get_or_create(MiscData, key='version')
                v.value = str(CURRENT_DB_VERSION)

        return f(*args, **kwargs)
    return wrapper


def hash_of(filename):
    """Get the sha256 hash of a file given a the specified path

    :param filename: path to the file to sha256 hash
    :type filename: str

    :return: sha256 hash string of the file's contents
    :rtype: str
    """
    with open(filename, 'rb') as f:
        m = hashlib.sha256()
        m.update(f.read())
        return m.hexdigest()


def hash_of_tests(tests_dirs):
    """Get the sha256 has of all the test files' combined contents

    :param tests_dirs:
    :type tests_dirs: list[str]

    :return: sha256 hash string of all the test files' combined contents
    :rtype: str
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


@init_db
@db_session
def print_result_cache():
    print('To apply a mutant on disk:')
    print('    mutmut apply <id>')
    print()
    print('To show a mutant:')
    print('    mutmut show <id>')
    print()

    def print_stuff(title, query):
        l = list(query)
        if l:
            print()
            print(title, '(%s)' % len(l))
            for filename, mutants in groupby(l, key=lambda x: x.line.sourcefile.filename):
                mutants = list(mutants)
                print()
                print('-' * 4, '%s' % filename, '(%s)' % len(mutants), '-' * 4)
                print()
                print(', '.join([str(x.id) for x in mutants]))

    from mutmut.mutators import BAD_SURVIVED, BAD_TIMEOUT, OK_KILLED, \
        OK_SUSPICIOUS, UNTESTED
    # TODO: shouldn't OK_KILLED be also specified?
    print_stuff('Timed out ⏰', select(x for x in Mutant if x.status == BAD_TIMEOUT))
    print_stuff('Suspicious 🤔', select(x for x in Mutant if x.status == OK_SUSPICIOUS))
    print_stuff('Survived 🙁', select(x for x in Mutant if x.status == BAD_SURVIVED))
    print_stuff('Untested', select(x for x in Mutant if x.status == UNTESTED))


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
    return obj


def sequence_ops(a, b):
    """

    :param a:
    :type: list[str]

    :param b:
    :type: list[str]

    :return:
    """
    sequence_matcher = SequenceMatcher(a=a, b=b)

    for tag, i1, i2, j1, j2 in sequence_matcher.get_opcodes():
        a_sub_sequence = a[i1:i2]
        b_sub_sequence = b[j1:j2]
        for x in zip_longest(a_sub_sequence, range(i1, i2), b_sub_sequence, range(j1, j2)):
            yield (tag,) + x


@init_db
@db_session
def update_line_numbers(filename):
    sourcefile = get_or_create(SourceFile, filename=filename)

    cached_line_objects = list(sourcefile.lines.order_by(Line.line_number))

    cached_lines = [x.line for x in cached_line_objects]

    with open(filename) as f:
        # :-1 to remove newline at the end
        existing_lines = [x[:-1] for x in f.readlines()]

    if not cached_lines:
        for i, line in enumerate(existing_lines):
            Line(sourcefile=sourcefile, line=line, line_number=i)
        return

    for command, a, a_index, b, b_index in sequence_ops(cached_lines, existing_lines):
        if command == 'equal':
            if a_index != b_index:
                cached_obj = cached_line_objects[a_index]
                assert cached_obj.line == existing_lines[b_index]
                cached_obj.line_number = b_index

        elif command == 'delete':
            cached_line_objects[a_index].delete()

        elif command == 'insert':
            Line(sourcefile=sourcefile, line=b, line_number=b_index)

        elif command == 'replace':
            cached_line_objects[a_index].delete()
            Line(sourcefile=sourcefile, line=b, line_number=b_index)
        else:
            raise ValueError('unknown opcode from SequenceMatcher: %s' % command)


@init_db
@db_session
def update_mutants(mutations_by_file):
    """Update/create Mutants within the database reflecting the Mutants
    defined in the ``mutations_by_file`` dictionary

    :param mutations_by_file:
    :type mutations_by_file: dict[str, list[MutationID]]
    """
    for filename, mutation_ids in mutations_by_file.items():
        sourcefile = get_or_create(SourceFile, filename=filename)

        for mutation_id in mutation_ids:
            line = Line.get(sourcefile=sourcefile, line=mutation_id.line, line_number=mutation_id.line_number)
            assert line is not None
            from mutmut.mutators import UNTESTED
            get_or_create(Mutant, line=line, index=mutation_id.index, defaults=dict(status=UNTESTED))


@init_db
@db_session
def update_mutant_status(file_to_mutate, mutation_id, status, tests_hash):
    """Update the status of the mutation test run within the database

    :param file_to_mutate:
    :type file_to_mutate: str

    :param mutation_id:
    :type mutation_id: MutationID

    :param status:
    :type status: str

    :param tests_hash:
    :type tests_hash: str
    """
    sourcefile = SourceFile.get(filename=file_to_mutate)
    line = Line.get(sourcefile=sourcefile, line=mutation_id.line, line_number=mutation_id.line_number)
    mutant = Mutant.get(line=line, index=mutation_id.index)
    mutant.status = status
    mutant.tested_against_hash = tests_hash


@init_db
@db_session
def get_cached_mutation_status(filename, mutation_id, tests_hash):
    sourcefile = SourceFile.get(filename=filename)
    line = Line.get(sourcefile=sourcefile, line=mutation_id.line, line_number=mutation_id.line_number)
    mutant = Mutant.get(line=line, index=mutation_id.index)

    from mutmut.mutators import OK_KILLED
    if mutant.status == OK_KILLED:
        # We assume that if a mutant was killed, a change to the test
        # suite will mean it's still killed
        return OK_KILLED

    if mutant.tested_against_hash != tests_hash:
        from mutmut.mutators import UNTESTED
        return UNTESTED

    return mutant.status


@init_db
@db_session
def get_mutation_id_from_pk(pk):
    """Get the MutationID related to the given Mutant primary key

    :param pk: primary key of a Mutant
    :type pk: str

    :return: the MutationID related to the given Mutant primary key
    :rtype: MutationID
    """
    mutant = Mutant.get(id=pk)
    from mutmut.mutators import MutationID
    return MutationID(line=mutant.line.line, index=mutant.index,
                      line_number=mutant.line.line_number)


@init_db
@db_session
def get_filename_and_mutation_id_from_pk(pk):
    """Get the source code filename and the MutationID related to the
    given Mutant primary key

    :param pk: primary key of a Mutant
    :type pk: str

    :return: the source code filename and the MutationID related to the
        given Mutant primary key
    :rtype: tuple[str, MutationID]
    """
    mutant = Mutant.get(id=pk)
    return mutant.line.sourcefile.filename, get_mutation_id_from_pk(pk)


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
def update_cached_test_time(baseline_time_elapsed):
    """Update/create the baseline tests (tests without mutations) execution
    time within the database

    :param baseline_time_elapsed: the baseline tests (tests without mutations)
        execution time
    :type baseline_time_elapsed: float
    """
    get_or_create(MiscData, key='baseline_time_elapsed').value = str(baseline_time_elapsed)
