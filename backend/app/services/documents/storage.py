"""S3-compatible object storage for document files (Railway Buckets)."""

import logging
from io import BytesIO
from uuid import UUID

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    if not settings.S3_BUCKET:
        raise RuntimeError("S3_BUCKET is not configured — cannot use object storage")
    _client = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
        config=BotoConfig(signature_version="s3v4"),
    )
    return _client


def make_s3_key(org_id: UUID, doc_id: UUID, filename: str) -> str:
    """Build the object key: {org_id}/{doc_id}_{filename}."""
    return f"{org_id}/{doc_id}_{filename}"


def upload_to_bucket(s3_key: str, data: bytes, content_type: str | None = None) -> str:
    """Upload raw bytes to the bucket. Returns the key stored."""
    client = _get_client()
    settings = get_settings()
    extra: dict = {}
    if content_type:
        extra["ContentType"] = content_type
    client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=s3_key,
        Body=data,
        **extra,
    )
    logger.info("s3_upload key=%s size=%d", s3_key, len(data))
    return s3_key


def download_from_bucket(s3_key: str) -> bytes:
    """Download an object and return its bytes."""
    client = _get_client()
    settings = get_settings()
    resp = client.get_object(Bucket=settings.S3_BUCKET, Key=s3_key)
    data = resp["Body"].read()
    logger.info("s3_download key=%s size=%d", s3_key, len(data))
    return data


def delete_from_bucket(s3_key: str) -> None:
    """Delete an object from the bucket. Silently succeeds if already gone."""
    client = _get_client()
    settings = get_settings()
    try:
        client.delete_object(Bucket=settings.S3_BUCKET, Key=s3_key)
        logger.info("s3_delete key=%s", s3_key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            logger.warning("s3_delete_missing key=%s", s3_key)
        else:
            raise
