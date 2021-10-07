from pathlib import Path

import boto3
from asnake import utils
from asnake.aspace import ASpace


class ArchivesSpaceClient:
    def __init__(self, baseurl, username, password, repository):
        self.client = ASpace(
            baseurl=baseurl,
            username=username,
            password=password,
            repository=repository).client
        self.repository = repository

    def get_object(self, uri):
        """Gets archival object title and date.

        Args:
            uri (str): an ArchivesSpace URI.
        Returns:
            obj (dict): A dictionary representation of an archival object from ArchivesSpace.
        """
        obj = self.client.get(uri).json()
        obj["dates"] = utils.find_closest_value(obj, 'dates', self.client)
        return self.format_data(obj)

    def format_data(self, data):
        """Parses ArchivesSpace data.

        Args:
            data (dict): ArchivesSpace data.
        Returns:
            parsed (dict): Parsed data, with only required fields present.
        """
        title = data.get("title", data.get("display_string")).title()
        dates = ", ".join([utils.get_date_display(d, self.client)
                           for d in data.get("dates", [])])
        return {"title": title, "dates": dates, "uri": data["uri"]}


class AWSClient:
    def __init__(self, region_name, access_key, secret_key, bucket):
        self.s3 = boto3.resource(
            service_name='s3',
            region_name=region_name,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key)
        self.bucket = bucket

    def upload_files(self, files, destination_dir):
        """Iterates over directories and conditionally uploads files to S3.

        Args:
            files (list): Filepaths to be uploaded.
            destination_dir (str): Path in the bucket in which the file should be stored.
        """
        for file in files:
            key = file.stem
            bucket_path = str(Path(destination_dir, key))
            content_type = "image/jp2"
            if file.suffix == ".json":
                content_type = "application/json"
            elif file.suffix == ".pdf":
                content_type = "application/pdf"
            self.s3.meta.client.upload_file(str(file), self.bucket, bucket_path, ExtraArgs={'ContentType': content_type})
