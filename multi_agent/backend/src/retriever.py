"""Internal Hybrid Chunk Retriever Module (`src.retriever`).

Provides a self-contained, container-safe `HybridChunkRetriever` (Sparse BM25 + Dense
Semantic Vector + Query-Adaptive RRF + O(1) `get_by_id()` hash lookup) for the backend
and MCP server without depending on external evaluation scripts or brittle `sys.path` hacks.
"""

import os
import re
import json
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Set

logger = logging.getLogger("k8s_retriever")

STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "did", "do",
    "does", "doing", "don", "down", "during", "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "isn", "it", "its",
    "itself", "just", "me", "more", "most", "my", "myself", "no", "nor", "not",
    "now", "of", "off", "on", "once", "only", "or", "other", "our", "ours", "ourselves",
    "out", "over", "own", "same", "she", "should", "so", "some", "such", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up", "very",
    "was", "wasn", "we", "were", "weren", "what", "when", "where", "which", "while",
    "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself", "yourselves"
}

K8S_SEMANTIC_EXPANSIONS: Dict[str, List[str]] = {
    "termination": ["sigterm", "grace", "period", "prestop", "kill", "shutting", "termination of pods"],
    "liveness": ["probe", "probes", "container probes", "restart", "deadlock", "healthz"],
    "readiness": ["probe", "probes", "container probes", "traffic", "service", "endpoints"],
    "clusterrole": ["rbac", "role", "authorization", "api objects", "clusterrolebinding", "namespaced"],
    "role": ["rbac", "clusterrole", "authorization", "api objects", "rolebinding", "namespace"],
    "crashloopbackoff": ["backoff", "restartpolicy", "exponential", "container states", "waiting"],
    "storageclass": ["provisioner", "reclaimpolicy", "volumebindingmode", "dynamic", "waitforfirstconsumer"],
    "affinity": ["nodeaffinity", "requiredduringscheduling", "preferredduringscheduling", "scheduler"],
    "taint": ["toleration", "noschedule", "noexecute", "prefernoschedule", "eviction"],
}


