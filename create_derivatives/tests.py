import shutil
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from pictor import settings
from rest_framework.test import APIRequestFactory

from .helpers import check_dir_exists, matching_files
from .models import Bag
from .routines import AWSUpload, BagPreparer


class ViewTestCase(TestCase):
    """Tests Views."""
    fixtures = ["created.json"]

    def setUp(self):
        self.factory = APIRequestFactory()

    def assert_status_code(
            self, method, url, expected_status, data=None, **kwargs):
        """Asserts that a URL returns an expected HTTP status code."""
        response = getattr(self.client, method)(url, data, **kwargs)
        self.assertEqual(
            expected_status, response.status_code,
            "Expected status code {} but got {}".format(expected_status, response.status_code))

    def test_bagviewset(self):
        """Asserts BagViewSet views return expected responses."""
        self.assert_status_code("get", reverse("bag-list"), 200)
        for bag in Bag.objects.all():
            self.assert_status_code(
                "get",
                reverse(
                    "bag-detail",
                    kwargs={
                        "pk": bag.pk}),
                200)
        data = {
            "bag_data": {
                "uri": "foo"},
            "origin": "digitization",
            "identifier": "foo"}
        self.assert_status_code(
            "post",
            reverse("bag-list"),
            201,
            data=data,
            content_type="application/json")


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
        MATCHING_FIXTURE_FILEPATH = Path("create_derivatives", "fixtures", "matching")
        MATCHING_SOURCE_DIR = Path("matching").absolute()
        if MATCHING_SOURCE_DIR.is_dir():
            shutil.rmtree(MATCHING_SOURCE_DIR)
        shutil.copytree(MATCHING_FIXTURE_FILEPATH, MATCHING_SOURCE_DIR)
        matching = matching_files(MATCHING_SOURCE_DIR)
        assert len(matching) == 4
        matching = matching_files(MATCHING_SOURCE_DIR, prefix="sample")
        assert len(matching) == 2
        matching = matching_files(MATCHING_SOURCE_DIR, prefix="foo")
        assert len(matching) == 0
        matching = matching_files(MATCHING_SOURCE_DIR, prefix="sample")
        assert len(matching) == 2
        matching = matching_files(MATCHING_SOURCE_DIR, suffix=".jp2")
        assert len(matching) == 1
        matching = matching_files(MATCHING_SOURCE_DIR, suffix=".tif")
        assert len(matching) == 1
        matching = matching_files(MATCHING_SOURCE_DIR, suffix=".pdf")
        assert len(matching) == 0
        matching = matching_files(MATCHING_SOURCE_DIR, prepend=True)
        path = str(matching[0])
        assert path.startswith(str(MATCHING_SOURCE_DIR))
        shutil.rmtree(MATCHING_SOURCE_DIR)


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
        """Creates a temp directory and adds an uncompressed bag fixture to the temp directory and database"""
        path = Path(settings.TMP_DIR)
        if not path.exists():
            path.mkdir(parents=True)
        bag = "3aai9usY3AZzCSFkB3RSQ9"
        fixture_directory = "aws_upload_bag"
        bag_path = Path(settings.TMP_DIR, bag)
        if not Path(bag_path).exists():
            shutil.copytree(Path("create_derivatives", "fixtures", fixture_directory, bag), bag_path)
            Bag.objects.create(
                bag_identifier="sdfjldskj",
                bag_path=bag_path,
                origin="digitization",
                as_data="sdjfkldsjf",
                dimes_identifier=bag,
                process_status=Bag.MANIFESTS_CREATED)

    @patch("create_derivatives.clients.AWSClient.__init__")
    @patch("create_derivatives.clients.AWSClient.upload_files")
    def test_run(self, mock_upload_files, mock_init):
        """Asserts that the run method produces the desired results message.

        Tests that the method updates the bag's process_status at the end.
        """
        mock_init.return_value = None
        routine = AWSUpload()
        msg, object_list = routine.run(True)
        self.assertEqual(msg, "Bags successfully uploaded")
        self.assertTrue(isinstance(object_list, list))
        self.assertEqual(len(object_list), 1)
        for bag in Bag.objects.all().filter(bag_identifier="sdfjldskj"):
            self.assertEqual(bag.process_status, Bag.UPLOADED)
        self.assertEqual(mock_upload_files.call_count, 3)

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)
