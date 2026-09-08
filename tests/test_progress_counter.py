from mutmut.mutation.data import SourceFileMutationData
from mutmut.stats import ProgressCounter
from mutmut.stats import calculate_summary_stats


def _data(path: str, results: dict[str, int | None]) -> SourceFileMutationData:
    data = SourceFileMutationData(path=path)
    data.exit_code_by_key = dict(results)
    return data


def test_counter_matches_a_full_recount_after_verdicts_change():
    by_path = {
        "a.py": _data("a.py", {"a.x_f__mutmut_1": None, "a.x_f__mutmut_2": None, "a.x_f__mutmut_3": 1}),
        "b.py": _data("b.py", {"b.x_g__mutmut_1": 0}),
    }
    counter = ProgressCounter(by_path)
    assert counter.stat == calculate_summary_stats(by_path)

    changes = [("a.py", "a.x_f__mutmut_1", 1), ("a.py", "a.x_f__mutmut_2", 36), ("b.py", "b.x_g__mutmut_1", 37)]
    for path, key, exit_code in changes:
        old = by_path[path].exit_code_by_key[key]
        by_path[path].set_result(key, exit_code)
        counter.record(old, exit_code)

    assert counter.stat == calculate_summary_stats(by_path)
    assert counter.stat.not_checked == 0
    assert counter.stat.killed == 2
    assert counter.stat.timeout == 1
    assert counter.stat.caught_by_type_check == 1
    assert counter.stat.total == 4


def test_recording_the_same_status_twice_is_a_no_op():
    by_path = {"a.py": _data("a.py", {"a.x_f__mutmut_1": 1})}
    counter = ProgressCounter(by_path)
    counter.record(1, 3)  # both "killed"
    assert counter.stat == calculate_summary_stats(by_path)
