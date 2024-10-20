#!/usr/bin/env python3
import os
import re
import io
import inspect

from setuptools import setup, find_packages, Command


def read_file(name):
    with io.open(os.path.join(os.path.dirname(__file__), name), encoding='utf8') as f:
        return f.read()


def read_reqs(name):
    return [line for line in read_file(name).split('\n') if line and not line.strip().startswith('#')]


def read_version():
    m = re.search(r'''__version__\s*=\s*['"]([^'"]*)['"]''', read_file('mutmut/__init__.py'))
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
        tag = check_output(['git', 'describe', '--all', '--exact-match', 'HEAD']).strip().decode().split('/')[-1]
        version = read_version()
        if tag != version:
            print('Missing {} tag on release'.format(version))
            raise SystemExit(1)

        current_branch = check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).decode().strip()
        if current_branch != 'main':
            print('Only release from main')
            raise SystemExit(1)

        print("Ok to distribute files")

running_inside_tests = any('pytest' in x[1] or 'hammett' in x[1] for x in inspect.stack())

# NB: _don't_ add namespace_packages to setup(), it'll break
#     everything using imp.find_module
setup(
    name='mutmut',
    version=read_version(),
    description='mutation testing for Python 3',
    long_description='' if running_inside_tests else read_file('README.rst'),
    author='Anders Hovmöller',
    author_email='boxed@killingar.net',
    url='https://github.com/boxed/mutmut',
    packages=find_packages('.'),
    package_dir={'': '.'},
    package_data={
        'mutmut': ['*.tcss'],
    },
    include_package_data=True,
    license="BSD",
    zip_safe=False,
    keywords='mutmut mutant mutation test testing',
    install_requires=read_reqs('requirements.txt'),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
    ],
    test_suite='tests',
    cmdclass={
        'tag': Tag,
        'release_check': ReleaseCheck,
    },
    # if I add entry_points while pytest runs,
    # it imports before the coverage collecting starts
    entry_points={
        'pytest11': [
            'mutmut = mutmut.pytestplugin',
        ],
    } if running_inside_tests else {
        'console_scripts': ["mutmut = mutmut.__main__:cli"],
    },
)
