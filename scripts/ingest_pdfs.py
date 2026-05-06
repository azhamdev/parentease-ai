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

from dotenv import load_dotenv
import chromadb
import pypdf
from openai import OpenAI
from chonkie import TokenChunker

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


def extract_text(pdf_path: pathlib.Path) -> str:
    """Return all text from a PDF, pages joined by a blank line."""
    reader = pypdf.PdfReader(pdf_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings and return their float vectors."""
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


# ── Main ingestion logic ───────────────────────────────────────────────────────


def ingest() -> None:
    pdf_files = sorted(DATA_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"[ERROR] No PDF files found in {DATA_DIR}")
        sys.exit(1)

    print(f"[INFO] Found {len(pdf_files)} PDF(s): {[f.name for f in pdf_files]}")

    # get_or_create keeps reruns idempotent; existing docs are preserved
    collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

    # TokenChunker: fast, no ML model required, tokenizer matches embedding model
    chunker = TokenChunker(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    total_stored = 0

    for pdf_path in pdf_files:
        print(f"\n── {pdf_path.name} ──")

        raw_text = extract_text(pdf_path)
        if not raw_text.strip():
            print("  [WARN] No text extracted – is this a scanned PDF? Skipping.")
            continue

        # 1. Chunk ───────────────────────────────────────────────────────────
        chunks = chunker(raw_text)
        texts = [chunk.text for chunk in chunks]
        print(
            f"  Chunks   : {len(texts):>5}  (size={CHUNK_SIZE}t, overlap={CHUNK_OVERLAP}t)"
        )

        # 2. Embed in batches ────────────────────────────────────────────────
        all_embeddings: list[list[float]] = []
        num_batches = (len(texts) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE

        for i in range(num_batches):
            batch = texts[i * EMBED_BATCH_SIZE : (i + 1) * EMBED_BATCH_SIZE]
            all_embeddings.extend(embed_texts(batch))
            print(f"  Embedded : batch {i + 1}/{num_batches}  ({len(batch)} chunks)")

        # 3. Build metadata ──────────────────────────────────────────────────
        ids = [str(uuid.uuid4()) for _ in texts]
        metadatas = [
            {"source": pdf_path.name, "chunk_index": idx} for idx in range(len(texts))
        ]

        # 4. Upsert into ChromaDB in batches ─────────────────────────────────
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
        print(
            f"  Stored   : {len(texts):>5} chunks  →  collection total: {collection.count()}"
        )

    print(
        f"\n[DONE] Ingested {total_stored} chunk(s) from {len(pdf_files)} file(s)."
        f" Collection '{COLLECTION_NAME}' now holds {collection.count()} document(s)."
    )


if __name__ == "__main__":
    ingest()
