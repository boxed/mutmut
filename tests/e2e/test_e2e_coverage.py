from inline_snapshot import snapshot

from tests.e2e.e2e_utils import run_mutmut_on_project


def test_mutate_only_covered_lines_result_snapshot():
    assert run_mutmut_on_project("mutate_only_covered_lines") == snapshot(
        {
            "mutants/src/mutate_only_covered_lines/__init__.py.meta": {
                "mutate_only_covered_lines.x_hello_mutate_only_covered_lines__mutmut_1": 1,
                "mutate_only_covered_lines.x_hello_mutate_only_covered_lines__mutmut_2": 1,
                "mutate_only_covered_lines.x_hello_mutate_only_covered_lines__mutmut_3": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_1": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_2": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_3": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_4": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_5": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_6": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_7": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_8": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_9": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_10": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_11": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_12": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_13": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_14": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_15": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_16": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_17": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_18": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_19": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_20": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_21": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_22": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_23": 0,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_24": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_25": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_26": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_27": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_28": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_29": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_30": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_31": 1,
                "mutate_only_covered_lines.x_mutate_only_covered_lines_multiline__mutmut_32": 1,
            }
        }
    )
