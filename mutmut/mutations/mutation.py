from abc import ABC, abstractmethod


class Mutation(ABC):
    def __init__(self, name):
        self.name = name

    @abstractmethod
    def mutate(self):
        ...
