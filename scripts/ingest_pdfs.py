#!/usr/bin/env python3
"""
Ingest medical PDF guidelines into ChromaDB for the ParentEase AI Medical Librarian.

Reads every *.pdf from the data/ directory, splits the text into token-sized
chunks with Chonkie, embeds each chunk via the OpenRouter embeddings endpoint
(openai/text-embedding-3-small), and stores the results in the ChromaDB
'pediatric_guidelines' collection.

Usage (from project root):
    uv run python -m scripts.ingest_pdfs
"""

import os
import sys
import uuid
import pathlib
from datetime import datetime

from dotenv import load_dotenv
import chromadb
import pypdf
from openai import OpenAI
from chonkie import TokenChunker
from sqlmodel import Session, select

from app.database import engine
from app.models import Document

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CHROMA_PATH = ROOT / "chroma_db"

COLLECTION_NAME = "pediatric_guidelines"
EMBEDDING_MODEL = "openai/text-embedding-3-small"

# TokenChunker settings (tokens, not characters)
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64

# How many chunks to send per embedding API call (max ~2 048 for most endpoints)
EMBED_BATCH_SIZE = 96

# How many (id, doc, embedding, metadata) rows to upsert into ChromaDB at once
CHROMA_BATCH_SIZE = 256

# ── Clients ────────────────────────────────────────────────────────────────────

openai_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPEN_ROUTER_API_KEY"),
)

chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))


# ── Helpers ────────────────────────────────────────────────────────────────────

# Page range: (start_char_inclusive, end_char_exclusive, page_number_1indexed)
PageRange = tuple[int, int, int]


def extract_text_with_pages(
    pdf_path: pathlib.Path,
) -> tuple[str, list[PageRange]]:
    """Return (full_text, page_ranges) so each chunk can be mapped to a page.

    page_ranges is a list of (start, end, page_num) where start/end are
    character offsets in full_text and page_num is 1-indexed.
    """
    reader = pypdf.PdfReader(pdf_path)
    page_texts: list[str] = [p.extract_text() or "" for p in reader.pages]

    page_ranges: list[PageRange] = []
    offset = 0
    for i, text in enumerate(page_texts):
        if i > 0:
            offset += 2  # accounts for the "\n\n" separator added by join()
        page_ranges.append((offset, offset + len(text), i + 1))
        offset += len(text)

    return "\n\n".join(page_texts), page_ranges


def get_page_number(start_index: int, page_ranges: list[PageRange]) -> int:
    """Return the 1-indexed page number for a chunk that starts at start_index."""
    for start, end, page_num in page_ranges:
        if start <= start_index < end:
            return page_num
    # Fallback: nearest page (handles edge case where chunk starts in a separator)
    return min(page_ranges, key=lambda r: abs(r[0] - start_index))[2]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings and return their float vectors."""
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def upsert_document_metadata(
    *,
    filename: str,
    status: str,
    chunk_count: int = 0,
    error_message: str | None = None,
) -> None:
    """Record local ingestion metadata in PostgreSQL for demo/proof checks."""
    now = datetime.utcnow()
    with Session(engine) as session:
        stmt = select(Document).where(Document.filename == filename)
        document = session.exec(stmt).first()
        if document is None:
            document = Document(filename=filename)
            session.add(document)

        document.source_type = "pdf"
        document.status = status
        document.collection_name = COLLECTION_NAME
        document.chunk_count = chunk_count
        document.error_message = error_message
        document.updated_at = now
        document.ingested_at = now if status == "completed" else None
        session.commit()


# ── Main ingestion logic ───────────────────────────────────────────────────────


def ingest() -> None:
    pdf_files = sorted(DATA_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"[ERROR] No PDF files found in {DATA_DIR}")
        sys.exit(1)

    print(f"[INFO] Found {len(pdf_files)} PDF(s): {[f.name for f in pdf_files]}")

    # Always start fresh so re-runs don't leave stale chunks (e.g. without page numbers)
    try:
        chroma_client.delete_collection(name=COLLECTION_NAME)
        print(f"[INFO] Cleared existing collection '{COLLECTION_NAME}'")
    except Exception:
        pass
    collection = chroma_client.create_collection(name=COLLECTION_NAME)

    # TokenChunker: fast, no ML model required, tokenizer matches embedding model
    chunker = TokenChunker(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    total_stored = 0

    for pdf_path in pdf_files:
        print(f"\n── {pdf_path.name} ──")
        upsert_document_metadata(filename=pdf_path.name, status="processing")

        try:
            raw_text, page_ranges = extract_text_with_pages(pdf_path)
            if not raw_text.strip():
                message = "No text extracted; file may be scanned."
                print(f"  [WARN] {message} Skipping.")
                upsert_document_metadata(
                    filename=pdf_path.name,
                    status="skipped",
                    error_message=message,
                )
                continue

            # 1. Chunk ───────────────────────────────────────────────────────
            chunks = chunker(raw_text)
            texts = [chunk.text for chunk in chunks]
            print(
                f"  Chunks   : {len(texts):>5}  (size={CHUNK_SIZE}t, overlap={CHUNK_OVERLAP}t)"
            )

            # 2. Embed in batches ────────────────────────────────────────────
            all_embeddings: list[list[float]] = []
            num_batches = (len(texts) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE

            for i in range(num_batches):
                batch = texts[i * EMBED_BATCH_SIZE : (i + 1) * EMBED_BATCH_SIZE]
                all_embeddings.extend(embed_texts(batch))
                print(f"  Embedded : batch {i + 1}/{num_batches}  ({len(batch)} chunks)")

            # 3. Build metadata - include page number for each chunk ─────────
            ids = [str(uuid.uuid4()) for _ in chunks]
            metadatas = [
                {
                    "source": pdf_path.name,
                    "chunk_index": idx,
                    "page": get_page_number(chunk.start_index, page_ranges),
                }
                for idx, chunk in enumerate(chunks)
            ]

            # 4. Upsert into ChromaDB in batches ─────────────────────────────
            num_chroma_batches = (len(texts) + CHROMA_BATCH_SIZE - 1) // CHROMA_BATCH_SIZE
            for i in range(num_chroma_batches):
                s = i * CHROMA_BATCH_SIZE
                e = s + CHROMA_BATCH_SIZE
                collection.add(
                    ids=ids[s:e],
                    documents=texts[s:e],
                    embeddings=all_embeddings[s:e],
                    metadatas=metadatas[s:e],
                )

            total_stored += len(texts)
            upsert_document_metadata(
                filename=pdf_path.name,
                status="completed",
                chunk_count=len(texts),
            )
            print(
                f"  Stored   : {len(texts):>5} chunks  ->  collection total: {collection.count()}"
            )
        except Exception as exc:
            upsert_document_metadata(
                filename=pdf_path.name,
                status="failed",
                error_message=str(exc),
            )
            raise

    print(
        f"\n[DONE] Ingested {total_stored} chunk(s) from {len(pdf_files)} file(s)."
        f" Collection '{COLLECTION_NAME}' now holds {collection.count()} document(s)."
    )


if __name__ == "__main__":
    ingest()
