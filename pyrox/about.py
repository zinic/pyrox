import os

import pyrox


def MissingResourceError(Exception):
    pass


def find_pyrox_resource(path):
    for pyrox_path in pyrox.__path__:
        full_path = os.path.join(pyrox_path, path)

        if os.path.exists(full_path):
            return open(full_path, 'r')
    raise MissingResourceError(path)


def _read(relative_path):
    with find_pyrox_resource(relative_path) as fin:
        return [l for l in fin.read().split('\n') if len(l) > 0]


VERSION = _read('VERSION')[0]
