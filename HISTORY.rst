Changelog
---------

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

