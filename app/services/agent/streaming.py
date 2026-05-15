import os
import json
import httpx
from typing import AsyncGenerator, Callable, cast
from openai import AsyncOpenAI, OpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from datetime import date
from dateutil.relativedelta import relativedelta
import chromadb
  
from app.tools.schemas import VaccineScheduleRequest
from app.tools.vaccine_schedule import calculate_vaccine_schedule
from app.tools.red_flags import detect_red_flags

from app.utils.langfuse_logger import langfuse_client
from langfuse import observe, propagate_attributes
from langfuse.openai import openai as langfuse_openai

# --- ✅ MCP CLIENT SETUP ---
async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """
    Memanggil MCP Server (M3) untuk eksekusi tool.
    """
    mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
    
    # Payload standar JSON-RPC 2.0
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            print(f"🔌 Calling MCP Server: {mcp_url}/rpc -> {tool_name}")
            response = await client.post(f"{mcp_url}/rpc", json=payload)
            response.raise_for_status()
            result = response.json()
            
            if "error" in result:
                raise Exception(result["error"].get("message", "MCP Server Error"))
            
            return result.get("result", {})
        except httpx.HTTPStatusError as e:
            raise Exception(f"MCP HTTP Error: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"MCP Connection Failed: {str(e)}")

# --- OPENAI CLIENTS ---
def get_async_client():
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPEN_ROUTER_API_KEY"),
    )

def get_sync_client():
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPEN_ROUTER_API_KEY"),
    )

# --- CHROMADB SETUP (M2) ---
chroma_client = chromadb.PersistentClient(path="./chroma_db")
COLLECTION_NAME = "pediatric_guidelines"

def _get_collection():
    return chroma_client.get_or_create_collection(name=COLLECTION_NAME)

def _embed_query(text: str) -> list[float]:
    client = get_sync_client()
    resp = client.embeddings.create(model="openai/text-embedding-3-small", input=[text])
    return resp.data[0].embedding

def format_title(filename: str) -> str:
    return filename.removesuffix(".pdf").replace("_", " ").replace("-", " ").title()

@observe()
def search_medical_guidelines(query: str) -> tuple[str, list[dict]]:
    """Fungsi pencarian RAG lokal (M2 Scope) - TETAP DIGUNAKAN."""
    emb = _embed_query(query)
    res = _get_collection().query(query_embeddings=[emb], n_results=3)
    if res["documents"] and res["documents"][0]:
        sources = [{"title": format_title(m.get("source", "Unknown")), "page": m.get("page")} for m in res["metadatas"][0]]
        return "\n\n---\n\n".join(res["documents"][0]), sources
    return "Tidak ditemukan panduan medis yang relevan.", []

# --- TOOLS SCHEMA (UNTUK LLM) ---
TOOLS: list[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "search_medical_guidelines",
            "description": "Gunakan untuk pertanyaan medis, ASI, MPASI, vaksin, atau tumbuh kembang.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_vaccine_schedule",
            "description": "Hitung jadwal vaksin berdasarkan tanggal lahir dan riwayat vaksin anak.",
            "parameters": {
                "type": "object",
                "properties": {
                    "birth_date": {"type": "string", "description": "Tanggal lahir anak (YYYY-MM-DD)"},
                    "completed_vaccines": {"type": "array", "items": {"type": "string"}, "description": "Daftar kode vaksin yang sudah diberikan (opsional)"}
                },
                "required": ["birth_date"]
            }
        }
    }
]

MEDICAL_KEYWORDS = ("asi", "mpasi", "makan", "menyusui", "susu", "vaksin", "imunisasi", "bcg", "dpt", "polio", "pcv", "rotavirus", "campak", "rubella", "tumbuh", "kembang", "berat", "tinggi", "demam", "batuk", "diare", "stunting", "posyandu", "bayi", "anak")
VACCINE_KEYWORDS = ("vaksin", "vaksinasi", "imunisasi", "bcg", "dpt", "polio", "pcv", "rotavirus", "campak", "rubella", "mr", "hb0", "hepatitis")

