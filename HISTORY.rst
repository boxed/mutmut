Changelog
---------

3.3.1
~~~~~

* Increased threshold for mutant timeouts

* Added `tests_dir` config. Accepts a single entry or a list of directories.

* Async generators fixes

* Fixed bad mutations for certain string escape sequences

* Performance fixes

* Various internal bug fixes


3.3.0
~~~~~

* Python 3.13 compatibility!

* New argument `--show-killed` for `mutmut browse`

* Fix to avoid accidentally importing the un-mutated original code

* Handle segfault for mutant subprocesses

* Added mutations for string literals

* Added mutations for common string methods

* Faster mutant generation via subprocesses

* Fix `self` parameter for mutated class methods

* Fix trampoline generation for function calls with 'orig' or 'mutants' as argument names.

* Copy full source directory before creating mutants

* Improved error message when forced fail test fails

* Fixed issue with spaces in the python executable path

* Do not mutate `__new__`

* Annotate mutant dicts (and fixes compatibility with Pydantic)

* Replaced parso with LibCST


3.2.3
~~~~~

* Crash with error message on invalid imports for `src` module

* Autodetect simpler project configurations with `test_*.py` in the dir directly

* Handle filenames (as opposed to dirnames) in paths_to_mutate

* Also copy `setup.cfg` and `pyproject.toml` by default

* Handle single line `paths_to_mutate`


3.2.2
~~~~~

* Fixed crash when running `mutmut results`

3.2.1
~~~~~

* Read `paths_to_mutate` from config file

* Mutate `break` to `return` to avoid timeouts

* Added debug mode. Enable with `debug=True` in `setup.cfg` under `[mutmut]`

* Fixed new test detection. The old code incorrectly detected new tests when there were none, creating a much slower interaction loop for fixing mutants.

* And many more fixes

3.2.0
~~~~~

* Timeouts for mutants implemented.

* Browser: syntax highlighting for diff view

* More fixes for generators.

* Fix for `src`-style layout of projects.

* Fixed bug where mutmut would recollect all tests on every run, slowing down startup.


3.1.0
~~~~~

* Correctly handle mutation for generator functions (`yield`).

* Fixed so that `from __future__` lines are always first.

* If no stats are collected exit directly, as that is a breaking error for mutation testing.

* Changed name mangling to make mutants less likely to trigger name-based python magic, like in pytest where functions named `test_*` have special meaning.


3.0.5
~~~~~

* Another attempt to get the pypi package to work


3.0.4
~~~~~

* Another attempt to get the pypi package to work

3.0.3
~~~~~

* Fixed missing requirement in install package

* Fixed missing file from the install package

3.0.2
~~~~~

* Fixed bad entrypoint definition

* Ignore files that can't be parsed by `parso`


3.0.1
~~~~~

* Missed a file in distribution, so `browse` command was broken.

3.0.0
~~~~~

* Execution model switched to mutation schemata, which enabled parallell execution.

* New terminal UI

* Pytest only, which enabled better integration, cutting execution time significantly.


2.0.0
~~~~~

* New execution model. This should result in some modest speed improvements when using pytest.

* A special execution mode when using the hammett test runner. This is MUCH MUCH faster. Please try it!

* Dropped support for python < 3.7. If you need to use mutmut on older versions of python, please use mutmut 1.9.0

* Some other speed improvements.


1.9.0
~~~~~

* `mutmut run 7` will always rerun the mutant `7`

* `mutmut show <filename>` to show all mutants for that file

* `mutmut run <filename>` to run mutation testing on that file

* New experimental plugin system: create a file `mutmut_config.py` in your base directory. In it you can have an `init()` function, and a `pre_mutation(context)` function. You can set `context.skip = True` to skip a mutant, and you can modify `context.config.runner`, this is useful to limit the tests. Check out the `Context` class for what information you get.

* Better display of `mutmut show`/`mutmut result`

* Fixed a spurious mutant on assigning a local variable with type annotations



1.8.1
~~~~~

* mutmut now will rerun tests without mutation when tests have changed. This avoids a common pitfall of introducing a failing test and then having all mutants killed incorrectly


1.8.0 (2020-03-02)
~~~~~~~~~~~~~~~~~~

* Added `mutmut html` report generation.

1.7.0 (2020-02-29)
~~~~~~~~~~~~~~~~~~

* Bugfix for multiple assignment. Mutmut used to not handle `foo = bar = baz` correctly (Thanks Roxane Bellot!)

* Bugfix for incorrect mutation of "in" operator (Thanks Roxane Bellot!)

