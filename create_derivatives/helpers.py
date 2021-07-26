from pathlib import Path


def check_dir_exists(dir):
    if not Path(dir).is_dir():
        raise Exception("Expected directory {} does not exist".format(dir))
    return True
