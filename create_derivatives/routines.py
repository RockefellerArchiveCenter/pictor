from pathlib import Path

import bagit
import shortuuid
from asterism.file_helpers import anon_extract_all
from pictor import settings

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
                "{}.tar.gz".format(str(Path(settings.SRC_DIR, bag_identifier))), settings.TMP_DIR):
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
    pass


class PDFMaker:
    # TO DO: make PDF derivates, compress, OCR
    pass


class ManifestMaker:
    # TO DO: make manifests
    pass


class AWSUpload:

    def __init__(self):
        self.aws_client = AWSClient(*settings.AWS)

    def run(self, replace):
        uploaded_bags = []
        for bag in Bag.objects.filter(process_status=Bag.MANIFESTS_CREATED):
            pdf_dir = Path(bag.bag_path).joinpath('data').joinpath('PDF')
            jp2_dir = Path(bag.bag_path).joinpath('data').joinpath('JP2')
            manifest_dir = Path(bag.bag_path).joinpath('data').joinpath('MANIFEST')
            check_dir_exists(pdf_dir)
            check_dir_exists(jp2_dir)
            check_dir_exists(manifest_dir)
            for src_dir, target_dir in [
                (pdf_dir, "pdfs"),
                (jp2_dir, "images"),
                (manifest_dir, "manifests")]:
                uploads = matching_files(
                    src_dir, prefix=bag.bag_identifier, prepend=True)
                self.aws_client.upload_files(uploads, target_dir, replace)
            bag.process_status = Bag.UPLOADED
            bag.save()
            uploaded_bags.append(bag.bag_identifier)
        return "Bags successfully uploaded", uploaded_bags


class CleanupRoutine:
    pass
