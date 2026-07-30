import botocore
import pytest

from notifications_utils.s3 import (
    s3_download_all_files_from_folder,
    s3_move_folder_between_buckets,
)

test_bucket = "test-bucket"
test_folder = "test-folder"
test_source_bucket = "source-bucket"
test_dest_bucket = "dest-bucket"


def test_s3_download_all_files_from_folder_success(mocker):
    mocked_s3 = mocker.patch("notifications_utils.s3.resource")
    mocked_bucket = mocked_s3.return_value.Bucket.return_value

    mock_file1 = mocker.Mock()
    mock_file1.key = f"{test_folder}/file1.txt"
    mock_body1 = mocker.Mock()
    mock_body1.read.return_value = b"content1"
    mock_file1.get.return_value = {"Body": mock_body1}

    mock_file2 = mocker.Mock()
    mock_file2.key = f"{test_folder}/file2.txt"
    mock_body2 = mocker.Mock()
    mock_body2.read.return_value = b"content2"
    mock_file2.get.return_value = {"Body": mock_body2}

    mocked_bucket.objects.filter.return_value = [mock_file1, mock_file2]

    result = s3_download_all_files_from_folder(test_bucket, test_folder)

    assert len(result) == 2
    assert "file1.txt" in result
    assert "file2.txt" in result
    assert result["file1.txt"] == b"content1"
    assert result["file2.txt"] == b"content2"

    mocked_bucket.objects.filter.assert_called_once_with(Prefix=f"{test_folder}/")


def test_s3_download_all_files_from_folder_with_trailing_slash(mocker):
    mocked_s3 = mocker.patch("notifications_utils.s3.resource")
    mocked_bucket = mocked_s3.return_value.Bucket.return_value

    folder_with_slash = f"{test_folder}/"

    mock_file = mocker.Mock()
    mock_file.key = f"{folder_with_slash}file.txt"
    mock_body = mocker.Mock()
    mock_body.read.return_value = b"content"
    mock_file.get.return_value = {"Body": mock_body}

    mocked_bucket.objects.filter.return_value = [mock_file]

    result = s3_download_all_files_from_folder(test_bucket, folder_with_slash)

    assert len(result) == 1
    assert "file.txt" in result
    assert result["file.txt"] == b"content"


def test_s3_download_all_files_from_folder_empty(mocker):
    mocked_s3 = mocker.patch("notifications_utils.s3.resource")
    mocked_bucket = mocked_s3.return_value.Bucket.return_value

    mock_folder = mocker.Mock()
    mock_folder.key = f"{test_folder}/"

    mocked_bucket.objects.filter.return_value = [mock_folder]

    result = s3_download_all_files_from_folder(test_bucket, test_folder)

    assert len(result) == 0


def test_s3_download_all_files_from_folder_error(mocker, app_with_mocked_logger):
    mocked_s3 = mocker.patch("notifications_utils.s3.resource")
    response = {"Error": {"Code": 404}}
    exception = botocore.exceptions.ClientError(response, "Not Found")

    mocked_s3.return_value.Bucket.return_value.objects.filter.side_effect = exception

    with pytest.raises(botocore.exceptions.ClientError):
        s3_download_all_files_from_folder(test_bucket, test_folder)


def test_s3_move_folder_between_buckets_success(mocker):
    mocked_s3_resource = mocker.patch("notifications_utils.s3.resource")
    mocked_s3_client = mocker.patch("notifications_utils.s3.client")

    source_bucket = mocked_s3_resource.return_value.Bucket.return_value
    mock_file1 = mocker.Mock()
    mock_file1.key = f"{test_folder}/file1.txt"
    mock_file2 = mocker.Mock()
    mock_file2.key = f"{test_folder}/file2.txt"

    source_bucket.objects.filter.return_value = [mock_file1, mock_file2]

    s3_move_folder_between_buckets(test_source_bucket, test_dest_bucket, test_folder)

    assert mocked_s3_client.return_value.copy_object.call_count == 2

    assert mocked_s3_resource.return_value.Object.return_value.delete.call_count == 2

    source_bucket.objects.filter.assert_called_once_with(Prefix=f"{test_folder}/")


def test_s3_move_folder_between_buckets_with_trailing_slash(mocker):
    mocked_s3_resource = mocker.patch("notifications_utils.s3.resource")
    mocked_s3_client = mocker.patch("notifications_utils.s3.client")

    folder_with_slash = f"{test_folder}/"

    source_bucket = mocked_s3_resource.return_value.Bucket.return_value
    mock_file = mocker.Mock()
    mock_file.key = f"{folder_with_slash}file.txt"

    source_bucket.objects.filter.return_value = [mock_file]

    s3_move_folder_between_buckets(test_source_bucket, test_dest_bucket, folder_with_slash)

    mocked_s3_client.return_value.copy_object.assert_called_once()
    mocked_s3_resource.return_value.Object.return_value.delete.assert_called_once()


def test_s3_move_folder_between_buckets_error(mocker, app_with_mocked_logger):
    mocked_s3_resource = mocker.patch("notifications_utils.s3.resource")

    response = {"Error": {"Code": 404}}
    exception = botocore.exceptions.ClientError(response, "Not Found")

    mocked_s3_resource.return_value.Bucket.return_value.objects.filter.side_effect = exception

    with pytest.raises(botocore.exceptions.ClientError):
        s3_move_folder_between_buckets(test_source_bucket, test_dest_bucket, test_folder)


def test_s3_move_folder_between_buckets_empty_folder(mocker):
    mocked_s3_resource = mocker.patch("notifications_utils.s3.resource")
    mocked_s3_client = mocker.patch("notifications_utils.s3.client")

    source_bucket = mocked_s3_resource.return_value.Bucket.return_value

    mock_folder = mocker.Mock()
    mock_folder.key = f"{test_folder}/"

    source_bucket.objects.filter.return_value = [mock_folder]

    s3_move_folder_between_buckets(test_source_bucket, test_dest_bucket, test_folder)

    mocked_s3_client.return_value.copy_object.assert_not_called()
    mocked_s3_resource.return_value.Object.return_value.delete.assert_not_called()
