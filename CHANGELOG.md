# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [3.4.2] - 2025-12-30

### Changed
- split the CLI implementation into focused command modules and expose them through `mutmut.cli.root`
- ensure generated mutations always end with a newline so files stay well-formed

## [3.4.1] - 2025-12-30

### Changed
- move cli implementation to `mutmut.cli` while keeping `python -m mutmut` working

## [3.4.0] - 2025-11-19

### Changed

- add action to view tests for mutant
- add basic description for all results in mutmut browse
- add description for timeout mutants
- exit early when stats find no tests for any mutant
- support python 3.14
- improve performance
- fix `mutate_only_covered_lines` when files are excluded from the test run
- add `pytest_add_cli_args` and `pytest_add_cli_args_test_selection` configs
- add `mutate_only_covered_lines` config option to control whether coverage.py filters mutations
- filter out identical string mutants with different values
- handle more exit codes
- disable common order-randomising pytest plugins, as that can seriously deteriorate mutation testing performance
- fix packaging issue

## [3.3.1] - 2025-07-30

### Changed

- increase threshold for mutant timeouts
- add `tests_dir` config that accepts either a single entry or a list of directories
- fix async generators
- fix bad mutations for certain string escape sequences
- improve performance
- fix various internal bugs

## [3.3.0] - 2025-05-18

### Changed

- add python 3.13 compatibility
- add argument `--show-killed` for `mutmut browse`
- prevent accidentally importing the un-mutated original code
- handle segfault for mutant subprocesses
- add mutations for string literals
- add mutations for common string methods
- speed up mutant generation via subprocesses
- fix the `self` parameter for mutated class methods
- fix trampoline generation for function calls with 'orig' or 'mutants' as argument names.
- copy full source directory before creating mutants
- improve error message when forced fail test fails
- fix issue with spaces in the python executable path
- avoid mutating `__new__`
- annotate mutant dicts to stay compatible with Pydantic
- replace parso with LibCST

## [3.2.3] - 2025-01-14

### Changed

- avoid crash with error message on invalid imports for `src` module
- autodetect simpler project configurations with `test_*.py` directly in the directory
- handle filenames (as opposed to dirnames) in `paths_to_mutate`
- copy `setup.cfg` and `pyproject.toml` by default
- handle single line `paths_to_mutate`

## [3.2.2] - 2024-11-20

### Changed

- fix crash when running `mutmut results`

## [3.2.1] - 2024-11-13

### Changed

- read `paths_to_mutate` from config file
- mutate `break` to `return` to avoid timeouts
- add debug mode, enabled with `debug=True` in `setup.cfg` under `[mutmut]`
- fix new test detection, which previously detected tests when there were none and slowed down the feedback loop
- fix many additional issues

## [3.2.0] - 2024-10-26

### Changed

- implement timeouts for mutants
- add syntax highlighting to the browser diff view
- fix additional generator issues
- fix support for `src`-style project layouts
- fix bug where mutmut recollected all tests on every run, slowing down startup

## [3.1.0] - 2024-10-22

### Changed

- handle mutation for generator functions (`yield`) correctly
- fix so that `from \_\_future\_\_` lines are always first.
- exit directly if no stats are collected, as that is a breaking error for mutation testing
- change name mangling to make mutants less likely to trigger name-based python magic, like in pytest where functions named `test\_\*` have special meaning.

## [3.0.5] - 2024-10-20

### Changed

- attempt to get the PyPI package to work

## [3.0.4] - 2024-10-20

### Changed

- attempt to get the PyPI package to work

## [3.0.3] - 2024-10-20

### Changed

- fix missing requirement in install package
- fix missing file from the install package

## [3.0.2] - 2024-10-20

### Changed

- fix bad entrypoint definition
- ignore files that can't be parsed by `parso`

## [3.0.1] - 2024-10-20

### Changed

- restore the missing distribution file so `browse` works

## [3.0.0] - 2024-10-20

### Changed

- switch the execution model to mutation schemata, enabling parallel execution
- add terminal UI
- restrict support to pytest only, enabling better integration and faster execution

## [2.0.0] - 2020-03-26

### Changed

- add a new execution model that yields modest speed improvements when using pytest
- add a special execution mode for the hammett test runner to deliver dramatic speed improvements
- drop support for python < 3.7 (use mutmut 1.9.0 on older versions)
- improve speed further

