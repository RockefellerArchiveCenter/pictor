from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from create_derivatives.clients import AWSClient
from create_derivatives.routines import ManifestRecreator


class Command(BaseCommand):
    help = 'Recreates all manifests.'

    def handle(self, *args, **kwargs):
        aws_client = AWSClient(*settings.AWS)
        manifests = aws_client.list_objects(prefix="manifests/")
        for manifest in manifests:
            dimes_identifier = manifest.split("/")[-1]
            try:
                ManifestRecreator().run(dimes_identifier)
                self.stdout.write(f"Recreated manifest {dimes_identifier}")
            except Exception as e:
                raise CommandError(f"Error recreating manifest {dimes_identifier}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Successfully recreated {len(manifests)} manifests."))
