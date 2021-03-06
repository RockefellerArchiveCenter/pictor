import shutil
from pathlib import Path
from unittest.mock import patch

import vcr
from botocore.stub import Stubber
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from pictor import settings

from .clients import ArchivesSpaceClient, AWSClient
from .helpers import matching_files
from .models import Bag
from .routines import (AWSUpload, BagPreparer, BaseRoutine, Cleanup, JP2Maker,
                       ManifestMaker, PDFCompressor, PDFMaker, PDFOCRer,
                       TIFFPreparer)
from .test_helpers import make_dir, set_up_bag


class HelpersTestCase(TestCase):

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
            "Expected status code {} for URL {} but got {}".format(expected_status, url, response.status_code))
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
    @patch("create_derivatives.routines.TIFFPreparer.run")
    @patch("create_derivatives.routines.PDFCompressor.run")
    @patch("create_derivatives.routines.PDFOCRer.run")
    def test_routine_views(self, mock_ocr_pdf, mock_compress_pdf, mock_prepare_tiff, mock_cleanup, mock_upload, mock_manifest, mock_pdf, mock_jp2, mock_prepare, mock_prepare_init):
        """Asserts routine views return expected status codes and data."""
        mock_prepare_init.return_value = None
        exception_text = "foobar"
        exception_id = "1"
        view_matrix = [
            ("bag-preparer", mock_prepare),
            ("tiff-preparer", mock_prepare_tiff),
            ("jp2-maker", mock_jp2),
            ("pdf-maker", mock_pdf),
            ("pdf-compressor", mock_compress_pdf),
            ("pdf-ocrer", mock_ocr_pdf),
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

    def test_health_check_view(self):
        status = self.client.get(reverse('ping'))
        self.assertEqual(status.status_code, 200, "Wrong HTTP code")


class BaseRoutineTestCase(TestCase):
    fixtures = ["created.json"]

    @patch("create_derivatives.routines.BaseRoutine.process_bag")
    def test_run(self, mock_process_bag):
        base_routine = BaseRoutine()
        base_routine.start_process_status = Bag.CREATED
        base_routine.in_process_status = Bag.PREPARING
        base_routine.end_process_status = Bag.PREPARED
        base_routine.success_message = "Bags successfully prepared."
        base_routine.idle_message = "No bags to prepare."
        created_len = len(Bag.objects.filter(process_status=Bag.CREATED))
        count = 1
        while count <= created_len:
            processed = base_routine.run()
            self.assertTrue(isinstance(processed, tuple))
            self.assertEqual(len(processed[1]), 1, "Wrong number of bags processed")
            self.assertEqual(processed[0], "Bags successfully prepared.")
            count += 1
        msg, processed = base_routine.run()
        self.assertEqual(msg, "No bags to prepare.")


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
        count = 1
        while count <= created_len:
            prepared = BagPreparer().run()
            self.assertEqual(prepared[0], "Bags successfully prepared.")
            self.assertTrue(len(list(Path(settings.TMP_DIR).glob("*"))), count)
            count += 1
        for bag in Bag.objects.all():
            self.assertEqual(bag.process_status, Bag.PREPARED)
            self.assertEqual(bag.bag_path, str(Path(settings.TMP_DIR, bag.bag_identifier)))
            self.assertEqual(bag.as_data, as_data)
            self.assertIsNot(bag.dimes_identifier, None)

    def tearDown(self):
        for f in Path(settings.SRC_DIR).iterdir():
            f.unlink()


class TIFFPreparerTestCase(TestCase):
    fixtures = ["prepared.json"]

    def setUp(self):
        make_dir(settings.TMP_DIR)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ9"

    def test_run(self):
        """Asserts that the run method produced a TIFF file.

        Tests that the method updates the bag's process_status and produces the
        desired results message.
        """
        set_up_bag(settings.TMP_DIR, "unpacked_bag_with_tiff", self.bag_id)
        msg, tiffs = TIFFPreparer().run()
        bag = Bag.objects.last()
        self.assertEqual(bag.process_status, Bag.TIFF_PREPARED)
        self.assertEqual(msg, "TIFFs prepared.")

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)


class JP2MakerTestCase(TestCase):
    fixtures = ["tiffs_prepared.json"]

    def setUp(self):
        make_dir(settings.TMP_DIR)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ9"

    def test_run(self):
        """Asserts that the run method produced a JP2000 file in the JP2 directory.

        Tests that the method updates the bag's process_status and produces the
        desired results message.
        """
        set_up_bag(settings.TMP_DIR, "unpacked_bag_with_tiff", self.bag_id)
        msg, jp2s = JP2Maker().run()
        bag = Bag.objects.last()
        self.assertEqual(bag.process_status, Bag.PDF_OCR)  # temporary change to skip PDF creation
        self.assertEqual(msg, "JPG2000s created.")

    def test_tiff_file_paths(self):
        """Asserts that TIFF filepaths are properly produced.

        Files in a service directory should be returned if present, otherwise
        TIFFs in the data directory should be returned.
        """
        for fixture_path, expected in [
                ("unpacked_bag_with_tiff", False),
                ("unpacked_bag_with_tiff_empty_service", False),
                ("unpacked_bag_with_tiff_service", True)]:
            set_up_bag(settings.TMP_DIR, fixture_path, self.bag_id)
            bag = Bag.objects.last()
            tiffs = JP2Maker().get_tiff_file_paths(bag.bag_path)
            for path in tiffs:
                self.assertTrue("data" in str(path))
                self.assertEqual("service" in str(path), expected)
            shutil.rmtree(bag.bag_path)

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
        bag = Bag.objects.last()
        self.assertTrue(Path(bag.pdf_path).is_file())
        self.assertEqual(len(list(Path(bag_path, "data", "PDF").glob("*"))), 1)
        self.assertEqual(bag.process_status, Bag.PDF)
        self.assertEqual(pdfs[0], "PDF created.")

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)


