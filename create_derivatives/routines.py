import json
import math
import subprocess
from pathlib import Path
from shutil import rmtree

import bagit
import shortuuid
from asterism.file_helpers import anon_extract_all
from iiif_prezi3 import (Annotation, AnnotationPage, Canvas, Manifest,
                         ResourceItem, ServiceItem1)
from pictor import settings
from PIL import Image

from .clients import ArchivesSpaceClient, AWSClient
from .helpers import check_dir_exists, get_page_number, matching_files
from .models import Bag


class BaseRoutine(object):
    """Base class which all routines inherit.

    Returns:
        msg (str): human-readable representation of the routine outcome

    Subclasses should implement a `process_bag` method which executes logic on
    one bag. They should also set the following attributes:
        start_process_status (int): a Bag process status which determines the starting
            queryset.
        in_process_status (int)L a Bag process status which indicates that a Bag is currently processing
        end_process_status (int): a Bag process status which will be applied to
            Bags after they have been successfully processed.
        success_message (str): a message indicating that the routine completed
            successfully.
        idle_message (str): a message indicating that there were no objects for
            the routine to act on.
    """

    def run(self):
        if not Bag.objects.filter(process_status=self.in_process_status).exists():
            bag = Bag.objects.filter(process_status=self.start_process_status).first()
            if bag:
                bag.process_status = self.in_process_status
                bag.save()
                try:
                    self.process_bag(bag)
                except Exception:
                    bag.process_status = self.start_process_status
                    bag.save()
                    raise
                bag.process_status = self.end_process_status
                bag.save()
                msg = self.success_message
            else:
                msg = self.idle_message
        else:
            msg = "Service currently running"
            bag = None
        return msg, [bag.bag_identifier] if bag else []

    def process_bag(self, bag):
        raise NotImplementedError("You must implement a `process_bag` method")

    def get_tiff_file_paths(self, bag_path):
        """Determines the location of TIFF files in the bag.

        Args:
            bag_path (str): root bag path.
        Returns:
            tiff_files (list of pathlib.Paths): absolute filepaths for TIFF files.
        """
        service_dir = Path(bag_path, "data", "service")
        if service_dir.is_dir() and any(service_dir.iterdir()):
            tiff_files_dir = Path(bag_path, "data", "service")
        else:
            tiff_files_dir = Path(bag_path, "data")
        return matching_files(tiff_files_dir, prepend=True)


class BagPreparer(BaseRoutine):
    """Prepares bags for derivative creation.

    Unpacks bags into settings.TMP_DIR and adds all necessary data to the object.

    Returns:
        A tuple containing human-readable message along with list of bag identifiers.
        Exceptions are raised for errors along the way.

    """
    start_process_status = Bag.CREATED
    in_process_status = Bag.PREPARING
    end_process_status = Bag.PREPARED
    success_message = "Bags successfully prepared."
    idle_message = "No bags to prepare."

    def __init__(self):
        self.as_client = ArchivesSpaceClient(*settings.ARCHIVESSPACE)
        check_dir_exists(settings.SRC_DIR)
        check_dir_exists(settings.TMP_DIR)

    def process_bag(self, bag):
        # TODO: presumes bag.bag_identifier and bag.origin are already set
        # TODO: we should also be sure that Ursa Major is delivering to two directories, or we will run into conflicts with Fornax
        if bag.origin != "digitization":
            raise Exception("Bags from origin {} cannot be processed".format(bag.origin), bag.bag_identifier)
        unpacked_path = self.unpack_bag(bag.bag_identifier)
        as_uri = self.get_as_uri(unpacked_path)
        bag.bag_path = unpacked_path
        bag.as_data = self.as_client.get_object(as_uri)
        bag.dimes_identifier = shortuuid.uuid(as_uri)

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


