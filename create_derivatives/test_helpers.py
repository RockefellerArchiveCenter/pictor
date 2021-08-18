import shutil
from pathlib import Path


def make_dir(directory_path, remove_first=False, parents=True):
    """Makes a directory. If remove_first is set to true, removes directory if it exists; if set to false, does not make directory if it exists"""
    path = Path(directory_path)
    if path.exists() and remove_first:
        shutil.rmtree(directory_path)
    if not path.exists():
        path.mkdir(parents=parents)


def set_up_bag(tmp_dir, fixture_directory, bag):
    """Adds an uncompressed bag fixture to the temp directory and database"""
    bag_path = Path(tmp_dir, bag)
    if not bag_path.exists():
        shutil.copytree(Path("create_derivatives", "fixtures", fixture_directory, bag), bag_path)
