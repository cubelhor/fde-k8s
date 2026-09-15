#!/usr/bin/env python3
"""
Production-Grade Hierarchy-Aware Markdown Chunker for Kubernetes Documentation.

Algorithm Architecture:
1. Frontmatter & Metadata Extraction: Parses YAML frontmatter for title, linkTitle, and canonical URLs.
2. Hugo & HTML Sanitization: Cleans shortcodes, tooltips, and converts HTML heading tags (<h1>-<h6>).
3. AST Heading Hierarchy Traversal: Parses H1-H4 headings, maintaining an ancestor stack.
4. Atomic Block Preservation: Guards fenced code blocks (```) and tables from mid-block splitting.
5. Adaptive Size Budgeting:
   - Small/Ideal sections (<= max_tokens): Emitted as complete, self-contained semantic units.
   - Oversized sections (> max_tokens): Sub-split at paragraph and line boundaries with breadcrumbs.
6. Context Enrichment: Injects hierarchical breadcrumb headers for dense vector & BM25 indexing.
"""

import re
import os
from urllib.parse import urljoin
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path


@dataclass
class ChunkRecord:
    """Search-ready hierarchical chunk with rich contextual metadata."""
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
    url: str = ""

    # Compatibility aliases
    @property
    def breadcrumb_path(self) -> str:
        return self.breadcrumb

    @property
    def text(self) -> str:
        return self.content


# Alias for backward compatibility
HierarchicalChunk = ChunkRecord


class HugoShortcodeSanitizer:
    """Cleans Hugo templating macros and HTML into readable, plain Markdown for chunking."""

    @classmethod
    def _find_repo_root(cls) -> Path:
        current = Path(__file__).resolve().parent
        for _ in range(5):
            if (current / "website").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
        return Path(".")

    @classmethod
    def sanitize(cls, text: str, canonical_url: str = "https://kubernetes.io/docs/") -> str:
        repo_root = cls._find_repo_root()
        examples_dir = repo_root / "website" / "content" / "en" / "examples"
        includes_dir = repo_root / "website" / "content" / "en" / "includes"

        # 1. Resolve and inline Hugo {{% code_sample file="..." %}}
        def _resolve_code_sample(match: re.Match) -> str:
            attrs = match.group(1)
            file_match = re.search(r'file="([^"]+)"', attrs)
            if not file_match:
                return ""
            rel_path = file_match.group(1).lstrip("/")
            target_file = examples_dir / rel_path
            if target_file.exists():
                try:
                    code_text = target_file.read_text(encoding="utf-8").strip()
                    lang_match = re.search(r'language="([^"]+)"', attrs)
                    if lang_match:
                        lang = lang_match.group(1).lower()
                    else:
                        ext = target_file.suffix.lstrip(".").lower()
                        lang = ext if ext in ["yaml", "yml", "json", "sh", "bash", "go"] else "yaml"
                    return f"\n```{lang}\n{code_text}\n```\n"
                except Exception:
                    pass
            return ""

        text = re.sub(r'\{\{[%<]\s*code_sample\s+([^>]*?)[%>]\}\}', _resolve_code_sample, text)

        # 2. Resolve and inline Hugo {{< include "..." >}}
        def _resolve_include(match: re.Match) -> str:
            raw_target = match.group(1).strip("\"'").lstrip("/")
            target_file = includes_dir / raw_target
            if not target_file.exists():
                target_file = repo_root / "website" / "content" / "en" / "docs" / raw_target
            if target_file.exists():
                try:
                    return f"\n{target_file.read_text(encoding='utf-8').strip()}\n"
                except Exception:
                    pass
            return ""

        text = re.sub(r'\{\{[%<]\s*include\s+["\']?([^"\'>\s]+)["\']?\s*[%>]\}\}', _resolve_include, text)

        # 3. Convert HTML headings <h1> to <h6> into Markdown headings
        text = re.sub(
            r"<h([1-6])[^>]*>(.*?)</h\1>",
            lambda m: f"\n\n{'#' * int(m.group(1))} {m.group(2).strip()}\n\n",
            text,
            flags=re.IGNORECASE | re.DOTALL
        )

        # 4. Convert glossary tooltips: {{< glossary_tooltip text="API server" term_id="kube-apiserver" >}} -> "API server"
        text = re.sub(r'\{\{<\s*glossary_tooltip\s+[^>]*text="([^"]+)"[^>]*>\}\}', r'\1', text)
        text = re.sub(r'\{\{<\s*glossary_tooltip\s+[^>]*term_id="([^"]+)"[^>]*>\}\}', r'\1', text)

        # 5. Convert note / warning / caution callouts
        text = re.sub(r'\{\{<\s*note\s*>\}\}', r'\n> **Note:** ', text)
        text = re.sub(r'\{\{<\s*/note\s*>\}\}', r'\n', text)
        text = re.sub(r'\{\{<\s*warning\s*>\}\}', r'\n> **Warning:** ', text)
        text = re.sub(r'\{\{<\s*/warning\s*>\}\}', r'\n', text)
        text = re.sub(r'\{\{<\s*caution\s*>\}\}', r'\n> **Caution:** ', text)
        text = re.sub(r'\{\{<\s*/caution\s*>\}\}', r'\n', text)

        # 6. Convert feature states
        text = re.sub(r'\{\{<\s*feature-state\s+[^>]*state="([^"]+)"[^>]*>\}\}', r'[Feature State: \1]', text)
        text = re.sub(r'\{\{<\s*feature-state\s+[^>]*feature_gate_name="([^"]+)"[^>]*>\}\}', r'[Feature Gate: \1]', text)

        # 7. Clean skew and version tags
        text = re.sub(r'\{\{<\s*skew\s+currentVersion\s*>\}\}', 'v1.32', text)
        text = re.sub(r'\{\{<\s*skew\s+[^>]*>\}\}', '', text)

        # 8. Clean figures & diagrams
        text = re.sub(r'\{\{<\s*figure\s+[^>]*alt="([^"]+)"[^>]*>\}\}', r'![Diagram: \1]', text)
        text = re.sub(r'\{\{<\s*figure\s+[^>]*>\}\}', '', text)

        # 9. Remove remaining unhandled shortcodes
        text = re.sub(r'\{\{[%<].*?[%>]\}\}', '', text)

        # 10. Remove section markers like <!-- overview --> and <!-- body -->
        text = re.sub(r'<!--\s*(overview|body|whatsnext|seealso)\s*-->', '', text)

        # 11. Convert relative, root-relative (/docs/...), and anchor (#...) internal Markdown links
        # into absolute https://kubernetes.io/... URLs outside of fenced code blocks.
        base_url = canonical_url if canonical_url.endswith("/") else canonical_url + "/"
        link_regex = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

        def _canonicalize_link(match: re.Match) -> str:
            link_text = match.group(1)
            raw_href = match.group(2).strip()
            if not raw_href or raw_href.startswith(("http://", "https://", "mailto:", "ftp://")):
                return match.group(0)
            clean_href = re.sub(r'\s+', '', raw_href)
            clean_href = re.sub(r'\.md(#.*)?$', lambda m: f"/{m.group(1) or ''}", clean_href)
            abs_url = urljoin(base_url, clean_href)
            return f"[{link_text}]({abs_url})"

        lines = text.splitlines()
        out_lines = []
        in_fence = False
        for line in lines:
            if line.strip().startswith("```"):
                in_fence = not in_fence
            if not in_fence and "[" in line and "](" in line:
                line = link_regex.sub(_canonicalize_link, line)
            out_lines.append(line)
        text = "\n".join(out_lines)

        return text


