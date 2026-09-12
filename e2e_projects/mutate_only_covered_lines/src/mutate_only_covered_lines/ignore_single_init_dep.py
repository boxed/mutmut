"""Stands in for a dependency that cannot be initialized twice in one process.

Regression guard for #528, where numpy and libyaml raise, cryptography fails a type
check and asyncpg segfaults. Named to match ``do_not_mutate = ["*ignore*"]``, so it is
copied and imported like any dependency but stays out of the result snapshot.
"""

import os

# Outside the module, or it would be evicted with it. Keyed by pid so forks, which
# inherit a copy of the environment, each get their own initialization.
_INITIALIZED_IN_PID = "MUTMUT_E2E_SINGLE_INIT_DEP_PID"

if os.environ.get(_INITIALIZED_IN_PID) == str(os.getpid()):
    raise ImportError("cannot load module more than once per process")

os.environ[_INITIALIZED_IN_PID] = str(os.getpid())


def single_init_value():
    return 42
