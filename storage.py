import os
import boto3
from urllib.parse import urlparse

# Ensure S3 clients can handle MinIO or other S3 compatible storages
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_REGION = os.getenv("S3_REGION", "us-east-1")

def get_s3_client():
    kwargs = {
        "aws_access_key_id": S3_ACCESS_KEY,
        "aws_secret_access_key": S3_SECRET_KEY,
        "region_name": S3_REGION,
    }
    if S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = S3_ENDPOINT_URL
        
    return boto3.client("s3", **kwargs)

def parse_s3_uri(uri: str):
    """
    Parses s3://bucket/path/to/key into bucket and key
    """
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    
    parsed = urlparse(uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    return bucket, key

def download_file(s3_uri: str, local_path: str):
    client = get_s3_client()
    bucket, key = parse_s3_uri(s3_uri)
    client.download_file(bucket, key, local_path)

def upload_file(local_path: str, s3_uri: str):
    client = get_s3_client()
    bucket, key = parse_s3_uri(s3_uri)
    client.upload_file(local_path, bucket, key)
