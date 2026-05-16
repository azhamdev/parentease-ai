import os
import json
from typing import AsyncGenerator, Callable, cast
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from datetime import date
from dateutil.relativedelta import relativedelta

from app.services.agent.intent_classifier import classify_intent
from app.services.agent.mcp_client import MCPClientError, get_mcp_client
from app.tools.verify_url import extract_urls

from app.utils import langfuse_logger
from langfuse import observe, propagate_attributes


# --- ✅ MCP CLIENT SETUP ---
async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """Memanggil MCP Server M3 lewat MCP client milik M1."""
    client = await get_mcp_client()
    return await client.call_tool(tool_name, arguments)


def _structured_error(error: Exception) -> dict:
    if isinstance(error, MCPClientError):
        return error.to_dict()
    return {
        "type": error.__class__.__name__,
        "message": str(error),
        "retryable": False,
    }


# --- OPENAI CLIENTS ---
def get_async_client():
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPEN_ROUTER_API_KEY"),
    )


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
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_vaccine_schedule",
            "description": "Hitung jadwal vaksin berdasarkan tanggal lahir dan riwayat vaksin anak.",
            "parameters": {
                "type": "object",
                "properties": {
                    "birth_date": {
                        "type": "string",
                        "description": "Tanggal lahir anak (YYYY-MM-DD)",
                    },
                    "completed_vaccines": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Daftar kode vaksin yang sudah diberikan (opsional)",
                    },
                },
                "required": ["birth_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_url_source",
            "description": (
                "Gunakan tool ini ketika user mengirimkan URL/link artikel. "
                "Tool akan mengekstrak konten dari URL menggunakan Tavily, "
                "mencocokkan dengan sumber RAG (knowledge base pediatrik), "
                "dan memberikan verifikasi apakah isi artikel tersebut valid "
                "dan sesuai dengan referensi terpercaya."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL lengkap artikel yang akan diverifikasi (harus dimulai dengan http:// atau https://)",
                    }
                },
                "required": ["url"],
            },
        },
    },
]

def should_verify_url(message: str) -> bool:
    """Return True when the user message contains at least one URL."""
    return bool(extract_urls(message))


def get_growth_records_for_session(session_id: str) -> list[dict]:
    """Fetch saved growth records from the database for a session."""
    from sqlmodel import Session as DBSession, select
    from app.database import engine
    from app.models import GrowthRecord

    with DBSession(engine) as db:
        stmt = (
            select(GrowthRecord)
            .where(GrowthRecord.session_id == session_id)
            .order_by(GrowthRecord.age_months.asc())  # type: ignore[union-attr]
        )
        records = db.exec(stmt).all()
        return [
            {
                "measurement_date": r.measurement_date.isoformat()
                if r.measurement_date
                else None,
                "age_months": r.age_months,
                "weight_kg": r.weight_kg,
                "height_cm": r.height_cm,
                "head_circumference_cm": r.head_circumference_cm,
                "notes": r.notes,
                "source_filename": r.source_filename,
            }
            for r in records
        ]