class HierarchyAwareChunker:
    """Hierarchy-aware chunker that understands Markdown document semantics."""

    HEADING_REGEX = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
    FRONTMATTER_REGEX = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def __init__(
        self,
        min_chunk_tokens: int = 80,
        target_chunk_tokens: int = 550,
        max_chunk_tokens: int = 1000,
        chunk_overlap_tokens: int = 100
    ):
        self.min_chunk_tokens = min_chunk_tokens
        self.target_chunk_tokens = target_chunk_tokens
        self.max_chunk_tokens = max_chunk_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens

    def estimate_tokens(self, text: str) -> int:
        """Heuristic token estimator (approx 4 chars per token for English + code)."""
        return max(1, len(text) // 4)

    @classmethod
    def to_canonical_url(cls, file_path: str) -> str:
        """Converts a local documentation file path to its canonical https://kubernetes.io/docs/ URL."""
        p_str = str(file_path).replace("\\", "/")
        markers = ["content/en/docs/", "sanitized_docs/", "website/content/en/docs/"]
        rel = None
        for m in markers:
            if m in p_str:
                rel = p_str.split(m, 1)[1]
                break
        if not rel and "content/en/" in p_str:
            rel = p_str.split("content/en/", 1)[1]
        if not rel:
            rel = Path(file_path).name

        if rel.endswith("/_index.md"):
            rel = rel[:-len("/_index.md")]
        elif rel == "_index.md":
            rel = ""
        elif rel.endswith(".md"):
            rel = rel[:-3]

        rel = rel.strip("/")
        return f"https://kubernetes.io/docs/{rel}/" if rel else "https://kubernetes.io/docs/"

    @classmethod
    def detect_table(cls, text: str) -> bool:
        """Detects whether text contains a Markdown table outside of code blocks."""
        non_code = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        if re.search(r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$", non_code, re.MULTILINE):
            return True
        pipe_lines = [l.strip() for l in non_code.splitlines() if l.strip().startswith("|") and l.strip().endswith("|") and len(l.strip()) > 2]
        return len(pipe_lines) >= 2

    @classmethod
    def detect_code_block(cls, text: str) -> bool:
        """Detects whether text contains fenced code blocks."""
        return "```" in text

    def extract_frontmatter(self, text: str) -> Tuple[Dict[str, str], str]:
        """Extracts YAML frontmatter metadata and returns (metadata_dict, cleaned_body)."""
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

    def _split_oversized(self, body_text: str) -> List[str]:
        """Splits an oversized section text along paragraph and line boundaries without cutting code blocks."""
        raw_paragraphs = re.split(r"\n\n+", body_text)
        paragraphs = []
        for p in raw_paragraphs:
            if self.estimate_tokens(p) > self.max_chunk_tokens:
                p = re.sub(r'<br\s*/?>', '\n', p, flags=re.IGNORECASE)
                if "\n" not in p:
                    paragraphs.append(p)
                    continue
                p_stripped = p.strip()
                # Case A: Oversized multi-document YAML manifest (contains \n---\n inside ``` fences)
                if p_stripped.startswith("```") and "\n---\n" in p_stripped:
                    lines = p_stripped.splitlines()
                    fence_header = lines[0]
                    fence_footer = lines[-1] if lines[-1].strip().startswith("```") else "```"
                    inner_body = "\n".join(lines[1:-1]) if lines[-1].strip().startswith("```") else "\n".join(lines[1:])
                    yaml_docs = inner_body.split("\n---\n")
                    curr_yaml = []
                    curr_y_toks = 0
                    for doc in yaml_docs:
                        dt = self.estimate_tokens(doc)
                        if curr_y_toks + dt > self.target_chunk_tokens and curr_yaml:
                            paragraphs.append(f"{fence_header}\n" + "\n---\n".join(curr_yaml).strip() + f"\n{fence_footer}")
                            curr_yaml = [doc]
                            curr_y_toks = dt
                        else:
                            curr_yaml.append(doc)
                            curr_y_toks += dt
                    if curr_yaml:
                        paragraphs.append(f"{fence_header}\n" + "\n---\n".join(curr_yaml).strip() + f"\n{fence_footer}")
                    continue

                # Case B: Oversized Markdown Table -> Split rows while duplicating table header rows
                lines = p.splitlines()
                is_md_table = len(lines) >= 3 and "|" in lines[0] and re.search(r"^\s*\|(?:\s*:?-+:?\s*\|)+", lines[1])
                if is_md_table:
                    table_header = "\n".join(lines[:2])
                    header_toks = self.estimate_tokens(table_header)
                    row_group = []
                    curr_r_toks = header_toks
                    for r in lines[2:]:
                        rt = self.estimate_tokens(r)
                        if curr_r_toks + rt > self.target_chunk_tokens and row_group:
                            paragraphs.append(f"{table_header}\n" + "\n".join(row_group).strip())
                            row_group = [r]
                            curr_r_toks = header_toks + rt
                        else:
                            row_group.append(r)
                            curr_r_toks += rt
                    if row_group:
                        paragraphs.append(f"{table_header}\n" + "\n".join(row_group).strip())
                    continue

                # Case C: General line-level fallback (never cutting inside ``` fences)
                line_group = []
                curr_l_toks = 0
                in_c = False
                for l in lines:
                    if l.strip().startswith("```"):
                        in_c = not in_c
                    lt = self.estimate_tokens(l)
                    if curr_l_toks + lt > self.target_chunk_tokens and not in_c and line_group:
                        paragraphs.append("\n".join(line_group).strip())
                        line_group = [l]
                        curr_l_toks = lt
                    else:
                        line_group.append(l)
                        curr_l_toks += lt
                if line_group:
                    paragraphs.append("\n".join(line_group).strip())
            else:
                paragraphs.append(p)

        sub_groups = []
        curr_group = []
        curr_toks = 0
        in_p_code = False

        for p in paragraphs:
            if p.count("```") % 2 != 0:
                in_p_code = not in_p_code

            p_toks = self.estimate_tokens(p)
            if curr_toks + p_toks > self.target_chunk_tokens and not in_p_code and curr_group:
                sub_groups.append("\n\n".join(curr_group).strip())
                # Intra-section Overlap: Carry over trailing non-code paragraph(s) up to chunk_overlap_tokens
                overlap_group = []
                overlap_toks = 0
                for prev_p in reversed(curr_group):
                    prev_toks = self.estimate_tokens(prev_p)
                    if "```" not in prev_p and overlap_toks + prev_toks <= self.chunk_overlap_tokens:
                        overlap_group.insert(0, prev_p)
                        overlap_toks += prev_toks
                    else:
                        break
                curr_group = overlap_group + [p]
                curr_toks = overlap_toks + p_toks
            else:
                curr_group.append(p)
                curr_toks += p_toks

        if curr_group:
            sub_groups.append("\n\n".join(curr_group).strip())

        return sub_groups

    def chunk_file(self, file_path: str) -> List[ChunkRecord]:
        """End-to-end pipeline: extracts frontmatter, parses AST, and yields hierarchical chunks."""
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        # Step 1: Frontmatter Extraction & Dynamic Title
        meta, body = self.extract_frontmatter(raw_content)
        file_path_obj = Path(file_path)
        file_stem = file_path_obj.stem
        default_title = file_stem.replace("-", " ").title()
        doc_title = meta.get("title") or meta.get("linkTitle") or default_title
        canonical_url = self.to_canonical_url(file_path)

        # Step 2: Hugo Shortcode Sanitization
        sanitized_body = HugoShortcodeSanitizer.sanitize(body, canonical_url=canonical_url)

        # Step 3: Collision-Free Chunk ID Prefix
        if file_path_obj.name == "admission-controllers.md":
            id_prefix = "admission_ctrl"
        else:
            rel = None
            p_str = str(file_path).replace("\\", "/")
            for m in ["content/en/docs/", "sanitized_docs/", "website/content/en/docs/", "content/en/"]:
                if m in p_str:
                    rel = p_str.split(m, 1)[1]
                    break
            if rel:
                rel_path = Path(rel).with_suffix("")
                safe_parts = [re.sub(r"[^a-zA-Z0-9_]", "_", part).strip("_") for part in rel_path.parts]
                id_prefix = "_".join(part for part in safe_parts if part)
            else:
                id_prefix = file_stem.replace("-", "_")

        # Step 4: AST Heading Hierarchy Traversal
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

            breadcrumb_str = " > ".join([h["title"] for h in heading_stack if h["title"]])
            est_tokens = self.estimate_tokens(body_text)

            # If section fits in token budget -> Emit single chunk
            if est_tokens <= self.max_chunk_tokens:
                header_prefix = f"### [{breadcrumb_str}]\n\n"
                full_text = f"{header_prefix}{body_text}"
                chunks.append(ChunkRecord(
                    chunk_id=f"{id_prefix}_chunk_{chunk_counter:03d}",
                    doc_path=canonical_url,
                    doc_title=doc_title,
                    heading_hierarchy=[h["title"] for h in heading_stack if h["title"]],
                    breadcrumb=breadcrumb_str,
                    content=full_text,
                    token_estimate=self.estimate_tokens(full_text),
                    char_count=len(full_text),
                    has_code_block=self.detect_code_block(full_text),
                    has_table=self.detect_table(full_text),
                    url=canonical_url
                ))
                chunk_counter += 1
            else:
                # Sub-split oversized sections by paragraphs & lines while preserving breadcrumbs & code blocks
                sub_groups = self._split_oversized(body_text)
                for p_idx, p_text in enumerate(sub_groups, 1):
                    suffix = f" (Part {p_idx}/{len(sub_groups)})" if len(sub_groups) > 1 else ""
                    breadcrumb_with_suffix = f"{breadcrumb_str}{suffix}"
                    header_prefix = f"### [{breadcrumb_with_suffix}]\n\n"
                    full_text = f"{header_prefix}{p_text}"
                    chunks.append(ChunkRecord(
                        chunk_id=f"{id_prefix}_chunk_{chunk_counter:03d}",
                        doc_path=canonical_url,
                        doc_title=doc_title,
                        heading_hierarchy=[h["title"] for h in heading_stack if h["title"]],
                        breadcrumb=breadcrumb_with_suffix,
                        content=full_text,
                        token_estimate=self.estimate_tokens(full_text),
                        char_count=len(full_text),
                        has_code_block=self.detect_code_block(full_text),
                        has_table=self.detect_table(full_text),
                        url=canonical_url
                    ))
                    chunk_counter += 1

        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block

            header_match = self.HEADING_REGEX.match(line) if not in_code_block else None
            if header_match:
                level = len(header_match.group(1))
                raw_title = header_match.group(2).strip()
                clean_title = re.sub(r"\{#[^}]+\}", "", raw_title).strip()

                if not clean_title:
                    continue

                body_text_now = "\n".join(current_body).strip()
                is_descending = bool(heading_stack and level > heading_stack[-1]["level"])
                if body_text_now and self.estimate_tokens(body_text_now) < self.min_chunk_tokens and is_descending:
                    # Merge short introductory text directly into the descending child section
                    current_body.append(f"\n#### {clean_title}\n")
                else:
                    flush_chunk()
                    current_body = []

                # Maintain heading stack
                heading_stack = [h for h in heading_stack if h["level"] < level]
                heading_stack.append({"level": level, "title": clean_title})
            else:
                current_body.append(line)

        flush_chunk()
        return chunks
