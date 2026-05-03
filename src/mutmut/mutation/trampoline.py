import inspect
import os
from collections.abc import Callable
from functools import wraps
from typing import Annotated
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from mutmut.__main__ import MutmutProgrammaticFailException
from mutmut.__main__ import mangled_name_from_mutant_name
from mutmut.__main__ import record_trampoline_hit

TReturn = TypeVar("TReturn")
MutantDict = Annotated[dict[str, Callable[..., TReturn]], "Mutant"]

# mypy: disable-error-code="no-any-return, unused-ignore"


# properly typed decorator
P = ParamSpec("P")
R = TypeVar("R")

# mutant dict only contains some callable. maybe could be typed better, but likely not necessary.
F = TypeVar("F", bound=Callable[..., Any])


def wrap_in_trampoline(
    mutants_dict: dict[str, F], is_classmethod: bool = False
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def mutmut_mutated(decorated_func: Callable[P, R]) -> Callable[P, R]:
        """Wrap the ``decorated_func`` in a trampoline.
        The trampoline forwards calls based on the MUTANT_UNDER_TEST environment variable,
        either to a copy of the original method,
        or to the currently active mutated method.
        """

        def trampoline(*args: P.args, **kwargs: P.kwargs) -> R:
            # orig_func is the non-mutated implementation.
            # we do not use `decorated_func` directly,
            # because using the func via SomeClass.foo makes it easier for classmethod wrapping
            orig_func = mutants_dict["_mutmut_orig"]
            call_args: list[Any] = list(args)

            if is_classmethod:
                # for @classmethod, the first arg is cls
                # with getattr(cls, 'some_method'), we get cls.some_method
                # which is necessary to get the method bound to the subclass, even if it's declared on the parent class
                call_args = list(args[1:])
                orig_func = getattr(args[0], orig_func.__name__)

            mutant_under_test = os.environ.get("MUTANT_UNDER_TEST", "")

            if mutant_under_test == "fail":
                raise MutmutProgrammaticFailException(
                    "Verifying setup. At least one test should fail if mutations cause errors."
                )

            if mutant_under_test == "stats":
                record_trampoline_hit(f"{orig_func.__module__}.{mangled_name_from_mutant_name(orig_func.__name__)}")
                return orig_func(*call_args, **kwargs)

            # mutant under test is {module}.{mutant_name}
            module, _, mutant_name = mutant_under_test.rpartition(".")

            if module != decorated_func.__module__:
                # mutant of another module is active -> call original function
                return orig_func(*call_args, **kwargs)

            mutated_func = mutants_dict.get(mutant_name)
            if mutated_func is None:
                # No mutant being tested -> call original function
                return orig_func(*call_args, **kwargs)

            if is_classmethod:
                mutated_func = getattr(args[0], mutated_func.__name__)
            return mutated_func(*call_args, **kwargs)

        # ensure that inspect calls still produce the same result for the trampoline
        # @wraps sadly does not preserve this, so we do all cases manually here
        if inspect.isgeneratorfunction(decorated_func):

            @wraps(decorated_func)
            def _trampoline_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore
                yield from trampoline(*args, **kwargs)  # type: ignore
        elif inspect.iscoroutinefunction(decorated_func):

            @wraps(decorated_func)
            async def _trampoline_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore
                return await trampoline(*args, **kwargs)  # type: ignore
        elif inspect.isasyncgenfunction(decorated_func):

            @wraps(decorated_func)
            async def _trampoline_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore
                async for result in trampoline(*args, **kwargs):  # type: ignore
                    yield result
        else:

            @wraps(decorated_func)
            def _trampoline_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                return trampoline(*args, **kwargs)

        return _trampoline_wrapper  # type: ignore

    return mutmut_mutated
