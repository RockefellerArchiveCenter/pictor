import random
import shutil
import string
from pathlib import Path

def copy_sample_files(directory, identifier, page_count, suffix):
    """Duplicates a sample file.

    Args:
        directory (str): Initial path of directory containing images to copy.
        identifier (string): Identifier used in filenames.
        page_count (int): The number of files to generate for each identifier.
        suffix (str): The filename suffix (extension) to be used
    """
    for f in Path(directory).iterdir():
        for page in range(page_count):
            target = Path(
                directory, "{}_{}.{}".format(
                    identifier, page, suffix))
            shutil.copyfile(
                Path(directory, f),
                Path(target))
        Path(directory, f).unlink()

def random_string(length=10):
    """Generates random ascii lowercase letters."""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))
