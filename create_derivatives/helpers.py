from pathlib import Path


def check_dir_exists(dir):
    if not Path(dir).is_dir():
        raise Exception("Expected directory {} does not exist".format(dir))
    return True


def matching_files(directory, prefix=None, suffix=None,
                   prepend=False):
    """Get a list of files that start with a specific prefix.
    Args:
        directory (str): The directory containing files.
        prefix (str): A prefix to match filenames against.
        suffix (str): A suffix (file extension) to match filenames against.
        prepend (bool): Add the directory to the filepaths returned
    Returns:
        files (lst): a list of files that matched the identifier.
    """
    directory_path = Path(directory)
    files = sorted([f for f in directory_path.iterdir() if (
        Path(directory, f).is_file() and not str(f).startswith((".", "Thumbs")))])
    if prefix:
        files = sorted([f for f in files if str(f).startswith(prefix)])
    if suffix:
        files = sorted([f for f in files if str(f).endswith(suffix)])
    return [Path(directory, f) for f in files] if prepend else files

