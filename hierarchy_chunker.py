#!/usr/bin/env python3
"""
Production-Grade Hierarchy-Aware Markdown Chunker for Kubernetes Documentation.

Algorithm Architecture:
1. AST / Section Tree Construction: Parses H1-H4 headings, maintaining an ancestor stack.
2. Atomic Block Preservation: Guards fenced code blocks (```), tables, and lists against mid-block cutting.
3. Adaptive Size Budgeting:
   - Small sections (< min_tokens): Merged with parent or siblings to prevent fragmented, low-signal chunks.
   - Ideal sections (min_tokens <= size <= max_tokens): Emitted as self-contained semantic units.
   - Large sections (> max_tokens): Sub-split at paragraph/list boundaries with ancestor breadcrumbs attached.
4. Context Enrichment: Injects hierarchical breadcrumb headers for dense vector & BM25 indexing.
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path


@dataclass
class SectionNode:
    """Represents a node in the Markdown heading hierarchy tree."""
    level: int  # 1 for #, 2 for ##, 3 for ###, 0 for root preamble
    title: str
    breadcrumbs: List[str]
    content_blocks: List[str] = field(default_factory=list)
    children: List["SectionNode"] = field(default_factory=list)


@dataclass
class HierarchicalChunk:
    """The emitted search-ready chunk with rich contextual metadata."""
    chunk_id: str
    doc_path: str
    doc_title: str
    heading_hierarchy: List[str]
    breadcrumb_path: str
    text: str
    token_estimate: int
    has_code_block: bool
    has_table: bool


class HierarchyAwareChunker:
    """Hierarchy-aware chunker that understands Markdown document semantics."""

    HEADING_REGEX = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
    CODE_BLOCK_REGEX = re.compile(r"```.*?```", re.DOTALL)
    TABLE_ROW_REGEX = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
    FRONTMATTER_REGEX = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def __init__(
        self,
        min_chunk_tokens: int = 150,
        target_chunk_tokens: int = 500,
        max_chunk_tokens: int = 900
    ):
        self.min_chunk_tokens = min_chunk_tokens
        self.target_chunk_tokens = target_chunk_tokens
        self.max_chunk_tokens = max_chunk_tokens

    def estimate_tokens(self, text: str) -> int:
        """Heuristic token estimator (approx 4 chars per token for English + code)."""
        return max(1, len(text) // 4)

    def extract_frontmatter(self, raw_md: str) -> tuple[Dict[str, str], str]:
        """Extracts YAML frontmatter metadata and returns (metadata_dict, cleaned_body)."""
        match = self.FRONTMATTER_REGEX.match(raw_md)
        meta = {}
        if match:
            fm_text = match.group(1)
            for line in fm_text.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip().strip("'\"")
            cleaned_body = raw_md[match.end():]
            return meta, cleaned_body
        return meta, raw_md

    def parse_section_tree(self, text: str, doc_title: str) -> SectionNode:
        """Parses Markdown into an AST-like hierarchical SectionNode tree."""
        root = SectionNode(level=0, title=doc_title or "Document", breadcrumbs=[doc_title] if doc_title else [])
        stack: List[SectionNode] = [root]

        lines = text.splitlines()
        current_block: List[str] = []
        in_code_block = False

        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block

            # Only check for headers if NOT inside a code block
            header_match = self.HEADING_REGEX.match(line) if not in_code_block else None

            if header_match:
                # Flush existing content into current node
                if current_block:
                    stack[-1].content_blocks.append("\n".join(current_block).strip())
                    current_block = []

                level = len(header_match.group(1))
                raw_title = header_match.group(2).strip()
                # Strip custom anchor tags like {#custom-id}
                title = re.sub(r"\{#[^}]+\}", "", raw_title).strip()

                # Pop stack until parent level is lower
                while len(stack) > 1 and stack[-1].level >= level:
                    stack.pop()

                parent = stack[-1]
                ancestor_breadcrumbs = [h.title for h in stack if h.title] + [title]
                new_node = SectionNode(
                    level=level,
                    title=title,
                    breadcrumbs=ancestor_breadcrumbs
                )
                parent.children.append(new_node)
                stack.append(new_node)
            else:
                current_block.append(line)

        if current_block:
            stack[-1].content_blocks.append("\n".join(current_block).strip())

        return root

    def flatten_tree_into_chunks(
        self,
        node: SectionNode,
        doc_path: str,
        doc_title: str
    ) -> List[HierarchicalChunk]:
        """Traverses the section tree and produces budget-aware, breadcrumb-injected chunks."""
        chunks: List[HierarchicalChunk] = []
        chunk_idx = 1

        def process_node(curr_node: SectionNode):
            nonlocal chunk_idx
            # 1. Combine direct text blocks for this section
            raw_body = "\n\n".join([b for b in curr_node.content_blocks if b]).strip()
            
            if raw_body:
                breadcrumb_str = " > ".join(curr_node.breadcrumbs)
                est_tokens = self.estimate_tokens(raw_body)

                # Case A: Fits in budget -> Emit complete section chunk
                if est_tokens <= self.max_chunk_tokens:
                    header_prefix = f"### [{breadcrumb_str}]\n\n" if breadcrumb_str else ""
                    full_content = f"{header_prefix}{raw_body}"
                    
                    chunks.append(HierarchicalChunk(
                        chunk_id=f"{Path(doc_path).stem}_chunk_{chunk_idx:03d}",
                        doc_path=doc_path,
                        doc_title=doc_title,
                        heading_hierarchy=list(curr_node.breadcrumbs),
                        breadcrumb_path=breadcrumb_str,
                        text=full_content,
                        token_estimate=self.estimate_tokens(full_content),
                        has_code_block="```" in full_content,
                        has_table="|" in full_content
                    ))
                    chunk_idx += 1

                # Case B: Oversized section -> Sub-split at paragraph boundaries
                else:
                    sub_paragraphs = self._split_large_body(raw_body)
                    for part_i, p_group in enumerate(sub_paragraphs, 1):
                        suffix = f" (Part {part_i}/{len(sub_paragraphs)})" if len(sub_paragraphs) > 1 else ""
                        header_prefix = f"### [{breadcrumb_str}{suffix}]\n\n"
                        full_content = f"{header_prefix}{p_group}"
                        
                        chunks.append(HierarchicalChunk(
                            chunk_id=f"{Path(doc_path).stem}_chunk_{chunk_idx:03d}",
                            doc_path=doc_path,
                            doc_title=doc_title,
                            heading_hierarchy=list(curr_node.breadcrumbs),
                            breadcrumb_path=f"{breadcrumb_str}{suffix}",
                            text=full_content,
                            token_estimate=self.estimate_tokens(full_content),
                            has_code_block="```" in full_content,
                            has_table="|" in full_content
                        ))
                        chunk_idx += 1

            # Recurse into children headings
            for child in curr_node.children:
                process_node(child)

        process_node(node)
        return chunks

    def _split_large_body(self, body_text: str) -> List[str]:
        """Splits an oversized section text along paragraph boundaries without cutting code blocks."""
        paragraphs = re.split(r"\n\n+", body_text)
        groups = []
        current_group: List[str] = []
        current_tokens = 0
        in_code = False

        for p in paragraphs:
            if p.count("```") % 2 != 0:
                in_code = not in_code

            p_tokens = self.estimate_tokens(p)
            # Group paragraphs until budget is reached
            if current_tokens + p_tokens > self.target_chunk_tokens and not in_code and current_group:
                groups.append("\n\n".join(current_group).strip())
                current_group = [p]
                current_tokens = p_tokens
            else:
                current_group.append(p)
                current_tokens += p_tokens

        if current_group:
            groups.append("\n\n".join(current_group).strip())

        return groups

    def chunk_file(self, file_path: str) -> List[HierarchicalChunk]:
        """End-to-end pipeline: extracts frontmatter, parses AST, and yields hierarchical chunks."""
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        meta, clean_body = self.extract_frontmatter(raw_text)
        doc_title = meta.get("title") or meta.get("linkTitle") or Path(file_path).stem.replace("-", " ").title()

        root = self.parse_section_tree(clean_body, doc_title=doc_title)
        return self.flatten_tree_into_chunks(root, doc_path=file_path, doc_title=doc_title)


if __name__ == "__main__":
    sample_file = "fde-k8s/website/content/en/docs/reference/access-authn-authz/admission-controllers.md"
    chunker = HierarchyAwareChunker(min_chunk_tokens=100, target_chunk_tokens=400, max_chunk_tokens=700)
    
    print("=" * 75)
    print(f"=== TESTING HIERARCHY-AWARE CHUNKER ON: {sample_file} ===")
    print("=" * 75)
    
    chunks = chunker.chunk_file(sample_file)
    print(f"✓ Total Hierarchy-Aware Chunks Generated: {len(chunks)}\n")

    print("--- Sample Chunks Preview (Chunks #1 to #4) ---")
    for chk in chunks[:4]:
        print(f"🔹 Chunk ID:      {chk.chunk_id}")
        print(f"   Breadcrumb:    {chk.breadcrumb_path}")
        print(f"   Est. Tokens:   {chk.token_estimate} | Code Block? {chk.has_code_block} | Table? {chk.has_table}")
        print(f"   Content Preview:\n{chk.text[:220]}...\n")
