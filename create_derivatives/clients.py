import os

import boto3
from asnake import utils
from asnake.aspace import ASpace
from botocore.exceptions import ClientError


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
            replace (bool): Upload files even if they exist.
        """
        for file in files:
            key = os.path.splitext(os.path.basename(file))[0]
            bucket_path = os.path.join(destination_dir, key)
            content_type = "image/jp2"
            if file.endswith(".json"):
                content_type = "application/json"
            elif file.endswith(".pdf"):
                content_type = "application/pdf"
            self.s3.meta.client.upload_file(file, self.bucket, bucket_path, ExtraArgs={'ContentType': content_type})

    def object_in_bucket(self, object_path):
        """Checks if a file already exists in an S3 bucket.

        Args:
            object_path (str): Path to the object in the bucket.
        Returns:
            boolean: True if file exists, false otherwise.
        """
        try:
            self.s3.Object(
                self.bucket, object_path).load()
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == "404":
                return False
            else:
                raise Exception("Error connecting to AWS: {}".format(e)) from e