class TIFFPreparer(BaseRoutine):
    """Prepares TIFFs for JPEG2000 processing.

    Converts tiled TIFFs to stripped TIFFs.
    """
    start_process_status = Bag.PREPARED
    in_process_status = Bag.PREPARING_TIFF
    end_process_status = Bag.TIFF_PREPARED
    success_message = "TIFFs prepared."
    idle_message = "No TIFF files ready for preparation."

    def process_bag(self, bag):
        tiff_files = self.get_tiff_file_paths(bag.bag_path)
        self.convert_to_strips(tiff_files)

    def get_tiff_file_paths(self, bag_path):
        """Determines the location of TIFF files in the bag.

        Args:
            bag_path (str): root bag path.
        Returns:
            tiff_files (list of pathlib.Paths): absolute filepaths for TIFF files.
        """
        service_dir = Path(bag_path, "data", "service")
        if service_dir.is_dir() and any(service_dir.iterdir()):
            tiff_files_dir = Path(bag_path, "data", "service")
        else:
            tiff_files_dir = Path(bag_path, "data")
        return matching_files(tiff_files_dir, prepend=True)

    def convert_to_strips(self, tiff_files):
        """Converts tiled TIFFs to stripped TIFFs.

        Args:
            tiff_files (list): TIFF files to be converted
        """

        for tiff in tiff_files:
            tmp_tiff = tiff.parent / (tiff.name.replace(".tif", "__copy.tif"))
            cmd = ["tiffcp", "-s", tiff, tmp_tiff]
            subprocess.run(cmd, check=True)
            tmp_tiff.rename(tiff)


class JP2Maker(BaseRoutine):
    """Creates JP2000 derivatives from TIFFs.

    Creates JP2 directory in bag's data directory and JP2 derivatives.
    TIFFs to be converted are targeted in the service directory. If the service directory is empty or
    does not exist, target TIFFs at the root of the data directory.

    Returns:
        A tuple containing human-readable message along with list of bag identifiers.
        Exceptions are raised for errors along the way.
    """
    start_process_status = Bag.TIFF_PREPARED
    in_process_status = Bag.CREATING_JP2
    end_process_status = Bag.PDF_OCR  # temporary change to skip PDF creation
    success_message = "JPG2000s created."
    idle_message = "No TIFF files ready for JP2 creation."

    def process_bag(self, bag):
        jp2_dir = Path(bag.bag_path, "data", "JP2")
        if not jp2_dir.is_dir():
            jp2_dir.mkdir()
        tiff_files = self.get_tiff_file_paths(bag.bag_path)
        self.create_jp2s(bag, tiff_files, jp2_dir)

    def calculate_layers(self, file):
        """Calculates the number of layers based on pixel dimensions.
        For TIFF files, image tag 256 is the width, and 257 is the height.

        Args:
            file (str): filename of a TIFF image file.
        Returns:
            layers (int): number of layers to convert to
        """

        with Image.open(file) as img:
            width = [w for w in img.tag[256]][0]
            height = [h for h in img.tag[257]][0]
        return math.ceil((math.log(max(width, height)) / math.log(2)
                          ) - ((math.log(96) / math.log(2)))) + 1

    def create_jp2s(self, bag, tiff_files, jp2_dir):
        """Creates JPEG2000 files from TIFF files.

        The default options for conversion below are:
        - Compression ration of `1.5`
        - Precinct size: `[256,256]` for first two layers and then `[128,128]` for all others
        - Code block size of `[64,64]`
        - Progression order of `RPCL`

        Args:
            bag (object): Unpacked bag object.
            tiff_files (lst): A list of TIFF files.
            jp2_dir (object): The JPEG200 derivatives target directory.

        Returns:
            jp2_list: A tuple of JPG2000 paths including their page numbers
        """

        default_options = ["-r", "1.5",
                           "-c", "[256,256],[256,256],[128,128]",
                           "-b", "64,64",
                           "-p", "RPCL"]
        jp2_list = []
        for tiff_file in tiff_files:
            page_number = get_page_number(tiff_file)
            jp2_path = jp2_dir.joinpath("{}_{}.jp2".format(bag.dimes_identifier, page_number))
            layers = self.calculate_layers(tiff_file)
            cmd = [settings.OPJ_COMPRESS,
                   "-i", tiff_file,
                   "-o", jp2_path,
                   "-n", str(layers),
                   "-SOP"] + default_options
            subprocess.run(cmd, check=True)
            jp2_list.append(jp2_path)
        return jp2_list


