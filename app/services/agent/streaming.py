import os
import json
from typing import AsyncGenerator
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from datetime import date
from dateutil.relativedelta import relativedelta
import chromadb
from openai import OpenAI

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

chroma_client = chromadb.PersistentClient(path="./chroma_db")
COLLECTION_NAME = "pediatric_guidelines"

def _get_collection():
    return chroma_client.get_or_create_collection(name=COLLECTION_NAME)

def _embed_query(text: str) -> list[float]:
    client = get_sync_client()
    resp = client.embeddings.create(model="openai/text-embedding-3-small", input=[text])
    return resp.data[0].embedding

def _format_title(filename: str) -> str:
    return filename.removesuffix(".pdf").replace("_", " ").replace("-", " ").title()

def search_medical_guidelines(query: str) -> tuple[str, list[dict]]:
    emb = _embed_query(query)
    res = _get_collection().query(query_embeddings=[emb], n_results=3)
    if res["documents"] and res["documents"][0]:
        sources = [{"title": _format_title(m.get("source", "Unknown")), "page": m.get("page")} for m in res["metadatas"][0]]
        return "\n\n---\n\n".join(res["documents"][0]), sources
    return "Tidak ditemukan panduan medis yang relevan.", []

TOOLS = [
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
    }
]

async def stream_chat_response(
    user_message: str,
    child_context: dict | None = None,
) -> AsyncGenerator[str, None]:
    async_client = get_async_client()
    today = date.today()
    today_str = today.strftime("%d %B %Y")
    
    base_prompt = (
        f"Anda adalah ParentEase AI, asisten parenting berbasis bukti ilmiah. "
        f"Tanggal hari ini: **{today_str}**. "
        f"Selalu gunakan tools untuk data medis dan gunakan sumber dari data yang sudah tersedia baik dari pdf atau file lainnya. Jangan mengarang. "
        f"Jawab dalam Bahasa Indonesia dengan nada hangat dan profesional.\n\n"
        f"👥 SAPAAN: Gunakan 'Bunda/Ayah', 'Anda', atau 'Parent'. Jangan asumsikan gender.\n\n"
        f"📝 ATURAN FORMAT WAJIB (IKUTI PERSIS):\n\n"
        f"**1. STRUKTUR JAWABAN:**\n"
        f"- Mulai dengan salam hangat dan konteks singkat\n"
        f"- Gunakan section bernomor untuk topik utama: **1. Judul Section**\n"
        f"- Setiap section maksimal 3-5 poin penting\n\n"
        
        f"**2. FORMAT LIST & BULLET:**\n"
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
        f"  - Bisa duduk dengan bantuan\n"
        f"  - Kontrol kepala baik\n"
        f"  - Minat pada makanan\n"
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
        f"- JANGAN buat list tanpa indentasi untuk sub-poin\n\n"
        
        f"**6. SPASI & PARAGRAF:**\n"
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
    )
    
    if child_context:
        birth = child_context.get("birth_date")
        age_months = 0
        if birth:
            try:
                delta = relativedelta(today, date.fromisoformat(birth))
                age_months = delta.years * 12 + delta.months
            except: pass
        base_prompt += f"\n📋 DATA ANAK:\n- Nama: {child_context.get('name', '-')}\n"
        base_prompt += f"- Lahir: {birth}\n- Usia: {age_months} bulan\n"
        base_prompt += f"- Gender: {child_context.get('gender', '-')}\n"
        if child_context.get('weight_kg'): base_prompt += f"- Berat: {child_context['weight_kg']} kg\n"
        if child_context.get('height_cm'): base_prompt += f"- Tinggi: {child_context['height_cm']} cm\n"

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": base_prompt},
        {"role": "user", "content": user_message},
    ]
    
    try:
        # 🔍 LOG: Check ChromaDB status
        try:
            collection = _get_collection()
            count = collection.count()
            print(f"📚 ChromaDB has {count} documents")
        except Exception as db_err:
            print(f"⚠️ ChromaDB check error: {db_err}")
        
        stream = await async_client.chat.completions.create(
            model="mistralai/mistral-large", messages=messages, tools=TOOLS, tool_choice="auto", stream=True
        )  # ty:ignore[no-matching-overload]
        
        tool_calls_buffer = []
        has_tools = False
        _last_char = ""
        first_stream_content = ""  # ✅ Track content dari stream pertama

        # 1️⃣ Stream awal (bisa trigger tool call)
        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                # Auto-space
                if _last_char and _last_char.isalnum() and len(token) > 0 and token[0].isalnum():
                    yield " "
                yield token
                _last_char = token[-1]
                first_stream_content += token

            if chunk.choices[0].delta.tool_calls:
                has_tools = True
                for tc in chunk.choices[0].delta.tool_calls:
                    if not tool_calls_buffer or tool_calls_buffer[-1].get("index") != tc.index:
                        tool_calls_buffer.append({"index": tc.index, "id": tc.id, "function": {"name": "", "arguments": ""}})
                    target = tool_calls_buffer[-1]
                    if tc.function and tc.function.name: target["function"]["name"] += tc.function.name
                    if tc.function and tc.function.arguments: target["function"]["arguments"] += tc.function.arguments

        # 2️⃣ Eksekusi tools
        all_sources = []
        if has_tools and tool_calls_buffer:
            print(f"🔧 Executing {len(tool_calls_buffer)} tool call(s)")
            messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls_buffer})
            
            for tc in tool_calls_buffer:
                try:
                    args = json.loads(tc["function"]["arguments"])
                    query = args.get("query", "")
                    print(f"🔍 Searching for: {query}")
                    
                    res, srcs = search_medical_guidelines(query)
                    print(f"✅ Found {len(srcs)} source(s)")
                    
                    all_sources.extend(srcs)
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "name": "search_medical_guidelines", "content": res})  # ty:ignore[invalid-argument-type]
                except Exception as tool_err:
                    print(f"❌ Tool execution error: {tool_err}")
                    import traceback
                    traceback.print_exc()
                    messages.append({
                        "role": "tool", 
                        "tool_call_id": tc["id"], 
                        "name": "search_medical_guidelines", 
                        "content": "Maaf, tidak dapat mengakses informasi medis saat ini."
                    })  # ty:ignore[invalid-argument-type]

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
            seen = set()
            unique_sources = []
            for s in all_sources:
                key = (s["title"], s.get("page"))
                if key not in seen:
                    seen.add(key)
                    unique_sources.append(s)
            
            if unique_sources:
                print(f"📎 Sending {len(unique_sources)} source(s) to frontend")
                yield f"\n\n[SOURCES] {json.dumps(unique_sources)}\n\n"
            else:
                print("⚠️ No sources to send")

        elif not has_tools:
            print("ℹ️ No tool calls detected - direct response")

    except Exception as e:
        print(f"❌ Streaming error: {e}")
        import traceback
        traceback.print_exc()
        yield f"\n\n❌ Terjadi kesalahan: {str(e)}"
        raise