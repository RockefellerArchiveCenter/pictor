from pathlib import Path


def check_dir_exists(dir):
    if not Path(dir).is_dir():
        raise Exception("Expected directory {} does not exist".format(dir))
    return True


def matching_files(directory, prefix=None, suffix=None, prepend=False):
    """Get a list of files that start with a specific prefix.
    Args:
        directory (pathlib.Path): The directory containing files.
        prefix (str): A prefix to match filenames against.
        suffix (str): A suffix (file extension) to match filenames against.
        prepend (bool): Add the directory to the filepaths returned
    Returns:
        files (lst): a list of files that matched the identifier, sorted alphabetically.
    """
    HIDDEN_FILES = (".", "Thumbs")  # files which start with these strings will be skipped

    files = sorted([f for f in directory.iterdir() if (
        directory.joinpath(f).is_file() and not str(f.name).startswith(HIDDEN_FILES))])
    if prefix:
        files = sorted([f for f in files if str(f.name).startswith(prefix)])
    if suffix:
        files = sorted([f for f in files if str(f.name).endswith(suffix)])
    return [directory.joinpath(f) for f in files] if prepend else files


def get_page_number(filename):
    """Parses a page number from a filename.

    Presumes that:
        The page number is preceded by an underscore
        The page number is immediately followed by either by `_m`, `_me` or `_se`,
        or the file extension.

    Args:
        file (str): filename of a TIFF image file.
    Returns:
        4-digit page number from the filename with leading zeroes
    """
    base_filename = Path(filename).stem
    if "_se" in base_filename:
        filename_trimmed = base_filename.split("_se")[0]
    elif "_m" in base_filename:
        filename_trimmed = base_filename.split("_m")[0]
    else:
        filename_trimmed = base_filename
    return filename_trimmed.split("_")[-1].lstrip("0").zfill(4)