class PDFMaker(BaseRoutine):
    """Creates concatenated PDF file from JP2 derivatives."""
    start_process_status = Bag.JPG2000
    in_process_status = Bag.CREATING_PDF
    end_process_status = Bag.PDF
    success_message = "PDF created."
    idle_message = "No JPG2000 files ready for PDF creation."

    def process_bag(self, bag):
        jp2_files_dir = Path(bag.bag_path, "data", "JP2")
        jp2_files = matching_files(jp2_files_dir, prepend=True)
        pdf_dir = Path(bag.bag_path, "data", "PDF")
        if not pdf_dir.is_dir():
            pdf_dir.mkdir()
        pdf_path = "{}.pdf".format(Path(pdf_dir, bag.dimes_identifier))
        subprocess.run([settings.IMG2PDF] + jp2_files + ["-o", pdf_path], check=True)
        bag.pdf_path = pdf_path


class PDFCompressor(BaseRoutine):
    """Compresses PDF"""
    start_process_status = Bag.PDF
    in_process_status = Bag.COMPRESSING_PDF
    end_process_status = Bag.PDF_COMPRESS
    success_message = "PDF compressed."
    idle_message = "No PDFs waiting for compression."

    def process_bag(self, bag):
        """Compress PDF via Ghostscript command line interface.

        Original PDF is replaced with compressed PDF.
        """
        output_pdf_path = "{}_compressed.pdf".format(
            Path(bag.bag_path, "data", "PDF", bag.dimes_identifier))
        subprocess.run(['gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4', '-dPDFSETTINGS={}'.format('/screen'),
                        '-dNOPAUSE', '-dQUIET', '-dBATCH', '-sOutputFile={}'.format(output_pdf_path), bag.pdf_path],
                       stderr=subprocess.PIPE, check=True)
        Path(output_pdf_path).rename(bag.pdf_path)


class PDFOCRer(BaseRoutine):
    """OCRs a PDF."""
    start_process_status = Bag.PDF_COMPRESS
    in_process_status = Bag.OCRING_PDF
    end_process_status = Bag.PDF_OCR
    success_message = "PDF OCRed."
    idle_message = "No PDFs waiting for OCR processing."

    def process_bag(self, bag):
        """Add OCR layer using ocrmypdf."""
        subprocess.run([
            settings.OCRMYPDF,
            bag.pdf_path,
            bag.pdf_path,
            "--output-type", "pdf",
            "--optimize", "0", "--quiet"], check=True)


