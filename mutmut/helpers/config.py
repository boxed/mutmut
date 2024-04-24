import os
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Set


@dataclass
class Config:
    swallow_output: bool
    test_command: str
    _default_test_command: str = field(init=False)
    covered_lines_by_filename: Optional[Dict[str, set[Optional[int]]]]
    baseline_time_elapsed: float
    test_time_multiplier: float
    test_time_base: float
    dict_synonyms: List[str]
    total: int
    using_testmon: bool
    tests_dirs: List[str]
    hash_of_tests: str
    post_mutation: str
    pre_mutation: str
    coverage_data: Dict[str, Dict[int, List[str]]]
    paths_to_mutate: List[str]
    mutation_types_to_apply: Set[str]
    no_progress: bool
    ci: bool
    rerun_all: bool

    def __post_init__(self):
        self._default_test_command = self.test_command


def should_exclude(context, config: Optional[Config]):
        if config is None or config.covered_lines_by_filename is None:
            return False

        try:
            covered_lines = config.covered_lines_by_filename[context.filename]
        except KeyError:
            if config.coverage_data is not None:
                covered_lines = config.coverage_data.get(os.path.abspath(context.filename))
                config.covered_lines_by_filename[context.filename] = covered_lines
            else:
                covered_lines = None

        if covered_lines is None:
            return True
        current_line = context.current_line_index + 1
        if current_line not in covered_lines:
            return True
        return False