## [1.9.0] - 2020-03-18

### Changed

- add `mutmut run 7` to rerun mutant `7`
- add `mutmut show <filename>` to list all mutants for that file
- add `mutmut run <filename>` to run mutation testing on a specific file
- add an experimental plugin system via `mutmut_config.py` with `init()` and `pre_mutation(context)` hooks that can skip mutants or tweak `context.config.runner`
- improve display of `mutmut show`/`mutmut result`
- fix a spurious mutant on assigning a local variable with type annotations

## [1.8.1] - 2020-03-13

### Changed

- rerun tests without mutation when tests have changed to avoid false positives

## [1.8.0] - 2020-03-02

### Changed

- add `mutmut html` report generation

## [1.7.0] - 2020-02-29

### Changed

- fix multiple assignment handling where `foo = bar = baz` was broken (thanks Roxane Bellot!)
- fix incorrect mutation of the `in` operator (thanks Roxane Bellot!)
- fix bug where a mutant survived in the internal AST too long. This could cause mutmut to apply more than one mutant at a time.
- improve startup performance drastically when resuming a mutation run
- add new experimental feature for advanced config at runtime of mutations

## [1.6.0] - 2019-09-21

### Changed

- add `mutmut show [path to file]` command that shows all mutants for a given file
- improve error messages if .coverage file isn't usable
- add support for windows paths in tests
- use the same python executable as mutmut is started as if possible
- drop python 2 support
- add more assignment operator mutations
- fix

## [1.5.0] - 2019-04-10

### Changed

- add mutation: None -> ''
- display all diffs for surviving mutants for a specific file with `mutmut show all path/to/file.py`
- display all diffs for surviving mutants with `mutmut show all`
- fix a bug with grouping of the results for `mutmut results`
- fix bug where `mutmut show X` sometimes showed no diff
- fix bug where `mutmut apply X` sometimes didn't apply a mutation
- improve error message when trying to find the code
- fix incorrect help message

## [1.4.0] - 2019-03-26

### Changed

- add setting: `--test-time-base=15.0`. This flag can be used to avoid issues with timing.
- add pre- and post-mutation hooks via `--pre-mutation=command` and `--post-mutation=command` to run commands around each mutation testing round
- fix a bug with mutation of imports.
- fix missing newline at end of the output of mutmut.
- add support for mutating only lines specified by a patch file: `--use-patch-file=foo.patch`
- fix mutation of arguments in function call.
- loosen heuristics for finding the source to mutate so more projects work out of the box
- fix mutation of arguments in function call for python 2.7.
- fix a bug where if mutmut couldn't find the test code it thought the tests hadn't changed. Now mutmut treats this situation as the tests always being changed.
- fix bug where the function body was skipped for mutation if a return type annotation existed

## [1.3.1] - 2019-01-30

### Changed

- fix a bug where mutmut crashed if a file contained exactly zero bytes.

## [1.3.0] - 2019-01-23

### Changed

- fix incorrect loading of coverage data when using the `--use-coverage` flag.
- fix a bug when updating the cache.
- fix incorrect handling of source files that didn't end with a newline.

## [1.2.0] - 2019-01-10

### Changed

- provide JUnit XML output via `mutmut junitxml`
- fix python 2 compatibility
- fix PyPy compatibility
- fix an issue where mutmut couldn't kill the spawned test process.
- expand Travis tests to cover python2, python3, PyPy, and Windows
- adjust the return code to reflect what mutmut found during execution
- add the `--test-time-multiplier` CLI option to tweak the detection threshold for slower mutations
- fix compatibility with Windows (thanks Marcelo Da Cruz Pinto and Savo Kovacevic)

## [1.1.0] - 2018-12-10

### Changed

- add mutant: mutate the first argument of function calls to None if it's not already None
- overhaul the cache system so it handles duplicate lines correctly

## [1.0.1] - 2018-11-18

### Changed

- fix minor UX issues: --version was broken, documentation was incorrect, and the trailing newline was missing
- cache the baseline test time to speed up restarting or rechecking mutants

## [1.0.0] - 2018-11-12

### Changed

