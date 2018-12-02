from mutmut.cache import sequence_ops


def test_sequence_ops():
    a = [
        'a',
        'b',
        'c',
        'd',
        'e',
        'f',
        'g',
    ]
    b = a[:]

    assert list(sequence_ops(a, b)) == [
        ('equal', 'a', 0, 'a', 0),
        ('equal', 'b', 1, 'b', 1),
        ('equal', 'c', 2, 'c', 2),
        ('equal', 'd', 3, 'd', 3),
        ('equal', 'e', 4, 'e', 4),
        ('equal', 'f', 5, 'f', 5),
        ('equal', 'g', 6, 'g', 6),
    ]

    # now modify
    b[1] = 'replaced'
    b.insert(3, 'inserted')
    del b[-1]

    assert list(sequence_ops(a, b)) == [
        ('equal', 'a', 0, 'a', 0),
        ('replace', 'b', 1, 'replaced', 1),
        ('equal', 'c', 2, 'c', 2),
        ('insert', None, None, 'inserted', 3),
        ('equal', 'd', 3, 'd', 4),
        ('equal', 'e', 4, 'e', 5),
        ('equal', 'f', 5, 'f', 6),
        ('delete', 'g', 6, None, None),
    ]
