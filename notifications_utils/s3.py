import urllib

import botocore
from boto3 import client, resource
from flask import current_app

from notifications_utils.eventlet import EventletTimeout
from notifications_utils.exception_handling import extract_reraise_chained_exception


@extract_reraise_chained_exception(EventletTimeout)
def s3upload(
    filedata,
    region,
    bucket_name,
    file_location,
    content_type="binary/octet-stream",
    tags=None,
    metadata=None,
):
    _s3 = resource("s3")

    key = _s3.Object(bucket_name, file_location)

    put_args = {"Body": filedata, "ServerSideEncryption": "AES256", "ContentType": content_type}

    if tags:
        tags = urllib.parse.urlencode(tags)
        put_args["Tagging"] = tags

    if metadata:
        metadata = put_args["Metadata"] = metadata

    try:
        key.put(**put_args)
    except botocore.exceptions.ClientError as e:
        current_app.logger.error(
            "Unable to upload file to S3 bucket %s",
            bucket_name,
            extra={"s3_key": file_location, "s3_bucket": bucket_name},
        )
        raise e


class S3ObjectNotFound(botocore.exceptions.ClientError):
    pass


@extract_reraise_chained_exception(EventletTimeout)
def s3download(bucket_name, filename):
    try:
        s3 = resource("s3")
        key = s3.Object(bucket_name, filename)
        return key.get()["Body"]
    except botocore.exceptions.ClientError as error:
        raise S3ObjectNotFound(error.response, error.operation_name) from error


S3_MULTIPART_UPLOAD_MIN_PART_SIZE = 5 * 1024 * 1024  # 5MB minimum multi part upload size


@extract_reraise_chained_exception(EventletTimeout)
def s3_multipart_upload_create(bucket_name, file_location, content_type="binary/octet-stream"):
    s3 = client("s3")

    args = {"Bucket": bucket_name, "Key": file_location, "ServerSideEncryption": "AES256", "ContentType": content_type}

    try:
        response = s3.create_multipart_upload(**args)
        return response
    except botocore.exceptions.ClientError as e:
        current_app.logger.error(
            "Unable to create multipart upload in S3 bucket %s for file %s",
            bucket_name,
            file_location,
            extra={"s3_key": file_location, "s3_bucket": bucket_name},
        )
        raise e


@extract_reraise_chained_exception(EventletTimeout)
def s3_multipart_upload_part(part_number, bucket_name, filename, upload_id, data_bytes):
    s3 = client("s3")

    try:
        response = s3.upload_part(
            Bucket=bucket_name,
            Key=filename,
            PartNumber=part_number,
            UploadId=upload_id,
            Body=data_bytes,
        )
        return response
    except botocore.exceptions.ClientError as e:
        current_app.logger.exception(
            "Unable to upload part %s in S3 bucket %s for file %s",
            part_number,
            bucket_name,
            filename,
            extra={"s3_key": filename, "s3_bucket": bucket_name, "part_number": part_number, "upload_id": upload_id},
        )
        raise e


@extract_reraise_chained_exception(EventletTimeout)
def s3_multipart_upload_complete(bucket_name, filename, upload_id, parts):
    s3 = client("s3")
    try:
        s3.complete_multipart_upload(
            Bucket=bucket_name,
            Key=filename,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
    except botocore.exceptions.ClientError as e:
        current_app.logger.exception(
            "Unable to complete multipart upload %s in S3 bucket %s for file %s",
            upload_id,
            bucket_name,
            filename,
            extra={"s3_key": filename, "s3_bucket": bucket_name, "upload_id": upload_id},
        )
        raise e


@extract_reraise_chained_exception(EventletTimeout)
def s3_multipart_upload_abort(bucket_name, filename, upload_id):
    s3 = client("s3")

    try:
        s3.abort_multipart_upload(Bucket=bucket_name, Key=filename, UploadId=upload_id)
    except botocore.exceptions.ClientError as e:
        current_app.logger.exception(
            "Unable to abort multipart upload %s in S3 bucket %s for file %s",
            upload_id,
            bucket_name,
            filename,
            extra={"s3_key": filename, "s3_bucket": bucket_name, "upload_id": upload_id},
        )
        raise e


#
# NotifyNL
#
def s3_download_all_files_from_folder(bucket_name, folder_name):
    try:
        s3 = resource("s3")
        bucket = s3.Bucket(bucket_name)

        if not folder_name.endswith("/"):
            folder_name += "/"

        files_data = {}

        for obj in bucket.objects.filter(Prefix=folder_name):
            if obj.key == folder_name:
                continue

            file_content = obj.get()["Body"].read()

            relative_filename = obj.key[len(folder_name) :]
            files_data[relative_filename] = file_content

        return files_data

    except botocore.exceptions.ClientError as error:
        current_app.logger.error("Unable to download files from folder %s in bucket %s", folder_name, bucket_name)
        raise S3ObjectNotFound(error.response, error.operation_name) from error


def s3_move_folder_between_buckets(source_bucket, dest_bucket, folder_name, dest_folder_name=None):
    try:
        s3 = resource("s3")
        s3_client = client("s3")

        if not folder_name.endswith("/"):
            folder_name += "/"

        if dest_folder_name is None:
            dest_folder_name = folder_name
        elif not dest_folder_name.endswith("/"):
            dest_folder_name += "/"

        source_bucket_obj = s3.Bucket(source_bucket)

        objects_to_move = []
        for obj in source_bucket_obj.objects.filter(Prefix=folder_name):
            if obj.key == folder_name:
                continue
            objects_to_move.append(obj.key)

        for obj_key in objects_to_move:
            dest_key = dest_folder_name + obj_key[len(folder_name) :]

            copy_source = {"Bucket": source_bucket, "Key": obj_key}

            s3_client.copy_object(CopySource=copy_source, Bucket=dest_bucket, Key=dest_key)

            s3.Object(source_bucket, obj_key).delete()

    except botocore.exceptions.ClientError as error:
        current_app.logger.error(
            "Unable to move folder %s from bucket %s to bucket %s", folder_name, source_bucket, dest_bucket
        )
        raise S3ObjectNotFound(error.response, error.operation_name) from error
