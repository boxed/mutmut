# -*- coding: utf-8 -*-

import hashlib
import os
from collections import defaultdict
from difflib import SequenceMatcher, unified_diff
from functools import wraps
from io import open
from itertools import groupby, zip_longest
from os.path import join, dirname
from typing import Tuple


from junit_xml import TestSuite, TestCase
from pony.orm import Database, Required, db_session, Set, Optional, select, \
    PrimaryKey, RowNotFound, ERDiagramError, OperationalError

from mutmut import MUTANT_STATUSES, BAD_TIMEOUT, OK_SUSPICIOUS, BAD_SURVIVED, UNTESTED, \
    OK_KILLED, RelativeMutationID, Context, mutate

db = Database()

current_db_version = 4


NO_TESTS_FOUND = 'NO TESTS FOUND'


class MiscData(db.Entity):
    key = PrimaryKey(str, auto=True)
    value = Optional(str, autostrip=False)


class SourceFile(db.Entity):
    filename = Required(str, autostrip=False)
    hash = Optional(str)
    lines = Set('Line')


class Line(db.Entity):
    sourcefile = Required(SourceFile)
    line = Optional(str, autostrip=False)
    line_number = Required(int)
    mutants = Set('Mutant')


class Mutant(db.Entity):
    line = Required(Line)
    index = Required(int)
    tested_against_hash = Optional(str, autostrip=False)
    status = Required(str, autostrip=False)  # really an enum of mutant_statuses


