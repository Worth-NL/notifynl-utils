from os import getenv

from boto3 import (
    client as boto_client,
)
from boto3 import (
    resource as boto_resource,
)
from boto3 import (
    session as boto_session,
)


def client(service_name="s3"):
    return boto_client(
        service_name,
        endpoint_url=getenv("MINIO_URL", "http://minio:9000"),
        aws_access_key_id=getenv("MINIO_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=getenv("MINIO_SECRET_KEY", "minioadmin"),
        aws_session_token=None,
        config=boto_session.Config(signature_version=getenv("MINIO_SIGNATURE_VERSION", "s3v4")),
        verify=getenv("MINIO_VERIFY_SSL", "0") == "1",
    )


def resource(service_name="s3"):
    return boto_resource(
        service_name,
        endpoint_url=getenv("MINIO_URL", "http://minio:9000"),
        aws_access_key_id=getenv("MINIO_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=getenv("MINIO_SECRET_KEY", "minioadmin"),
        aws_session_token=None,
        config=boto_session.Config(signature_version=getenv("MINIO_SIGNATURE_VERSION", "s3v4")),
        verify=getenv("MINIO_VERIFY_SSL", "0") == "1",
    )