def resolve_chunks_jsonl_path() -> Optional[Path]:
    """Resolves the path to `k8s_chunks_custom.jsonl` safely across Docker and local environments.

    Resolution order:
    1. `K8S_CHUNKS_JSONL_PATH` environment variable (recommended for containerized deployments).
    2. Bundled backend data directory (`<backend_root>/data/k8s_chunks_custom.jsonl`).
    3. Monorepo pipeline artifact (`<repo_root>/multi_agent/data_pipeline/artifacts/k8s_chunks_custom.jsonl`).
    """
    env_path = os.getenv("K8S_CHUNKS_JSONL_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    backend_root = Path(__file__).resolve().parent.parent
    candidates = [
        backend_root / "data" / "k8s_chunks_custom.jsonl",
        backend_root.parent / "data_pipeline" / "artifacts" / "k8s_chunks_custom.jsonl",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class HybridChunkRetriever:
    """Models Vertex AI Search's Hybrid Search (Sparse BM25 + Dense Semantic Vector + RRF) with O(1) ID lookup."""

    def __init__(self, jsonl_path: Optional[Path] = None):
        self.chunks: List[Dict[str, Any]] = []
        self.chunk_map: Dict[str, Dict[str, Any]] = {}
        self.df: Dict[str, int] = {}
        self.total_docs: int = 0
        self.doc_vectors: List[Tuple[Dict[str, float], float]] = []
        target_path = jsonl_path or resolve_chunks_jsonl_path()
        if target_path is not None:
            self._load_chunks(target_path)
            self._build_indices()

    def _load_chunks(self, jsonl_path: Path):
        if jsonl_path.exists():
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        chk = json.loads(line)
                        self.chunks.append(chk)
                        cid = chk.get("id") or chk.get("_id") or chk.get("chunk_id")
                        if cid:
                            self.chunk_map[cid] = chk

        self.total_docs = len(self.chunks)

    def get_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """O(1) hash map lookup for a specific chunk by its deterministic ID."""
        return self.chunk_map.get(chunk_id)

    @staticmethod
    def _stem(word: str) -> str:
        w = word.lower()
        if len(w) > 3 and w.endswith("s"):
            return w[:-1]
        return w

    def _extract_features(self, text: str, breadcrumb: str = "", is_query: bool = False) -> Dict[str, float]:
        """Extracts unigrams, bigrams, and semantic concept features for dense vector representation."""
        words = [w.lower() for w in re.findall(r"[A-Za-z0-9_]+", text) if w.lower() not in STOPWORDS and len(w) > 2]
        bc_words = [w.lower() for w in re.findall(r"[A-Za-z0-9_]+", breadcrumb) if w.lower() not in STOPWORDS and len(w) > 2]

        feats: Dict[str, float] = {}
        for w in words:
            stem = self._stem(w)
            feats[stem] = feats.get(stem, 0.0) + 1.0

        for i in range(len(words) - 1):
            bg = f"{self._stem(words[i])}_{self._stem(words[i+1])}"
            feats[bg] = feats.get(bg, 0.0) + 1.5

        for w in bc_words:
            stem = self._stem(w)
            feats[stem] = feats.get(stem, 0.0) + 3.0
        for i in range(len(bc_words) - 1):
            bg = f"{self._stem(bc_words[i])}_{self._stem(bc_words[i+1])}"
            feats[bg] = feats.get(bg, 0.0) + 4.0

        if is_query:
            for w in list(words):
                for syn in K8S_SEMANTIC_EXPANSIONS.get(w, []):
                    for syn_w in re.findall(r"[A-Za-z0-9_]+", syn):
                        s_stem = self._stem(syn_w)
                        feats[s_stem] = feats.get(s_stem, 0.0) + 1.2

        return feats

    def _build_indices(self):
        """Builds Sparse IDF table and precomputes L2-normalized Dense Semantic Vectors."""
        raw_doc_feats: List[Dict[str, float]] = []
        for chk in self.chunks:
            bcrumb = chk.get("breadcrumb", "")
            content = chk.get("content", chk.get("text", ""))
            feats = self._extract_features(content, bcrumb, is_query=False)
            raw_doc_feats.append(feats)
            for term in feats.keys():
                self.df[term] = self.df.get(term, 0) + 1

        for feats in raw_doc_feats:
            vec: Dict[str, float] = {}
            norm_sq = 0.0
            for term, tf in feats.items():
                idf = self.compute_idf(term)
                w = (1.0 + math.log(tf)) * idf
                vec[term] = w
                norm_sq += w * w
            norm = math.sqrt(norm_sq) if norm_sq > 0 else 1.0
            self.doc_vectors.append((vec, norm))

    def compute_idf(self, term: str) -> float:
        stem = self._stem(term)
        n_w = self.df.get(stem, 0)
        if n_w == 0:
            return 1.5
        return math.log(1.0 + (self.total_docs - n_w + 0.5) / (n_w + 0.5))

    def search_sparse(self, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
        """Sparse BM25 / Lexical branch."""
        raw_words = re.findall(r"[A-Za-z0-9_]+", query)
        informative_terms = [w.lower() for w in raw_words if w.lower() not in STOPWORDS and len(w) > 2]
        scored: List[Tuple[int, float]] = []

        for idx, chk in enumerate(self.chunks):
            bcrumb = chk.get("breadcrumb", chk.get("breadcrumb_path", ""))
            content = chk.get("content", chk.get("text", ""))
            bcrumb_lower = bcrumb.lower()
            content_lower = content.lower()

            score = 0.0
            for term in informative_terms:
                idf = self.compute_idf(term)
                stem = self._stem(term)

                if term in bcrumb_lower or stem in bcrumb_lower:
                    score += idf * 8.0

                c_count = max(content_lower.count(term), content_lower.count(stem))
                if c_count > 0:
                    tf = 1.0 + (c_count ** 0.5)
                    score += idf * tf * 1.5

            if query.lower() in content_lower:
                score += 25.0

            if score > 0:
                scored.append((idx, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def search_dense(self, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
        """Dense Semantic Vector branch using L2-normalized Cosine Similarity."""
        q_feats = self._extract_features(query, is_query=True)
        q_vec: Dict[str, float] = {}
        q_norm_sq = 0.0
        for term, tf in q_feats.items():
            idf = self.compute_idf(term)
            w = (1.0 + math.log(tf)) * idf
            q_vec[term] = w
            q_norm_sq += w * w
        q_norm = math.sqrt(q_norm_sq) if q_norm_sq > 0 else 1.0

        scored: List[Tuple[int, float]] = []
        for idx, (d_vec, d_norm) in enumerate(self.doc_vectors):
            dot = 0.0
            for term, q_w in q_vec.items():
                d_w = d_vec.get(term, 0.0)
                if d_w > 0:
                    dot += q_w * d_w
            if dot > 0:
                cos_sim = dot / (q_norm * d_norm)
                scored.append((idx, cos_sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Executes Hybrid Search (Sparse BM25 + Dense Semantic Vector + Query-Adaptive RRF)."""
        sparse_results = self.search_sparse(query, top_k=60)
        dense_results = self.search_dense(query, top_k=60)

        has_camelcase_id = any(
            any(c.isupper() for c in w[1:]) and any(c.islower() for c in w)
            for w in re.findall(r"[A-Za-z0-9_]+", query)
        )
        w_sparse = 2.4 if has_camelcase_id else 1.0
        w_dense = 1.0 if has_camelcase_id else 1.35

        rrf_k = 60.0
        rrf_scores: Dict[int, float] = {}

        for rank, (doc_idx, _) in enumerate(sparse_results, 1):
            rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0.0) + (w_sparse / (rrf_k + rank))

        for rank, (doc_idx, _) in enumerate(dense_results, 1):
            rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0.0) + (w_dense / (rrf_k + rank))

        final_ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for doc_idx, score in final_ranked:
            chk = self.chunks[doc_idx]
            results.append({
                "id": chk.get("id", chk.get("_id", chk.get("chunk_id", ""))),
                "breadcrumb": chk.get("breadcrumb", chk.get("breadcrumb_path", "")),
                "content": chk.get("content", chk.get("text", "")),
                "score": score
            })
        return results
