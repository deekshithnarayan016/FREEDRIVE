import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions
)

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("CONTAINER_NAME")
AZURE_ACCOUNT_NAME = os.getenv("AZURE_ACCOUNT_NAME")
AZURE_ACCOUNT_KEY = os.getenv("AZURE_ACCOUNT_KEY")

# Validate env variables
if not all([
    AZURE_STORAGE_CONNECTION_STRING,
    CONTAINER_NAME,
    AZURE_ACCOUNT_NAME,
    AZURE_ACCOUNT_KEY
]):
    raise EnvironmentError("One or more Azure environment variables are missing")

# -----------------------------
# Azure Blob Clients
# -----------------------------
blob_service_client = BlobServiceClient.from_connection_string(
    AZURE_STORAGE_CONNECTION_STRING
)

container_client = blob_service_client.get_container_client(CONTAINER_NAME)

# Create container if it does not exist
try:
    container_client.create_container()
except Exception:
    pass  # container already exists

# -----------------------------
# Upload File
# -----------------------------
def upload_file(file, user: str) -> str:
    """
    Upload a file to Azure Blob Storage under user-specific folder.
    """
    blob_name = f"users/{user}/{file.filename}"

    container_client.upload_blob(
        name=blob_name,
        data=file.stream,
        overwrite=True
    )

    return blob_name

# -----------------------------
# List Files
# -----------------------------
def list_files(user: str):
    """
    List all files for a given user.
    """
    prefix = f"users/{user}/"
    return container_client.list_blobs(
        name_starts_with=prefix
    )

# -----------------------------
# Generate SAS Token
# -----------------------------
def generate_sas(blob_name: str) -> str:
    """
    Generate a short-lived SAS token for secure read access.
    """
    return generate_blob_sas(
        account_name=AZURE_ACCOUNT_NAME,
        container_name=CONTAINER_NAME,
        blob_name=blob_name,
        account_key=AZURE_ACCOUNT_KEY,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=5)
    )

# -----------------------------
# Generate Download URL
# -----------------------------
def get_download_url(blob_name: str) -> str:
    """
    Generate a full download URL with SAS token.
    """
    sas_token = generate_sas(blob_name)

    return (
        f"https://{AZURE_ACCOUNT_NAME}.blob.core.windows.net/"
        f"{CONTAINER_NAME}/{blob_name}?{sas_token}"
    )
