"""
Tool: verify_url_source

Extracts content from a URL using Tavily, matches the extracted claims
against the local RAG knowledge base (ChromaDB), and returns a structured
verification result so the LLM can tell the user whether the article is
consistent with trusted pediatric references.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

VerificationVerdict = Literal[
    "supported", "partially_supported", "not_supported", "no_match"
]


@dataclass
class VerificationResult:
    """Returned to the LLM as structured context."""

    url: str
    verdict: VerificationVerdict
    web_summary: str
    matched_rag_excerpts: list[dict] = field(default_factory=list)
    rag_sources: list[dict] = field(default_factory=list)
    explanation: str = ""

    def to_tool_string(self) -> str:
        """Serialise to a human-readable string the LLM can embed in its reply."""
        lines = [
            f"URL: {self.url}",
            f"Verdict: {self.verdict}",
            f"Web Summary: {self.web_summary}",
        ]
        if self.matched_rag_excerpts:
            lines.append("Matched RAG Excerpts:")
            for i, excerpt in enumerate(self.matched_rag_excerpts, 1):
                lines.append(f"  {i}. {excerpt.get('text', '')[:300]}")
                src = excerpt.get("source", "")
                if src:
                    lines.append(
                        f"     Source: {src} (page {excerpt.get('page', '?')})"
                    )
        else:
            lines.append("Matched RAG Excerpts: none")
        if self.explanation:
            lines.append(f"Explanation: {self.explanation}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def extract_urls(text: str) -> list[str]:
    """Return all HTTP(S) URLs found in *text*."""
    return _URL_RE.findall(text)


def _tavily_extract(url: str) -> str:
    """Use Tavily extract API to get the main content of a URL."""
    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise RuntimeError(
            "tavily-python is not installed. Run `uv sync` before using URL verification."
        ) from exc

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set in the environment.")

    client = TavilyClient(api_key=api_key)
    response = client.extract(urls=[url])

    # response is a dict with "results" key
    results = response.get("results", [])
    if not results:
        return ""
    # Take the first (and usually only) result's raw_content or text
    first = results[0]
    return first.get("raw_content", "") or first.get("text", "")


def _search_rag(query: str, n_results: int = 5) -> tuple[list[str], list[dict]]:
    """Query the local ChromaDB collection and return (documents, metadatas)."""
    # Import lazily so the module can be tested without a running ChromaDB.
    import chromadb
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPEN_ROUTER_API_KEY"),
    )
    emb_resp = client.embeddings.create(
        model="openai/text-embedding-3-small", input=[query]
    )
    embedding = emb_resp.data[0].embedding

    chroma = chromadb.PersistentClient(path="./chroma_db")
    collection = chroma.get_or_create_collection(name="pediatric_guidelines")
    results = collection.query(query_embeddings=[embedding], n_results=n_results)

    docs: list[str] = results["documents"][0] if results["documents"] else []
    metas: list[dict] = results["metadatas"][0] if results["metadatas"] else []  # ty:ignore[invalid-assignment]
    return docs, metas


def _format_title(filename: str) -> str:
    return filename.removesuffix(".pdf").replace("_", " ").replace("-", " ").title()


# ---------------------------------------------------------------------------
# Main tool function
# ---------------------------------------------------------------------------


def verify_url_source(url: str) -> VerificationResult:
    """
    1. Extract web content via Tavily.
    2. Build a search query from the extracted text.
    3. Query RAG for matching excerpts.
    4. Determine a verdict based on overlap.
    """

    # Step 1 - extract web content
    try:
        web_content = _tavily_extract(url)
    except Exception as exc:
        return VerificationResult(
            url=url,
            verdict="no_match",
            web_summary="",
            explanation=f"Failed to extract content from URL: {exc}",
        )

    if not web_content:
        return VerificationResult(
            url=url,
            verdict="no_match",
            web_summary="",
            explanation="Tavily returned no content for this URL.",
        )

    # Truncate for embedding query (ChromaDB / OpenAI limits)
    query_text = web_content[:2000]
    web_summary = web_content[:1000]

    # Step 2 - search RAG
    try:
        docs, metas = _search_rag(query_text, n_results=5)
    except Exception as exc:
        return VerificationResult(
            url=url,
            verdict="no_match",
            web_summary=web_summary,
            explanation=f"RAG search failed: {exc}",
        )

    if not docs:
        return VerificationResult(
            url=url,
            verdict="not_supported",
            web_summary=web_summary,
            explanation="No matching documents found in the knowledge base.",
        )

    # Step 3 - build matched excerpts & sources
    matched_excerpts: list[dict] = []
    rag_sources: list[dict] = []
    seen_sources: set[tuple] = set()

    for doc, meta in zip(docs, metas):
        title = _format_title(meta.get("source", "Unknown"))
        page = meta.get("page")
        matched_excerpts.append({"text": doc, "source": title, "page": page})
        key = (title, page)
        if key not in seen_sources:
            seen_sources.add(key)
            rag_sources.append({"title": title, "page": page})

    # Step 4 - simple heuristic verdict
    # We check how many of the top-5 RAG chunks share significant keyword
    # overlap with the web content.  A production system would use an LLM
    # for semantic comparison, but keyword overlap is a reasonable proxy
    # for an MVP and avoids an extra LLM call.
    web_tokens = set(web_content.lower().split())
    overlap_scores: list[float] = []
    for doc in docs:
        doc_tokens = set(doc.lower().split())
        if not doc_tokens:
            overlap_scores.append(0.0)
            continue
        intersection = web_tokens & doc_tokens
        # Jaccard-like but weighted toward the smaller set
        score = len(intersection) / min(len(web_tokens), len(doc_tokens))
        overlap_scores.append(score)

    avg_overlap = sum(overlap_scores) / len(overlap_scores) if overlap_scores else 0.0

    if avg_overlap >= 0.25:
        verdict: VerificationVerdict = "supported"
        explanation = (
            "The web article content has strong overlap with trusted references "
            "in the knowledge base."
        )
    elif avg_overlap >= 0.10:
        verdict = "partially_supported"
        explanation = (
            "Some claims in the web article are consistent with knowledge base "
            "references, but not all could be verified."
        )
    else:
        verdict = "not_supported"
        explanation = (
            "The web article content does not significantly match any trusted "
            "references in the knowledge base."
        )

    return VerificationResult(
        url=url,
        verdict=verdict,
        web_summary=web_summary,
        matched_rag_excerpts=matched_excerpts,
        rag_sources=rag_sources,
        explanation=explanation,
    )
