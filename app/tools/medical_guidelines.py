from __future__ import annotations

import os
from dataclasses import dataclass, field

import chromadb
from openai import OpenAI


CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "pediatric_guidelines"
EMBEDDING_MODEL = "openai/text-embedding-3-small"


@dataclass
class MedicalGuidelinesResult:
    tool_name: str = "search_medical_guidelines"
    status: str = "ok"
    query: str = ""
    content: str = ""
    sources: list[dict] = field(default_factory=list)
    error: str | None = None

    def model_dump(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "query": self.query,
            "content": self.content,
            "sources": self.sources,
            "error": self.error,
        }


def search_medical_guidelines(
    query: str,
    n_results: int = 3,
) -> MedicalGuidelinesResult:
    """Search local pediatric guideline chunks from ChromaDB."""
    clean_query = query.strip()
    if not clean_query:
        return MedicalGuidelinesResult(
            status="needs_more_input",
            query=query,
            content="Query diperlukan untuk mencari panduan medis.",
        )

    try:
        embedding = _embed_query(clean_query)
        result = _get_collection().query(
            query_embeddings=[embedding],
            n_results=max(1, min(n_results, 10)),
        )
    except Exception as exc:
        return MedicalGuidelinesResult(
            status="error",
            query=clean_query,
            content="Tidak dapat mengakses knowledge base medis saat ini.",
            sources=[],
            error=str(exc),
        )

    documents = result["documents"][0] if result.get("documents") else []
    metadatas = result["metadatas"][0] if result.get("metadatas") else []
    if not documents:
        return MedicalGuidelinesResult(
            status="no_match",
            query=clean_query,
            content="Tidak ditemukan panduan medis yang relevan.",
            sources=[],
        )

    sources = [
        {
            "type": "rag_document",
            "title": _format_title(metadata.get("source", "Unknown")),
            "page": metadata.get("page"),
        }
        for metadata in metadatas
    ]
    return MedicalGuidelinesResult(
        status="ok",
        query=clean_query,
        content="\n\n---\n\n".join(documents),
        sources=sources,
    )


def _embed_query(text: str) -> list[float]:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPEN_ROUTER_API_KEY"),
    )
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return response.data[0].embedding


def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(name=COLLECTION_NAME)


def _format_title(filename: str) -> str:
    return filename.removesuffix(".pdf").replace("_", " ").replace("-", " ").title()
