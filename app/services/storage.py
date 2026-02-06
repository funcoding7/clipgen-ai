import boto3
from botocore.exceptions import ClientError
import os
from typing import Optional
import tempfile
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load from environment
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "clipgen-ai-storage")

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)


def upload_file(local_path: str, s3_key: str) -> bool:
    """
    Upload a local file to S3.
    
    Args:
        local_path: Path to the local file
        s3_key: The key (path) to use in S3
        
    Returns:
        True if successful, False otherwise
    """
    try:
        s3_client.upload_file(local_path, S3_BUCKET_NAME, s3_key)
        print(f"Uploaded {local_path} to s3://{S3_BUCKET_NAME}/{s3_key}")
        return True
    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        return False


def download_file(s3_key: str, local_path: str) -> bool:
    """
    Download a file from S3 to local path.
    
    Args:
        s3_key: The key (path) in S3
        local_path: Where to save the file locally
        
    Returns:
        True if successful, False otherwise
    """
    try:
        s3_client.download_file(S3_BUCKET_NAME, s3_key, local_path)
        print(f"Downloaded s3://{S3_BUCKET_NAME}/{s3_key} to {local_path}")
        return True
    except ClientError as e:
        print(f"Error downloading from S3: {e}")
        return False


def get_presigned_url(s3_key: str, expires_in: int = 3600) -> Optional[str]:
    """
    Generate a presigned URL for downloading a file.
    
    Args:
        s3_key: The key (path) in S3
        expires_in: URL expiration time in seconds (default 1 hour)
        
    Returns:
        Presigned URL string, or None on error
    """
    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=expires_in,
        )
        return url
    except ClientError as e:
        print(f"Error generating presigned URL: {e}")
        return None


def delete_file(s3_key: str) -> bool:
    """
    Delete a file from S3.
    
    Args:
        s3_key: The key (path) in S3
        
    Returns:
        True if successful, False otherwise
    """
    try:
        s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        print(f"Deleted s3://{S3_BUCKET_NAME}/{s3_key}")
        return True
    except ClientError as e:
        print(f"Error deleting from S3: {e}")
        return False


def ensure_bucket_exists() -> bool:
    """
    Create the S3 bucket if it doesn't exist.
    
    Returns:
        True if bucket exists or was created, False on error
    """
    try:
        s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "404":
            try:
                # Create bucket with region-specific config
                if AWS_REGION == "us-east-1":
                    s3_client.create_bucket(Bucket=S3_BUCKET_NAME)
                else:
                    s3_client.create_bucket(
                        Bucket=S3_BUCKET_NAME,
                        CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
                    )
                print(f"Created bucket: {S3_BUCKET_NAME}")
                return True
            except ClientError as create_error:
                print(f"Error creating bucket: {create_error}")
                return False
        else:
            print(f"Error checking bucket: {e}")
            return False


def get_temp_path(filename: str) -> str:
    """Get a path in the temp directory for a given filename."""
    return os.path.join(tempfile.gettempdir(), filename)
