# agent.py
import os
import json
import chromadb
from openai import OpenAI
from dotenv import load_dotenv
from datetime import date
from dateutil.relativedelta import relativedelta

load_dotenv()

EMBEDDING_MODEL = "openai/text-embedding-3-small"

# Initialize OpenAI client pointing to OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPEN_ROUTER_API_KEY"),
)

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
        metas = results["metadatas"][0]  # list of metadata dicts

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


# Define the tools schema for Mistral
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


def process_parent_query(user_message: str, child_context: dict | None = None) -> dict:
    """
    Run the agentic loop and return {"response": str, "sources": list[dict]}.
    child_context: dict dengan keys: birth_date, gender, name, weight_kg, height_cm, topic
    """
    
    # 📅 Tanggal hari ini
    today = date.today()
    today_str = today.strftime("%d %B %Y")

    # 🧠 System Prompt dengan Panduan Menyapa Parent
    base_prompt = (
        f"You are ParentEase AI, asisten parenting berbasis evidence untuk orangtua baru. "
        f"Tanggal hari ini adalah **{today_str}**. "
        f"ALWAYS use your tools to fetch medical data or calculate growth. Never hallucinate. "
        f"Reply in Indonesian with warm, empathetic, and professional tone.\n\n"
        
        f"👥 PANDUAN MENYAPA (WAJIB): "
        f"Sapa pengguna sebagai 'Parent'. Gunakan sapaan yang inklusif untuk Ibu maupun Ayah, "
        f"seperti 'Bunda atau Ayah', 'Ayah/Bunda', atau 'Anda'. JANGAN mengasumsikan gender orangtua. "
        f"Akui peran mereka sebagai pengasuh yang peduli. "
        f"Contoh aman: 'Baik, Bunda/Papa, berikut info untuk si kecil...' atau 'Sebagai orangtua yang perhatian, pertanyaan Anda sangat relevan...'"
    )
    
    # ✅ Injeksi data anak jika ada
    if child_context:
        birth_date_str = child_context.get("birth_date")
        age_months = 0
        age_years = 0
        
        if birth_date_str:
            try:
                # Hitung usia dari birth_date
                birth = date.fromisoformat(birth_date_str)
                delta = relativedelta(today, birth)
                age_years = delta.years
                age_months = delta.months
                total_months = age_years * 12 + age_months
            except Exception as e:
                print(f"⚠️ Error calculating age: {e}")
                total_months = 0
        
        base_prompt += f"\n\n📋 CURRENT CHILD PROFILE (USE THIS DATA):\n"
        base_prompt += f"- Name: {child_context.get('name', 'Unknown')}\n"
        base_prompt += f"- Birth Date: {child_context.get('birth_date', 'Unknown')}\n"
        base_prompt += f"- Age: {total_months} months"
        
        if age_years > 0:
            base_prompt += f" ({age_years} year(s) and {age_months} month(s))"
        base_prompt += "\n"
        
        base_prompt += f"- Gender: {child_context.get('gender', 'Unknown')}\n"
        
        if child_context.get('weight_kg'):
            base_prompt += f"- Weight: {child_context['weight_kg']} kg\n"
        if child_context.get('height_cm'):
            base_prompt += f"- Height: {child_context['height_cm']} cm\n"
        if child_context.get('topic'):
            base_prompt += f"- Parent Focus: {child_context['topic']}\n"
        
        base_prompt += "\n⚠️ ALWAYS use this child's data to answer questions. "
        base_prompt += "If user asks about THEIR child, use the data above. "
        base_prompt += f"Calculate age based on today's date ({today_str}) and birth_date.\n"

    messages = [
        {"role": "system", "content": base_prompt},
        {"role": "user", "content": user_message},
    ]

    # ... sisa kode agent.py tetap sama (tool calls, dll) ...
    response = client.chat.completions.create(
        model="mistralai/mistral-large",
        messages=messages,
        tools=tools,
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
                tool_result, sources = search_medical_guidelines(function_args.get("query"))
                all_sources.extend(sources)
            elif function_name == "calculate_z_score":
                tool_result = calculate_z_score(
                    function_args.get("weight_kg"), 
                    function_args.get("age_months")
                )
            else:
                tool_result = "Unknown tool."

            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": str(tool_result),
            })

        second_response = client.chat.completions.create(
            model="mistralai/mistral-large",
            messages=messages,
        )
        
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

    return {"response": response_message.content, "sources": []}