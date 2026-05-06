# agent.py
import os
import json
import chromadb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Initialize OpenAI client pointing to OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPEN_ROUTER_API_KEY"),
)

# Initialize ChromaDB for RAG (Agent A)
chroma_client = chromadb.PersistentClient(path="./chroma_db")
medical_collection = chroma_client.get_or_create_collection(name="pediatric_guidelines")

# --- Tool Definitions ---

def search_medical_guidelines(query: str) -> str:
    """Agent A Tool: Searches the vector DB for ASI, MPASI, and pediatric guidelines."""
    results = medical_collection.query(
        query_texts=[query],
        n_results=2
    )
    # Simplified return; in reality, parse the documents
    if results['documents'] and results['documents'][0]:
        return "\n".join(results['documents'][0])
    return "No verified medical guidelines found in the knowledge base."

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
                    "query": {"type": "string", "description": "The search query based on the user's question."}
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
                    "age_months": {"type": "integer"}
                },
                "required": ["weight_kg", "age_months"],
            },
        },
    }
]

def process_parent_query(user_message: str) -> str:
    messages = [
        {"role": "system", "content": "You are ParentEase AI. You have two main roles: A Medical Librarian and a Growth Analyst. ALWAYS use your tools to fetch medical data or calculate growth. Never hallucinate."},
        {"role": "user", "content": user_message}
    ]

    response = client.chat.completions.create(
        model="mistralai/mistral-large", # Or your preferred mistral variant
        messages=messages,  # ty:ignore[invalid-argument-type]
        tools=tools,  # ty:ignore[invalid-argument-type]
        tool_choice="auto",
    )

    response_message = response.choices[0].message

    # Handle Tool Calls if Mistral decides to use one
    if response_message.tool_calls:
        messages.append(response_message) # Append assistant's intent to call tool
        
        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            # Execute the respective tool
            if function_name == "search_medical_guidelines":
                tool_result = search_medical_guidelines(function_args.get("query"))
            elif function_name == "calculate_z_score":
                tool_result = calculate_z_score(function_args.get("weight_kg"), function_args.get("age_months"))
            else:
                tool_result = "Unknown tool."

            # Append tool result back to the context
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": str(tool_result),
            })
            
        # Get final response from Mistral after reading the tool output
        second_response = client.chat.completions.create(
            model="mistralai/mistral-large",
            messages=messages,  # ty:ignore[invalid-argument-type]
        )
        return second_response.choices[0].message.content

    return response_message.content