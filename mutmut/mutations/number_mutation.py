from mutmut.mutations.mutation import Mutation


class NumberMutation(Mutation):

    def __init__(self):
        super().__init__('NumberMutation')

    def mutate(self, value, **kwargs):
        suffix = ''
        if value.upper().endswith('L'):  # pragma: no cover (python 2 specific)
            suffix = value[-1]
            value = value[:-1]

        if value.upper().endswith('J'):
            suffix = value[-1]
            value = value[:-1]

        if value.startswith('0o'):
            base = 8
            value = value[2:]
        elif value.startswith('0x'):
            base = 16
            value = value[2:]
        elif value.startswith('0b'):
            base = 2
            value = value[2:]
        elif value.startswith('0') and len(value) > 1 and value[1] != '.':  # pragma: no cover (python 2 specific)
            base = 8
            value = value[1:]
        else:
            base = 10

        try:
            parsed = int(value, base=base)
            result = repr(parsed + 1)
        except ValueError:
            # Since it wasn't an int, it must be a float
            parsed = float(value)
            # This avoids all very small numbers becoming 1.0, and very
            # large numbers not changing at all
            if (1e-5 < abs(parsed) < 1e5) or (parsed == 0.0):
                result = repr(parsed + 1)
            else:
                result = repr(parsed * 2)

        if not result.endswith(suffix):
            result += suffix
        return result
