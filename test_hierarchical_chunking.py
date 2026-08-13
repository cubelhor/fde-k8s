#!/usr/bin/env python3
"""
Interactive Hierarchical Chunking Test Suite for Kubernetes Documentation.
Specifically configured for: admission-controllers.md

Features:
1. Hugo Shortcode Sanitization (glossary_tooltip, skew, notes, figures).
2. Hierarchy-Aware AST Chunking with Ancestor Breadcrumb Injection.
3. Code Block & Table Integrity Preservation.
4. Exports all structured chunks to 'fde-k8s/admission_controllers_chunks.json'.
5. Built-in Interactive & CLI Search Simulator for Testing.
"""

import sys
import os
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict, field


# ============================================================================
# 1. HUGO SHORTCODE SANITIZER
# ============================================================================

class HugoShortcodeSanitizer:
    """Cleans Hugo templating macros into readable, plain Markdown for chunking."""

    @classmethod
    def sanitize(cls, text: str) -> str:
        # 1. Convert glossary tooltips: {{< glossary_tooltip text="API server" term_id="kube-apiserver" >}} -> "API server"
        text = re.sub(
            r'\{\{<\s*glossary_tooltip\s+[^>]*text="([^"]+)"[^>]*>\}\}',
            r'\1',
            text
        )
        text = re.sub(
            r'\{\{<\s*glossary_tooltip\s+[^>]*term_id="([^"]+)"[^>]*>\}\}',
            r'\1',
            text
        )

        # 2. Convert note / warning / caution callouts
        text = re.sub(r'\{\{<\s*note\s*>\}\}', r'\n> **Note:** ', text)
        text = re.sub(r'\{\{<\s*/note\s*>\}\}', r'\n', text)
        text = re.sub(r'\{\{<\s*warning\s*>\}\}', r'\n> **Warning:** ', text)
        text = re.sub(r'\{\{<\s*/warning\s*>\}\}', r'\n', text)
        text = re.sub(r'\{\{<\s*caution\s*>\}\}', r'\n> **Caution:** ', text)
        text = re.sub(r'\{\{<\s*/caution\s*>\}\}', r'\n', text)

        # 3. Convert feature states: {{< feature-state for_k8s_version="v1.30" state="stable" >}}
        text = re.sub(
            r'\{\{<\s*feature-state\s+[^>]*state="([^"]+)"[^>]*>\}\}',
            r'[Feature State: \1]',
            text
        )
        text = re.sub(
            r'\{\{<\s*feature-state\s+[^>]*feature_gate_name="([^"]+)"[^>]*>\}\}',
            r'[Feature Gate: \1]',
            text
        )

        # 4. Clean skew and version tags
        text = re.sub(r'\{\{<\s*skew\s+currentVersion\s*>\}\}', 'v1.32', text)
        text = re.sub(r'\{\{<\s*skew\s+[^>]*>\}\}', '', text)

        # 5. Clean figures & diagrams
        text = re.sub(r'\{\{<\s*figure\s+[^>]*alt="([^"]+)"[^>]*>\}\}', r'![Diagram: \1]', text)
        text = re.sub(r'\{\{<\s*figure\s+[^>]*>\}\}', '', text)

        # 6. Remove remaining unhandled shortcodes
        text = re.sub(r'\{\{[%<].*?[%>]\}\}', '', text)

        # 7. Remove section markers like <!-- overview --> and <!-- body -->
        text = re.sub(r'<!--\s*(overview|body|whatsnext|seealso)\s*-->', '', text)

        return text


# ============================================================================
# 2. HIERARCHY-AWARE AST CHUNKER
# ============================================================================

@dataclass
class ChunkRecord:
    chunk_id: str
    doc_path: str
    doc_title: str
    heading_hierarchy: List[str]
    breadcrumb: str
    content: str
    token_estimate: int
    char_count: int
    has_code_block: bool
    has_table: bool


