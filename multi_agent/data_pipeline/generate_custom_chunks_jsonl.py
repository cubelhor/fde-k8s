#!/usr/bin/env python3
"""
High-Throughput Batch Markdown Chunker for Kubernetes Documentation.
Converts all Markdown files from /website into Vertex AI Search ingestion-ready JSONL.

Output Format (JSONL):
{
  "_id": "<chunk_id>",
  "title": "<doc_title>",
  "breadcrumb": "<breadcrumb_path>",
  "heading_hierarchy": ["H1", "H2", ...],
  "doc_path": "https://kubernetes.io/docs/...",
  "url": "https://kubernetes.io/docs/...",
  "content": "### [H1 > H2]\n\n...",
  "token_estimate": 245,
  "has_code_block": true,
  "has_table": false
}
"""

import sys
import os
import re
import json
import time
import argparse
import statistics
from pathlib import Path
from typing import List, Dict, Any

# Ensure pipeline directory is in path
PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
from hierarchy_chunker import HierarchyAwareChunker, ChunkRecord

DEFAULT_DOCS_DIR = REPO_ROOT / "website" / "content" / "en" / "docs"
DEFAULT_OUTPUT_JSONL = PIPELINE_DIR / "artifacts" / "k8s_chunks_custom.jsonl"
UNUSED_OUTPUT_JSONL = REPO_ROOT / "unused" / "k8s_chunks_custom.jsonl"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch process Kubernetes documentation Markdown files into Vertex AI Search JSONL chunks."
    )
    parser.add_argument(
        "--docs-dir",
        type=str,
        default=str(DEFAULT_DOCS_DIR),
        help=f"Target documentation directory (default: {DEFAULT_DOCS_DIR})"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_OUTPUT_JSONL),
        help=f"Output JSONL path (default: {DEFAULT_OUTPUT_JSONL})"
    )
    parser.add_argument(
        "--sync-unused",
        action="store_true",
        default=True,
        help="Also sync output to unused/k8s_chunks_custom.jsonl (default: True)"
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=80,
        help="Minimum target tokens per chunk (default: 80)"
    )
    parser.add_argument(
        "--target-tokens",
        type=int,
        default=550,
        help="Target tokens per chunk (default: 550)"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1000,
        help="Maximum tokens per chunk before sub-splitting (default: 1000)"
    )
    return parser.parse_args()


