from asterism.models import BasePackage
from django.contrib.auth.models import AbstractUser


class Bag(BasePackage):
    CREATED = 0
    PREPARED = 1
    JPG2000 = 2
    PDF = 3
    MANIFESTS_CREATED = 4
    UPLOADED = 5
    CLEANED_UP = 6
    PROCESS_STATUS_CHOICES = (
        (CREATED,
        "Created"),
        (PREPARED,
         "Prepared"),
        (JPG2000,
         "JPG2000 derivatives created"),
        (PDF,
         "PDF derivatives created"),
        (MANIFESTS_CREATED,
         "Manifests created"),
        (UPLOADED,
         "Derivatives and manifests uploaded to AWS"),
        (CLEANED_UP,
         "Files removed from temp directory"))


class User(AbstractUser):
    pass
