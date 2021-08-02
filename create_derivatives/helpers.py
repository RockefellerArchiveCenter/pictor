from pathlib import Path, PurePath


def check_dir_exists(dir):
    if not Path(dir).is_dir():
        raise Exception("Expected directory {} does not exist".format(dir))
    return True


def matching_files(directory, prefix=None, suffix=None,
                   prepend=False):
    """Get a list of files that start with a specific prefix, optionally removing
    any files that end in `_001`.

    Args:
        directory (str): The directory containing files.
        prefix (str): A prefix to match filenames against.
        suffix (str): A suffix (file extension) to match filenames against.
        skip (bool): Flag indicating if files ending with `_001` should be removed.
        prepend (bool): Add the directory to the filepaths returned
    Returns:
        files (lst): a list of files that matched the identifier.
    """
    directory_path = Path(directory)
    files = sorted([f for f in directory_path.iterdir() if (
        Path(PurePath(directory, f)).is_file() and not str(f).startswith((".", "Thumbs")))])
    if prefix:
        files = sorted([f for f in files if str(f).startswith(prefix)])
    if suffix:
        files = sorted([f for f in files if str(f).endswith(suffix)])
    return [PurePath(directory, f) for f in files] if prepend else files
