from pathlib import Path

import shortuuid
from asterism.file_helpers import anon_extract_all
from pictor import settings
from .helpers import check_dir_exists
from .models import Bag


class BagPreparer:
    """Prepares bags for derivative creation.

    Unpacks bags into settings.TMP_DIR and adds all necessary data the object.

    Returns:
        A tuple containing human-readable message along with list of bag identifiers.
        Exceptions are raised for errors along the way.

    """
    def __init__(self):
        self.as_client = ArchivesSpaceClient(**settings.ARCHIVESSPACE)
        check_dir_exists(settings.SRC_DIR)
        check_dir_exists(settings.TMP_DIR)

    def run(self):
        processed_bags = []
        for bag in Bag.objects.filter(process_status=Bag.CREATED):
            # TODO: presumes bag.data, bag.bag_identifier, bag.origin are all set by this point
            # TODO: we should also be sure that Ursa Major is delivering to two directories, or we will run into conflicts with Fornax
            unpacked_path = self.unpack_bag(bag.bag_identifier)
            self.validate_structure(unpacked_path)
            bag.bag_path = unpacked_path
            bag.as_data = as_client.get_object(ref_id) # TODO: where is this?
            bag.dimes_identifier = shortuuid.uuid(bag.as_data["uri"])
            bag.process_status = Bag.PREPARED
            bag.save()
            processed_bags.append(bag.bag_identifier)
        return "Bags successfully prepared", processed_bags

    def unpack_bag(self, bag_identifier):
        """Extracts a serialized bag to the tmp directory."""
        if anon_extract_all(
                ".tar.gz".format(str(Path(settings.SRC_DIR, bag_identifier))), settings.TMP_DIR):
            return str(Path(settings.TMP_DIR, bag_identifier))
        else:
            raise Exception("Unable to extract bag", bag_identifier)

    def validate_structure(self, bag_filepath):
        """Ensures that the structure of the data directory contains expected subdirectories."""
        check_dir_exists(str(Path(bag_filepath, "data", "master")))

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
    # TO DO: upload files and PDFs
    pass


class CleanupRoutine:
    pass
