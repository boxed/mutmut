#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import io
import inspect

from setuptools import setup, find_packages, Command
from setuptools.command.test import test

readme = io.open('README.rst', encoding='utf8').read()
history = io.open('HISTORY.rst', encoding='utf8').read().replace('.. :changelog:', '')


def read_reqs(name):
    with open(os.path.join(os.path.dirname(__file__), name)) as f:
        return [line for line in f.read().split('\n') if line and not line.strip().startswith('#')]


def read_version():
    with open(os.path.join('mutmut', '__init__.py')) as f:
        m = re.search(r'''__version__\s*=\s*['"]([^'"]*)['"]''', f.read())
        if m:
            return m.group(1)
        raise ValueError("couldn't find version")


class Tag(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        from subprocess import call
        version = read_version()
        errno = call(['git', 'tag', '--annotate', version, '--message', 'Version {}'.format(version)])
        if errno == 0:
            print("Added tag for version {}".format(version))
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
        version = read_version()
        if tag != version:
            print('Missing {} tag on release'.format(version))
            raise SystemExit(1)

        current_branch = check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).strip()
        if current_branch != 'master':
            print('Only release from master')
            raise SystemExit(1)

        print("Ok to distribute files")


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


test_reqs = read_reqs('test_requirements.txt')
extras_reqs = {
    'pytest': [
        item for item in test_reqs if item.startswith('pytest')],
    'coverage': [
        item for item in test_reqs if item.startswith('coverage')],
    'patch': [
        item for item in test_reqs if item.startswith('whatthepatch')],
}

running_inside_tests = any(['pytest' in x[1] for x in inspect.stack()])

# NB: _don't_ add namespace_packages to setup(), it'll break
#     everything using imp.find_module
setup(
    name='mutmut',
    version=read_version(),
    description='mutation testing for Python 3',
    long_description=readme,
    author='Anders Hovmöller',
    author_email='boxed@killingar.net',
    url='https://github.com/boxed/mutmut',
    packages=find_packages('.'),
    package_dir={'': '.'},
    include_package_data=True,
    license="BSD",
    zip_safe=False,
    keywords='mutmut mutant mutation test testing',
    install_requires=read_reqs('requirements.txt'),
    extras_require=extras_reqs,
    tests_require=test_reqs,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Framework :: Pytest',
    ],
    test_suite='tests',
    cmdclass={
        'tag': Tag,
        'release_check': ReleaseCheck,
        'test': PyTest,
    },
    # if I add entry_points while pytest runs,
    # it imports before the coverage collecting starts
    entry_points={
        'pytest11': [
            'mutmut = mutmut.pytestplugin',
        ],
    } if running_inside_tests else {
        'console_scripts': ["mutmut = mutmut.__main__:climain"],
    },
)
