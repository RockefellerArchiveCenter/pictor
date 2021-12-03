from asterism.models import BasePackage
from django.contrib.auth.models import AbstractUser
from django.db import models


class Bag(BasePackage):
    CREATED = 0
    PREPARED = 1
    JPG2000 = 2
    PDF = 3
    MANIFESTS_CREATED = 4
    UPLOADED = 5
    CLEANED_UP = 6
    TIFF_PREPARED = 7
    PDF_COMPRESS = 8
    PDF_OCR = 9
    PREPARING = 10
    CREATING_JP2 = 11
    CREATING_PDF = 12
    CREATING_MANIFESTS = 13
    UPLOADING = 14
    CLEANING_UP = 15
    PREPARING_TIFF = 16
    COMPRESSING_PDF = 17
    OCRING_PDF = 18
    PROCESS_STATUS_CHOICES = (
        (CREATED, "Created"),
        (PREPARED, "Prepared"),
        (JPG2000, "JPG2000 derivatives created"),
        (PDF, "PDF derivatives created"),
        (MANIFESTS_CREATED, "Manifests created"),
        (UPLOADED, "Derivatives and manifests uploaded to AWS"),
        (CLEANED_UP, "Files removed from temp directory"),
        (TIFF_PREPARED, "TIFFs prepared for conversion"),
        (PDF_COMPRESS, "PDF compressed"),
        (PDF_OCR, "PDF OCRed"),
        (PREPARING, "Preparing"),
        (CREATING_JP2, "Creating JPG2000 derivatives"),
        (CREATING_PDF, "Creating PDF"),
        (CREATING_MANIFESTS, "Creating manifests"),
        (UPLOADING, "Uploading derivatives and manifests to AWS"),
        (CLEANING_UP, "Removing files from temp directory"),
        (PREPARING_TIFF, "Preparing TIFFs for conversion"),
        (COMPRESSING_PDF, "Compressing PDF"),
        (OCRING_PDF, "OCRing PDF")
    )

    as_data = models.JSONField(blank=True, null=True)
    dimes_identifier = models.CharField(max_length=255, blank=True, null=True)
    pdf_path = models.CharField(max_length=255, blank=True, null=True)


class User(AbstractUser):
    pass
