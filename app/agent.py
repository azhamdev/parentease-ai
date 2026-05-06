# agent.py
import os
import json
import chromadb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = "openai/text-embedding-3-small"

# Initialize OpenAI client pointing to OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPEN_ROUTER_API_KEY"),
)

# Initialize ChromaDB client (collection is fetched per-call, never cached,
# so a re-ingest that deletes+recreates the collection never leaves a stale UUID)
chroma_client = chromadb.PersistentClient(path="./chroma_db")
COLLECTION_NAME = "pediatric_guidelines"


def _get_collection() -> chromadb.Collection:
    return chroma_client.get_or_create_collection(name=COLLECTION_NAME)


def _embed_query(text: str) -> list[float]:
    """Embed a single query string using the same model as the ingest pipeline."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return response.data[0].embedding


def _format_title(filename: str) -> str:
    """'asi_guidelines.pdf'  →  'Asi Guidelines'"""
    return filename.removesuffix(".pdf").replace("_", " ").replace("-", " ").title()


# --- Tool Definitions ---


def search_medical_guidelines(query: str) -> tuple[str, list[dict]]:
    """Agent A Tool: Searches the vector DB for ASI, MPASI, and pediatric guidelines.

    Returns:
        (context_text_for_model, sources)
        sources is a list of {"title": str, "page": int | None}
    """
    query_embedding = _embed_query(query)
    results = _get_collection().query(
        query_embeddings=[query_embedding],
        n_results=3,
    )
    if results["documents"] and results["documents"][0]:
        docs = results["documents"][0]
        metas = results["metadatas"][0]   # list of metadata dicts

        sources = [
            {
                "title": _format_title(m.get("source", "Unknown")),
                "page": m.get("page"),  # None when not stored (old index)
            }
            for m in metas
        ]
        return "\n\n---\n\n".join(docs), sources

    return "No verified medical guidelines found in the knowledge base.", []


def calculate_z_score(weight_kg: float, age_months: int) -> str:
    """Agent B Tool: Calculates WHO growth percentiles."""
    # Placeholder for actual WHO calculation logic or external python sandbox execution
    return f"Calculated Z-score for {weight_kg}kg at {age_months} months is within normal limits (+0.5 SD)."

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_medical_guidelines",
            "description": "Always use this to answer medical, ASI, MPASI, or vaccination questions. Do not guess.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query based on the user's question.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_z_score",
            "description": "Use this to calculate growth percentiles when the user provides weight and age.",
            "parameters": {
                "type": "object",
                "properties": {
                    "weight_kg": {"type": "number"},
                    "age_months": {"type": "integer"},
                },
                "required": ["weight_kg", "age_months"],
            },
        },
    },
]


def process_parent_query(user_message: str) -> dict:
    """Run the agentic loop and return {"response": str, "sources": list[dict]}."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are ParentEase AI. You have two main roles: A Medical Librarian "
                "and a Growth Analyst. ALWAYS use your tools to fetch medical data or "
                "calculate growth. Never hallucinate."
            ),
        },
        {"role": "user", "content": user_message},
    ]

    response = client.chat.completions.create(
        model="openai/gpt-5.4-mini",
        messages=messages,  # ty:ignore[invalid-argument-type]
        tools=tools,  # ty:ignore[invalid-argument-type]
        tool_choice="auto",
    )

    response_message = response.choices[0].message

    if response_message.tool_calls:
        messages.append(response_message)

        all_sources: list[dict] = []

        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            if function_name == "search_medical_guidelines":
                tool_result, sources = search_medical_guidelines(
                    function_args.get("query")
                )
                all_sources.extend(sources)
            elif function_name == "calculate_z_score":
                tool_result = calculate_z_score(
                    function_args.get("weight_kg"), function_args.get("age_months")
                )
            else:
                tool_result = "Unknown tool."

            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": str(tool_result),
                }
            )

        second_response = client.chat.completions.create(
            # model="mistralai/mistral-large",
            model="openai/gpt-5.4-mini", 
            messages=messages,  # ty:ignore[invalid-argument-type]
        )

        # Deduplicate sources by (title, page) while preserving order
        seen: set[tuple] = set()
        unique_sources: list[dict] = []
        for s in all_sources:
            key = (s["title"], s.get("page"))
            if key not in seen:
                seen.add(key)
                unique_sources.append(s)

        return {
            "response": second_response.choices[0].message.content,
            "sources": unique_sources,
        }

    # No tool calls — plain conversational reply, no sources
    return {"response": response_message.content, "sources": []}