* Fixed bug where a mutant survived in the internal AST too long. This could cause mutmut to apply more than one mutant at a time.

* Vastly improved startup performance when resuming a mutation run.

* Added new experimental feature for advanced config at runtime of mutations


1.6.0 (2019-09-21)
~~~~~~~~~~~~~~~~~~

* Add `mutmut show [path to file]` command that shows all mutants for a given file

* Better error messages if .coverage file isn't usable

* Added support for windows paths in tests

* Use the same python executable as mutmut is started as if possible

* Dropped python 2 support

* Added more assignment operator mutations

* Bugfixes


1.5.0 (2019-04-10)
~~~~~~~~~~~~~~~~~~

* New mutation: None -> ''

* Display all diffs for surviving mutants for a specific file with `mutmut show all path/to/file.py`

* Display all diffs for surviving mutants with `mutmut show all`

* Fixed a bug with grouping of the results for `mutmut results`

* Fixed bug where `mutmut show X` sometimes showed no diff

* Fixed bug where `mutmut apply X` sometimes didn't apply a mutation

* Improved error message when trying to find the code

* Fixed incorrect help message

1.4.0 (2019-03-26)
~~~~~~~~~~~~~~~~~~

* New setting: `--test-time-base=15.0`. This flag can be used to avoid issues with timing.

* Post and pre hooks for the mutation step: `--pre-mutation=command` and `--post-mutation=command` if you want to run some command before and after a mutation testing round.

* Fixed a bug with mutation of imports.

* Fixed missing newline at end of the output of mutmut.

* Support for mutating only lines specified by a patch file: `--use-patch-file=foo.patch`.

* Fixed mutation of arguments in function call.

* Looser heuristics for finding the source to mutate. This should mean more projects will just work out of the box.

* Fixed mutation of arguments in function call for python 2.7.

* Fixed a bug where if mutmut couldn't find the test code it thought the tests hadn't changed. Now mutmut treats this situation as the tests always being changed.

* Fixed bug where the function body was skipped for mutation if a return type annotation existed.

*


1.3.1 (2019-01-30)
~~~~~~~~~~~~~~~~~~

* Fixed a bug where mutmut crashed if a file contained exactly zero bytes.


1.3.0 (2019-01-23)
~~~~~~~~~~~~~~~~~~

* Fixed incorrect loading of coverage data when using the `--use-coverage` flag.

* Fixed a bug when updating the cache.

* Fixed incorrect handling of source files that didn't end with a newline.


1.2.0 (2019-01-10)
~~~~~~~~~~~~~~~~~~

* JUnit XML output: Run `mutmut junitxml` to output the results as a JUnit compatible XML file.

* Python 2 compatibility fixes.

* pypy compatibility fixes.

* Fixed an issue where mutmut couldn't kill the spawned test process.

* Travis tests now test much more thoroughly, both python2, 3, pypy and on windows.

* The return code of mutmut now reflects what mutmut found during execution.

* New command line option `--test-time-multiplier` to tweak the detection threshold for mutations that make the code slower.

* Fixed compatibility with Windows.


Thanks goes out Marcelo Da Cruz Pinto, Savo Kovačević,


1.1.0 (2018-12-10)
~~~~~~~~~~~~~~~~~~~

* New mutant: mutate the first argument of function calls to None if it's not already None

* Totally overhauled cache system: now handles duplicates lines correctly.


1.0.1 (2018-11-18)
~~~~~~~~~~~~~~~~~~~

* Minor UX fixes: --version command was broken, incorrect documentation shown, missing newline at the very end.

* Caching the baseline test time. This makes restarting/rechecking existing mutants much faster, with a small risk of that time being out of date.


1.0.0 (2018-11-12)
~~~~~~~~~~~~~~~~~~~

* Totally new user interface! Should be much easier to understand and it's easier to see that something is happening

* Totally new cache handling. Mutmut will now know which mutants are already killed and not try them again, and it will know which mutants to retest if the tests change

* Infinite loop detection now works in Python < 3.3

* Added `--version` flag

* Nice error message when no `.coverage` file is found when using the `--use-coverage` flag

* Fixed crash when using `--use-coverage` flag. Thanks Daniel Hahler!

* Added mutation based on finding on tri.struct


0.0.24 (2018-11-04)
~~~~~~~~~~~~~~~~~~~

* Stopped mutation of type annotation

* Simple infinite loop detection: timeout on 10x the baseline time


0.0.23 (2018-11-03)
~~~~~~~~~~~~~~~~~~~

* Make number_mutation more robust to floats (Thanks Trevin Gandhi!)

