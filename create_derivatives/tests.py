import shutil
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from pictor import settings
from rest_framework.test import APIRequestFactory

from .helpers import check_dir_exists, matching_files
from .models import Bag
from .routines import (AWSUpload, BagPreparer, CleanupRoutine, ManifestMaker,
                       PDFMaker)
from .test_helpers import copy_sample_files, random_string


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
        return response

    def test_bagviewset(self):
        """Asserts BagViewSet views return expected responses."""
        self.assert_status_code("get", reverse("bag-list"), 200)
        for bag in Bag.objects.all():
            self.assert_status_code("get", reverse("bag-detail", kwargs={"pk": bag.pk}), 200)
        data = {
            "bag_data": {"uri": "foo"},
            "origin": "digitization",
            "identifier": "foo"}
        self.assert_status_code("post", reverse("bag-list"), 201, data=data, content_type="application/json")

    @patch("create_derivatives.routines.BagPreparer.__init__")
    @patch("create_derivatives.routines.BagPreparer.run")
    @patch("create_derivatives.routines.JP2Maker.run")
    @patch("create_derivatives.routines.PDFMaker.run")
    @patch("create_derivatives.routines.ManifestMaker.run")
    @patch("create_derivatives.routines.AWSUpload.run")
    @patch("create_derivatives.routines.Cleanup.run")
    def test_routine_views(self, mock_cleanup, mock_upload, mock_manifest, mock_pdf, mock_jp2, mock_prepare, mock_prepare_init):
        """Asserts routine views return expected status codes and data."""
        mock_prepare_init.return_value = None
        exception_text = "foobar"
        exception_id = "1"
        view_matrix = [
            ("bag-preparer", mock_prepare),
            ("jp2-maker", mock_jp2),
            ("pdf-maker", mock_pdf),
            ("manifest-maker", mock_manifest),
            ("aws-upload", mock_upload),
            ("cleanup", mock_cleanup)]
        for view, routine in view_matrix:
            self.assert_status_code("post", reverse(view), 200)
            routine.side_effect = Exception(exception_text, exception_id)
            error_response = self.assert_status_code("post", reverse(view), 500)
            self.assertEqual(
                error_response.json(),
                {'detail': exception_text, 'objects': [exception_id], 'count': 1},
                "Unexpected error response")


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


class PDFMakerTestCase(TestCase):

    def setUp(self):
        tmp_path = Path(settings.TMP_DIR)
        if not tmp_path.exists():
            tmp_path.mkdir(parents=True)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ9"
        self.set_up_bag("unpacked_bag_with_jp2", self.bag_id)

    def set_up_bag(self, fixture_directory, bag):
        """Adds an uncompressed bag fixture to the temp directory and database"""
        bag_path = str(Path(settings.TMP_DIR, bag))
        if not Path(bag_path).exists():
            shutil.copytree(Path("create_derivatives", "fixtures", fixture_directory, bag), bag_path)
            Bag.objects.create(
                bag_identifier="sdfjldskj",
                bag_path=bag_path,
                origin="digitization",
                as_data="sdjfkldsjf",
                dimes_identifier=bag,
                process_status=Bag.JPG2000)

    def test_run(self):
        pdfs = PDFMaker().run()
        bag_path = Path(settings.TMP_DIR, self.bag_id)
        bag = Bag.objects.get(bag_path=bag_path)
        self.assertTrue(Path(bag_path, "data", "PDF", "{}.pdf".format(self.bag_id)).is_file())
        self.assertEqual(len(list(Path(bag_path, "data", "PDF").glob("*"))), 1)
        self.assertEqual(bag.process_status, Bag.PDF)
        self.assertEqual(pdfs[0], "PDFs created.")

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)


class ManifestMakerTestCase(TestCase):
    fixtures = ["manifests.json"]

    def setUp(self):
        tmp_path = Path(settings.TMP_DIR)
        if not tmp_path.exists():
            tmp_path.mkdir(parents=True)
        self.bag_path = Path(settings.TMP_DIR, "3aai9usY3AZzCSFkB3RSQ8")
        self.derivative_dir = Path(settings.TMP_DIR, "JP2")
        self.manifest_dir = Path(settings.TMP_DIR, "MANIFEST")
        if not self.bag_path.exists():
            shutil.copytree(Path("create_derivatives", "fixtures", "manifest_generation_bag", "3aai9usY3AZzCSFkB3RSQ8"), self.bag_path)
        for p in [self.derivative_dir, self.manifest_dir]:
            if not p.exists():
                p.mkdir(parents=True)
        for f in Path("create_derivatives", "fixtures", "jp2").iterdir():
            shutil.copy(f, self.derivative_dir)

    def test_run(self):
        routine = ManifestMaker()
        for bag in Bag.objects.filter(process_status=Bag.PDF):
            msg, object_list = routine.run()
            self.assertEqual(msg, "Manifests successfully created.")
            self.assertTrue(isinstance(object_list, list))
            self.assertEqual(len(object_list), 1)
            for bag in Bag.objects.all().filter(bag_identifier="asdfjklmn"):
                self.assertEqual(bag.process_status, Bag.MANIFESTS_CREATED)

    def test_create_manifest(self):
        """Ensures a correctly-named manifest is created."""
        uuid = random_string(9)
        copy_sample_files(self.derivative_dir, uuid, 2, "jp2")
        ManifestMaker().create_manifest(
            matching_files(str(self.derivative_dir), prefix=uuid), self.manifest_dir,
            self.derivative_dir, uuid,
            {"title": random_string(), "dates": random_string()})
        manifests = [str(f) for f in Path(self.manifest_dir).iterdir()]
        assert len(manifests) == 1
        assert Path(self.manifest_dir, "{}.json".format(uuid)).is_file()

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)
        

class AWSUploadTestCase(TestCase):
    fixtures = ["uploaded.json"]

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


class CleanupTestCase(TestCase):
    def setUp(self):
        tmp_path = Path(settings.TMP_DIR)
        if tmp_path.exists():
            shutil.rmtree(settings.TMP_DIR)
        tmp_path.mkdir(parents=True)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ9"
        self.set_up_bag("aws_upload_bag", self.bag_id)

    def set_up_bag(self, fixture_directory, bag):
        """Adds an uncompressed bag fixture to the temp directory and database"""
        bag_path = str(Path(settings.TMP_DIR, bag))
        if not Path(bag_path).exists():
            shutil.copytree(Path("create_derivatives", "fixtures", fixture_directory, bag), bag_path)
            Bag.objects.create(
                bag_identifier="sdfjldskj",
                bag_path=bag_path,
                origin="digitization",
                as_data="sdjfkldsjf",
                dimes_identifier=bag,
                process_status=Bag.UPLOADED)

    def test_run(self):
        msg, object_list = Cleanup().run()
        self.assertEqual(len(list(Path(settings.TMP_DIR).glob("*"))), 0)
        self.assertEqual(msg, "Bags successfully cleaned up.")
        self.assertTrue(isinstance(object_list, list))
        self.assertEqual(len(object_list), 1)

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)