def should_retrieve_guidelines(message: str) -> bool:
    text = message.lower()
    return any(keyword in text for keyword in MEDICAL_KEYWORDS)

@observe()
def should_calculate_vaccine_schedule(message: str) -> bool:
    text = message.lower()
    return any(keyword in text for keyword in VACCINE_KEYWORDS)

@observe()
def _unique_sources(sources: list[dict]) -> list[dict]:
    seen = set()
    unique_sources = []
    for source in sources:
        key = (source["title"], source.get("page"))
        if key not in seen:
            seen.add(key)
            unique_sources.append(source)
    return unique_sources

@observe()
def _format_vaccine_schedule_result(result) -> str:
    def item_lines(title: str, items: list) -> list[str]:
        if not items: return [f"{title}: tidak ada."]
        lines = [f"{title}:"]
        for item in items:
            lines.append(f"- {item.label} ({item.due_age_label})")
        return lines
    
    lines = [
        f"Status: {result.status}",
        f"Usia anak: {result.age_months} bulan ({result.age_days} hari)",
        *item_lines("Sudah tercatat diberikan", result.completed),
        *item_lines("Jatuh tempo sekarang", result.due_now),
        *item_lines("Terlambat/overdue", result.overdue),
        *item_lines("Akan datang", result.upcoming[:6]),
    ]
    if result.warnings:
        lines.append("Catatan:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines)

# --- MAIN STREAMING FUNCTION ---
@observe()
async def stream_chat_response(
    user_message: str,
    child_context: dict | None = None,
    tool_audit_callback: Callable[[dict], None] | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    with propagate_attributes(session_id=session_id):
        async_client = get_async_client()
        today = date.today()
        today_str = today.strftime("%d %B %Y")
        
        # Base Prompt Construction
        base_prompt = (
            f"Anda adalah ParentEase AI, asisten parenting berbasis bukti ilmiah. "
            f"Tanggal hari ini: {today_str}. "
            f"Selalu gunakan tools untuk data medis dan gunakan sumber dari data yang sudah tersedia baik dari pdf atau file lainnya. Jangan mengarang. "
            f"Jawab dalam Bahasa Indonesia dengan nada hangat dan profesional.\n\n"
            
            # ✅ BATASAN TOPIK
            f"🚫 **BATASAN TOPIK YANG WAJIB DIPATUHI**:\n"
            f"- Anda HANYA boleh membahas topik seputar:\n"
            f"  1. **Kesehatan dan tumbuh kembang anak** (ASI, MPASI, vaksinasi, tidur, milestones, dll)\n"
            f"  2. **Kesehatan ibu** (postpartum, menyusui, nutrisi ibu, mental health ibu, dll)\n"
            f"  3. **Peran dan pengasuhan orangtua** (bonding, disiplin positif, stimulasi anak, dll)\n"
            f"  4. **Gizi dan nutrisi keluarga** (pola makan sehat untuk anak dan ibu)\n"
            f"- Anda TIDAK BOLEH membahas topik di luar itu seperti:\n"
            f"  - Teknologi, programming, gadget review\n"
            f"  - Politik, ekonomi, berita umum\n"
            f"  - Topik dewasa yang tidak berkaitan dengan parenting\n"
            f"  - Atau topik non-parenting lainnya\n"
            f"- Jika user bertanya di luar scope, TOLAK dengan sopan dan arahkan kembali ke topik parenting.\n\n"
            
            f"👥 SAPAAN: Gunakan 'Bunda/Ayah', 'Anda', atau 'Parent'. Jangan asumsikan gender.\n\n"
            f"📝 ATURAN FORMAT WAJIB (IKUTI PERSIS):\n\n"
            f"1. STRUKTUR JAWABAN:\n"
            f"- Mulai dengan salam hangat dan konteks singkat\n"
            f"- Gunakan section bernomor untuk topik utama: **1. Judul Section**\n"
            f"- Setiap section maksimal 3-5 poin penting\n\n"
            f"**2. FORMAT LIST  & BULLET:**\n"
            f"- Untuk list utama gunakan: - Poin utama\n"
            f"- Untuk sub-bullet (poin di dalam poin) WAJIB indent 2 spasi:\n"
            f"  - Poin utama:\n"
            f"    - Sub poin level 1 (2 spasi sebelum -)\n"
            f"      - Sub poin level 2 (4 spasi sebelum -)\n"
            f"  - Poin utama berikutnya\n\n"
            
            f"**3. CONTOH FORMAT YANG BENAR:**\n"
            f"**1. Kapan Mulai MPASI?**\n"
            f"- **Usia ideal**: 6 bulan\n"
            f"- **Tanda kesiapan**:\n"
            f"  - Bayi bisa duduk dengan bantuan\n"
            f"  - Kontrol kepala baik\n"
            f"  - Menunjukkan minat pada makanan\n"
            f"- **Yang harus dihindari**:\n"
            f"  - Mulai sebelum 4 bulan\n"
            f"  - Terlalu lama menunda\n\n"
            
            f"**4. FORMATTING TEXT:**\n"
            f"- Gunakan **bold** untuk istilah penting dan angka kunci\n"
            f"- Jangan gunakan ### atau #### (cukup bold dengan **text**)\n"
            f"- Jangan gunakan --- (horizontal rule)\n"
            f"- Gunakan paragraf pendek (2-3 kalimat)\n"
            f"- Beri 1 baris kosong antar section\n\n"
            
            f"**5. LARANGAN KERAS:**\n"
            f"- JANGAN gunakan #### atau ###\n"
            f"- JANGAN gunakan ---\n"
            f"- JANGAN gabungkan kata tanpa spasi\n"
            f"- JANGAN buat list tanpa indentasi untuk sub-poin\n"
            f"- JANGAN bahas topik di luar parenting (teknologi, politik, dll)\n\n"
            
            f"**6. SPASI  & PARAGRAF:**\n"
            f"- SELALU beri spasi antar kata\n"
            f"- Beri jarak 1 baris kosong antar section utama\n"
            f"- Gunakan paragraf pendek agar mudah dibaca\n"

            f"\n**CONTOH RESPONSE YANG BAIK:**\n\n"
            f"Halo Parent! 👋 Berikut informasi untuk Anda:\n\n"
            f"**1. Usia Ideal MPASI**\n"
            f"- **Rekomendasi WHO**: 6 bulan\n"
            f"- **Tanda siap**:\n"
            f"  - Bayi bisa duduk dengan bantuan\n"
            f"  - Kepala tegak dan stabil\n"
            f"  - Menunjukkan minat pada makanan\n\n"
            f"**2. Makanan yang Dianjurkan**\n"
            f"- **Kelompok karbohidrat**:\n"
            f"  - Bubur beras\n"
            f"  - Kentang lumat\n"
            f"  - Ubi halus\n"
            f"- **Kelompok protein**:\n"
            f"  - Ayam cincang halus\n"
            f"  - Ikan tanpa duri\n\n"
            
            # ✅ CONTOH PENOLAKAN TOPIK DI LUAR SCOPE
            f"\n**CONTOH CARA MENOLAK TOPIK DI LUAR SCOPE:**\n"
            f"- Jika user tanya: 'Apa itu JavaScript?'\n"
            f"  Response: 'Maaf Parent, saya khusus membantu seputar parenting, kesehatan anak, dan pengasuhan. "
            f"Untuk pertanyaan tentang teknologi, saya sarankan mencari sumber lain. "
            f"Ada yang bisa saya bantu seputar tumbuh kembang si kecil? 😊'\n"
            f"- Jika user tanya: 'Bagaimana cara coding Python?'\n"
            f"  Response: 'Mohon maaf, saya hanya bisa membantu topik seputar parenting dan kesehatan anak. "
            f"Silakan tanyakan tentang ASI, MPASI, vaksinasi, atau tumbuh kembang anak ya! 😊'\n"
        )

        if child_context:
            birth = child_context.get("birth_date")
            age_months = 0
            if birth:
                try:
                    parsed_birth = birth if isinstance(birth, date) else date.fromisoformat(birth)
                    delta = relativedelta(today,  parsed_birth)
                    age_months = delta.years * 12 + delta.months
                except (TypeError, ValueError):
                    age_months = 0
            base_prompt += f"\n📋 DATA ANAK:\n- Nama: {child_context.get('name', '-')}\n "
            base_prompt += f"- Lahir: {birth}\n- Usia: {age_months} bulan\n "
            base_prompt += f"- Gender: {child_context.get('gender', '-')}\n "
            if child_context.get('weight_kg'):
                base_prompt += f"- Berat: {child_context['weight_kg']} kg\n "
            if child_context.get('height_cm'):
                base_prompt += f"- Tinggi: {child_context['height_cm']} cm\n "

        red_flag = detect_red_flags(user_message, child_context)
        if red_flag.is_red_flag:
            reasons = "\n".join(f"- {reason}" for reason in red_flag.reasons)
            yield (
                "Parent, dari cerita Anda ada tanda bahaya yang perlu ditangani segera.\n\n"
                f"{reasons}\n\n"
                f"**Tindakan:** {red_flag.action}\n\n"
                "Saya tidak bisa memastikan diagnosis lewat chat, tetapi kondisi seperti ini "
                "lebih aman diperiksa langsung oleh tenaga kesehatan."
            )
            return

        retrieved_sources: list[dict] = []
        if should_retrieve_guidelines(user_message):
            try:
                retrieved_context, retrieved_sources = search_medical_guidelines(user_message)
                print(f"🔍 Pre-retrieved {len(retrieved_sources)} source(s)")
                base_prompt += (
                    "\n\n📚 KONTEKS DARI KNOWLEDGE BASE:\n"
                    f"{retrieved_context}\n\n"
                    "Gunakan konteks di atas sebagai sumber utama. Jika konteks tidak cukup, "
                    "jelaskan batasannya dan sarankan konsultasi tenaga kesehatan."
                )
            except Exception as retrieve_err:
                print(f"⚠️ Pre-retrieval error: {retrieve_err}")

        if should_calculate_vaccine_schedule(user_message):
            vaccine_child_context = child_context or {}
            birth_date = vaccine_child_context.get("birth_date")
            if birth_date:
                try:
                    parsed_birth_date = (
                        birth_date if isinstance(birth_date, date) else date.fromisoformat(birth_date)
                    )
                    completed_vaccines = vaccine_child_context.get("completed_vaccines", [])
                    if not isinstance(completed_vaccines, list):
                        completed_vaccines = []
                    vaccine_result = calculate_vaccine_schedule(
                        VaccineScheduleRequest(
                            birth_date=parsed_birth_date,
                            as_of_date=today,
                            completed_vaccines=completed_vaccines,
                        )
                    )
                    if tool_audit_callback:
                        tool_audit_callback(
                            {
                                "tool_name": vaccine_result.tool_name,
                                "status": vaccine_result.status,
                                "input_payload": {
                                    "birth_date": parsed_birth_date.isoformat(),
                                    "as_of_date": today.isoformat(),
                                    "completed_vaccines": completed_vaccines,
                                },
                                "output_payload": vaccine_result.model_dump(mode="json"),
                                "sources": [
                                    source.model_dump(mode="json")
                                    for source in vaccine_result.sources
                                ],
                            }
                        )
                    print("💉 Calculated vaccine schedule from child profile")
                    base_prompt += (
                        "\n\n💉 HASIL TOOL calculate_vaccine_schedule:\n"
                        f"{_format_vaccine_schedule_result(vaccine_result)}\n\n"
                        "Jika user bertanya jadwal vaksin, gunakan hasil tool ini sebagai jawaban utama. "
                        "Jelaskan bahwa jadwal bergantung pada riwayat vaksin yang sudah diterima."
                    )
                    retrieved_sources.extend(
                        source.model_dump() for source in vaccine_result.sources
                    )
                except Exception as vaccine_err:
                    print(f"⚠️ Vaccine schedule error: {vaccine_err}")
            else:
                base_prompt += (
                    "\n\n💉 CATATAN TOOL VAKSIN:\n"
                    "User bertanya tentang vaksin, tetapi tanggal lahir anak belum tersedia. "
                    "Minta tanggal lahir anak sebelum menghitung jadwal vaksin personal."
                )

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": base_prompt},
            {"role": "user", "content": user_message},
        ]

        # LANGFUSE: Safe Client Selection
        trace = None

        if langfuse_client is not None:
            try:
                trace_method = getattr(langfuse_client, "trace", None)
                
                if trace_method is not None:
                    trace = trace_method(
                        name="parentease_chat",
                        session_id=session_id,
                        user_id=child_context.get("name") if child_context else None,
                        metadata={"model": "mistralai/mistral-large"}
                    )
            except Exception as e:
                print(f"⚠️ Langfuse trace creation failed: {e}")
                trace = None

        # LANGFUSE: Safe Client Selection
        # Jika langfuse aktif, gunakan client ter-instrumentasi. Jika tidak, pakai async_client biasa.
        llm_client: AsyncOpenAI = async_client 

        if langfuse_client is not None:
            try:
                from langfuse.openai import openai as langfuse_openai
                # Wrapper Langfuse mewarisi AsyncOpenAI, jadi assignment ini valid
                llm_client = langfuse_openai.AsyncOpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=os.getenv("OPEN_ROUTER_API_KEY"),
                )
            except ImportError:
                # Jika langfuse openai wrapper tidak ada, tetap gunakan async_client default
                pass

        try:        
            # 🔍 LOG: Check ChromaDB status
            try:
                collection = _get_collection()
                count = collection.count()
                print(f"📚 ChromaDB has {count} documents")
            except Exception as db_err:
                print(f"⚠️ ChromaDB check error: {db_err}")
            
            stream = await llm_client.chat.completions.create(
                model="mistralai/mistral-large",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                stream=True,
            )
            
            tool_calls_buffer = []
            has_tools = False
            _last_char = ""

            # 1️⃣ Stream awal (bisa trigger tool call)
            async for chunk in stream:
                token = chunk.choices[0].delta.content
                if token:
                    # Auto-space
                    if _last_char and _last_char.isalnum() and len(token) > 0 and token[0].isalnum():
                        yield " "
                    yield token
                    _last_char = token[-1]

                if chunk.choices[0].delta.tool_calls:
                    has_tools = True
                    for tc in chunk.choices[0].delta.tool_calls:
                        if not tool_calls_buffer or tool_calls_buffer[-1].get("index") != tc.index:
                            tool_calls_buffer.append(
                                {
                                    "index": tc.index,
                                    "id": tc.id,
                                    "function": {"name": "", "arguments": ""},
                                }
                            )
                        target = tool_calls_buffer[-1]
                        if not isinstance(target.get("function"), dict):
                            target["function"] = {"name": "", "arguments": ""}
                        function = target["function"]
                        if tc.function and tc.function.name:
                            function["name"] = f"{function.get('name', '')}{tc.function.name}"
                        if tc.function and tc.function.arguments:
                            function["arguments"] = (
                                f"{function.get('arguments', '')}{tc.function.arguments}"
                            )

            # 2️⃣ Eksekusi tools
            all_sources = list(retrieved_sources)
            if has_tools and tool_calls_buffer:
                print(f"🔧 Executing {len(tool_calls_buffer)} tool call(s)")
                messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls_buffer})
                
                for tc in tool_calls_buffer:
                    try:
                        args = json.loads(tc[ "function "][ "arguments "])
                        tool_name = tc[ "function "][ "name "]
                        print(f"🔍 Tool Requested: {tool_name} with args: {args} ")
                        
                        # ✅ MCP INTEGRATION LOGIC
                        if tool_name == "calculate_vaccine_schedule":
                            print(f"🔌 Routing to MCP Server...")
                            try:
                                mcp_result = await call_mcp_tool(tool_name, args)
                                # Convert MCP result (dict) to JSON string for LLM
                                res = json.dumps(mcp_result, ensure_ascii=False)
                                # Extract sources if available in MCP result
                                srcs = mcp_result.get("sources", []) 
                            except Exception as mcp_err:
                                print(f"❌ MCP Execution Error: {mcp_err}")
                                res = f"Error calling tool via MCP: {mcp_err}"
                                srcs = []
                                
                        elif tool_name == "search_medical_guidelines":
                            # Fallback ke local logic (M2 Scope)
                            query = args.get("query", " ")
                            print(f"🔍 Searching locally for: {query} ")
                            res, srcs = search_medical_guidelines(query)
                            print(f"✅ Found {len(srcs)} source(s) ")
                        else:
                            res = f"Tool {tool_name} tidak dikenali."
                            srcs = []
                        
                        all_sources.extend(srcs)
                        messages.append(
                            cast(
                                ChatCompletionMessageParam,
                                {
                                    "role ":  "tool ",
                                    "tool_call_id ": tc[ "id "],
                                    "name ": tool_name,
                                    "content ": res,
                                },
                            )
                        )
                    except Exception as tool_err:
                        print(f"❌ Tool execution error: {tool_err} ")
                        import traceback
                        traceback.print_exc()
                        messages.append(
                            cast(
                                ChatCompletionMessageParam,
                                {
                                    "role ":  "tool ",
                                    "tool_call_id ": tc[ "id "],
                                    "name ": tool_name,
                                    "content ": (
                                        "Maaf, tidak dapat mengakses informasi medis saat ini. "
                                    ),
                                },
                            )
                        )

                # 3️⃣ Stream respons akhir
                print("🔄 Generating final response...")
                try:
                    final_stream = await async_client.chat.completions.create(
                        model="mistralai/mistral-large", messages=messages, stream=True
                    )
                    
                    final_content = ""
                    async for chunk in final_stream:
                        token = chunk.choices[0].delta.content
                        if token:
                            # Auto-space
                            if _last_char and _last_char.isalnum() and len(token) > 0 and token[0].isalnum():
                                yield " "
                            yield token
                            _last_char = token[-1]
                            final_content += token
                    
                    if not final_content:
                        print("⚠️ WARNING: Final stream returned empty content!")
                        # Fallback: berikan pesan default
                        yield "\n\nMaaf, saya tidak dapat menemukan informasi spesifik untuk pertanyaan ini. Silakan konsultasikan dengan tenaga medis."
                        
                except Exception as final_err:
                    print(f"❌ Final stream error: {final_err}")
                    yield "\n\nMaaf, terjadi gangguan teknis saat menyusun jawaban."

                # 4️⃣ Kirim sources
                unique_sources = _unique_sources(all_sources)
                
                if unique_sources:
                    print(f"📎 Sending {len(unique_sources)} source(s) to frontend")
                    yield f"\n\n[SOURCES] {json.dumps(unique_sources)}\n\n"
                else:
                    print("⚠️ No sources to send")

            elif not has_tools:
                print("ℹ️ No tool calls detected - direct response")
                unique_sources = _unique_sources(retrieved_sources)
                if unique_sources:
                    print(f"📎 Sending {len(unique_sources)} pre-retrieved source(s) to frontend")
                    yield f"\n\n[SOURCES] {json.dumps(unique_sources)}\n\n"

            # ✅ LANGFUSE: Update trace pada success (Safe check)
            if trace:
                try:
                    trace.update(
                        output={
                            "status": "completed",
                            "tools_executed": has_tools
                        }
                    )
                except Exception as trace_err:
                    print(f"⚠️ Failed to update trace: {trace_err}")

        except Exception as e:
            print(f"❌ Streaming error: {e}")
            import traceback
            traceback.print_exc()
            
            # LANGFUSE: Catat error ke trace
            if trace:
                try:
                    trace.update(
                        output={"error": str(e)},
                        level="ERROR"
                    )
                except Exception as trace_err:
                    print(f"⚠️ Failed to update trace with error: {trace_err}")
            
            yield f"\n\n❌ Terjadi kesalahan: {str(e)}"
            raise