class PDFCompressorTestCase(TestCase):
    fixtures = ["pdf_created.json"]

    def setUp(self):
        make_dir(settings.TMP_DIR, remove_first=True)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ9"
        set_up_bag(settings.TMP_DIR, "unpacked_bag_with_pdf", self.bag_id)

    def test_run(self):
        msg, _ = PDFCompressor().run()
        bag_path = Path(settings.TMP_DIR, self.bag_id)
        bag = Bag.objects.last()
        self.assertTrue(Path(bag.pdf_path).is_file())
        self.assertEqual(len(list(Path(bag_path, "data", "PDF").glob("*"))), 1)
        self.assertEqual(bag.process_status, Bag.PDF_COMPRESS)
        self.assertEqual(msg, "PDF compressed.")

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)


class PDFOCRerTestCase(TestCase):
    fixtures = ["pdf_compressed.json"]

    def setUp(self):
        make_dir(settings.TMP_DIR, remove_first=True)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ9"
        set_up_bag(settings.TMP_DIR, "unpacked_bag_with_pdf", self.bag_id)

    def test_run(self):
        msg, _ = PDFOCRer().run()
        bag_path = Path(settings.TMP_DIR, self.bag_id)
        bag = Bag.objects.last()
        self.assertTrue(Path(bag.pdf_path).is_file())
        self.assertEqual(len(list(Path(bag_path, "data", "PDF").glob("*"))), 1)
        self.assertEqual(bag.process_status, Bag.PDF_OCR)
        self.assertEqual(msg, "PDF OCRed.")

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
        msg, object_list = routine.run()
        self.assertEqual(msg, "Files successfully uploaded.")
        self.assertTrue(isinstance(object_list, list))
        self.assertEqual(len(object_list), 1)
        for bag in Bag.objects.all().filter(dimes_identifier="sdfjldskj"):
            self.assertEqual(bag.process_status, Bag.UPLOADED)
        self.assertEqual(mock_upload_files.call_count, 2)


class CleanupTestCase(TestCase):
    fixtures = ["cleanup.json"]

    def setUp(self):
        make_dir(settings.TMP_DIR, remove_first=True)
        self.bag_id = "3aai9usY3AZzCSFkB3RSQ9"
        set_up_bag(settings.TMP_DIR, "aws_upload_bag", self.bag_id)

    def test_run(self):
        msg, object_list = Cleanup().run()
        self.assertEqual(len(list(Path(settings.TMP_DIR).glob("*"))), 0)
        self.assertEqual(len(list(Path(settings.SRC_DIR).glob("*"))), 0)
        self.assertEqual(msg, "Source and temporary files successfully removed.")
        self.assertTrue(isinstance(object_list, list))
        self.assertEqual(len(object_list), 1)

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)


class ClientsTestCase(TestCase):

    archivesspace_vcr = vcr.VCR(
        serializer='json',
        cassette_library_dir='create_derivatives/fixtures/cassettes',
        record_mode='once',
        match_on=['path', 'method'],
        filter_query_parameters=['username', 'password'],
        filter_headers=['Authorization', 'X-ArchivesSpace-Session'],
    )

    def test_aspace(self):
        with self.archivesspace_vcr.use_cassette("get_ao.json"):
            object = ArchivesSpaceClient(*settings.ARCHIVESSPACE).get_object("repositories/101/archival_objects/2336")
            self.assertTrue(isinstance(object, dict))
            for key in ["title", "dates", "uri"]:
                self.assertTrue(key in object)

    @patch("boto3.s3.transfer.S3Transfer.upload_file")
    def test_upload_files(self, mock_upload):
        aws = AWSClient(*settings.AWS)
        with Stubber(aws.s3.meta.client):
            for filename, key, target_dir, mimetype in [
                    ("123456.json", "123456", "manifests", "application/json"),
                    ("123456.jp2", "123456", "images", "image/jp2"),
                    ("123456.pdf", "123456", "pdfs", "application/pdf")]:
                aws.upload_files([Path(filename)], target_dir)
                mock_upload.assert_called_with(
                    bucket=settings.AWS[3],
                    callback=None,
                    extra_args={"ContentType": mimetype},
                    filename=filename,
                    key="{}/{}".format(target_dir, key))
