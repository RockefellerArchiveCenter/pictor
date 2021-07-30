import shutil
from os.path import join
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from pictor import settings

from .helpers import check_dir_exists
from .models import Bag
from .routines import BagPreparer, PDFMaker


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

    def set_up_bag(self, fixture_directory, bag):
        bag_path = join(settings.TMP_DIR, bag)
        if not Path(bag_path).exists():
            shutil.copytree(join("create_derivatives", "fixtures", fixture_directory, bag), bag_path)
            Bag.objects.create(
                bag_identifier="sdfjldskj",
                bag_path=bag_path,
                origin="digitization",
                as_data="sdjfkldsjf",
                dimes_identifier=bag,
                process_status=Bag.JPG2000)

    # def test_create_pdf(self):
    #     bag = Bag.objects.all()[0]
    #     create_pdf = PDFMaker().create_pdf(bag, jp2_files_dir)

    def test_compress_pdf(self):
        bag_id = "75ddpuBHgPf2TmZRhZ2bKR"
        self.set_up_bag("unpacked_bag_with_pdf", bag_id)
        bag = Bag.objects.get(dimes_identifier=bag_id)
        compress_pdf = PDFMaker().compress_pdf(bag)
        self.assertTrue(compress_pdf)

    # def test_ocr_pdf(self):
    #     """docstring for test_ocr_pdf"""
    # pass

    # def test_run(self):
    #     make_pdf = PDFMaker().run()
    #     self.assertTrue(make_pdf)

    def tearDown(self):
        shutil.rmtree(settings.TMP_DIR)
