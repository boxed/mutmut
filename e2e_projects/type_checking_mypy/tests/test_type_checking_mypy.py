from type_checking_mypy import mutate_me

def test_mutate_me() -> None:
    assert mutate_me() == "Hello from type-checking-mypy! Goodbye"
