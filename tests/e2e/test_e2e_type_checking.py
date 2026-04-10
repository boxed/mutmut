from inline_snapshot import snapshot

from tests.e2e.e2e_utils import run_mutmut_on_project


def test_type_checking_pyrefly_result_snapshot():
    assert run_mutmut_on_project("type_checking") == snapshot(
        {
            "mutants/src/type_checking/__init__.py.meta": {
                "type_checking.x_hello__mutmut_1": 37,
                "type_checking.x_hello__mutmut_2": 1,
                "type_checking.x_hello__mutmut_3": 1,
                "type_checking.x_hello__mutmut_4": 1,
                "type_checking.x_a_hello_wrapper__mutmut_1": 37,
                "type_checking.x_a_hello_wrapper__mutmut_2": 0,
                "type_checking.xǁPersonǁset_name__mutmut_1": 37,
                "type_checking.xǁPersonǁcreate__mutmut_1": 37,
                "type_checking.xǁPersonǁcreate__mutmut_2": 37,
                "type_checking.xǁEmployeeǁ__init____mutmut_1": 0,
                "type_checking.xǁEmployeeǁ__init____mutmut_2": 0,
                "type_checking.xǁEmployeeǁ__init____mutmut_3": 0,
                "type_checking.xǁEmployeeǁ__init____mutmut_4": 37,
                "type_checking.xǁEmployeeǁset_number__mutmut_1": 37,
                "type_checking.xǁEmployeeǁnew__mutmut_1": 37,
                "type_checking.xǁEmployeeǁnew__mutmut_2": 37,
                "type_checking.xǁColorǁis_primary__mutmut_1": 33,
                "type_checking.xǁColorǁdarken__mutmut_1": 37,
                "type_checking.xǁColorǁdarken__mutmut_2": 37,
                "type_checking.xǁColorǁdarken__mutmut_3": 37,
                "type_checking.xǁColorǁdarken__mutmut_4": 37,
                "type_checking.xǁColorǁget_next_color__mutmut_1": 1,
                "type_checking.xǁColorǁget_next_color__mutmut_2": 0,
                "type_checking.xǁColorǁget_next_color__mutmut_3": 1,
                "type_checking.xǁColorǁget_next_color__mutmut_4": 1,
                "type_checking.xǁColorǁget_next_color__mutmut_5": 0,
                "type_checking.xǁColorǁget_next_color__mutmut_6": 0,
                "type_checking.xǁColorǁto_index__mutmut_1": 37,
                "type_checking.xǁColorǁto_index__mutmut_2": 37,
                "type_checking.xǁColorǁto_index__mutmut_3": 37,
                "type_checking.xǁColorǁto_index__mutmut_4": 0,
                "type_checking.xǁColorǁto_index__mutmut_5": 0,
                "type_checking.xǁColorǁto_index__mutmut_6": 0,
                "type_checking.xǁColorǁfrom_index__mutmut_1": 0,
                "type_checking.xǁColorǁfrom_index__mutmut_2": 0,
                "type_checking.xǁColorǁcreate__mutmut_1": 1,
                "type_checking.x_mutate_me__mutmut_1": 37,
                "type_checking.x_mutate_me__mutmut_2": 37,
                "type_checking.x_mutate_me__mutmut_3": 1,
                "type_checking.x_mutate_me__mutmut_4": 1,
                "type_checking.x_mutate_me__mutmut_5": 37,
            }
        }
    )


def test_type_checking_mypy_result_snapshot(patch_config):
    # we use the same project as for pyrefly, but patch the type checking command
    mypy_command = ["mypy", "src", "--output", "json", "--disable-error-code", "unused-ignore"]
    patch_config("type_check_command", mypy_command)

    assert run_mutmut_on_project("type_checking") == snapshot(
        {
            "mutants/src/type_checking/__init__.py.meta": {
                "type_checking.x_hello__mutmut_1": 37,
                "type_checking.x_hello__mutmut_2": 1,
                "type_checking.x_hello__mutmut_3": 1,
                "type_checking.x_hello__mutmut_4": 1,
                "type_checking.x_a_hello_wrapper__mutmut_1": 37,
                "type_checking.x_a_hello_wrapper__mutmut_2": 0,
                "type_checking.xǁPersonǁset_name__mutmut_1": 37,
                "type_checking.xǁPersonǁcreate__mutmut_1": 37,
                "type_checking.xǁPersonǁcreate__mutmut_2": 37,
                "type_checking.xǁEmployeeǁ__init____mutmut_1": 0,
                "type_checking.xǁEmployeeǁ__init____mutmut_2": 0,
                "type_checking.xǁEmployeeǁ__init____mutmut_3": 0,
                "type_checking.xǁEmployeeǁ__init____mutmut_4": 37,
                "type_checking.xǁEmployeeǁset_number__mutmut_1": 37,
                "type_checking.xǁEmployeeǁnew__mutmut_1": 37,
                "type_checking.xǁEmployeeǁnew__mutmut_2": 37,
                "type_checking.xǁColorǁis_primary__mutmut_1": 33,
                "type_checking.xǁColorǁdarken__mutmut_1": 37,
                "type_checking.xǁColorǁdarken__mutmut_2": 37,
                "type_checking.xǁColorǁdarken__mutmut_3": 37,
                "type_checking.xǁColorǁdarken__mutmut_4": 37,
                "type_checking.xǁColorǁget_next_color__mutmut_1": 37,
                "type_checking.xǁColorǁget_next_color__mutmut_2": 37,
                "type_checking.xǁColorǁget_next_color__mutmut_3": 37,
                "type_checking.xǁColorǁget_next_color__mutmut_4": 37,
                "type_checking.xǁColorǁget_next_color__mutmut_5": 37,
                "type_checking.xǁColorǁget_next_color__mutmut_6": 37,
                "type_checking.xǁColorǁto_index__mutmut_1": 37,
                "type_checking.xǁColorǁto_index__mutmut_2": 37,
                "type_checking.xǁColorǁto_index__mutmut_3": 37,
                "type_checking.xǁColorǁto_index__mutmut_4": 37,
                "type_checking.xǁColorǁto_index__mutmut_5": 37,
                "type_checking.xǁColorǁto_index__mutmut_6": 37,
                "type_checking.xǁColorǁfrom_index__mutmut_1": 0,
                "type_checking.xǁColorǁfrom_index__mutmut_2": 0,
                "type_checking.xǁColorǁcreate__mutmut_1": 1,
                "type_checking.x_mutate_me__mutmut_1": 37,
                "type_checking.x_mutate_me__mutmut_2": 37,
                "type_checking.x_mutate_me__mutmut_3": 1,
                "type_checking.x_mutate_me__mutmut_4": 1,
                "type_checking.x_mutate_me__mutmut_5": 37,
            }
        }
    )
