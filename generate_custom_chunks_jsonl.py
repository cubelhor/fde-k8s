#!/usr/bin/env python3
"""
Converts Kubernetes Markdown files into Vertex AI Search ingestion-ready JSONL format.

Format:
{"id": "<chunk_id>", "structData": {"title": "...", "breadcrumb": "...", "content": "...", ...}}
"""

import sys
import json
import os
from pathlib import Path

# Add script directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))
from test_hierarchical_chunking import HierarchyAwareChunker

OUTPUT_JSONL = "fde-k8s/k8s_chunks_custom.jsonl"
SAMPLE_DOC = "fde-k8s/website/content/en/docs/reference/access-authn-authz/admission-controllers.md"


def generate_jsonl():
    print("=" * 70)
    print("=== GENERATING VERTEX AI SEARCH CUSTOM CHUNKS JSONL ===")
    print("=" * 70)

    chunker = HierarchyAwareChunker(target_chunk_tokens=350, max_chunk_tokens=650)
    chunks = chunker.chunk_file(SAMPLE_DOC)

    print(f"✓ Parsed {SAMPLE_DOC}")
    print(f"✓ Generated {len(chunks)} hierarchical chunks.")

    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
        for c in chunks:
            record = {
                "_id": c.chunk_id,
                "title": c.doc_title,
                "breadcrumb": c.breadcrumb,
                "heading_hierarchy": c.heading_hierarchy,
                "doc_path": c.doc_path,
                "content": c.content,
                "token_estimate": c.token_estimate,
                "has_code_block": c.has_code_block,
                "has_table": c.has_table
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    file_size_kb = os.path.getsize(OUTPUT_JSONL) / 1024
    print(f"✓ Saved Vertex Search JSONL ({file_size_kb:.1f} KB) -> {OUTPUT_JSONL}\n")

    # Preview first line
    with open(OUTPUT_JSONL, "r", encoding="utf-8") as f:
        first_line = f.readline()
        print("--- Sample Ingestion Record (Line 1) ---")
        parsed = json.loads(first_line)
        print(json.dumps(parsed, indent=2)[:400] + "...\n")


if __name__ == "__main__":
    generate_jsonl()
