import math
import subprocess
from pathlib import Path
from shutil import rmtree

import bagit
import shortuuid
from asterism.file_helpers import anon_extract_all
from pictor import settings
from PIL import Image

from .clients import ArchivesSpaceClient, AWSClient
from .helpers import check_dir_exists, matching_files
from .models import Bag


class BagPreparer:
    """Prepares bags for derivative creation.

    Unpacks bags into settings.TMP_DIR and adds all necessary data to the object.

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
    """Creates JP2000 derivatives from TIFFs.

    Creates JP2 directory in bag's data directory and JP2 derivatives.
    TIFFs to be converted are targeted in the service directory. If the service directory is empty or
    does not exist, target TIFFs at the root of the data directory.

    Returns:
        A tuple containing human-readable message along with list of bag identifiers.
        Exceptions are raised for errors along the way.
    """

    def run(self):
        bags_with_jp2s = []
        for bag in Bag.objects.filter(process_status=Bag.PREPARED):
            service_dir = Path(bag.bag_path, "data", "service")
            if service_dir.is_dir() and len(service_dir):
                tiff_files_dir = Path(bag.bag_path, "data", "service")
            else:
                tiff_files_dir = Path(bag.bag_path, "data")
            self.jp2_list = self.create_jp2(bag, tiff_files_dir)
            bag.process_status = Bag.JPG2000
            bag.save()
            bags_with_jp2s.append(bag.bag_identifier)
        msg = "JPG2000s created." if len(bags_with_jp2s) else "No TIFF files ready for JP2 creation."
        return msg, bags_with_jp2s

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

    def get_page_number(self, file):
        """Parses a page number from a filename.

        Presumes that:
            The page number is preceded by an underscore
            The page number is immediately followed by either by `_m`, `_me` or `_se`,
            or the file extension.

        Args:
            file (str): filename of a TIFF image file.
        Returns:
            page number from the filename
        """
        filename = Path(file).stem
        if "_se" in filename:
            filename_trimmed = filename.split("_se")[0]
        elif "_m" in filename:
            filename_trimmed = filename.split("_m")[0]
        else:
            filename_trimmed = filename
        return filename_trimmed.split("_")[-1]

    def create_jp2(self, bag, tiff_files_dir):
        """Creates JPEG2000 files from TIFF files.

        Args:
            -r(str): Compression ratio. Default is 1.5.
            -c(str): Precinct size. Default is `[256,256]` for first two layers and `[128,128]` for others.
            -b(str): Code block. Default size of `[64,64]`.
            -p(str): Progression order. Default of 'RPCL`.

        Returns:
            jp2_list: A tuple of JPG2000 paths including their page numbers
        """

        default_options = ["-r", "1.5",
                           "-c", "[256,256],[256,256],[128,128]",
                           "-b", "64,64",
                           "-p", "RPCL"]
        jp2_dir = Path(bag.bag_path, "data", "JP2")
        if not jp2_dir.is_dir():
            jp2_dir.mkdir()
        jp2_list = []
        tiff_files = matching_files(str(tiff_files_dir), prepend=True)
        for file in tiff_files:
            page_number = self.get_page_number(file)
            jp2_path = Path(jp2_dir, "{}_{}.jp2".format(bag.dimes_identifier, page_number))
            layers = self.calculate_layers(file)
            cmd = ["/usr/local/bin/opj_compress",
                   "-i", file,
                   "-o", jp2_path,
                   "-n", str(layers),
                   "-SOP"] + default_options
            subprocess.run(cmd, check=True)
            jp2_list.append(jp2_path)
        return jp2_list


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
    # TO DO: make manifests
    pass


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
                    str(src_dir), prefix=bag.bag_identifier, prepend=True)
                self.aws_client.upload_files(uploads, target_dir, replace)
            bag.process_status = Bag.UPLOADED
            bag.save()
            uploaded_bags.append(bag.bag_identifier)
        return "Bags successfully uploaded", uploaded_bags


class CleanupRoutine:
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
