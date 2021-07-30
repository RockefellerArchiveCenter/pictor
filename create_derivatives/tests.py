import random
import shutil
from os.path import isdir, join
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from pictor import settings

from .helpers import check_dir_exists, matching_files
from .models import Bag
from .routines import AWSUpload, BagPreparer
from .test_helpers import copy_sample_files, random_string


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
            self.assertTrue(
                p in str(context.exception), "Directory was not found in exception")

    def test_matching_files(self):
        MATCHING_FIXTURE_FILEPATH = join("create_derivatives", "fixtures", "matching")
        MATCHING_SOURCE_DIR = join("/", "matching")
        if isdir(MATCHING_SOURCE_DIR):
            shutil.rmtree(MATCHING_SOURCE_DIR)
        shutil.copytree(MATCHING_FIXTURE_FILEPATH, MATCHING_SOURCE_DIR)
        matching = matching_files(MATCHING_SOURCE_DIR)
        assert len(matching) == 4
        matching = matching_files(MATCHING_SOURCE_DIR, prefix="sample")
        assert len(matching) == 2
        matching = matching_files(MATCHING_SOURCE_DIR, prefix="foo")
        assert len(matching) == 0
        matching = matching_files(MATCHING_SOURCE_DIR, prefix="sample", skip=True)
        assert len(matching) == 2
        matching = matching_files(MATCHING_SOURCE_DIR, suffix=".jp2")
        assert len(matching) == 1
        matching = matching_files(MATCHING_SOURCE_DIR, suffix=".tif")
        assert len(matching) == 1
        matching = matching_files(MATCHING_SOURCE_DIR, suffix=".pdf")
        assert len(matching) == 0
        matching = matching_files(MATCHING_SOURCE_DIR, prepend=True)
        assert matching[0].startswith(MATCHING_SOURCE_DIR)


class BagPreparerTestCase(TestCase):
    fixtures = ["created.json"]

    def setUp(self):
        for p in [settings.SRC_DIR, settings.TMP_DIR]:
            path = Path(p)
            if not path.exists():
                path.mkdir(parents=True)
        for f in Path("create_derivatives", "fixtures", "bags").iterdir():
            shutil.copy(str(f), settings.SRC_DIR)

    @patch("create_derivatives.clients.ArchivesSpaceClient.__init__")
    def test_unpack_bag(self, mock_init):
        """Asserts bags are correctly unpacked."""
        mock_init.return_value = None
        routine = BagPreparer()
        for bag in Bag.objects.filter(process_status=Bag.CREATED):
            created = routine.unpack_bag(bag.bag_identifier)
            self.assertTrue(
                Path(settings.TMP_DIR, bag.bag_identifier).exists(),
                "Extracted path does not exist")
            self.assertEqual(
                created, str(Path(settings.TMP_DIR, bag.bag_identifier)),
                "Wrong bag path returned")

    @patch("create_derivatives.clients.ArchivesSpaceClient.__init__")
    @patch("create_derivatives.clients.ArchivesSpaceClient.get_object")
    def test_run(self, mock_get_object, mock_init):
        """Asserts that the run method produces the desired results.

        Tests that the correct number of bags was processsed, and that the
        attributes of each have been correctly set.
        """
        mock_init.return_value = None
        as_data = {"uri": "foobar", "title": "baz", "dates": "January 1, 2020"}
        mock_get_object.return_value = as_data
        created_len = len(Bag.objects.filter(process_status=Bag.CREATED))
        prepared = BagPreparer().run()
        self.assertTrue(isinstance(prepared, tuple))
        self.assertEqual(prepared[0], "Bags successfully prepared")
        self.assertEqual(len(prepared[1]), created_len, "Wrong number of bags processed")
        self.assertTrue(len(list(Path(settings.TMP_DIR).glob("*"))), created_len)
        for bag in Bag.objects.all():
            self.assertEqual(bag.process_status, Bag.PREPARED)
            self.assertEqual(bag.bag_path, str(Path(settings.TMP_DIR, bag.bag_identifier)))
            self.assertEqual(bag.as_data, as_data)
            self.assertIsNot(bag.dimes_identifier, None)

    def tearDown(self):
        for f in Path(settings.SRC_DIR).iterdir():
            f.unlink()


class AWSUploadTestCase(TestCase):

    def setUp(self):
        MANIFEST_FIXTURES = join("create_derivatives", "fixtures", "manifests")
        MANIFEST_DIR = join("/", "manifests")
        DERIVATIVE_FIXTURES = join("create_derivatives", "fixtures", "jp2")
        DERIVATIVE_DIR = join("/", "derivatives")
        UUIDS = [random_string() for x in range(random.randint(1, 3))]
        PAGE_COUNT = random.randint(1, 5)
        for d in [MANIFEST_DIR, DERIVATIVE_DIR]:
            if isdir(d):
                d.unlink()
        shutil.copytree(DERIVATIVE_FIXTURES, DERIVATIVE_DIR)
        shutil.copytree(MANIFEST_FIXTURES, MANIFEST_DIR)
        copy_sample_files(DERIVATIVE_DIR, UUIDS, PAGE_COUNT, "jp2")
        copy_sample_files(MANIFEST_DIR, UUIDS, PAGE_COUNT, "json")
        routine = AWSUpload
        print(routine)

    def teardown():
        for d in [self.MANIFEST_DIR, self.DERIVATIVE_DIR]:
            shutil.rmtree(d)
