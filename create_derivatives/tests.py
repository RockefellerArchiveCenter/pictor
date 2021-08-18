import shutil
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from pictor import settings
from rest_framework.test import APIRequestFactory

from .models import Bag
from .routines import (AWSUpload, BagPreparer, Cleanup, JP2Maker,
                       ManifestMaker, PDFMaker)
from .test_helpers import make_dir, set_up_bag


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


class BagPreparerTestCase(TestCase):
    fixtures = ["created.json"]

    def setUp(self):
        for p in [settings.SRC_DIR, settings.TMP_DIR]:
            make_dir(p)
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

        Tests that the correct number of bags was processed, and that the
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


class JP2MakerTestCase(TestCase):
    fixtures = ["jpg2000.json"]

    def setUp(self):
        make_dir(settings.TMP_DIR)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ9"
        set_up_bag(settings.TMP_DIR, "unpacked_bag_with_tiff", self.bag_id)

    def test_run(self):
        """Asserts that the run method produced a JP2000 file in the JP2 directory.

        Tests that the method updates the bag's process_status and produces the
        desired results message.
        """
        msg, jp2s = JP2Maker().run()
        bag_path = Path(settings.TMP_DIR, self.bag_id)
        bag = Bag.objects.get(bag_path=bag_path)
        self.assertEqual(bag.process_status, Bag.JPG2000)
        self.assertEqual(msg, "JPG2000s created.")

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)


class PDFMakerTestCase(TestCase):
    fixtures = ["pdf.json"]

    def setUp(self):
        make_dir(settings.TMP_DIR, remove_first=True)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ9"
        set_up_bag(settings.TMP_DIR, "unpacked_bag_with_jp2", self.bag_id)

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
        """Sets paths for fixture directories and copies files over if needed."""
        make_dir(settings.TMP_DIR)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ8"
        set_up_bag(settings.TMP_DIR, "manifest_generation_bag", self.bag_id)

    def test_run(self):
        for bag in Bag.objects.all().filter(process_status=3):
            manifest_dir = Path(bag.bag_path, "data", "MANIFEST")
            routine = ManifestMaker()
            msg, object_list = routine.run()
            bag.refresh_from_db()
            manifests = [str(f) for f in Path(manifest_dir).iterdir()]
            self.assertEqual(len(manifests), 1)
            self.assertTrue(Path(manifest_dir, "{}.json".format("asdfjklmn")).is_file())
            self.assertEqual(msg, "Manifests successfully created.")
            self.assertTrue(isinstance(object_list, list))
            self.assertEqual(len(object_list), 1)
            self.assertEqual(bag.process_status, bag.MANIFESTS_CREATED)

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
        for bag in Bag.objects.all().filter(dimes_identifier="sdfjldskj"):
            self.assertEqual(bag.process_status, Bag.UPLOADED)
        self.assertEqual(mock_upload_files.call_count, 3)


class CleanupTestCase(TestCase):
    fixtures = ["cleanup.json"]

    def setUp(self):
        make_dir(settings.TMP_DIR, remove_first=True)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ9"
        set_up_bag(settings.TMP_DIR, "aws_upload_bag", self.bag_id)

    def test_run(self):
        msg, object_list = Cleanup().run()
        self.assertEqual(len(list(Path(settings.TMP_DIR).glob("*"))), 0)
        self.assertEqual(msg, "Bags successfully cleaned up.")
        self.assertTrue(isinstance(object_list, list))
        self.assertEqual(len(object_list), 1)

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)
