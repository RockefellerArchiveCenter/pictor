import shutil
from pathlib import Path

from django.test import TestCase
from pictor import settings

from .helpers import check_dir_exists
from .models import Bag
from .routines import BagPreparer


class HelpersTestCase(TestCase):

    def test_check_dir_exists(self):
        """Asserts check_dir_exists handles found and missing directories."""
        test_paths = ["/foo", "/bar", "/baz"]
        for p in test_paths:
            path = Path(p)
            path.mkdir(exist_ok=True)
            self.assertTrue(
                check_dir_exists(p),
                "Function did not return True")
            path.rmdir()
            with self.assertRaises(Exception) as context:
                check_dir_exists(p)
            self.assertTrue(
                p in str(
                    context.exception),
                "Directory was not found in exception")


class BagPreparerTestCase(TestCase):
    fixtures = ["created.json"]

    def setUp(self):
        for p in [settings.SRC_DIR, settings.TMP_DIR]:
            path = Path(p)
            if not path.exists():
                path.mkdir(parents=True)
        for f in Path("create_derivatives", "fixtures", "bags").iterdir():
            shutil.copy(str(f), settings.SRC_DIR)

    def test_unpack_bag(self):
        """Asserts bags are correctly unpacked."""
        routine = BagPreparer()
        for bag in Bag.objects.filter(process_status=Bag.CREATED):
            created = routine.unpack_bag(bag.bag_identifier)
            self.assertTrue(
                Path(
                    settings.TMP_DIR,
                    bag.bag_identifier).exists())
            self.assertEqual(
                created, str(
                    Path(
                        settings.TMP_DIR, bag.bag_identifier)))

    def test_run(self):
        BagPreparer().run()
        # assert bags in tmp
        # assert bag.bag_path, bag.as_data, bag.dimes_identifier, bag.process_status
        # assert return value
        pass

    def tearDown(self):
        for f in Path(settings.SRC_DIR).iterdir():
            f.unlink()