class HierarchyAwareChunker:
    """Parses Markdown into a hierarchical heading tree with ancestor context."""

    HEADING_REGEX = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
    FRONTMATTER_REGEX = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def __init__(self, target_chunk_tokens: int = 400, max_chunk_tokens: int = 750):
        self.target_chunk_tokens = target_chunk_tokens
        self.max_chunk_tokens = max_chunk_tokens

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def extract_frontmatter(self, text: str) -> Tuple[Dict[str, str], str]:
        match = self.FRONTMATTER_REGEX.match(text)
        meta = {}
        if match:
            fm_text = match.group(1)
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip("'\"")
            return meta, text[match.end():]
        return meta, text

    def chunk_file(self, file_path: str) -> List[ChunkRecord]:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        # Step 1: Frontmatter Extraction
        meta, body = self.extract_frontmatter(raw_content)
        doc_title = meta.get("title") or meta.get("linkTitle") or "Admission Control in Kubernetes"

        # Step 2: Hugo Shortcode Sanitization
        sanitized_body = HugoShortcodeSanitizer.sanitize(body)

        # Step 3: AST Heading Hierarchy Traversal
        lines = sanitized_body.splitlines()
        chunks: List[ChunkRecord] = []
        heading_stack = [{"level": 1, "title": doc_title}]
        current_body = []
        chunk_counter = 1
        in_code_block = False

        def flush_chunk():
            nonlocal chunk_counter
            if not current_body:
                return
            body_text = "\n".join(current_body).strip()
            if not body_text:
                return

            breadcrumb_str = " > ".join([h["title"] for h in heading_stack])
            est_tokens = self.estimate_tokens(body_text)

            # If section fits in token budget -> Emit single chunk
            if est_tokens <= self.max_chunk_tokens:
                header_prefix = f"### [{breadcrumb_str}]\n\n"
                full_text = f"{header_prefix}{body_text}"
                
                chunks.append(ChunkRecord(
                    chunk_id=f"admission_ctrl_chunk_{chunk_counter:03d}",
                    doc_path=file_path,
                    doc_title=doc_title,
                    heading_hierarchy=[h["title"] for h in heading_stack],
                    breadcrumb=breadcrumb_str,
                    content=full_text,
                    token_estimate=self.estimate_tokens(full_text),
                    char_count=len(full_text),
                    has_code_block="```" in full_text,
                    has_table="|" in full_text
                ))
                chunk_counter += 1
            else:
                # Sub-split oversized sections by paragraphs while preserving breadcrumbs
                paragraphs = re.split(r"\n\n+", body_text)
                sub_groups = []
                curr_group = []
                curr_toks = 0

                for p in paragraphs:
                    p_toks = self.estimate_tokens(p)
                    if curr_toks + p_toks > self.target_chunk_tokens and curr_group:
                        sub_groups.append("\n\n".join(curr_group).strip())
                        curr_group = [p]
                        curr_toks = p_toks
                    else:
                        curr_group.append(p)
                        curr_toks += p_toks
                if curr_group:
                    sub_groups.append("\n\n".join(curr_group).strip())

                for p_idx, p_text in enumerate(sub_groups, 1):
                    suffix = f" (Part {p_idx}/{len(sub_groups)})" if len(sub_groups) > 1 else ""
                    breadcrumb_with_suffix = f"{breadcrumb_str}{suffix}"
                    header_prefix = f"### [{breadcrumb_with_suffix}]\n\n"
                    full_text = f"{header_prefix}{p_text}"

                    chunks.append(ChunkRecord(
                        chunk_id=f"admission_ctrl_chunk_{chunk_counter:03d}",
                        doc_path=file_path,
                        doc_title=doc_title,
                        heading_hierarchy=[h["title"] for h in heading_stack],
                        breadcrumb=breadcrumb_with_suffix,
                        content=full_text,
                        token_estimate=self.estimate_tokens(full_text),
                        char_count=len(full_text),
                        has_code_block="```" in full_text,
                        has_table="|" in full_text
                    ))
                    chunk_counter += 1

        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block

            header_match = self.HEADING_REGEX.match(line) if not in_code_block else None
            if header_match:
                flush_chunk()
                current_body = []

                level = len(header_match.group(1))
                raw_title = header_match.group(2).strip()
                clean_title = re.sub(r"\{#[^}]+\}", "", raw_title).strip()

                # Maintain heading stack
                heading_stack = [h for h in heading_stack if h["level"] < level]
                heading_stack.append({"level": level, "title": clean_title})
            else:
                current_body.append(line)

        flush_chunk()
        return chunks


