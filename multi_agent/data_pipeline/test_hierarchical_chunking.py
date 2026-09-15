#!/usr/bin/env python3
"""
Hierarchical Chunking Test & Retrieval Verification Suite.

Tests the HierarchyAwareChunker algorithm and evaluates retrieval precision
on either a single canary document or across the entire generated JSONL corpus.

Usage:
  # 1. Test single canary document (admission-controllers.md)
  python3 multi_agent/data_pipeline/test_hierarchical_chunking.py

  # 2. Test search across the entire 17,539-chunk corpus
  python3 multi_agent/data_pipeline/test_hierarchical_chunking.py --corpus

  # 3. Test a custom ad-hoc search query on the full corpus
  python3 multi_agent/data_pipeline/test_hierarchical_chunking.py --corpus --query "How to fix CrashLoopBackOff?"
"""

import sys
import os
import re
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import asdict

# Import core chunking engine from canonical library module
PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
from hierarchy_chunker import HierarchyAwareChunker, ChunkRecord, HugoShortcodeSanitizer


# ============================================================================
# 1. IN-MEMORY HYBRID SEARCH SIMULATOR
# ============================================================================

def search_chunks(chunks: List[ChunkRecord], query: str, top_k: int = 3) -> List[Tuple[ChunkRecord, float]]:
    """Simulates hybrid ranking over hierarchical chunks with breadcrumb weighting."""
    raw_terms = re.findall(r"[A-Za-z0-9_]+", query)
    query_terms = [q.lower() for q in raw_terms if len(q) > 2]
    scored = []

    for chk in chunks:
        score = 0.0
        text_lower = chk.content.lower()
        breadcrumb_lower = chk.breadcrumb.lower()

        # High weight for technical identifiers in breadcrumb
        for term in raw_terms:
            if len(term) > 3 and term.lower() in breadcrumb_lower:
                score += 15.0
            if term.lower() in text_lower:
                score += 2.0

        for q in query_terms:
            if q in breadcrumb_lower:
                score += 4.0
            if q in text_lower:
                score += 1.0 + (text_lower.count(q) * 0.1)

        # Exact phrase bonus
        if query.lower() in text_lower:
            score += 10.0

        if score > 0:
            scored.append((chk, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


# ============================================================================
# 2. TEST RUNNER & BENCHMARK DEMO
# ============================================================================

def run_demo(query_override: str = None, target_file: str = None, use_full_corpus: bool = False):
    default_doc = REPO_ROOT / "website" / "content" / "en" / "docs" / "reference" / "access-authn-authz" / "admission-controllers.md"
    doc_path = target_file if target_file else str(default_doc)
    output_json = str(PIPELINE_DIR / "artifacts" / "admission_controllers_chunks.json")
    corpus_jsonl = PIPELINE_DIR / "artifacts" / "k8s_chunks_custom.jsonl"

    print("=" * 80)
    print("=== HIERARCHY-AWARE CHUNKING TEST & RETRIEVAL SUITE ===")
    print("=" * 80)

    # 1. Single Document Canary Benchmark
    print(f"📄 Canary Document: {doc_path}")
    chunker = HierarchyAwareChunker(min_chunk_tokens=60, target_chunk_tokens=350, max_chunk_tokens=650)
    chunks = chunker.chunk_file(doc_path)

    # Export to JSON
    json_data = [asdict(c) for c in chunks]
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)

    total_tokens = sum(c.token_estimate for c in chunks)
    avg_tokens = total_tokens / len(chunks)
    code_chunks = sum(1 for c in chunks if c.has_code_block)
    table_chunks = sum(1 for c in chunks if c.has_table)

    print(f"✓ Generated {len(chunks)} Hierarchical Chunks.")
    print(f"✓ Exported canary chunks with metadata to: {output_json}\n")
    print("📊 Canary Chunk Statistics:")
    print(f"   • Total Estimated Tokens: {total_tokens:,}")
    print(f"   • Average Tokens / Chunk: {avg_tokens:.1f}")
    print(f"   • Chunks with Code Blocks: {code_chunks}")
    print(f"   • Chunks with Tables:      {table_chunks}")
    print("-" * 80)

    # 2. Target Chunks Selection (Canary vs Full Corpus)
    if use_full_corpus and corpus_jsonl.exists():
        print(f"🌐 Loading Entire Generated Corpus from: {corpus_jsonl.name}...")
        t_load = time.time()
        search_target_chunks = []
        with open(corpus_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    search_target_chunks.append(ChunkRecord(
                        chunk_id=rec.get("_id", ""),
                        doc_path=rec.get("doc_path", ""),
                        doc_title=rec.get("title", ""),
                        heading_hierarchy=rec.get("heading_hierarchy", []),
                        breadcrumb=rec.get("breadcrumb", ""),
                        content=rec.get("content", ""),
                        token_estimate=rec.get("token_estimate", 0),
                        char_count=len(rec.get("content", "")),
                        has_code_block=rec.get("has_code_block", False),
                        has_table=rec.get("has_table", False),
                        url=rec.get("url", "")
                    ))
        print(f"✓ Loaded {len(search_target_chunks):,} Chunks in {time.time() - t_load:.2f}s!")
        test_queries = [
            "What are the two phases of admission control?",
            "How do I fix CrashLoopBackOff for a pod?",
            "What is CoreDNS and how does cluster DNS work?",
            "How do I configure persistent volume claim with StorageClass?",
            "Which admission controller replaced PodSecurityPolicy in Kubernetes?"
        ]
    else:
        search_target_chunks = chunks
        test_queries = [
            "What are the two phases of admission control?",
            "Does admission control block read requests?",
            "How to configure ValidatingAdmissionPolicy?",
            "What is MutatingAdmissionWebhook?"
        ]

    if query_override:
        test_queries = [query_override]

    scope_name = f"ENTIRE CORPUS ({len(search_target_chunks):,} chunks)" if use_full_corpus else f"CANARY DOC ({len(chunks)} chunks)"
    print(f"\n🔍 EXECUTING RETRIEVAL DEMO ON: {scope_name}")
    print("-" * 80)

    for q_idx, q in enumerate(test_queries, 1):
        t_query = time.time()
        matches = search_chunks(search_target_chunks, q, top_k=2)
        q_latency_ms = (time.time() - t_query) * 1000

        print(f"\n[Test Query #{q_idx}] '{q}' ({q_latency_ms:.1f}ms)")
        if not matches:
            print("   ❌ No match found.")
            continue

        for m_idx, (chk, score) in enumerate(matches, 1):
            print(f"   🏆 Match #{m_idx} (Score: {score:.1f}) | ID: {chk.chunk_id}")
            print(f"      📍 Breadcrumb: {chk.breadcrumb}")
            print(f"      🔗 URL:        {chk.url}")
            print(f"      📏 Size:       {chk.token_estimate} tokens ({chk.char_count} chars)")
            print(f"      📄 Content Excerpt:\n         " + chk.content.replace("\n", "\n         ")[:220] + "...\n")

    print("=" * 80)
    print("To test against the entire corpus, run:")
    print("python3 multi_agent/data_pipeline/test_hierarchical_chunking.py --corpus")
    print("To test a custom query, add: --query \"your question here\"")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Hierarchy-Aware Chunking & Retrieval.")
    parser.add_argument("--query", type=str, default=None, help="Custom search query to test retrieval")
    parser.add_argument("--file", type=str, default=None, help="Path to specific Markdown document to chunk")
    parser.add_argument("--corpus", action="store_true", default=False, help="Search across the entire generated JSONL corpus")
    args = parser.parse_args()
    run_demo(query_override=args.query, target_file=args.file, use_full_corpus=args.corpus)
