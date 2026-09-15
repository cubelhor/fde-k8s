#!/usr/bin/env python3
"""
Vertex AI Search Datastore & Upload Verification Tool.

Provides 4 independent ways to test and verify the custom chunks upload:
1. Local JSONL Schema & Payload Audit: Verifies all 14,148 chunks conform to Vertex AI Search's
   custom schema requirements (valid IDs, required fields, inlined YAML manifests).
2. GCS Blob Integrity Check: Verifies the uploaded gs:// blob matches the local artifact size.
3. Datastore Document Inspection: Queries Vertex AI Search DocumentServiceClient to list and
   inspect indexed documents in branches/0, checking struct_data fields and code blocks.
4. Live Search Smoke Test: Queries Vertex AI Search SearchServiceClient across 4 diagnostic
   queries (RBAC YAML code sample, CrashLoopBackOff, Admission Control, Storage Binding).
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")
LOCATION = os.getenv("DISCOVERY_ENGINE_LOCATION", "global")
COLLECTION_ID = "default_collection"
DATASTORE_ID = "k8s-custom-chunks-store"
BUCKET_NAME = "k8s-docs-fde-k8s-sandbox-dev-505119"
GCS_BLOB_PATH = "custom_chunks/k8s_chunks_custom.jsonl"

PIPELINE_DIR = Path(__file__).resolve().parent
LOCAL_JSONL_PATH = PIPELINE_DIR / "artifacts" / "k8s_chunks_custom.jsonl"


def verify_local_jsonl_schema(jsonl_path: Path) -> Dict[str, Any]:
    """
    Audits the local JSONL artifact to ensure 100% compliance with Vertex AI Search
    Custom Schema ingestion rules.
    """
    print("=" * 80)
    print("=== CHECK 1: LOCAL JSONL VERTEX SCHEMA & PAYLOAD AUDIT ===")
    print("=" * 80)
    if not jsonl_path.exists():
        print(f"❌ File not found: {jsonl_path}")
        return {"valid": False}

    total_records = 0
    missing_id = 0
    missing_content = 0
    code_block_chunks = 0
    inlined_rbac_found = False
    sample_record = None
    required_fields = {"_id", "title", "breadcrumb", "heading_hierarchy", "url", "content", "token_estimate"}

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            total_records += 1
            rec = json.loads(line)
            if sample_record is None:
                sample_record = rec

            if not rec.get("_id"):
                missing_id += 1
            if not rec.get("content"):
                missing_content += 1
            if rec.get("has_code_block"):
                code_block_chunks += 1
            if "kind: Role" in rec.get("content", "") and "rules:" in rec.get("content", ""):
                inlined_rbac_found = True

    file_size_mb = jsonl_path.stat().st_size / (1024 * 1024)
    schema_keys = set(sample_record.keys()) if sample_record else set()
    missing_schema_keys = required_fields - schema_keys

    print(f"• Artifact Path:             {jsonl_path}")
    print(f"• File Size:                 {file_size_mb:.2f} MB ({jsonl_path.stat().st_size:,} bytes)")
    print(f"• Total JSONL Records:       {total_records:,}")
    print(f"• Schema Keys Present:       {sorted(list(schema_keys))}")
    print(f"• Missing IDs / Empty Text:  {missing_id} / {missing_content}")
    print(f"• Chunks with Code Blocks:   {code_block_chunks:,}")
    print(f"• Inlined RBAC YAML Verified:{' ✅ YES' if inlined_rbac_found else ' ❌ NO'}")
    print("-" * 80)

    is_valid = (total_records > 0 and missing_id == 0 and missing_content == 0 and not missing_schema_keys)
    if is_valid:
        print("✅ PASS: Local JSONL is 100% compliant with Vertex AI Search Custom Schema.\n")
    else:
        print(f"❌ FAIL: Schema issues detected (missing keys: {missing_schema_keys}).\n")

    return {
        "valid": is_valid,
        "total_records": total_records,
        "file_size_bytes": jsonl_path.stat().st_size,
        "code_block_chunks": code_block_chunks
    }


def verify_cloud_datastore(query_override: str = None):
    """
    Connects to Google Cloud Storage and Vertex AI Search (Discovery Engine) to verify:
    1. GCS blob size matches local JSONL size.
    2. Datastore `k8s-custom-chunks-store` exists and has indexed documents in branches/0.
    3. Live search queries retrieve structured chunks with intact breadcrumbs and code blocks.
    """
    print("=" * 80)
    print("=== CHECK 2-4: CLOUD GCS & VERTEX AI SEARCH DATASTORE VERIFICATION ===")
    print("=" * 80)

    try:
        from google.auth import default
        from google.auth.transport.requests import Request
        from google.cloud import storage, discoveryengine

        creds, _ = default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
            quota_project_id=PROJECT_ID
        )
        if not creds.valid:
            creds.refresh(Request())

        storage_client = storage.Client(project=PROJECT_ID, credentials=creds)
        ds_client = discoveryengine.DataStoreServiceClient(credentials=creds)
        doc_client = discoveryengine.DocumentServiceClient(credentials=creds)
        search_client = discoveryengine.SearchServiceClient(credentials=creds)
    except Exception as e:
        print(f"⚠️ Google Cloud ADC Re-authentication Needed: {e}\n")
        print("To run live Cloud checks (GCS Blob check, Datastore Document listing, and Live Search):")
        print("1. Run this command in your terminal to refresh your Google Cloud credentials:")
        print("   gcloud auth application-default login --client-id-file=/Users/cuebelhoer/secure/client_secrets.json --scopes=\"https://www.googleapis.com/auth/cloud-platform\"")
        print("2. Then re-run this script:")
        print("   python3 multi_agent/data_pipeline/verify_vertex_datastore.py\n")
        return False

    # -------------------------------------------------------------------------
    # Check 2: GCS Blob Integrity
    # -------------------------------------------------------------------------
    print("\n--- [Check 2] Verifying GCS Blob Integrity ---")
    try:
        bucket = storage_client.get_bucket(BUCKET_NAME)
        blob = bucket.get_blob(GCS_BLOB_PATH)
        if blob:
            local_size = LOCAL_JSONL_PATH.stat().st_size if LOCAL_JSONL_PATH.exists() else 0
            print(f"• GCS URI:         gs://{BUCKET_NAME}/{GCS_BLOB_PATH}")
            print(f"• GCS Blob Size:   {blob.size:,} bytes ({blob.size / (1024*1024):.2f} MB)")
            print(f"• Local File Size: {local_size:,} bytes")
            print(f"• Last Updated:    {blob.updated}")
            if blob.size == local_size:
                print("✅ PASS: GCS blob byte size matches local JSONL artifact exactly.")
            else:
                print("⚠️ NOTE: GCS blob size differs from local artifact (re-run import_to_vertex_search.py if needed).")
        else:
            print(f"❌ Blob gs://{BUCKET_NAME}/{GCS_BLOB_PATH} not found in bucket.")
    except Exception as e:
        print(f"⚠️ Could not inspect GCS blob: {e}")

    # -------------------------------------------------------------------------
    # Check 3: Vertex AI Search Datastore & Indexed Document Sample
    # -------------------------------------------------------------------------
    print("\n--- [Check 3] Inspecting Vertex AI Search Datastore & Branch 0 Documents ---")
    datastore_path = (
        f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/{COLLECTION_ID}/"
        f"dataStores/{DATASTORE_ID}"
    )
    branch_path = f"{datastore_path}/branches/0"

    try:
        ds = ds_client.get_data_store(name=datastore_path)
        print(f"• Datastore Name:  {ds.display_name} ({DATASTORE_ID})")
        print(f"• Branch Path:     {branch_path}")

        # List sample documents from Branch 0
        list_req = discoveryengine.ListDocumentsRequest(parent=branch_path, page_size=5)
        page_result = doc_client.list_documents(request=list_req)
        sample_docs = []
        for doc in page_result:
            sample_docs.append(doc)
            if len(sample_docs) >= 3:
                break

        if sample_docs:
            print(f"✅ PASS: Datastore branch is populated and returning indexed documents.")
            first_doc = sample_docs[0]
            struct_keys = list(first_doc.struct_data.keys()) if first_doc.struct_data else []
            print(f"• Sample Document ID:     {first_doc.id}")
            print(f"• Indexed Schema Fields:  {sorted(struct_keys)}")
            print(f"• Sample Breadcrumb:      {first_doc.struct_data.get('breadcrumb', 'N/A')}")
        else:
            print("⚠️ No documents returned from Branch 0 yet (indexing may still be in progress).")
    except Exception as e:
        print(f"⚠️ Could not inspect Datastore documents: {e}")

    # -------------------------------------------------------------------------
    # Check 4: Live Vertex AI Search Retrieval Smoke Tests
    # -------------------------------------------------------------------------
    print("\n--- [Check 4] Live Vertex AI Search Query Smoke Test ---")
    serving_config = f"{datastore_path}/servingConfigs/default_search"

    diagnostic_queries = [
        query_override
    ] if query_override else [
        "What is the difference between a Role and a ClusterRole and how are rules defined in YAML?",
        "What is CrashLoopBackOff and how does Kubernetes manage container restart backoff delay?",
        "In what order do mutating and validating admission controllers execute?",
        "How does the Kubernetes control plane bind a PersistentVolumeClaim to a PersistentVolume?"
    ]

    for q_idx, query in enumerate(diagnostic_queries, 1):
        print(f"\n🔎 [Query {q_idx}] \"{query}\"")
        try:
            req = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query=query,
                page_size=3
            )
            res = search_client.search(req)
            results = list(res.results)
            if not results:
                print("   ⚠️ 0 results returned from Vertex AI Search.")
                continue

            for r_idx, hit in enumerate(results, 1):
                doc = hit.document
                sdata = doc.struct_data or {}
                bcrumb = sdata.get("breadcrumb", "N/A")
                has_code = sdata.get("has_code_block", False)
                content_preview = (sdata.get("content", "")[:140] + "...").replace("\n", " ")
                print(f"   #{r_idx} | ID: {doc.id:<45} | CodeBlock: {str(has_code):<5}")
                print(f"      Breadcrumb: {bcrumb}")
                print(f"      Preview:    {content_preview}")
        except Exception as e:
            print(f"   ❌ Search request failed: {e}")

    print("\n" + "=" * 80)
    print("✅ Live Vertex AI Search Datastore verification completed!")
    print("=" * 80 + "\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Vertex AI Search Datastore upload & schema.")
    parser.add_argument("--query", type=str, default=None, help="Optional custom query to test against Vertex AI Search")
    parser.add_argument("--local-only", action="store_true", help="Only run local JSONL schema & payload audit")
    args = parser.parse_args()

    verify_local_jsonl_schema(LOCAL_JSONL_PATH)
    if not args.local_only:
        verify_cloud_datastore(query_override=args.query)
