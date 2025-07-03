from mutmut.__main__ import CustomProcessPool, Task
import pytest
import time

def test_custom_process_pool():
    tasks = [
        Task(id='a-small', args=(1, 2), timeout_seconds=1000),
        Task(id='b-medium', args=(30, 20), timeout_seconds=1000),
        Task(id='c-neg', args=(-2, -2), timeout_seconds=1000),
        Task(id='d-div-by-zero', args=(-2, 0), timeout_seconds=1000),
    ]
    pool = CustomProcessPool(tasks, _divide, max_workers=2)

    results = []
    for result in pool.run():
        print(result)
        results.append(result)

    assert len(results) == 4

    results = sorted(results, key=lambda result: result.id)
    assert results[0].result == pytest.approx(0.5)
    assert results[1].result == pytest.approx(1.5)
    assert results[2].result == pytest.approx(1)
    assert results[3].result == None
    assert isinstance(results[3].error, ZeroDivisionError)

def _divide(task: Task):
    a, b = task.args
    # time.sleep(timeout)
    return a / b
