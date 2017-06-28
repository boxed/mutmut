Changelog
---------

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

