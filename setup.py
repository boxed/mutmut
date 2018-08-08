#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re
from setuptools import setup, find_packages, Command

readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')


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
        version = read_version()
        if tag != version:
            print('Missing %s tag on release' % version)
            raise SystemExit(1)

        current_branch = check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).strip()
        if current_branch != 'master':
            print('Only release from master')
            raise SystemExit(1)

        print("Ok to distribute files")

import inspect
running_inside_tests = any(['pytest' in x[1] for x in inspect.stack()])

# NB: _don't_ add namespace_packages to setup(), it'll break
#     everything using imp.find_module
setup(
    name='mutmut',
    version=read_version(),
    description='',
    long_description=readme,
    author='Anders Hovmöller',
    author_email='boxed@killingar.net',
    url='https://github.com/boxed/mutmut',
    packages=find_packages('.'),
    package_dir={'': '.'},
    include_package_data=True,
    install_requires=read_reqs('requirements.txt'),
    license="BSD",
    zip_safe=False,
    keywords='',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        "Framework :: Pytest",
    ],
    test_suite='tests',
    cmdclass={'tag': Tag,
              'release_check': ReleaseCheck},
    # if I add entry_points while pytest runs, it imports before the coverage collecting starts
    entry_points={
        'pytest11': [
            'mutmut = mutmut.pytestplugin',
        ]
    } if running_inside_tests else {},
    scripts=['bin/mutmut'],
)