def init_db(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if db.provider is None:
            cache_filename = os.path.join(os.getcwd(), '.mutmut-cache')
            db.bind(provider='sqlite', filename=cache_filename, create_db=True)

            try:
                db.generate_mapping(create_tables=True)
            except OperationalError:
                pass

            if os.path.exists(cache_filename):
                # If the existing cache file is out of data, delete it and start over
                with db_session:
                    try:
                        v = MiscData.get(key='version')
                        if v is None:
                            existing_db_version = 1
                        else:
                            existing_db_version = int(v.value)
                    except (RowNotFound, ERDiagramError, OperationalError):
                        existing_db_version = 1

                if existing_db_version != current_db_version:
                    print('mutmut cache is out of date, clearing it...')
                    db.drop_all_tables(with_all_data=True)
                    db.schema = None  # Pony otherwise thinks we've already created the tables
                    db.generate_mapping(create_tables=True)

            with db_session:
                v = get_or_create(MiscData, key='version')
                v.value = str(current_db_version)

        return f(*args, **kwargs)
    return wrapper


def hash_of(filename):
    with open(filename, 'rb') as f:
        m = hashlib.sha256()
        m.update(f.read())
        return m.hexdigest()


def hash_of_tests(tests_dirs):
    m = hashlib.sha256()
    found_something = False
    for tests_dir in tests_dirs:
        for root, dirs, files in os.walk(tests_dir):
            for filename in files:
                if not filename.endswith('.py'):
                    continue
                if not filename.startswith('test') and not filename.endswith('_tests.py') and 'test' not in root:
                    continue
                with open(os.path.join(root, filename), 'rb') as f:
                    m.update(f.read())
                    found_something = True
    if not found_something:
        return NO_TESTS_FOUND
    return m.hexdigest()


def get_apply_line(mutant):
    apply_line = 'mutmut apply {}'.format(mutant.id)
    return apply_line


def ranges(numbers):
    if not numbers:
        return []

    result = []
    start_range = numbers[0]
    end_range = numbers[0]

    def add_result():
        if start_range == end_range:
            result.append(str(start_range))
        else:
            result.append('{}-{}'.format(start_range, end_range))

    for x in numbers[1:]:
        if end_range + 1 == x:
            end_range = x
        else:
            add_result()

            start_range = x
            end_range = x

    add_result()

    return ', '.join(result)


@init_db
@db_session
def print_result_cache(show_diffs=False, dict_synonyms=None, only_this_file=None):
    print('To apply a mutant on disk:')
    print('    mutmut apply <id>')
    print('')
    print('To show a mutant:')
    print('    mutmut show <id>')
    print('')

    def print_stuff(title, mutant_query):
        mutant_list = sorted(mutant_query, key=lambda x: x.line.sourcefile.filename)
        if mutant_list:
            print('')
            print("{} ({})".format(title, len(mutant_list)))
            for filename, mutants in groupby(mutant_list, key=lambda x: x.line.sourcefile.filename):
                if only_this_file and filename != only_this_file:
                    continue

                mutants = list(mutants)
                print('')
                print("---- {} ({}) ----".format(filename, len(mutants)))
                print('')
                if show_diffs:
                    with open(filename) as f:
                        source = f.read()

                    for x in mutants:
                        print('# mutant {}'.format(x.id))
                        print(get_unified_diff(x.id, dict_synonyms, update_cache=False, source=source))
                else:
                    print(ranges([x.id for x in mutants]))

    print_stuff('Timed out ⏰', select(x for x in Mutant if x.status == BAD_TIMEOUT))
    print_stuff('Suspicious 🤔', select(x for x in Mutant if x.status == OK_SUSPICIOUS))
    print_stuff('Survived 🙁', select(x for x in Mutant if x.status == BAD_SURVIVED))
    print_stuff('Untested/skipped', select(x for x in Mutant if x.status == UNTESTED))


@init_db
@db_session
def print_result_ids_cache(desired_status):
    status = MUTANT_STATUSES[desired_status]
    mutant_query = select(x for x in Mutant if x.status == status)
    print(" ".join(str(mutant.id) for mutant in mutant_query))


def get_unified_diff(argument, dict_synonyms, update_cache=True, source=None):
    filename, mutation_id = filename_and_mutation_id_from_pk(argument)
    if source is None:
        with open(filename) as f:
            source = f.read()

    return _get_unified_diff(source, filename, mutation_id, dict_synonyms, update_cache)


def _get_unified_diff(source, filename, mutation_id, dict_synonyms, update_cache):

    if update_cache:
        update_line_numbers(filename)

    if source is None:
        with open(filename) as f:
            source = f.read()
    context = Context(
        source=source,
        filename=filename,
        mutation_id=mutation_id,
        dict_synonyms=dict_synonyms,
    )
    mutated_source, number_of_mutations_performed = mutate(context)
    if not number_of_mutations_performed:
        return ""

    output = ""
    for line in unified_diff(source.split('\n'), mutated_source.split('\n'), fromfile=filename, tofile=filename, lineterm=''):
        output += line + "\n"
    return output


@init_db
@db_session
def print_result_cache_junitxml(dict_synonyms, suspicious_policy, untested_policy):
    test_cases = []
    mutant_list = list(select(x for x in Mutant))
    for filename, mutants in groupby(mutant_list, key=lambda x: x.line.sourcefile.filename):
        for mutant in mutants:
            tc = TestCase("Mutant #{}".format(mutant.id), file=filename, line=mutant.line.line_number, stdout=mutant.line.line)
            if mutant.status == BAD_SURVIVED:
                tc.add_failure_info(message=mutant.status, output=get_unified_diff(mutant.id, dict_synonyms))
            if mutant.status == BAD_TIMEOUT:
                tc.add_error_info(message=mutant.status, error_type="timeout", output=get_unified_diff(mutant.id, dict_synonyms))
            if mutant.status == OK_SUSPICIOUS:
                if suspicious_policy != 'ignore':
                    func = getattr(tc, 'add_{}_info'.format(suspicious_policy))
                    func(message=mutant.status, output=get_unified_diff(mutant.id, dict_synonyms))
            if mutant.status == UNTESTED:
                if untested_policy != 'ignore':
                    func = getattr(tc, 'add_{}_info'.format(untested_policy))
                    func(message=mutant.status, output=get_unified_diff(mutant.id, dict_synonyms))

            test_cases.append(tc)

    ts = TestSuite("mutmut", test_cases)
    print(TestSuite.to_xml_string([ts]))


@init_db
@db_session
def create_html_report(dict_synonyms):
    mutants = list(select(x for x in Mutant))

    os.makedirs('html', exist_ok=True)

    with open('html/index.html', 'w') as index_file:
        index_file.write('<h1>Mutation testing report</h1>')

        index_file.write('Killed %s out of %s mutants' % (len([x for x in mutants if x.status == OK_KILLED]), len(mutants)))

        index_file.write('<table><thead><tr><th>File</th><th>Total</th><th>Killed</th><th>% killed</th><th>Survived</th></thead>')

        for filename, mutants in groupby(mutants, key=lambda x: x.line.sourcefile.filename):
            report_filename = join('html', filename)

            mutants = list(mutants)

            with open(filename) as f:
                source = f.read()

            os.makedirs(dirname(report_filename), exist_ok=True)
            with open(join(report_filename + '.html'), 'w') as f:
                mutants_by_status = defaultdict(list)
                for mutant in mutants:
                    mutants_by_status[mutant.status].append(mutant)

                f.write('<html><body>')

                f.write('<h1>%s</h1>' % filename)

                killed = len(mutants_by_status[OK_KILLED])
                f.write('Killed %s out of %s mutants' % (killed, len(mutants)))

                index_file.write('<tr><td><a href="%s.html">%s</a></td><td>%s</td><td>%s</td><td>%.2f</td><td>%s</td>' % (
                    filename,
                    filename,
                    len(mutants),
                    killed,
                    (killed / len(mutants) * 100),
                    len(mutants_by_status[BAD_SURVIVED]),
                ))

                def print_diffs(status):
                    mutants = mutants_by_status[status]
                    for mutant in sorted(mutants, key=lambda m: m.id):
                        diff = _get_unified_diff(source, filename, RelativeMutationID(mutant.line.line, mutant.index, mutant.line.line_number), dict_synonyms, update_cache=False)
                        f.write('<h3>Mutant %s</h3>' % mutant.id)
                        f.write('<pre>%s</pre>' % diff)

                if mutants_by_status[BAD_TIMEOUT]:
                    f.write('<h2>Timeouts</h2>')
                    f.write('Mutants that made the test suite take a lot longer so the tests were killed.')
                    print_diffs(BAD_TIMEOUT)

                if mutants_by_status[BAD_SURVIVED]:
                    f.write('<h2>Survived</h2>')
                    f.write('Survived mutation testing. These mutants show holes in your test suite.')
                    print_diffs(BAD_SURVIVED)

                if mutants_by_status[OK_SUSPICIOUS]:
                    f.write('<h2>Suspicious</h2>')
                    f.write('Mutants that made the test suite take longer, but otherwise seemed ok')
                    print_diffs(OK_SUSPICIOUS)

                f.write('</body></html>')

        index_file.write('</table></body></html>')


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


def sequence_ops(a, b):
    sequence_matcher = SequenceMatcher(a=a, b=b)

    for tag, i1, i2, j1, j2 in sequence_matcher.get_opcodes():
        a_sub_sequence = a[i1:i2]
        b_sub_sequence = b[j1:j2]
        for x in zip_longest(a_sub_sequence, range(i1, i2), b_sub_sequence, range(j1, j2)):
            yield (tag,) + x


@init_db
@db_session
def update_line_numbers(filename):
    hash = hash_of(filename)
    sourcefile = get_or_create(SourceFile, filename=filename)
    if hash == sourcefile.hash:
        return
    cached_line_objects = list(sourcefile.lines.order_by(Line.line_number))

    cached_lines = [x.line for x in cached_line_objects]

    with open(filename) as f:
        existing_lines = [x.strip('\n') for x in f.readlines()]

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
            if b is not None:
                Line(sourcefile=sourcefile, line=b, line_number=b_index)

        elif command == 'replace':
            if a_index is not None:
                cached_line_objects[a_index].delete()
            if b is not None:
                Line(sourcefile=sourcefile, line=b, line_number=b_index)

        else:
            raise ValueError('Unknown opcode from SequenceMatcher: {}'.format(command))

    sourcefile.hash = hash


@init_db
@db_session
def register_mutants(mutations_by_file):
    for filename, mutation_ids in mutations_by_file.items():
        hash = hash_of(filename)
        sourcefile = get_or_create(SourceFile, filename=filename)
        if hash == sourcefile.hash:
            continue

        for mutation_id in mutation_ids:
            line = Line.get(sourcefile=sourcefile, line=mutation_id.line, line_number=mutation_id.line_number)
            if line is None:
                raise ValueError("Obtained null line for mutation_id: {}".format(mutation_id))
            get_or_create(Mutant, line=line, index=mutation_id.index, defaults=dict(status=UNTESTED))

        sourcefile.hash = hash


@init_db
@db_session
def update_mutant_status(file_to_mutate, mutation_id, status, tests_hash):
    sourcefile = SourceFile.get(filename=file_to_mutate)
    line = Line.get(sourcefile=sourcefile, line=mutation_id.line, line_number=mutation_id.line_number)
    mutant = Mutant.get(line=line, index=mutation_id.index)
    mutant.status = status
    mutant.tested_against_hash = tests_hash


@init_db
@db_session
def get_cached_mutation_statuses(filename, mutations, hash_of_tests):
    sourcefile = SourceFile.get(filename=filename)
    assert sourcefile

    line_obj_by_line = {}

    result = {}

    for mutation_id in mutations:
        if mutation_id.line not in line_obj_by_line:
            line_obj_by_line[mutation_id.line] = Line.get(sourcefile=sourcefile, line=mutation_id.line, line_number=mutation_id.line_number)
        line = line_obj_by_line[mutation_id.line]
        assert line
        mutant = Mutant.get(line=line, index=mutation_id.index)
        if mutant is None:
            mutant = get_or_create(Mutant, line=line, index=mutation_id.index, defaults=dict(status=UNTESTED))

        result[mutation_id] = mutant.status
        if mutant.status == OK_KILLED:
            # We assume that if a mutant was killed, a change to the test
            # suite will mean it's still killed
            result[mutation_id] = mutant.status
        else:
            if mutant.tested_against_hash != hash_of_tests or \
                    mutant.tested_against_hash == NO_TESTS_FOUND or \
                    hash_of_tests == NO_TESTS_FOUND:
                result[mutation_id] = UNTESTED
            else:
                result[mutation_id] = mutant.status

    return result


@init_db
@db_session
def cached_mutation_status(filename, mutation_id, hash_of_tests):
    sourcefile = SourceFile.get(filename=filename)
    assert sourcefile
    line = Line.get(sourcefile=sourcefile, line=mutation_id.line, line_number=mutation_id.line_number)
    assert line
    mutant = Mutant.get(line=line, index=mutation_id.index)
    if mutant is None:
        mutant = get_or_create(Mutant, line=line, index=mutation_id.index, defaults=dict(status=UNTESTED))

    if mutant.status == OK_KILLED:
        # We assume that if a mutant was killed, a change to the test
        # suite will mean it's still killed
        return OK_KILLED

    if mutant.tested_against_hash != hash_of_tests or \
            mutant.tested_against_hash == NO_TESTS_FOUND or \
            hash_of_tests == NO_TESTS_FOUND:
        return UNTESTED

    return mutant.status


@init_db
@db_session
def mutation_id_from_pk(pk):
    mutant = Mutant.get(id=pk)
    return RelativeMutationID(line=mutant.line.line, index=mutant.index, line_number=mutant.line.line_number)


@init_db
@db_session
def filename_and_mutation_id_from_pk(pk) -> Tuple[str, RelativeMutationID]:
    mutant = Mutant.get(id=pk)
    if mutant is None:
        raise ValueError("Obtained null mutant for pk: {}".format(pk))
    return mutant.line.sourcefile.filename, mutation_id_from_pk(pk)


@init_db
@db_session
def cached_test_time():
    d = MiscData.get(key='baseline_time_elapsed')
    return float(d.value) if d else None


@init_db
@db_session
def set_cached_test_time(baseline_time_elapsed, current_hash_of_tests):
    get_or_create(MiscData, key='baseline_time_elapsed').value = str(baseline_time_elapsed)
    get_or_create(MiscData, key='hash_of_tests').value = current_hash_of_tests


@init_db
@db_session
def cached_hash_of_tests():
    d = MiscData.get(key='hash_of_tests')
    return d.value if d else None
