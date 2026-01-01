import os
from datetime import datetime, timedelta
from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions
)

# -----------------------------
# Environment variables
# -----------------------------
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("CONTAINER_NAME")

blob_service_client = None
container_client = None
ACCOUNT_NAME = None
ACCOUNT_KEY = None


# -----------------------------
# Initialize Azure Storage
# -----------------------------
def init_storage():
    """
    Initialize Azure Blob Storage safely.
    """
    global blob_service_client, container_client, ACCOUNT_NAME, ACCOUNT_KEY

    if not AZURE_STORAGE_CONNECTION_STRING or not CONTAINER_NAME:
        print("⚠️ Azure Storage env vars not configured")
        return

    try:
        blob_service_client = BlobServiceClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING
        )

        container_client = blob_service_client.get_container_client(
            CONTAINER_NAME
        )

        ACCOUNT_NAME = blob_service_client.account_name
        ACCOUNT_KEY = blob_service_client.credential.account_key



        # Create container if missing
        try:
            container_client.create_container()
        except Exception:
            pass

        print("✅ Azure Blob Storage initialized")

    except Exception as e:
        print("❌ Azure Blob Storage init failed:", e)


# Initialize immediately (Azure-safe)
init_storage()


# -----------------------------
# Upload File (FILES + FOLDERS)
# -----------------------------
def upload_file(file, user: str, path=None) -> str:
    """
    Uploads a file to Azure Blob Storage.

    - `path` MUST include filename if provided
    - Used for files AND .keep folder markers
    """
    if not container_client:
        raise RuntimeError("Storage not initialized")

    if path:
        clean_path = path.replace("\\", "/").lstrip("/")
        blob_name = f"users/{user}/{clean_path}"
    else:
        blob_name = f"users/{user}/{file.filename}"

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(file.stream, overwrite=True)

    return blob_name


# -----------------------------
# List All User Blobs (RAW)
# -----------------------------
def list_files(user: str):
    """
    Returns all blobs for a user.
    Folder logic is handled in app.py
    """
    if not container_client:
        return []

    prefix = f"users/{user}/"
    return container_client.list_blobs(name_starts_with=prefix)


# -----------------------------
# Generate Secure Download URL
# -----------------------------
def get_download_url(blob_name: str) -> str:
    """
    Generates a short-lived SAS URL for a single file.
    """
    if not ACCOUNT_NAME or not ACCOUNT_KEY:
        raise RuntimeError("Storage credentials unavailable")

    sas_token = generate_blob_sas(
        account_name=ACCOUNT_NAME,
        container_name=CONTAINER_NAME,
        blob_name=blob_name,
        account_key=ACCOUNT_KEY,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=5)
    )

    return (
        f"https://{ACCOUNT_NAME}.blob.core.windows.net/"
        f"{CONTAINER_NAME}/{blob_name}?{sas_token}"
    )
