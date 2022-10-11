from pathlib import Path

import boto3
from asnake import utils
from asnake.aspace import ASpace
from django.conf import settings

from .helpers import image_dimensions_from_file


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
        self.s3_client = boto3.client(
            's3',
            region_name=region_name,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key)
        self.bucket = bucket

    def get_content_type(self, file):
        """Returns a content type for images, PDFs and Manifests.

        Args:
            file (pathlib.Path): filepath to file.
        """
        content_type = "image/jp2"
        if file.suffix == ".json":
            content_type = "application/json"
        elif file.suffix == ".pdf":
            content_type = "application/pdf"
        return content_type

    def upload_files(self, files, destination_dir):
        """Iterates over directories and conditionally uploads files to S3.

        Args:
            files (list): Filepaths to be uploaded.
            destination_dir (str): Path in the bucket in which the file should be stored.
        """
        for file in files:
            key = file.stem
            bucket_path = str(Path(destination_dir, key))
            content_type = self.get_content_type(file)
            if content_type == "image/jp2":
                width, height = image_dimensions_from_file(file)
                self.s3_client.upload_file(
                    str(file), self.bucket, bucket_path,
                    ExtraArgs={'ContentType': content_type, 'Metadata': {"width": str(width), "height": str(height)}})
            else:
                self.s3_client.upload_file(str(file), self.bucket, bucket_path, ExtraArgs={'ContentType': content_type})

    def list_objects(self, prefix=None):
        """Returns a list of keys in a bucket.

        Args:
            prefix (string): optional prefix to filter by.

        Returns:
            objects (list): list of object keys, sorted in increasing order.
        """
        objects = []
        paginator = self.s3_client.get_paginator('list_objects_v2')
        results = paginator.paginate(Bucket=self.bucket, Prefix=prefix)
        for page in results:
            objects += [item["Key"] for item in page.get("Contents", [])]
        return sorted(objects)

    def get_image_dimensions(self, key):
        """Gets dimensions recorded in an object's metadata.

        If the attributes are unavailable in the object's metadata, downloads
        the file locally to determine dimensions, then updates metadata in AWS.

        Args:
            key (str): key for the object.
        """
        metadata = self.s3_client.head_object(Bucket=self.bucket, Key=key).get("Metadata", {})
        try:
            width = int(metadata["width"])
            height = int(metadata["height"])
        except KeyError:
            target_path = Path(settings.TMP_DIR, key.split("/")[-1])
            self.s3_client.download_file(self.bucket, key, str(target_path))
            width, height = image_dimensions_from_file(target_path)
            metadata.update({"width": str(width), "height": str(height)})
            self.s3_client.copy_object(
                Bucket=self.bucket,
                Key=key,
                CopySource={"Bucket": self.bucket, "Key": key},
                ContentType=self.get_content_type(target_path),
                Metadata=metadata,
                MetadataDirective="REPLACE")
            target_path.unlink()
        return width, height
