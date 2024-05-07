import os
from pathlib import Path
from shutil import copy

import click
from glob2 import glob


def split_paths(paths):
    # This method is used to split paths that are separated by commas or colons
    for sep in [',', ':']:
        separated = list(filter(lambda p: Path(p).exists(), paths.split(sep)))
        if separated:
            return separated
    return None


def get_split_paths(p, test_paths):
    split = []

    for pt in test_paths:
        split.extend(glob(p + '/**/' + pt, recursive=True))

    return split


def copy_testmon_data(using_testmon):
    if using_testmon:
        copy('.testmondata', '.testmondata-initial')


def stop_creating_pyc_files():
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'


def check_file_exists(filename):
    if not os.path.exists(filename):
        raise click.BadArgumentUsage(f'File {filename} does not exist')