# ============================================================================
# 3. INTERACTIVE & CLI QUERY DEMONSTRATOR
# ============================================================================

def search_chunks(chunks: List[ChunkRecord], query: str, top_k: int = 3) -> List[Tuple[ChunkRecord, float]]:
    """Simulates hybrid ranking over the hierarchical chunks."""
    query_terms = [q.lower() for q in re.findall(r"\w+", query)]
    scored = []

    for chk in chunks:
        score = 0.0
        text_lower = chk.content.lower()
        breadcrumb_lower = chk.breadcrumb.lower()

        # Breadcrumb matches have 3x weight
        for term in query_terms:
            if term in breadcrumb_lower:
                score += 3.0
            if term in text_lower:
                score += 1.0 + (text_lower.count(term) * 0.2)

        # Exact phrase bonus
        if query.lower() in text_lower:
            score += 5.0

        if score > 0:
            scored.append((chk, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def run_demo(query_override: str = None):
    doc_path = "fde-k8s/website/content/en/docs/reference/access-authn-authz/admission-controllers.md"
    output_json = "fde-k8s/admission_controllers_chunks.json"

    print("=" * 80)
    print("=== HIERARCHY-AWARE CHUNKING TEST BENCHMARK ===")
    print("=" * 80)
    print(f"Target Document: {doc_path}")

    chunker = HierarchyAwareChunker(target_chunk_tokens=350, max_chunk_tokens=650)
    chunks = chunker.chunk_file(doc_path)

    # Save to JSON
    json_data = [asdict(c) for c in chunks]
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)

    print(f"✓ Generated {len(chunks)} Hierarchical Chunks.")
    print(f"✓ Exported all chunks with metadata to: {output_json}\n")

    # Display Chunk Summary Statistics
    total_tokens = sum(c.token_estimate for c in chunks)
    avg_tokens = total_tokens / len(chunks)
    code_chunks = sum(1 for c in chunks if c.has_code_block)
    table_chunks = sum(1 for c in chunks if c.has_table)

    print("📊 Chunk Statistics:")
    print(f"   • Total Estimated Tokens: {total_tokens:,}")
    print(f"   • Average Tokens / Chunk: {avg_tokens:.1f}")
    print(f"   • Chunks with Code Blocks: {code_chunks}")
    print(f"   • Chunks with Tables:      {table_chunks}")
    print("-" * 80)

    # Test Queries
    test_queries = [
        "What are the two phases of admission control?",
        "Does admission control block read requests?",
        "How to configure ValidatingAdmissionPolicy?",
        "What is MutatingAdmissionWebhook?"
    ]

    if query_override:
        test_queries = [query_override]

    print("\n🔍 EXECUTING RETRIEVAL DEMO ON HIERARCHICAL CHUNKS:")
    print("-" * 80)

    for q_idx, q in enumerate(test_queries, 1):
        print(f"\n[Test Query #{q_idx}] '{q}'")
        matches = search_chunks(chunks, q, top_k=2)
        if not matches:
            print("   ❌ No match found.")
            continue

        for m_idx, (chk, score) in enumerate(matches, 1):
            print(f"   🏆 Match #{m_idx} (Score: {score:.1f}) | ID: {chk.chunk_id}")
            print(f"      📍 Breadcrumb: {chk.breadcrumb}")
            print(f"      📏 Size:       {chk.token_estimate} tokens ({chk.char_count} chars)")
            print(f"      📄 Content Excerpt:\n         " + chk.content.replace("\n", "\n         ")[:240] + "...\n")

    print("=" * 80)
    print("To test any custom query, run:")
    print("python3 fde-k8s/test_hierarchical_chunking.py --query \"your question here\"")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Hierarchy-Aware Chunking on admission-controllers.md")
    parser.add_argument("--query", type=str, default=None, help="Custom search query to test retrieval")
    args = parser.parse_args()
    run_demo(query_override=args.query)
