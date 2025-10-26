import coverage
import importlib
import sys
from pathlib import Path
import json


# Returns a set of lines that are covered in this file gvein the covered_lines dict
#  returned by gather_coverage
# None means it's not enabled, set() means no lines are covered
def get_covered_lines_for_file(filename: str, covered_lines: dict[str, set[int]]):
    if covered_lines is None or filename is None:
        return None

    abs_filename = str((Path('mutants') / filename).absolute())
    lines = None
    if abs_filename in covered_lines:
        lines = covered_lines[abs_filename]

    return lines or set() 

# Gathers coverage for the given source files and
# Returns a dict of filenames to sets of lines that are covered
# Since this is run on the source files before we create mutations, 
# we need to unload any modules that get loaded during the test run
def gather_coverage(runner, source_files):    
    # We want to unload any python modules that get loaded
    # because we plan to mutate them and want them to be reloaded
    modules = dict(sys.modules)

    mutants_path = Path('mutants')
    
    # Run the tests and gather coverage
    cov = coverage.Coverage(source=[str(mutants_path.absolute())], data_file=None)
    with cov.collect():
        runner.prepare_main_test_run()
        runner.run_tests(mutant_name=None, tests=None)

    # Build mapping of filenames to covered lines
    # The CoverageData object is a wrapper around sqlite, and this
    # will make it more efficient to access the data
    covered_lines = {}
    coverage_data = cov.get_data()

    for filename in source_files:
        abs_filename = str((mutants_path / filename).absolute())
        lines = coverage_data.lines(abs_filename)
        if lines is None:
            # file was not imported during test run, e.g. because test selection excluded this file
            lines = []
        covered_lines[abs_filename] = list(lines)

    _unload_modules_not_in(modules)

    return covered_lines

# Unloads modules that are not in the 'modules' list
def _unload_modules_not_in(modules):
    for name in list(sys.modules):  
        if name == 'mutmut.code_coverage':
            continue
        if name not in modules:
            sys.modules.pop(name, None)
    importlib.invalidate_caches()