- introduce a new user interface that is easier to understand and monitor
- introduce a new cache handling system that tracks killed mutants and retests only what changed
- ensure infinite loop detection works in Python < 3.3
- add `--version` flag
- add a nicer error message when no `.coverage` file is found while using `--use-coverage`
- fix crash when using `--use-coverage` flag. Thanks Daniel Hahler!
- add mutation based on finding on tri.struct

## [0.0.24] - 2018-11-04

### Changed

- stop mutating type annotations
- add simple infinite loop detection via a 10x baseline timeout

## [0.0.23] - 2018-11-03

### Changed

- improve number_mutation robustness with floats (thanks Trevin Gandhi!)
- fix crash when using Python 3 typing to declare a type but not assigning to that variable

## [0.0.22] - 2018-10-07

### Changed

- handle annotated assignment in Python 3.6. Thanks William Orr!

## [0.0.21] - 2018-08-25

### Changed

- fix critical bug: mutmut reported killed mutants as surviving and vice versa.
- fix an issue where the install failed on some systems.
- handle tests dirs spread out in the file system. This is the normal case for django projects for example.
- fix support for both python 3 and python 2
- improve mutation fixes.
- add the ability to test a single mutation
- add a `--print-cache` command to print the cache
- turn off parso error recovery so invalid or unsupported python code raises exceptions

## [0.0.20] - 2018-08-02

### Changed

- change AST library from baron to parso
- implement usability enhancements suggested by David M. Howcraft

## [0.0.19] - 2018-07-20

### Changed

- cache mutation testing results to reduce reruns
- add mutation IDs. They are now indexed per line instead of an index for the entire file. This means you can apply your mutations in any order you see fit and the rest of the apply commands will be unaffected.

## [0.0.18] - 2018-04-27

### Changed

- fix bug where initial mutation count was wrong, which caused mutmut to miss mutants at the end of the file
- change the mutation API to always require a `Context` object, making it easier to pass additional data to callers
- support specifying individual files to mutate (thanks Felipe Pontes!)

## [0.0.16] - 2017-10-09

### Changed

- improve error message when baron crashes a bit (fixes \#10)
- add mutation: right hand side of assignments
- fix nasty bug where applying a mutation could apply a different mutation than the one that was found during mutation testing

## [0.0.14] - 2017-09-02

### Changed

- stop assuming UNIX to fix Windows support (GitHub #9)

## [0.0.12] - 2017-08-27

### Changed

- change default runner to add `-x` flag to pytest. Could radically speed up tests if you're lucky!
- add flag: `--show-times`
- warn when a mutation triggers very long test times
- add a workaround for pytest-testmon (all tests deselected is return code 5 even though it's a success)

## [0.0.11] - 2017-08-03

### Changed

- fix bug that made mutmut crash when setup.cfg was missing

## [0.0.10] - 2017-07-16

### Changed

- rename parameter `--testsdir` to `--tests-dir`
- refactor setup.cfg handling and add the `--dict-synonyms` command-line parameter

## [0.0.9] - 2017-07-05

### Changed

- fix dict parameter mutation bugs that mutated every parameter
- add mutation: remove the body or return 0 instead of None

## [0.0.8] - 2017-06-28

### Changed

- fix the broken PyPI version from the previous release

## [0.0.7] - 2017-06-28

### Changed

- fix bug where pragma didn't work for decorator mutations
- mutate dict literals like `dict(a=foo)` and allow declaring synonyms in setup.cfg
- fix "from x import \*"

## [0.0.6] - 2017-06-13

### Changed

- add mutation: remove decorators!
- improve status while running. This should make it easier to handle when you hit mutants that cause infinite loops.
- fix failing attempts to mutate parentheses. (Thanks Hristo Georgiev!)

## [0.0.5] - 2017-05-06

### Changed

- attempt to fix the PyPI package

## [0.0.4] - 2017-05-06

### Changed

- attempt to fix the PyPI package

## [0.0.3] - 2017-05-05

### Changed

- add python 3 support (as far as baron supports it)
- run tests without mutations first to ensure the suite is clean before mutation testing
- implement a feature to run mutations on covered lines only for existing test suites without 100% coverage
- add an error message for incorrect invocation

## [0.0.2] - 2016-12-01

### Changed

- apply numerous fixes

## [0.0.1] - 2016-12-01

### Changed

- publish the initial version
