import json
import subprocess
from pathlib import Path
from shutil import rmtree

import bagit
import shortuuid
from asterism.file_helpers import anon_extract_all
from iiif_prezi.factory import ManifestFactory
from iiif_prezi_upgrader import Upgrader
from pictor import settings
from PIL import Image

from .clients import ArchivesSpaceClient, AWSClient
from .helpers import check_dir_exists, matching_files
from .models import Bag


class BagPreparer:
    """Prepares bags for derivative creation.

    Unpacks bags into settings.TMP_DIR and adds all necessary data the object.

    Returns:
        A tuple containing human-readable message along with list of bag identifiers.
        Exceptions are raised for errors along the way.

    """

    def __init__(self):
        self.as_client = ArchivesSpaceClient(*settings.ARCHIVESSPACE)
        check_dir_exists(settings.SRC_DIR)
        check_dir_exists(settings.TMP_DIR)

    def run(self):
        processed_bags = []
        for bag in Bag.objects.filter(process_status=Bag.CREATED):
            # TODO: presumes bag.bag_identifier and bag.origin are already set
            # TODO: we should also be sure that Ursa Major is delivering to two directories, or we will run into conflicts with Fornax
            if bag.origin != "digitization":
                raise Exception("Bags from origin {} cannot be processed".format(bag.origin), bag.bag_identifier)
            unpacked_path = self.unpack_bag(bag.bag_identifier)
            as_uri = self.get_as_uri(unpacked_path)
            bag.bag_path = unpacked_path
            bag.as_data = self.as_client.get_object(as_uri)
            bag.dimes_identifier = shortuuid.uuid(as_uri)
            bag.process_status = Bag.PREPARED
            bag.save()
            processed_bags.append(bag.bag_identifier)
        return "Bags successfully prepared", processed_bags

    def unpack_bag(self, bag_identifier):
        """Extracts a serialized bag to the tmp directory."""
        if anon_extract_all(
                "{}.tar.gz".format(Path(settings.SRC_DIR, bag_identifier)), settings.TMP_DIR):
            return str(Path(settings.TMP_DIR, bag_identifier))
        else:
            raise Exception("Unable to extract bag", bag_identifier)

    def get_as_uri(self, bag_filepath):
        """Gets the ArchivesSpace RefID from bag-info.txt."""
        bag = bagit.Bag(bag_filepath)
        try:
            return bag.info["ArchivesSpace-URI"]
        except KeyError as e:
            raise Exception(
                "ArchivesSpace URI not found in bag-info.txt file",
                bag_filepath) from e


class JP2Maker:
    # TO DO: make JPG2000 derivatives
    def run(self):
        pass


class PDFMaker:
    """Creates concatenated PDF file from JP2 derivatives.

    Creates PDF directory in bag's data directory, creates PDF, then compresses and OCRs the PDF

    Returns:
        A tuple containing human-readable message along with list of bag identifiers.
        Exceptions are raised for errors along the way.

    """

    def run(self):
        bags_with_pdfs = []
        for bag in Bag.objects.filter(process_status=Bag.JPG2000):
            jp2_files_dir = str(Path(bag.bag_path, "data", "JP2"))
            self.pdf_path = self.create_pdf(bag, jp2_files_dir)
            self.compress_pdf(bag)
            self.ocr_pdf()
            bag.process_status = Bag.PDF
            bag.save()
            bags_with_pdfs.append(bag.bag_identifier)
        msg = "PDFs created." if len(bags_with_pdfs) else "No JPG2000 files ready for PDF creation."
        return msg, bags_with_pdfs

    def create_pdf(self, bag, jp2_files_dir):
        """Creates concatenated PDF from JPEG2000 files."""
        jp2_files = matching_files(jp2_files_dir, prepend=True)
        pdf_dir = Path(bag.bag_path, "data", "PDF")
        if not pdf_dir.is_dir():
            pdf_dir.mkdir()
        pdf_path = "{}.pdf".format(Path(pdf_dir, bag.dimes_identifier))
        subprocess.run(["/usr/local/bin/img2pdf"] + jp2_files + ["-o", pdf_path])
        return pdf_path

    def compress_pdf(self, bag):
        """Compress PDF via Ghostscript command line interface.

        Original PDF is replaced with compressed PDF.
        """
        output_pdf_path = "{}_compressed.pdf".format(
            Path(bag.bag_path, "data", "PDF", bag.dimes_identifier))
        subprocess.run(['gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4', '-dPDFSETTINGS={}'.format('/screen'),
                        '-dNOPAUSE', '-dQUIET', '-dBATCH', '-sOutputFile={}'.format(output_pdf_path), self.pdf_path], stderr=subprocess.PIPE)
        Path(self.pdf_path).unlink()
        Path(output_pdf_path).rename(self.pdf_path)

    def ocr_pdf(self):
        """Add OCR layer using ocrmypdf."""
        subprocess.run(["ocrmypdf",
                        self.pdf_path,
                        self.pdf_path,
                        "--output-type",
                        "pdf",
                        "--optimize",
                        "0",
                        "--quiet"])


