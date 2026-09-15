#!/usr/bin/env python3
"""
End-to-End Pipeline: Uploads Custom Hierarchical Chunks to GCS & Ingests into Vertex AI Search.
"""

import sys
import os
import time
from google.auth import default
from google.cloud import storage, discoveryengine

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")
LOCATION = os.getenv("DISCOVERY_ENGINE_LOCATION", "global")
COLLECTION_ID = "default_collection"
DATASTORE_ID = "k8s-custom-chunks-store"
DATASTORE_DISPLAY_NAME = "Kubernetes Hierarchical Chunks"

BUCKET_NAME = "k8s-docs-fde-k8s-sandbox-dev-505119"
GCS_BLOB_PATH = "custom_chunks/k8s_chunks_custom.jsonl"
LOCAL_JSONL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts", "k8s_chunks_custom.jsonl")


def get_authenticated_clients():
    try:
        from google.auth.transport.requests import Request
        from google.api_core.exceptions import NotFound

        creds, _ = default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
            quota_project_id=PROJECT_ID
        )
        if not creds.valid:
            creds.refresh(Request())

        storage_client = storage.Client(project=PROJECT_ID, credentials=creds)
        ds_client = discoveryengine.DataStoreServiceClient(credentials=creds)
        doc_client = discoveryengine.DocumentServiceClient(credentials=creds)
        return storage_client, ds_client, doc_client
    except Exception as e:
        print(f"\n❌ [Google Cloud ADC Authentication Required] {e}")
        print("\nYour local Google Cloud Application Default Credentials (ADC) session has expired.")
        print("Please run the following command in your terminal to authenticate via browser, then re-run this script:\n")
        print("  gcloud auth application-default login --client-id-file=/Users/cuebelhoer/secure/client_secrets.json --scopes=\"https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive.readonly\"\n")
        sys.exit(1)


def upload_jsonl_to_gcs(storage_client):
    from google.api_core.exceptions import NotFound

    print("\n" + "=" * 70)
    print("=== STEP 1: UPLOADING CUSTOM CHUNKS TO GOOGLE CLOUD STORAGE ===")
    print("=" * 70)
    
    # Ensure bucket exists
    try:
        bucket = storage_client.get_bucket(BUCKET_NAME)
    except NotFound:
        print(f"Creating bucket gs://{BUCKET_NAME} in EU...")
        bucket = storage_client.create_bucket(BUCKET_NAME, location="EU")

    blob = bucket.blob(GCS_BLOB_PATH)
    print(f"Uploading {LOCAL_JSONL_PATH} -> gs://{BUCKET_NAME}/{GCS_BLOB_PATH}...")
    blob.upload_from_filename(LOCAL_JSONL_PATH, content_type="application/jsonl")
    
    # Reload blob to verify size
    blob.reload()
    print(f"✅ Upload Complete! Blob size: {blob.size:,} bytes")
    return f"gs://{BUCKET_NAME}/{GCS_BLOB_PATH}"


def get_or_create_data_store(ds_client):
    print("\n" + "=" * 70)
    print("=== STEP 2: ENSURING VERTEX AI SEARCH DATA STORE EXISTS ===")
    print("=" * 70)

    parent = f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/{COLLECTION_ID}"
    datastore_path = f"{parent}/dataStores/{DATASTORE_ID}"

    try:
        ds = ds_client.get_data_store(name=datastore_path)
        print(f"✓ Found existing Data Store: {ds.display_name} ({DATASTORE_ID})")
        return datastore_path
    except Exception:
        print(f"Creating new Data Store '{DATASTORE_ID}' with Custom Schema in Vertex AI Search...")
        
        data_store_config = discoveryengine.DataStore(
            display_name=DATASTORE_DISPLAY_NAME,
            industry_vertical=discoveryengine.IndustryVertical.GENERIC,
            solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
            content_config=discoveryengine.DataStore.ContentConfig.CONTENT_CONFIG_UNSPECIFIED,
        )

        operation = ds_client.create_data_store(
            parent=parent,
            data_store=data_store_config,
            data_store_id=DATASTORE_ID
        )
        print(f"Creating Data Store (Operation: {operation.operation.name})...")
        res = operation.result()
        print(f"✅ Data Store Created: {res.name}")
        return res.name


def import_chunks_to_vertex_search(doc_client, datastore_path, gcs_uri):
    print("\n" + "=" * 70)
    print("=== STEP 3: IMPORTING CUSTOM CHUNKS INTO VERTEX AI SEARCH ===")
    print("=" * 70)

    branch_path = f"{datastore_path}/branches/0"
    
    request = discoveryengine.ImportDocumentsRequest(
        parent=branch_path,
        gcs_source=discoveryengine.GcsSource(
            input_uris=[gcs_uri],
            data_schema="custom",  # Option A: Automatic custom schema inference
        ),
        reconciliation_mode=discoveryengine.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
    )

    print(f"Importing from: {gcs_uri}")
    print(f"Target Branch:  {branch_path}")
    print(f"Schema Mode:    custom (automatic inference)")

    operation = doc_client.import_documents(request=request)
    print(f"\n🚀 Import Operation Submitted! (ID: {operation.operation.name})")
    print("Vertex AI Search is now indexing vector embeddings and BM25 keywords...")
    
    # Wait for completion or poll
    print("\nWaiting for import completion...")
    try:
        response = operation.result(timeout=180)
        print("\n✅ IMPORT SUCCESSFUL!")
        print("Response:", response)
    except Exception as e:
        print(f"\nImport job is running asynchronously in the background. Check status in Cloud Console.")


if __name__ == "__main__":
    storage_client, ds_client, doc_client = get_authenticated_clients()
    gcs_uri = upload_jsonl_to_gcs(storage_client)
    datastore_path = get_or_create_data_store(ds_client)
    import_chunks_to_vertex_search(doc_client, datastore_path, gcs_uri)