def _format_growth_records(records: list[dict]) -> str:
    """Format growth records into a readable string for the LLM."""
    if not records:
        return "Belum ada data tumbuh kembang yang tersimpan."
    lines = [f"Total {len(records)} pengukuran:"]
    for i, r in enumerate(records, 1):
        parts = []
        if r.get("measurement_date"):
            parts.append(f"tanggal={r['measurement_date']}")
        if r.get("age_months") is not None:
            parts.append(f"usia={r['age_months']} bulan")
        if r.get("weight_kg") is not None:
            parts.append(f"BB={r['weight_kg']} kg")
        if r.get("height_cm") is not None:
            parts.append(f"TB={r['height_cm']} cm")
        if r.get("head_circumference_cm") is not None:
            parts.append(f"LK={r['head_circumference_cm']} cm")
        if r.get("notes"):
            parts.append(f"catatan={r['notes']}")
        lines.append(f"  {i}. {', '.join(parts)}")
    return "\n".join(lines)


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
def _format_vaccine_schedule_dict(result: dict) -> str:
    def item_lines(title: str, items: list[dict]) -> list[str]:
        if not items:
            return [f"{title}: tidak ada."]
        lines = [f"{title}:"]
        for item in items:
            label = item.get("label", item.get("vaccine_code", "-"))
            due_age_label = item.get("due_age_label", "-")
            lines.append(f"- {label} ({due_age_label})")
        return lines

    lines = [
        f"Status: {result.get('status')}",
        (
            f"Usia anak: {result.get('age_months')} bulan "
            f"({result.get('age_days')} hari)"
        ),
        *item_lines("Sudah tercatat diberikan", result.get("completed", [])),
        *item_lines("Jatuh tempo sekarang", result.get("due_now", [])),
        *item_lines("Terlambat/overdue", result.get("overdue", [])),
        *item_lines("Akan datang", result.get("upcoming", [])[:6]),
    ]
    warnings = result.get("warnings", [])
    if warnings:
        lines.append("Catatan:")
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)


def _format_red_flag_response(red_flag_result: dict) -> str:
    reasons = red_flag_result.get("reasons") or [
        "Ada tanda bahaya yang perlu dinilai tenaga kesehatan."
    ]
    action = red_flag_result.get(
        "action",
        "Segera bawa anak ke IGD atau fasilitas kesehatan terdekat.",
    )
    reason_lines = "\n".join(f"- {reason}" for reason in reasons)
    return (
        "Parent, dari cerita Anda ada tanda bahaya yang perlu ditangani segera.\n\n"
        f"{reason_lines}\n\n"
        f"**Tindakan:** {action}\n\n"
        "Saya tidak bisa memastikan diagnosis lewat chat, tetapi kondisi seperti ini "
        "lebih aman diperiksa langsung oleh tenaga kesehatan."
    )


def _format_red_flag_unavailable_response(error: Exception) -> str:
    print(f"⚠️ Red flag MCP error: {error}")
    return (
        "Parent, saya belum bisa mengecek tanda bahaya secara otomatis saat ini.\n\n"
        "Kalau anak mengalami gejala berat seperti demam tinggi pada bayi kecil, kejang, "
        "sesak napas, bibir kebiruan, sangat lemas, tidak sadar, tidak mau minum/menyusu, "
        "atau tanda dehidrasi, segera bawa ke IGD atau fasilitas kesehatan terdekat.\n\n"
        "Untuk kondisi yang terasa mengkhawatirkan, lebih aman diperiksa langsung oleh "
        "tenaga kesehatan."
    )


def _format_url_verification_result(result: dict) -> str:
    lines = [
        f"URL: {result.get('url', '')}",
        f"Verdict: {result.get('verdict', result.get('status', 'no_match'))}",
        f"Confidence: {result.get('confidence', 'unknown')}",
        f"Web Summary: {result.get('web_summary', '')}",
    ]
    claim_judgments = result.get("claim_judgments", [])
    if claim_judgments:
        lines.append("Claim Judgments:")
        for index, judgment in enumerate(claim_judgments, 1):
            lines.append(
                "  "
                f"{index}. {judgment.get('verdict', 'not_enough_evidence')} "
                f"({judgment.get('confidence', 'unknown')}): "
                f"{judgment.get('claim', '')}"
            )
            rationale = judgment.get("rationale")
            if rationale:
                lines.append(f"     Rationale: {rationale}")
    excerpts = result.get("matched_rag_excerpts", [])
    if excerpts:
        lines.append("Matched RAG Excerpts:")
        for index, excerpt in enumerate(excerpts, 1):
            lines.append(f"  {index}. {excerpt.get('text', '')[:300]}")
            source = excerpt.get("source", "")
            if source:
                lines.append(f"     Source: {source} (page {excerpt.get('page', '?')})")
    else:
        lines.append("Matched RAG Excerpts: none")
    if result.get("explanation"):
        lines.append(f"Explanation: {result['explanation']}")
    return "\n".join(lines)


