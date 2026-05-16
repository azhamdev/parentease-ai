"""
Tool: verify_url_source

Extracts content from a URL using Tavily, matches the extracted claims
against the local RAG knowledge base (ChromaDB), and returns a structured
verification result so the LLM can tell the user whether the article is
consistent with trusted pediatric references.
"""

from __future__ import annotations

import os
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from dotenv import load_dotenv

load_dotenv()

VerificationVerdict = Literal[
    "supported",
    "partially_supported",
    "contradicted",
    "not_enough_evidence",
    "not_supported",
    "no_match",
]


@dataclass
class VerificationResult:
    """Returned to the LLM as structured context."""

    url: str
    verdict: VerificationVerdict
    web_summary: str
    matched_rag_excerpts: list[dict] = field(default_factory=list)
    rag_sources: list[dict] = field(default_factory=list)
    claim_judgments: list[dict] = field(default_factory=list)
    confidence: float | None = None
    explanation: str = ""

    def to_tool_string(self) -> str:
        """Serialise to a human-readable string the LLM can embed in its reply."""
        lines = [
            f"URL: {self.url}",
            f"Verdict: {self.verdict}",
            f"Confidence: {self.confidence if self.confidence is not None else 'unknown'}",
            f"Web Summary: {self.web_summary}",
        ]
        if self.claim_judgments:
            lines.append("Claim Judgments:")
            for i, judgment in enumerate(self.claim_judgments, 1):
                lines.append(
                    "  "
                    f"{i}. {judgment.get('verdict', 'not_enough_evidence')} "
                    f"({judgment.get('confidence', 'unknown')}): "
                    f"{judgment.get('claim', '')}"
                )
                rationale = judgment.get("rationale")
                if rationale:
                    lines.append(f"     Rationale: {rationale}")
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


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from an LLM response, tolerating light wrapping."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object.")
    return parsed


