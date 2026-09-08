"""Results are written to the meta file in batches, not once per mutant."""

import json
from pathlib import Path

from mutmut.mutation.data import SourceFileMutationData


def _data(tmp_path: Path, monkeypatch) -> SourceFileMutationData:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mutants" / "src").mkdir(parents=True)
    data = SourceFileMutationData(path=Path("src/module.py"))
    data.exit_code_by_key = {"module.x_f__mutmut_1": None, "module.x_f__mutmut_2": None}
    return data


def _saved_results(data: SourceFileMutationData) -> dict[str, int | None]:
    with open(data.meta_path) as f:
        return json.load(f)["exit_code_by_key"]


def test_registering_a_result_marks_the_file_dirty_without_writing_it(tmp_path, monkeypatch):
    data = _data(tmp_path, monkeypatch)
    data.register_pid(pid=1234, key="module.x_f__mutmut_1")

    assert data.register_result(pid=1234, exit_code=1) == "module.x_f__mutmut_1"

    assert data.exit_code_by_key["module.x_f__mutmut_1"] == 1
    assert data.durations_by_key["module.x_f__mutmut_1"] >= 0
    assert 1234 not in data.key_by_pid
    assert data.dirty
    assert not data.meta_path.exists()


def test_save_if_dirty_writes_once_and_clears_the_flag(tmp_path, monkeypatch):
    data = _data(tmp_path, monkeypatch)
    data.save_if_dirty()
    assert not data.meta_path.exists()

    data.set_result("module.x_f__mutmut_2", 33)
    data.save_if_dirty()
    assert _saved_results(data) == {"module.x_f__mutmut_1": None, "module.x_f__mutmut_2": 33}
    assert not data.dirty

    data.meta_path.unlink()
    data.save_if_dirty()
    assert not data.meta_path.exists()


def test_save_always_writes_and_clears_the_flag(tmp_path, monkeypatch):
    data = _data(tmp_path, monkeypatch)
    data.set_result("module.x_f__mutmut_1", 0)

    data.save()

    assert not data.dirty
    assert _saved_results(data) == {"module.x_f__mutmut_1": 0, "module.x_f__mutmut_2": None}
