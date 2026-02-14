def hello() -> str:
    greeting: str = "Hello from type-checking!"
    return greeting

def a_hello_wrapper() -> str:
    # verify that hello() keeps the return type str
    # (if not, this will type error and not be mutated)
    return hello() + "2"

class Person:
    def set_name(self, name: str):
        self.name = name

    def get_name(self):
        # return type should be inferred as "str"
        return self.name

def mutate_me():
    p = Person()
    p.set_name('charlie')
    # Verify that p.get_name keeps the return type str
    name: str = p.get_name()
    return name