class ManifestMaker:
    """Creates a IIIF presentation manifest version 3 from JP2 files.

    Creates manifest directory in bag's data directory and then creates manifest.

    Returns:
        A tuple containing human-readable message along with list of bag identifiers.
        Exceptions are raised for errors along the way.
    """

    def __init__(self):
        server_url = settings.IMAGESERVER_URL
        self.resource_url = "{}/iiif/3/".format(server_url)
        self.fac = ManifestFactory()
        self.fac.set_base_prezi_uri("{}/manifests/".format(server_url))
        self.fac.set_base_image_uri(self.resource_url)
        self.fac.set_debug(settings.PREZI_DEBUG)
        self.upgrader = Upgrader()
        self.manifest_dir = None
        self.jp2_path = None
        self.jp2_files = None

    def run(self):
        bags_with_manifests = []
        for bag in Bag.objects.filter(process_status=Bag.PDF):
            self.bag = bag
            self.jp2_path = Path(bag.bag_path, "data", "JP2")
            self.jp2_files = sorted([f for f in matching_files(self.jp2_path)])
            self.manifest_dir = Path(bag.bag_path, "data", "MANIFEST")
            if not self.manifest_dir.is_dir():
                self.manifest_dir.mkdir()
            self.fac.set_base_prezi_dir(str(self.manifest_dir))
            self.create_manifest(bag.dimes_identifier, bag.as_data)
            bag.process_status = Bag.MANIFESTS_CREATED
            bag.save()
            bags_with_manifests.append(bag.dimes_identifier)
        msg = "Manifests successfully created." if len(bags_with_manifests) else "No manifests created."
        return msg, bags_with_manifests

    def create_manifest(self, identifier, obj_data):
        """Method that runs the other methods to build a manifest file and populate
        it with information.

        Args:
            identifier (str): A unique identifier.
            obj_data (dict): Data about the archival object.
        """
        manifest_path = Path(self.manifest_dir, "{}.json".format(identifier))
        page_number = 1
        manifest = self.fac.manifest(ident="{}{}".format(self.fac.prezi_base, identifier), label=obj_data["title"])
        manifest.set_metadata({"Date": obj_data["dates"]})
        manifest.thumbnail = self.set_thumbnail(self.jp2_files[0].stem)
        sequence = manifest.sequence(ident=identifier)
        for file in self.jp2_files:
            filename = file.stem
            width, height = self.get_image_info(file)
            """Set the canvas ID, which starts the same as the manifest ID,
            and then include page_number as the canvas ID.
            """
            canvas = sequence.canvas(
                ident="{}/canvas/{}".format(
                    manifest.id, str(page_number).zfill(3)),
                label="Page {}".format(
                    str(page_number)))
            canvas.set_hw(height, width)
            annotation = canvas.annotation(ident=filename)
            img = annotation.image(
                ident="/{}/full/max/0/default.jpg".format(filename))
            self.set_image_data(img, height, width, filename)
            canvas.thumbnail = self.set_thumbnail(filename)
            page_number += 1
        v2_json = manifest.toJSON(top=True)
        v3_json = self.upgrader.process_resource(v2_json, top=True)
        with open(manifest_path, 'w', encoding='utf-8') as jf:
            json.dump(v3_json, jf, ensure_ascii=False, indent=4)

    def get_image_info(self, file):
        """Gets information about the image file.

        Args:
            file (str): filename of the image file
        Returns:
            img.size (tuple): A tuple containing the width and height of an image.
        """
        with Image.open(Path(self.jp2_path, file)) as img:
            return img.size

    def set_image_data(self, img, height, width, ref):
        """Sets the image height and width. Creates the image object.

        Args:
            img (object): An iiif-prezi Image object.
            height (int): Pixel height of the image.
            width (int): Pixel width of the image.
            ref (string): Reference identifier for the file, including page in filename.
        Returns:
            img (object): A iiif_prezi image object with data.
        """
        img.height = height
        img.width = width
        img.format = "image/jpeg"
        img.service = self.set_service(ref)
        return img

    def set_thumbnail(self, identifier):
        """Creates a IIIF-compatible thumbnail.

        Args:
            identifier (str): A string identifier to use as the thumbnail id.
        Returns:
            thumbnail (object): An iiif_prezi Image object.
        """
        thumbnail_height = 200
        thumbnail_width = 200
        thumbnail = self.fac.image(
            ident="/{}/square/{},/0/default.jpg".format(identifier, thumbnail_width))
        self.set_image_data(
            thumbnail,
            thumbnail_height,
            thumbnail_width,
            identifier)
        return thumbnail

    def set_service(self, identifier):
        return self.fac.service(
            ident="{}{}".format(self.resource_url, identifier),
            context="http://iiif.io/api/image/3/context.json",
            profile="http://iiif.io/api/image/3/level2.json")


class AWSUpload:

    def __init__(self):
        self.aws_client = AWSClient(*settings.AWS)

    def run(self, replace):
        uploaded_bags = []
        for bag in Bag.objects.filter(process_status=Bag.MANIFESTS_CREATED):
            pdf_dir = Path(bag.bag_path, "data", "PDF")
            jp2_dir = Path(bag.bag_path, "data", "JP2")
            manifest_dir = Path(bag.bag_path, "data", "MANIFEST")
            for src_dir, target_dir in [
                    (pdf_dir, "pdfs"),
                    (jp2_dir, "images"),
                    (manifest_dir, "manifests")]:
                uploads = matching_files(
                    str(src_dir), prefix=bag.dimes_identifier, prepend=True)
                self.aws_client.upload_files(uploads, target_dir, replace)
            bag.process_status = Bag.UPLOADED
            bag.save()
            uploaded_bags.append(bag.dimes_identifier)
        return "Bags successfully uploaded", uploaded_bags


class Cleanup:
    """Removes bag files that have been processed.

    Returns:
        A tuple containing human-readable message along with list of bag identifiers.

    """

    def run(self):
        cleaned_up = []
        for bag in Bag.objects.filter(process_status=Bag.UPLOADED):
            rmtree(bag.bag_path)
            bag.process_status = Bag.CLEANED_UP
            bag.save()
            cleaned_up.append(bag.bag_identifier)
        msg = "Bags successfully cleaned up." if len(cleaned_up) else "No bags ready for cleanup."
        return msg, cleaned_up