* Fixed crash when using Python 3 typing to declare a type but not assigning to that variable



0.0.22 (2018-10-07)
~~~~~~~~~~~~~~~~~~~

* Handle annotated assignment in Python 3.6. Thanks William Orr!


0.0.21 (2018-08-25)
~~~~~~~~~~~~~~~~~~~

* Fixed critical bug: mutmut reported killed mutants as surviving and vice versa.

* Fixed an issue where the install failed on some systems.

* Handle tests dirs spread out in the file system. This is the normal case for django projects for example.

* Fixes for supporting both python 3 and 2.

* Misc mutation fixes.

* Ability to test a single mutation.

* Feature to print the cache (--print-cache).

* Turned off error recovery mode for parso. You will now get exceptions for invalid or unsupported python code.


0.0.20 (2018-08-02)
~~~~~~~~~~~~~~~~~~~

* Changed AST library from baron to parso

* Some usability enhancements suggested by David M. Howcraft


0.0.19 (2018-07-20)
~~~~~~~~~~~~~~~~~~~

* Caching of mutation testing results. This is still rather primitive but can in some cases cut down on rerunning mutmut drastically.

* New mutation IDs. They are now indexed per line instead of an index for the entire file. This means you can apply your mutations in any order you see fit and the rest of the apply commands will be unaffected.


0.0.18 (2018-04-27)
~~~~~~~~~~~~~~~~~~~

* Fixed bug where initial mutation count was wrong, which caused mutmut to miss mutants at the end of the file

* Changed mutation API to always require a `Context` object. This makes is much easier to pass additional data out to the caller

* Support specifying individual files to mutate (thanks Felipe Pontes!)


0.0.16 (2017-10-09)
~~~~~~~~~~~~~~~~~~~

* Improve error message when baron crashes a bit (fixes #10)

* New mutation: right hand side of assignments

* Fixed nasty bug where applying a mutation could apply a different mutation than the one that was found during mutation testing


0.0.14 (2017-09-02)
~~~~~~~~~~~~~~~~~~~

* Don't assume UNIX (fixes github issue #9: didn't work on windows)


0.0.12 (2017-08-27)
~~~~~~~~~~~~~~~~~~~

* Changed default runner to add `-x` flag to pytest. Could radically speed up tests if you're lucky!

* New flag: `--show-times`

* Now warns if a mutation triggers very long test times

* Added a workaround for pytest-testmon (all tests deselected is return code 5 even though it's a success)


0.0.11 (2017-08-03)
~~~~~~~~~~~~~~~~~~~

* Fixed bug that made mutmut crash when setup.cfg was missing


0.0.10 (2017-07-16)
~~~~~~~~~~~~~~~~~~~

* Renamed parameter `--testsdir` to `--tests-dir`

* Refactored handling of setup.cfg file. Much cleaner solution and adds `--dict-synonyms` command line parameter


0.0.9 (2017-07-05)
~~~~~~~~~~~~~~~~~~

* Bug with dict param mutations: it mutated all parameters, this could vastly decrease the odds of finding a mutant

* New mutation: remove the body or return 0 instead of None


0.0.8 (2017-06-28)
~~~~~~~~~~~~~~~~~~

* Previous version had broken version on pypi


0.0.7 (2017-06-28)
~~~~~~~~~~~~~~~~~~

* Fixed bug where pragma didn't work for decorator mutations

* Dict literals looking like `dict(a=foo)` now have mutated keys. You can also declare synonyms in setup.cfg.

* Fix "from x import *"


0.0.6 (2017-06-13)
~~~~~~~~~~~~~~~~~~

* New mutation: remove decorators!

* Improved status while running. This should make it easier to handle when you hit mutants that cause infinite loops.

* Fixes failing attempts to mutate parentheses. (Thanks Hristo Georgiev!)


0.0.5 (2017-05-06)
~~~~~~~~~~~~~~~~~~

* Try to fix pypi package


0.0.4 (2017-05-06)
~~~~~~~~~~~~~~~~~~

* Try to fix pypi package


0.0.3 (2017-05-05)
~~~~~~~~~~~~~~~~~~

* Python 3 support (as far as baron supports it anyway)

* Try running without mutations first to make sure we can run the test suite cleanly before starting mutation

* Implemented feature to run mutation on covered lines only, this is useful for mutation testing existing tests when you don't have 100% coverage

* Error message on incorrect invocation


0.0.2 (2016-12-01)
~~~~~~~~~~~~~~~~~~

* Tons of fixes


0.0.1 (2016-12-01)
~~~~~~~~~~~~~~~~~~

* Initial version
