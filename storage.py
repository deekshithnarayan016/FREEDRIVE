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

if not AZURE_STORAGE_CONNECTION_STRING:
    print("⚠️ AZURE_STORAGE_CONNECTION_STRING is missing")

if not CONTAINER_NAME:
    print("⚠️ CONTAINER_NAME is missing")

# -----------------------------
# Azure Blob Clients
# -----------------------------
blob_service_client = None
container_client = None

if AZURE_STORAGE_CONNECTION_STRING and CONTAINER_NAME:
    try:
        blob_service_client = BlobServiceClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING
        )

        container_client = blob_service_client.get_container_client(
            CONTAINER_NAME
        )

        # Create container if it doesn't exist
        try:
            container_client.create_container()
        except Exception:
            pass

        print("✅ Azure Blob Storage connected")

    except Exception as e:
        print("❌ Azure Blob initialization failed:", e)

# -----------------------------
# Upload File (FILES + FOLDERS)
# -----------------------------
def upload_file(file, user: str, path: str | None = None) -> str:
    if not container_client:
        raise RuntimeError("Storage not initialized")

    if path:
        # Normalize folder paths (important for Windows)
        clean_path = path.replace("\\", "/")
        blob_name = f"users/{user}/{clean_path}"
    else:
        blob_name = f"users/{user}/{file.filename}"

    blob_client = container_client.get_blob_client(blob_name)

    blob_client.upload_blob(
        file.stream,
        overwrite=True
    )

    return blob_name

# -----------------------------
# List Files
# -----------------------------
def list_files(user: str):
    if not container_client:
        return []

    prefix = f"users/{user}/"
    return container_client.list_blobs(name_starts_with=prefix)

# -----------------------------
# Generate Secure Download URL (SAS)
# -----------------------------
def get_download_url(blob_name: str) -> str:
    if not blob_service_client or not container_client:
        raise RuntimeError("Storage not initialized")

    sas_token = generate_blob_sas(
        account_name=blob_service_client.account_name,
        container_name=CONTAINER_NAME,
        blob_name=blob_name,
        account_key=blob_service_client.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=5)
    )

    return (
        f"https://{blob_service_client.account_name}.blob.core.windows.net/"
        f"{CONTAINER_NAME}/{blob_name}?{sas_token}"
    )