class ManifestMaker(BaseRoutine):
    """Creates a IIIF presentation manifest from JP2 files.

    Creates manifest directory in bag's data directory and then creates manifest.

    Returns:
        A tuple containing human-readable message along with list of bag identifiers.
        Exceptions are raised for errors along the way.
    """
    success_message = "Manifests successfully created."
    idle_message = "No manifests created."

    def __init__(self):
        server_url = settings.IMAGESERVER_URL
        self.image_api_version = settings.IIIF_API['image_api']
        self.presentation_api_version = settings.IIIF_API['presentation_api']
        if self.image_api_version not in [2, 3]:
            raise Exception("Version {} of IIIF Image API not supported.".format(self.image_api_version))
        elif self.presentation_api_version not in [2, 3]:
            raise Exception("Version {} of IIIF Presentation API not supported.".format(self.presentation_api_version))
        self.resource_url = "{}/iiif/{}/".format(server_url, self.image_api_version)
        self.manifest_url = "{}/manifests/".format(settings.MANIFESTS_URL)

    def process_bag(self, bag):
        self.jp2_path = Path(bag.bag_path, "data", "JP2")
        self.jp2_files = sorted([f for f in matching_files(self.jp2_path)])
        self.manifest_dir = Path(bag.bag_path, "data", "MANIFEST")
        if not self.manifest_dir.is_dir():
            self.manifest_dir.mkdir()
        self.create_manifest(bag.dimes_identifier, bag.as_data)

    def create_manifest(self, identifier, obj_data):
        """Method that runs the other methods to build a manifest file and populate
        it with information.

        Args:
            identifier (str): A unique identifier.
            obj_data (dict): Data about the archival object.
        """
        manifest_path = Path(self.manifest_dir, "{}.json".format(identifier))
        manifest = Manifest(id="{}{}.json".format(self.manifest_url, identifier),
                            type="Manifest",
                            label={"en": [obj_data["title"]]},
                            context="https://iiif.io/api/image/{}/context.json".format(self.image_api_version),
                            thumbnail=[self.set_thumbnail(self.jp2_files[0].stem)])
        items = []
        for jp2_file in self.jp2_files:
            page_number = get_page_number(jp2_file).lstrip("0")
            jp2_filename = jp2_file.stem
            width, height = self.get_image_info(jp2_file)
            """Creates a canvas, annotation pages, a list of annotations on those pages,
            and bodies with targets for those annotations.
            """
            canvas = Canvas(id="{}canvas/{}.json".format(self.manifest_url, jp2_filename),
                            type="Canvas",
                            label={"none": "Page {}".format(page_number)},
                            height=height,
                            width=width,
                            thumbnail=[self.set_thumbnail(jp2_filename)])
            annotation_page = AnnotationPage(id="{}{}/page/p{}.json".format(self.manifest_url, jp2_filename, page_number),
                                             type="AnnotationPage")
            annotation_page_items = Annotation(type="Annotation",
                                               id="{}annotation/{}.json".format(self.manifest_url, jp2_filename),
                                               motivation="painting",
                                               target=[canvas.id.__root__])
            annotation_body = ResourceItem(id="{}{}/full/max/0/default.jpg".format(self.resource_url, jp2_filename),
                                           type="Image",
                                           height=height,
                                           width=width,
                                           service=[self.set_service(jp2_filename)])
            annotation_page_items.body = annotation_body
            annotation_page.items = [annotation_page_items]
            canvas.items = [annotation_page]
            items.append(canvas)
        manifest.items = items
        with open(manifest_path, 'w', encoding='utf-8') as jf:
            json.dump(manifest, jf, ensure_ascii=False, indent=4)

    def get_image_info(self, file):
        """Gets information about the image file.

        Args:
            file (str): filename of the image file
        Returns:
            img.size (tuple): A tuple containing the width and height of an image.
        """
        with Image.open(Path(self.jp2_path, file)) as img:
            return img.size

    def set_thumbnail(self, identifier):
        """Creates a IIIF-compatible thumbnail.

        Args:
            identifier (str): A string identifier to use as the thumbnail id.
        Returns:
            thumbnail (object): A prezi3 ResourceItem object.
        """
        thumbnail_height = 200
        thumbnail_width = 200
        thumbnail = ResourceItem(id="{}{}/square/{},/0/default.jpg".format(self.resource_url, identifier, 200),
                                 type="Image",
                                 format="image/jpeg",
                                 height=thumbnail_height,
                                 width=thumbnail_width,
                                 service=[self.set_service(identifier)])
        return thumbnail

    def set_service(self, identifier):
        return ServiceItem1(
            id="{}{}".format(self.resource_url, identifier),
            context="http://iiif.io/api/image/{}/context.json".format(self.image_api_version),
            profile="http://iiif.io/api/image/{}/level2.json".format(self.image_api_version))


class AWSUpload(BaseRoutine):
    """Uploads files to AWS."""
    start_process_status = Bag.MANIFESTS_CREATED
    in_process_status = Bag.UPLOADING
    end_process_status = Bag.UPLOADED
    success_message = "Files successfully uploaded."
    idle_message = "No files to upload."

    def __init__(self):
        self.aws_client = AWSClient(*settings.AWS)

    def process_bag(self, bag):
        # pdf_dir = Path(bag.bag_path, "data", "PDF")
        jp2_dir = Path(bag.bag_path, "data", "JP2")
        manifest_dir = Path(bag.bag_path, "data", "MANIFEST")
        for src_dir, target_dir in [
                # (pdf_dir, "pdfs"),
                (jp2_dir, "images"),
                (manifest_dir, "manifests")]:
            uploads = matching_files(src_dir, prefix=bag.dimes_identifier, prepend=True)
            self.aws_client.upload_files(uploads, target_dir)


class Cleanup(BaseRoutine):
    """Removes bag files that have been processed.

    Returns:
        A tuple containing human-readable message along with list of bag identifiers.
    """
    start_process_status = Bag.UPLOADED
    in_process_status = Bag.CLEANING_UP
    end_process_status = Bag.CLEANED_UP
    success_message = "Source and temporary files successfully removed."
    idle_message = "No source or temporary files waiting for cleanup."

    def process_bag(self, bag):
        rmtree(bag.bag_path)
        src_file = Path(settings.SRC_DIR, f"{bag.bag_identifier}.tar.gz")
        if src_file.exists():
            Path(settings.SRC_DIR, f"{bag.bag_identifier}.tar.gz").unlink()
