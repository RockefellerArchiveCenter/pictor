from pathlib import Path

from django.test import TestCase
from .helpers import check_dir_exists


class HelpersTestCase(TestCase):

    def test_check_dir_exists(self):
        """Asserts check_dir_exists handles found and missing directories."""
        test_paths = ["/foo", "/bar", "/baz"]
        for p in test_paths:
            path = Path(p)
            path.mkdir(exist_ok=True)
            self.assertTrue(check_dir_exists(p), "Function did not return True")
            path.rmdir()
            with self.assertRaises(Exception) as context:
                check_dir_exists(p)
            self.assertTrue(p in str(context.exception), "Directory was not found in exception")


class BagPreparerTestCase(TestCase):
    # fixtures = ["prepare_data.json"]

    def setUp(self):
        # add bags to directory
        pass

    def test_unpack_bag(self):
        # check bag is extracted to correct path
        # assert string matching bag_identifier is returned
        pass

    def test_run(self):
        # assert bags in tmp
        # assert bag.bag_path, bag.as_data, bag.dimes_identifier, bag.process_status
        # assert return value
        pass

    def tearDown(self):
        # remove bags from directories
        pass
