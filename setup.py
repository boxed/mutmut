#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""setup.py for mutmut"""

import codecs
import os
import re
import sys

from setuptools import setup, find_packages, Command
from setuptools.command.test import test

history = open('HISTORY.rst').read().replace('.. :changelog:', '')


def find_version(*file_paths):
    with codecs.open(os.path.join(os.path.abspath(os.path.dirname(__file__)), *file_paths), 'r') as fp:
        version_file = fp.read()
    m = re.search(r"^__version__ = \((\d+), ?(\d+), ?(\d+)\)", version_file, re.M)
    if m:
        return "{}.{}.{}".format(*m.groups())
    raise RuntimeError("Unable to find a valid version")


VERSION = find_version("mutmut", "__init__.py")


class Tag(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        from subprocess import call
        version = VERSION
        errno = call(['git', 'tag', '--annotate', version, '--message', 'Version %s' % version])
        if errno == 0:
            print("Added tag for version %s" % version)
        raise SystemExit(errno)


class ReleaseCheck(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        from subprocess import check_output
        tag = check_output(['git', 'describe', '--all', '--exact-match', 'HEAD']).strip().split('/')[-1]
        version = VERSION
        if tag != version:
            print('Missing %s tag on release' % version)
            raise SystemExit(1)

        current_branch = check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).strip()
        if current_branch != 'master':
            print('Only release from master')
            raise SystemExit(1)

        print("Ok to distribute files")


class Pylint(test):
    def run_tests(self):
        from pylint.lint import Run
        Run(["mutmut", "--persistent", "y", "--rcfile", ".pylintrc",
             "--output-format", "colorized"])


class PyTest(test):
    user_options = [('pytest-args=', 'a', "Arguments to pass to pytest")]

    def initialize_options(self):
        test.initialize_options(self)
        self.pytest_args = "-v --cov={}".format("mutmut")

    def run_tests(self):
        import shlex
        # import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(shlex.split(self.pytest_args))
        sys.exit(errno)


import inspect
running_inside_tests = any(['pytest' in x[1] for x in inspect.stack()])

# NB: _don't_ add namespace_packages to setup(), it'll break
#     everything using imp.find_module
setup(
    name='mutmut',
    version=VERSION,
    description='',
    long_description=open("README.rst").read(),
    author='Anders Hovmöller',
    author_email='boxed@killingar.net',
    url='https://github.com/boxed/mutmut',
    packages=find_packages('.'),
    package_dir={'': '.'},
    include_package_data=True,
    install_requires=[
        "glob2",
        "parso",
        "tri.declarative",
        "pony",
    ],
    tests_require=[
        "pytest",
        "pytest-cov",
        "pylint>=1.9.1,<2.0.0",
    ],
    license="BSD",
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        "Framework :: Pytest",
    ],
    test_suite='tests',
    cmdclass={'tag': Tag,
              'release_check': ReleaseCheck, "test": PyTest, "lint": Pylint},
    # if I add entry_points while pytest runs, it imports before the coverage collecting starts
    entry_points={
        'pytest11': [
            'mutmut = mutmut.pytestplugin',
        ]
    } if running_inside_tests else {},
    scripts=['bin/mutmut'],
)
