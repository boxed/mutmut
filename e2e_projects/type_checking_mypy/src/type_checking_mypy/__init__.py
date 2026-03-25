def hello() -> str:
    greeting = "Hello from type-checking-mypy!"
    return greeting

def mutate_me() -> str:
    # verify that hello() keeps the return type str
    # (if not, this will type error and not be mutated)
    return hello() + " Goodbye"
