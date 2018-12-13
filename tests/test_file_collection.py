#!/usr/bin/python
# -*- coding: utf-8 -*-

"""pytests for :mod:`mutmut.file_collection`"""

import os

import pytest

from mutmut.file_collection import python_source_files

from tests.test_main import filesystem


@pytest.mark.parametrize(
    "expected, source_path, tests_dirs",
    [
        (["foo.py"], "foo.py", []),
        ([os.path.join(".", "foo.py"),
          os.path.join(".", "tests", "test_foo.py")], ".", []),
        ([os.path.join(".", "foo.py")], ".", [os.path.join(".", "tests")])
    ]
)
@pytest.mark.usefixtures('filesystem')
def test_python_source_files(expected, source_path, tests_dirs):
    assert expected == list(python_source_files(source_path, tests_dirs))