def _chat_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    from openai import OpenAI

    api_key = os.getenv("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPEN_ROUTER_API_KEY is not set in the environment.")

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    response = client.chat.completions.create(
        model="mistralai/mistral-large",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    content = response.choices[0].message.content or "{}"
    return _parse_json_object(content)


def _fallback_claims(web_content: str, max_claims: int = 5) -> list[str]:
    text = _clean_text(web_content)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    claims = [sentence.strip() for sentence in sentences if len(sentence.split()) >= 6]
    return claims[:max_claims] or [text[:500]]


def _extract_claims(web_content: str, max_claims: int = 5) -> list[str]:
    """Extract verifiable factual claims from web content."""
    excerpt = _clean_text(web_content)[:6000]
    try:
        payload = _chat_json(
            "You extract factual claims from pediatric/parenting articles. "
            "Return only JSON.",
            (
                "Extract the most important verifiable medical or parenting claims "
                "from this article. Ignore ads, navigation, author bios, and repeated text. "
                f"Return JSON with this shape: {{\"claims\": [\"claim 1\"]}}. "
                f"Maximum {max_claims} claims.\n\n"
                f"ARTICLE:\n{excerpt}"
            ),
        )
    except Exception:
        return _fallback_claims(web_content, max_claims=max_claims)

    raw_claims = payload.get("claims", [])
    if not isinstance(raw_claims, list):
        return _fallback_claims(web_content, max_claims=max_claims)

    claims: list[str] = []
    for claim in raw_claims:
        if isinstance(claim, str) and claim.strip():
            claims.append(_clean_text(claim))
        if len(claims) >= max_claims:
            break

    return claims or _fallback_claims(web_content, max_claims=max_claims)


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


def _normalize_verdict(value: Any) -> VerificationVerdict:
    if value in {
        "supported",
        "partially_supported",
        "contradicted",
        "not_enough_evidence",
        "no_match",
    }:
        return value
    if value == "not_supported":
        return "not_enough_evidence"
    return "not_enough_evidence"


def _normalize_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _derive_overall_verdict(judgments: list[dict]) -> VerificationVerdict:
    verdicts = [judgment.get("verdict") for judgment in judgments]
    if not verdicts:
        return "not_enough_evidence"
    if "contradicted" in verdicts:
        return "contradicted"
    if all(verdict == "supported" for verdict in verdicts):
        return "supported"
    if "supported" in verdicts:
        return "partially_supported"
    return "not_enough_evidence"


def _judge_claims(
    claims: list[str],
    matched_excerpts: list[dict],
) -> tuple[VerificationVerdict, float, list[dict], str]:
    """Judge extracted claims against local RAG excerpts using an LLM."""
    evidence = []
    for index, excerpt in enumerate(matched_excerpts, 1):
        source = excerpt.get("source", "Unknown")
        page = excerpt.get("page", "?")
        text = _clean_text(excerpt.get("text", ""))[:1200]
        evidence.append(
            {
                "source_index": index,
                "source": source,
                "page": page,
                "text": text,
            }
        )

    try:
        payload = _chat_json(
            "You are a conservative medical evidence checker. "
            "Judge claims only against the provided local trusted references. "
            "If the references do not clearly support or contradict a claim, use "
            "not_enough_evidence. Return only JSON.",
            (
                "For each claim, return verdict supported, contradicted, or "
                "not_enough_evidence. Include confidence from 0 to 1, short rationale, "
                "and source_indexes used. Also return an overall_verdict: supported, "
                "partially_supported, contradicted, or not_enough_evidence.\n\n"
                "JSON shape:\n"
                "{"
                "\"claims\":[{\"claim\":\"...\",\"verdict\":\"supported\","
                "\"confidence\":0.8,\"rationale\":\"...\",\"source_indexes\":[1]}],"
                "\"overall_verdict\":\"partially_supported\","
                "\"confidence\":0.7,"
                "\"explanation\":\"...\""
                "}\n\n"
                f"CLAIMS:\n{json.dumps(claims, ensure_ascii=False)}\n\n"
                f"LOCAL TRUSTED REFERENCES:\n{json.dumps(evidence, ensure_ascii=False)}"
            ),
        )
    except Exception as exc:
        judgments = [
            {
                "claim": claim,
                "verdict": "not_enough_evidence",
                "confidence": 0.0,
                "rationale": "Claim-level LLM judging failed.",
                "source_indexes": [],
            }
            for claim in claims
        ]
        return (
            "not_enough_evidence",
            0.0,
            judgments,
            f"Claim-level judging failed: {exc}",
        )

    raw_judgments = payload.get("claims", [])
    judgments: list[dict] = []
    if isinstance(raw_judgments, list):
        for raw in raw_judgments:
            if not isinstance(raw, dict):
                continue
            claim = raw.get("claim")
            if not isinstance(claim, str) or not claim.strip():
                continue
            source_indexes = raw.get("source_indexes", [])
            if not isinstance(source_indexes, list):
                source_indexes = []
            judgments.append(
                {
                    "claim": _clean_text(claim),
                    "verdict": _normalize_verdict(raw.get("verdict")),
                    "confidence": _normalize_confidence(raw.get("confidence")),
                    "rationale": _clean_text(str(raw.get("rationale", ""))),
                    "source_indexes": [
                        index for index in source_indexes if isinstance(index, int)
                    ],
                }
            )

    if not judgments:
        judgments = [
            {
                "claim": claim,
                "verdict": "not_enough_evidence",
                "confidence": 0.0,
                "rationale": "The judge did not return a usable assessment.",
                "source_indexes": [],
            }
            for claim in claims
        ]

    overall = _normalize_verdict(payload.get("overall_verdict"))
    if overall == "not_enough_evidence":
        overall = _derive_overall_verdict(judgments)
    confidence = _normalize_confidence(payload.get("confidence"))
    if confidence == 0.0 and judgments:
        confidence = sum(j["confidence"] for j in judgments) / len(judgments)

    explanation = payload.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        explanation = "Claims were checked against local trusted RAG references."

    return overall, confidence, judgments, _clean_text(explanation)


# ---------------------------------------------------------------------------
# Main tool function
# ---------------------------------------------------------------------------


def verify_url_source(url: str) -> VerificationResult:
    """
    1. Extract web content via Tavily.
    2. Extract the main verifiable claims.
    3. Retrieve relevant local RAG excerpts.
    4. Judge each claim against those excerpts with an LLM.
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

    claims = _extract_claims(web_content)
    query_text = " ".join(claims)[:4000]
    web_summary = _clean_text(web_content)[:1000]

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
            verdict="not_enough_evidence",
            web_summary=web_summary,
            claim_judgments=[
                {
                    "claim": claim,
                    "verdict": "not_enough_evidence",
                    "confidence": 0.0,
                    "rationale": "No matching local trusted references were found.",
                    "source_indexes": [],
                }
                for claim in claims
            ],
            confidence=0.0,
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

    verdict, confidence, claim_judgments, explanation = _judge_claims(
        claims, matched_excerpts
    )

    return VerificationResult(
        url=url,
        verdict=verdict,
        web_summary=web_summary,
        matched_rag_excerpts=matched_excerpts,
        rag_sources=rag_sources,
        claim_judgments=claim_judgments,
        confidence=confidence,
        explanation=explanation,
    )