def process_documentation(
    docs_dir: Path,
    output_path: Path,
    min_tokens: int = 80,
    target_tokens: int = 550,
    max_tokens: int = 1000,
    sync_unused: bool = True
):
    print("=" * 80)
    print("=== KUBERNETES DOCUMENTATION BATCH HIERARCHICAL CHUNKER ===")
    print("=" * 80)
    print(f"📁 Source Directory: {docs_dir}")
    print(f"📄 Target Output:    {output_path}")
    print(f"⚙️  Budget Limits:    min={min_tokens}, target={target_tokens}, max={max_tokens} tokens")
    print("-" * 80)

    if not docs_dir.exists():
        raise FileNotFoundError(f"Documentation directory not found: {docs_dir}")

    # Discover all .md files
    md_files = sorted(docs_dir.rglob("*.md"))
    total_files = len(md_files)
    print(f"🔍 Discovered {total_files:,} Markdown documentation files.")

    if total_files == 0:
        print("⚠️ No Markdown files found. Exiting.")
        return

    chunker = HierarchyAwareChunker(
        min_chunk_tokens=min_tokens,
        target_chunk_tokens=target_tokens,
        max_chunk_tokens=max_tokens
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    total_chunks = 0
    all_token_counts: List[int] = []
    code_block_count = 0
    table_count = 0
    errors: List[Dict[str, str]] = []
    seen_ids = set()
    duplicate_ids: List[str] = []

    print("\n🚀 Starting batch hierarchical chunking...")
    with open(output_path, "w", encoding="utf-8") as out_f:
        for idx, file_path in enumerate(md_files, 1):
            try:
                chunks: List[ChunkRecord] = chunker.chunk_file(str(file_path))
                for c in chunks:
                    if c.chunk_id in seen_ids:
                        duplicate_ids.append(c.chunk_id)
                    seen_ids.add(c.chunk_id)

                    record = {
                        "id": c.chunk_id,
                        "_id": c.chunk_id,
                        "title": c.doc_title,
                        "breadcrumb": c.breadcrumb,
                        "heading_hierarchy": c.heading_hierarchy,
                        "uri": c.url,
                        "url": c.url,
                        "doc_path": c.doc_path,
                        "content": c.content,
                        "token_estimate": c.token_estimate,
                        "has_code_block": c.has_code_block,
                        "has_table": c.has_table
                    }
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")

                    total_chunks += 1
                    all_token_counts.append(c.token_estimate)
                    if c.has_code_block:
                        code_block_count += 1
                    if c.has_table:
                        table_count += 1

            except Exception as exc:
                errors.append({"file": str(file_path), "error": str(exc)})

            if idx % 250 == 0 or idx == total_files:
                elapsed_so_far = time.time() - start_time
                rate = idx / max(0.001, elapsed_so_far)
                print(f"   [{idx:>4}/{total_files}] files processed ({rate:.1f} files/s) | {total_chunks:>6} chunks generated...")

    total_time = time.time() - start_time
    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)

    # Optional sync to unused/k8s_chunks_custom.jsonl
    if sync_unused and UNUSED_OUTPUT_JSONL.parent.exists():
        import shutil
        shutil.copyfile(output_path, UNUSED_OUTPUT_JSONL)
        print(f"✓ Synced output to: {UNUSED_OUTPUT_JSONL}")

    print("\n" + "=" * 80)
    print("=== BATCH CHUNKING COMPLETE ===")
    print("=" * 80)
    print(f"⏱️  Total Processing Time:  {total_time:.2f} seconds ({total_files / total_time:.1f} files/sec)")
    print(f"📄 Total Documents Parsed: {total_files:,}")
    print(f"🧩 Total Chunks Generated: {total_chunks:,} ({total_chunks / max(1, total_files):.1f} chunks/doc)")
    print(f"💾 Output File Size:       {file_size_mb:.2f} MB ({output_path})")
    print(f"🔑 Unique Chunk IDs:       {len(seen_ids):,} (Duplicates: {len(duplicate_ids)})")
    print(f"💻 Chunks with Code Blocks: {code_block_count:,} ({code_block_count / max(1, total_chunks) * 100:.1f}%)")
    print(f"📊 Chunks with Tables:      {table_count:,} ({table_count / max(1, total_chunks) * 100:.1f}%)")
    print(f"⚠️  Parsing Errors:         {len(errors)}")

    if all_token_counts:
        quantiles = statistics.quantiles(all_token_counts, n=4)
        print("\n📈 Token Distribution Summary:")
        print(f"   • Min:    {min(all_token_counts):>5} tokens")
        print(f"   • 25%:    {quantiles[0]:>5.0f} tokens")
        print(f"   • Median: {quantiles[1]:>5.0f} tokens")
        print(f"   • 75%:    {quantiles[2]:>5.0f} tokens")
        print(f"   • Max:    {max(all_token_counts):>5} tokens")
        print(f"   • Mean:   {statistics.mean(all_token_counts):>5.0f} tokens")
        print(f"   • Total Estimated Tokens: {sum(all_token_counts):,} tokens")

    if errors:
        print("\n❌ Errors:")
        for err in errors[:5]:
            print(f"   • {err['file']}: {err['error']}")

    # Verification: Read line 1 and line 53
    print("\n" + "-" * 80)
    print("🔍 Sample Ingestion Record Verification:")
    with open(output_path, "r", encoding="utf-8") as f:
        first_line = f.readline()
        parsed_first = json.loads(first_line)
        print(f"Record #1: ID='{parsed_first.get('_id')}', Title='{parsed_first.get('title')}', Tokens={parsed_first.get('token_estimate')}")
        print(f"           URL={parsed_first.get('url')}")
        print(f"           Breadcrumb='{parsed_first.get('breadcrumb')}'")

    print("-" * 80)
    print("✅ Ready for Vertex AI Search ingestion!")


if __name__ == "__main__":
    args = parse_args()
    process_documentation(
        docs_dir=Path(args.docs_dir),
        output_path=Path(args.output),
        min_tokens=args.min_tokens,
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
        sync_unused=args.sync_unused
    )