# --- MAIN STREAMING FUNCTION ---
@observe()
async def stream_chat_response(
    user_message: str,
    child_context: dict | None = None,
    tool_audit_callback: Callable[[dict], None] | None = None,
    session_id: str | None = None,
    skip_growth_injection: bool = False,
) -> AsyncGenerator[str, None]:
    with propagate_attributes(session_id=session_id):
        async_client = get_async_client()
        today = date.today()
        today_str = today.strftime("%d %B %Y")
        intent = classify_intent(user_message)
        print(
            "🧭 Intent scores: "
            f"medical={intent.medical.score:.1f}, "
            f"vaccine={intent.vaccine.score:.1f}, "
            f"growth={intent.growth.score:.1f}, "
            f"url={intent.has_url}"
        )
        print(
            "🧭 Intent reasons: "
            f"medical={intent.medical.reasons[:4]}, "
            f"vaccine={intent.vaccine.reasons[:4]}, "
            f"growth={intent.growth.reasons[:4]}"
        )

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
            f"👥 SAPAAN: Gunakan sapaan netral seperti 'Parent' atau 'Ayah/Bunda'. "
            f"Jangan memilih hanya 'Bunda' atau hanya 'Ayah' kecuali user menyebut preferensi/identitasnya sendiri. "
            f"Jika ada nama orang tua dari ekstraksi data, sebut namanya tanpa mengasumsikan gender.\n\n"
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
            f"- Gunakan sapaan netral. Contoh: 'Halo Parent!' atau 'Halo Ayah/Bunda!'. "
            f"Jika nama orang tua tersedia, gunakan 'Halo, [Nama]!' tanpa menambahkan Bunda/Ayah kecuali preferensi user jelas.\n"
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
                    parsed_birth = (
                        birth if isinstance(birth, date) else date.fromisoformat(birth)
                    )
                    delta = relativedelta(today, parsed_birth)
                    age_months = delta.years * 12 + delta.months
                except (TypeError, ValueError):
                    age_months = 0
            base_prompt += (
                f"\n📋 DATA ANAK:\n- Nama: {child_context.get('name', '-')}\n "
            )
            base_prompt += f"- Lahir: {birth}\n- Usia: {age_months} bulan\n "
            base_prompt += f"- Gender: {child_context.get('gender', '-')}\n "
            if child_context.get("weight_kg"):
                base_prompt += f"- Berat: {child_context['weight_kg']} kg\n "
            if child_context.get("height_cm"):
                base_prompt += f"- Tinggi: {child_context['height_cm']} cm\n "

        try:
            red_flag = await call_mcp_tool(
                "detect_red_flags",
                {
                    "message": user_message,
                    "child_context": child_context or {},
                },
            )
        except Exception as red_flag_err:
            if tool_audit_callback:
                tool_audit_callback(
                    {
                        "tool_name": "detect_red_flags",
                        "status": "error",
                        "input_payload": {
                            "message": user_message,
                            "child_context": child_context or {},
                        },
                        "output_payload": {"error": _structured_error(red_flag_err)},
                        "sources": [],
                    }
                )
            yield _format_red_flag_unavailable_response(red_flag_err)
            return

        if red_flag.get("is_red_flag"):
            if tool_audit_callback:
                tool_audit_callback(
                    {
                        "tool_name": red_flag.get("tool_name", "detect_red_flags"),
                        "status": red_flag.get("status", "ok"),
                        "input_payload": {
                            "message": user_message,
                            "child_context": child_context or {},
                        },
                        "output_payload": red_flag,
                        "sources": red_flag.get("sources", []),
                    }
                )
            yield _format_red_flag_response(red_flag)
            return

        retrieved_sources: list[dict] = []
        if intent.needs_guidelines:
            try:
                guideline_result = await call_mcp_tool(
                    "search_medical_guidelines",
                    {"query": user_message, "n_results": 3},
                )
                retrieved_context = guideline_result.get("content", "")
                retrieved_sources = guideline_result.get("sources", [])
                print(f"🔍 Pre-retrieved {len(retrieved_sources)} source(s)")
                if tool_audit_callback:
                    tool_audit_callback(
                        {
                            "tool_name": guideline_result.get(
                                "tool_name",
                                "search_medical_guidelines",
                            ),
                            "status": guideline_result.get("status", "ok"),
                            "input_payload": {
                                "query": user_message,
                                "n_results": 3,
                                "phase": "pre_retrieve",
                            },
                            "output_payload": {
                                "status": guideline_result.get("status", "ok"),
                                "content_length": len(retrieved_context),
                                "source_count": len(retrieved_sources),
                            },
                            "sources": retrieved_sources,
                        }
                    )
                base_prompt += (
                    "\n\n📚 KONTEKS DARI KNOWLEDGE BASE:\n"
                    f"{retrieved_context}\n\n"
                    "Gunakan konteks di atas sebagai sumber utama. Jika konteks tidak cukup, "
                    "jelaskan batasannya dan sarankan konsultasi tenaga kesehatan."
                )
            except Exception as retrieve_err:
                print(f"⚠️ Pre-retrieval error: {retrieve_err}")
                if tool_audit_callback:
                    tool_audit_callback(
                        {
                            "tool_name": "search_medical_guidelines",
                            "status": "error",
                            "input_payload": {
                                "query": user_message,
                                "n_results": 3,
                                "phase": "pre_retrieve",
                            },
                            "output_payload": {"error": _structured_error(retrieve_err)},
                            "sources": [],
                        }
                    )

        if intent.needs_vaccine_schedule:
            vaccine_child_context = child_context or {}
            birth_date = vaccine_child_context.get("birth_date")
            if birth_date:
                try:
                    parsed_birth_date = (
                        birth_date
                        if isinstance(birth_date, date)
                        else date.fromisoformat(birth_date)
                    )
                    completed_vaccines = vaccine_child_context.get(
                        "completed_vaccines", []
                    )
                    if not isinstance(completed_vaccines, list):
                        completed_vaccines = []
                    vaccine_input = {
                        "birth_date": parsed_birth_date.isoformat(),
                        "as_of_date": today.isoformat(),
                        "completed_vaccines": completed_vaccines,
                    }
                    vaccine_result = await call_mcp_tool(
                        "calculate_vaccine_schedule",
                        vaccine_input,
                    )
                    if tool_audit_callback:
                        tool_audit_callback(
                            {
                                "tool_name": vaccine_result.get(
                                    "tool_name",
                                    "calculate_vaccine_schedule",
                                ),
                                "status": vaccine_result.get("status", "ok"),
                                "input_payload": vaccine_input,
                                "output_payload": vaccine_result,
                                "sources": vaccine_result.get("sources", []),
                            }
                        )
                    print("💉 Calculated vaccine schedule via MCP")
                    base_prompt += (
                        "\n\n💉 HASIL TOOL calculate_vaccine_schedule:\n"
                        f"{_format_vaccine_schedule_dict(vaccine_result)}\n\n"
                        "Jika user bertanya jadwal vaksin, gunakan hasil tool ini sebagai jawaban utama. "
                        "Jelaskan bahwa jadwal bergantung pada riwayat vaksin yang sudah diterima."
                    )
                    retrieved_sources.extend(vaccine_result.get("sources", []))
                except Exception as vaccine_err:
                    print(f"⚠️ Vaccine schedule error: {vaccine_err}")
                    if tool_audit_callback:
                        tool_audit_callback(
                            {
                                "tool_name": "calculate_vaccine_schedule",
                                "status": "error",
                                "input_payload": {
                                    "birth_date": str(birth_date),
                                    "as_of_date": today.isoformat(),
                                    "completed_vaccines": (
                                        vaccine_child_context.get(
                                            "completed_vaccines",
                                            [],
                                        )
                                    ),
                                },
                                "output_payload": {"error": _structured_error(vaccine_err)},
                                "sources": [],
                            }
                        )
                    base_prompt += (
                        "\n\n💉 CATATAN TOOL VAKSIN:\n"
                        "User bertanya tentang vaksin, tetapi MCP tool server sedang tidak tersedia "
                        "atau gagal mengembalikan hasil. Jelaskan bahwa fitur jadwal vaksin personal "
                        "sedang tidak tersedia sementara, lalu berikan informasi umum berbasis sumber "
                        "yang tersedia tanpa mengarang jadwal personal."
                    )
            else:
                base_prompt += (
                    "\n\n💉 CATATAN TOOL VAKSIN:\n"
                    "User bertanya tentang jadwal vaksin, tetapi tanggal lahir anak belum tersedia. "
                    "Jangan menghitung atau menebak jadwal vaksin personal. Jawab dengan bahasa yang "
                    "ramah dan mudah dipahami: sampaikan bahwa jadwal vaksin bisa dibuat lebih akurat "
                    "kalau tanggal lahir anak sudah diisi. Minta user mengisi atau memperbarui data anak "
                    "terlebih dahulu, terutama tanggal lahir. Jika sesuai, arahkan user untuk memakai "
                    "tombol Edit Data Anak Saya. Tetap jawab kebutuhan user dengan informasi umum dari "
                    "KONTEKS DARI KNOWLEDGE BASE jika tersedia, misalnya gambaran bahwa jadwal imunisasi "
                    "mengikuti usia bayi. Tegaskan bahwa itu informasi umum, bukan jadwal personal. Jadwal "
                    "personal baru bisa dihitung setelah tanggal lahir tersedia."
                )

        # --- GROWTH DATA INJECTION ---
        # Always inject saved growth records when they exist for this session,
        # so the LLM can reference them regardless of what the user asks.
        # Skip only during the upload-pdf flow where the data is already inline.
        if session_id and not skip_growth_injection:
            try:
                growth_records = get_growth_records_for_session(session_id)
                if growth_records:
                    print(
                        f"📊 Injecting {len(growth_records)} growth record(s) into context"
                    )
                    base_prompt += (
                        "\n\n📊 DATA TUMBUH KEMBANG ANAK (dari PDF yang pernah diupload sebelumnya):\n"
                        f"{_format_growth_records(growth_records)}\n\n"
                        "Data di atas adalah riwayat pengukuran tumbuh kembang anak yang sudah "
                        "tersimpan dari dokumen yang pernah diupload. "
                        "SELALU gunakan data ini sebagai referensi utama ketika user bertanya "
                        "tentang kondisi, pertumbuhan, berat badan, tinggi badan, atau "
                        "perkembangan anak mereka. "
                        "Bandingkan dengan standar WHO jika relevan dan berikan insight "
                        "apakah pertumbuhan anak sesuai atau perlu perhatian."
                    )
            except Exception as growth_err:
                print(f"⚠️ Growth data injection error: {growth_err}")

        # --- URL VERIFICATION (pre-retrieval) ---
        if should_verify_url(user_message):
            urls = extract_urls(user_message)
            for target_url in urls[:3]:  # limit to 3 URLs per message
                try:
                    print(f"🔗 Verifying URL: {target_url}")
                    verification = await call_mcp_tool(
                        "verify_url_source",
                        {"url": target_url},
                    )
                    if tool_audit_callback:
                        tool_audit_callback(
                            {
                                "tool_name": "verify_url_source",
                                "status": verification.get("status", "no_match"),
                                "input_payload": {"url": target_url},
                                "output_payload": {
                                    "verdict": verification.get("verdict"),
                                    "web_summary": verification.get("web_summary", "")[
                                        :500
                                    ],
                                    "explanation": verification.get("explanation", ""),
                                    "matched_count": len(
                                        verification.get("matched_rag_excerpts", [])
                                    ),
                                },
                                "sources": verification.get("sources", []),
                            }
                        )
                    base_prompt += (
                        f"\n\n🔗 HASIL VERIFIKASI URL ({target_url}):\n"
                        f"{_format_url_verification_result(verification)}\n\n"
                        "Gunakan hasil verifikasi di atas untuk menjawab user. "
                        "Jelaskan apakah artikel tersebut sesuai, sebagian sesuai, "
                        "atau tidak sesuai dengan referensi terpercaya di knowledge base. "
                        "Jika verdict 'supported', sampaikan bahwa informasi tersebut "
                        "konsisten dengan panduan medis. "
                        "Jika 'partially_supported', sebutkan bagian mana yang sesuai dan mana yang tidak. "
                        "Jika 'not_supported' atau 'no_match', peringatkan user agar hati-hati "
                        "dan sarankan merujuk ke sumber terpercaya atau konsultasi tenaga kesehatan."
                    )
                    retrieved_sources.extend(verification.get("sources", []))
                except Exception as url_err:
                    print(f"⚠️ URL verification error: {url_err}")

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": base_prompt},
            {"role": "user", "content": user_message},
        ]

        # LANGFUSE: Safe Client Selection
        trace = None

        if langfuse_logger.langfuse_client is not None:
            try:
                trace_method = getattr(langfuse_logger.langfuse_client, "trace", None)

                if trace_method is not None:
                    trace = trace_method(
                        name="parentease_chat",
                        session_id=session_id,
                        user_id=child_context.get("name") if child_context else None,
                        metadata={"model": "mistralai/mistral-large"},
                    )
            except Exception as e:
                print(f"⚠️ Langfuse trace creation failed: {e}")
                trace = None

        # LANGFUSE: Safe Client Selection
        # Jika langfuse aktif, gunakan client ter-instrumentasi. Jika tidak, pakai async_client biasa.
        llm_client: AsyncOpenAI = async_client

        if langfuse_logger.langfuse_client is not None:
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
            stream = await llm_client.chat.completions.create(
                model="mistralai/mistral-large",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                stream=True,
            )

            tool_calls_buffer = []
            has_tools = False
            direct_content = ""
            _last_char = ""

            # 1️⃣ Stream awal (bisa trigger tool call)
            async for chunk in stream:
                token = chunk.choices[0].delta.content
                if token:
                    # Auto-space
                    if (
                        _last_char
                        and _last_char.isalnum()
                        and len(token) > 0
                        and token[0].isalnum()
                    ):
                        yield " "
                    yield token
                    _last_char = token[-1]
                    direct_content += token

                if chunk.choices[0].delta.tool_calls:
                    has_tools = True
                    for tc in chunk.choices[0].delta.tool_calls:
                        if (
                            not tool_calls_buffer
                            or tool_calls_buffer[-1].get("index") != tc.index
                        ):
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
                            function["name"] = (
                                f"{function.get('name', '')}{tc.function.name}"
                            )
                        if tc.function and tc.function.arguments:
                            function["arguments"] = (
                                f"{function.get('arguments', '')}{tc.function.arguments}"
                            )

            # 2️⃣ Eksekusi tools
            all_sources = list(retrieved_sources)
            if has_tools and tool_calls_buffer:
                print(f"🔧 Executing {len(tool_calls_buffer)} tool call(s)")
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": tool_calls_buffer,
                    }
                )

                for tc in tool_calls_buffer:
                    try:
                        args = json.loads(tc["function"]["arguments"])
                        tool_name = tc["function"]["name"]
                        print(f"🔍 Tool Requested: {tool_name} with args: {args}")

                        # ✅ MCP INTEGRATION LOGIC
                        if tool_name == "calculate_vaccine_schedule":
                            print("🔌 Routing to MCP Server...")
                            try:
                                mcp_result = await call_mcp_tool(tool_name, args)
                                # Convert MCP result (dict) to JSON string for LLM
                                res = json.dumps(mcp_result, ensure_ascii=False)
                                # Extract sources if available in MCP result
                                srcs = mcp_result.get("sources", [])
                            except Exception as mcp_err:
                                print(f"❌ MCP Execution Error: {mcp_err}")
                                res = json.dumps(
                                    {
                                        "status": "error",
                                        "error": _structured_error(mcp_err),
                                    },
                                    ensure_ascii=False,
                                )
                                srcs = []

                        elif tool_name == "search_medical_guidelines":
                            query = args.get("query", "")
                            print(f"🔌 Routing RAG search to MCP Server: {query}")
                            guideline_result = await call_mcp_tool(
                                "search_medical_guidelines",
                                {"query": query, "n_results": args.get("n_results", 3)},
                            )
                            res = guideline_result.get("content", "")
                            srcs = guideline_result.get("sources", [])
                            print(f"✅ Found {len(srcs)} source(s)")
                        elif tool_name == "verify_url_source":
                            target_url = args.get("url", "")
                            print(f"🔗 LLM requested URL verification: {target_url}")
                            verification = await call_mcp_tool(
                                "verify_url_source",
                                {"url": target_url},
                            )
                            res = _format_url_verification_result(verification)
                            srcs = verification.get("sources", [])
                            print(
                                f"✅ URL verdict: {verification.get('verdict', 'no_match')}"
                            )
                        else:
                            res = f"Tool {tool_name} tidak dikenali."
                            srcs = []

                        all_sources.extend(srcs)
                        messages.append(
                            cast(
                                ChatCompletionMessageParam,
                                {
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "name": tool_name,
                                    "content": res,
                                },
                            )
                        )
                    except Exception as tool_err:
                        print(f"❌ Tool execution error: {tool_err}")
                        import traceback

                        traceback.print_exc()
                        fallback_tool_name = "unknown"
                        if isinstance(tc.get("function"), dict):
                            fallback_tool_name = tc["function"].get("name") or fallback_tool_name
                        messages.append(
                            cast(
                                ChatCompletionMessageParam,
                                {
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "name": fallback_tool_name,
                                    "content": (
                                        "Maaf, tidak dapat mengakses informasi medis saat ini."
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
                            if (
                                _last_char
                                and _last_char.isalnum()
                                and len(token) > 0
                                and token[0].isalnum()
                            ):
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
                print("ℹ️ No LLM-requested tool calls detected - direct response")
                if not direct_content.strip():
                    print("⚠️ Direct stream returned empty content; retrying once.")
                    fallback_response = await async_client.chat.completions.create(
                        model="mistralai/mistral-large",
                        messages=messages,
                        stream=False,
                    )
                    fallback_content = (
                        fallback_response.choices[0].message.content or ""
                    )
                    if fallback_content.strip():
                        yield fallback_content
                    else:
                        yield (
                            "Maaf, saya belum bisa menyusun jawaban untuk pertanyaan "
                            "ini. Coba kirim ulang pertanyaannya dengan sedikit konteks "
                            "tambahan."
                        )
                unique_sources = _unique_sources(retrieved_sources)
                if unique_sources:
                    print(
                        f"📎 Sending {len(unique_sources)} pre-retrieved source(s) to frontend"
                    )
                    yield f"\n\n[SOURCES] {json.dumps(unique_sources)}\n\n"

            # ✅ LANGFUSE: Update trace pada success (Safe check)
            if trace:
                try:
                    trace.update(
                        output={"status": "completed", "tools_executed": has_tools}
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
                    trace.update(output={"error": str(e)}, level="ERROR")
                except Exception as trace_err:
                    print(f"⚠️ Failed to update trace with error: {trace_err}")

            yield f"\n\n❌ Terjadi kesalahan: {str(e)}"
            raise
