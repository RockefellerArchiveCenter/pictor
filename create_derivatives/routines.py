import json
import math
import subprocess
from pathlib import Path
from shutil import rmtree

import bagit
import requests
import shortuuid
from asterism.file_helpers import anon_extract_all
from django.core.exceptions import ObjectDoesNotExist
from iiif_prezi3 import Manifest, config
from PIL import Image
from shortuuid import uuid

from pictor import settings

from .clients import ArchivesSpaceClient, AWSClient
from .helpers import (check_dir_exists, get_page_number,
                      image_dimensions_from_file, matching_files)
from .models import Bag

Image.MAX_IMAGE_PIXELS = 200000000


class BaseRoutine(object):
    """Base class which all routines inherit.

    Returns:
        msg (str): human-readable representation of the routine outcome

    Subclasses should implement a `process_bag` method which executes logic on
    one bag. They should also set the following attributes:
        start_process_status (int): a Bag process status which determines the starting
            queryset.
        in_process_status (int): a Bag process status which indicates that a Bag is currently processing
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
    start_process_status = Bag.PDF_OCR
    in_process_status = Bag.CREATING_MANIFESTS
    end_process_status = Bag.MANIFESTS_CREATED
    success_message = "Manifests successfully created."
    idle_message = "No manifests created."

    def __init__(self):
        self.image_api_version = settings.IIIF_API['image_api']
        self.presentation_api_version = settings.IIIF_API['presentation_api']
        if self.image_api_version not in [2, 3]:
            raise Exception("Version {} of IIIF Image API not supported.".format(self.image_api_version))
        elif self.presentation_api_version not in [2, 3]:
            raise Exception("Version {} of IIIF Presentation API not supported.".format(self.presentation_api_version))
        self.resource_url = "{}/iiif/{}/".format(settings.IMAGESERVER_URL, self.image_api_version)
        config.configs['helpers.auto_fields.AutoLang'].auto_lang = "en"

    def process_bag(self, bag, jp2_files=None, recreate=False):
        self.jp2_path = Path(bag.bag_path, "data", "JP2")
        self.jp2_files = jp2_files if jp2_files else sorted([f for f in matching_files(self.jp2_path)])
        self.manifest_dir = Path(bag.bag_path, "data", "MANIFEST")
        if not self.manifest_dir.is_dir():
            self.manifest_dir.mkdir(parents=True)
        self.create_manifest(bag.dimes_identifier, bag.as_data, recreate)

    def create_manifest(self, identifier, obj_data, file_uploaded):
        """Method that runs the other methods to build a manifest file and populate
        it with information.

        Args:
            identifier (str): A unique identifier.
            obj_data (dict): Data about the archival object.
        """
        manifest_path = Path(self.manifest_dir, f"{identifier}.json")
        manifest_id = f"{settings.IIIF_URL.rstrip('/')}/manifests/{identifier}"
        manifest = Manifest(id=manifest_id, label=obj_data["title"])
        manifest.add_metadata("Date", obj_data["dates"])
        for jp2_file in self.jp2_files:
            page_number = get_page_number(jp2_file).lstrip("0")
            jp2_filename = jp2_file.stem
            width, height = self.get_image_info(jp2_file, file_uploaded)
            """Set the canvas ID, which starts the same as the manifest ID,
            and then include page_number as the canvas ID.
            """
            canvas_id = f"{manifest_id}/canvas/{page_number}"
            thumbnail = [{
                "id": f"{self.resource_url.rstrip('/')}/{jp2_filename}/square/200,/0/default.jpg",
                "type": "Image",
                "format": "image/jpeg",
                "height": 200,
                "width": 200,
            }]
            canvas = manifest.make_canvas(id=canvas_id, height=height, width=width, label=f"Page {page_number}", thumbnail=thumbnail)
            canvas.add_image(
                anno_page_id=f"{canvas_id}/annotation-page/1",
                anno_id=f"{canvas_id}/annotation/1",
                image_url=f"{self.resource_url.rstrip('/')}/{jp2_filename}/full/max/0/default.jpg",
                format="image/jpeg",
                height=height,
                width=width)
        with open(manifest_path, 'w', encoding='utf-8') as jf:
            json.dump(json.loads(manifest.jsonld()), jf, ensure_ascii=False, indent=4)

    def get_image_info(self, file, file_uploaded):
        """Gets information about the image file.

        Args:
            file (str): filename of the image file
            file_uploaded (bool): indicates whether or not the file has already
                been uploaded to S3 (in cases where the manifest is being recreated).
        Returns:
            width, height (tuple): A tuple containing the width and height of an image.
        """
        if file_uploaded:
            return AWSClient(*settings.AWS).get_image_dimensions(str(file))
        return image_dimensions_from_file(Path(self.jp2_path, file))


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


class ManifestRecreator(object):
    """Recreates a manifest."""

    def __init__(self):
        self.aws_client = AWSClient(*settings.AWS)
        self.as_client = ArchivesSpaceClient(*settings.ARCHIVESSPACE)

    def run(self, dimes_identifier):
        """Creates and uploads an updated manifest.

        Args:
            dimes_identifier (string): a DIMES identifier for the manifest to be
            recreated.
        """
        try:
            bag = Bag.objects.get(dimes_identifier=dimes_identifier)
        except ObjectDoesNotExist:
            resp = requests.get(f"https://api.rockarch.org/objects/{dimes_identifier}")
            resp.raise_for_status()
            obj_data = resp.json()
            as_uri = [ident["identifier"] for ident in obj_data["external_identifiers"] if ident["source"] == "archivesspace"][0]
            as_data = self.as_client.get_object(as_uri)
            bag_identifier = uuid(name=as_uri)
            bag = Bag.objects.create(
                bag_identifier=bag_identifier,
                bag_path=str(Path(settings.TMP_DIR, bag_identifier)),
                dimes_identifier=dimes_identifier,
                origin="digitization",
                as_data=as_data,
                process_status=Bag.CLEANED_UP)
        jp2_files = [Path(f) for f in self.aws_client.list_objects(f"images/{dimes_identifier}")]
        ManifestMaker().process_bag(bag, jp2_files, True)
        uploads = matching_files(Path(bag.bag_path, "data", "MANIFEST"), prefix=dimes_identifier, prepend=True)
        self.aws_client.upload_files(uploads, "manifests")
        rmtree(bag.bag_path)
        return "Manifest recreated.", [dimes_identifier]
