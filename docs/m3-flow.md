# M3 Flow: BE Core, Database, Tools, and MCP

Dokumen ini merangkum scope M3 berdasarkan kondisi repo saat ini dan pembagian kerja tim. Tujuannya adalah memberi alur kerja yang bisa mulai dikerjakan tanpa menabrak M1 dan M2.

## Kondisi Repo Saat Ini

Repo saat ini sudah melewati struktur awal sederhana. Backend aktif sekarang memakai FastAPI dengan modul `app/api/v1`, tool deterministic, Alembic, dan PostgreSQL lokal via Docker Compose.

```text
app/
  main.py
  database.py
  models.py
  api/v1/endpoints/
    chat.py
    child_profiles.py
    sessions.py
    tools.py
  services/agent/
    streaming.py
    orchestrator.py
  tools/
    red_flags.py
    schemas.py
    vaccine_schedule.py
alembic/
  versions/
docker-compose.yml
frontend/
tests/
```

Status aktual M3:

```text
PostgreSQL Docker        : tersedia
Alembic                  : tersedia
Redis Docker             : tersedia
Celery app skeleton      : tersedia
Vaccine schedule tool    : tersedia dan tested
Vaccine endpoint         : tersedia
Vaccine history endpoint : tersedia
Chat auto vaccine tool   : tersedia
Basic red flag handler   : tersedia
RAG Chroma static PDFs   : tersedia lokal setelah ingest
Tool call audit table    : tersedia untuk tracking pemanggilan tool
MCP server               : belum dibuat
Redis/Celery active flow : skeleton tersedia, belum dipakai upload/chat
Growth/z-score valid WHO : belum dibuat
PDF upload               : belum dibuat
```

Implikasinya: pekerjaan M3 berikutnya sebaiknya fokus ke hardening, auditability, dan foundation yang tidak menabrak M1/M2. Refactor besar ke struktur `src/` tidak direkomendasikan untuk MVP karena repo aktif sudah berjalan dengan struktur `app/`.

## Scope M3

M3 bertanggung jawab untuk:

- PostgreSQL + Alembic schema design.
- Redis + Celery setup untuk background jobs.
- Tool medis `calculate_vaccine_schedule()`.
- API routing dan validation layer.
- MCP server / tool exposure agar agent milik M1 bisa consume.
- Shared model contracts yang dipakai M1/M2.

## Mapping Dari Pembagian Tim

Bagian ini menyatukan tiga sumber pembagian kerja: struktur folder target, tabel ownership anggota, dan tabel teknologi/collaboration point.

### Ownership Anggota

```text
M1 - AI Agent & Session
  Fokus folder target:
    services/agent/
    api/v1/endpoints/chat.py
    api/v1/endpoints/sessions.py
    utils/langfuse_logger.py
  Tugas:
    Agent streaming via SSE/WebSocket
    MCP client ke agent loop
    Session dan welcome context
    Langfuse tracing/prompt versioning/eval dashboard
    Redis-backed session cache untuk short-term memory

M2 - RAG & User Data
  Fokus folder target:
    services/rag/
    services/uploads/
    models/document.py
    models/history.py
  Tugas:
    User upload parsing PDF/TXT/IMG
    Chunking, cleaning, embedding, vector search
    History user data dan long-term memory
    Context builder untuk welcome data + history + retrieved chunks
    Trigger async upload processing via Celery infra dari M3

M3 - BE Core, Database & Tools
  Fokus folder target:
    core/
    services/tools/
    api/v1/endpoints/tools.py
    models/
    alembic/
  Tugas:
    PostgreSQL + Alembic schema, migration, constraint, index
    Redis + Celery broker, queue, retry, result backend
    calculate_vaccine_schedule() logic, validasi input, expose via MCP server
    API routing, middleware, validation, rate limit, error format
    MCP server endpoint/tool exposure agar M1 bisa consume
```

### Teknologi dan Collaboration Point

| Teknologi | Primary Owner | Cross-Usage / Collaboration Point |
| --- | --- | --- |
| Redis + Celery | M3 | M2 memakai untuk async upload processing. M1 bisa memakai untuk fallback async tool execution/session cache. |
| MCP | M1 client + M3 server | M3 expose tools seperti `vaccine_schedule`. M1 integrasikan MCP client ke agent loop. |
| User's Upload | M2 | Celery task dari M3 handle heavy parsing. Vector store dipakai M2 untuk chunking/retrieval. |
| `calculate_vaccine_schedule()` | M3 | M3 handle logic dan validasi. M1 bind sebagai tool agent, idealnya via MCP. |
| History User Data | M2 | Disimpan di PostgreSQL schema dari M3 dan/atau vector index. M2 build retrieval logic. |
| Session | M1 | Redis cache + DB persistence. Context welcome masuk ke session state lalu agent system prompt. |
| Agent Streaming | M1 | FastAPI `StreamingResponse`/WebSocket, yield token dari LLM call dan tool calls. |
| Welcome Page Context | M1 state + M2 storage | M1 parse dan inject ke prompt awal. M2 simpan sebagai history/context untuk recall jangka panjang. |
| Alembic | M3 | Manage semua DB schema changes. M2 submit migration PR untuk vector/history tables jika menyentuh schema. |
| Langfuse | M1 | Semua anggota idealnya wrap LLM/tool call dengan tracing yang disiapkan M1. |
| PostgreSQL | M3 core + M2 pgvector | M3 handle relational schema. M2 install/konfigurasi `pgvector` dan buat index retrieval jika pindah dari Chroma. |

### Mapping Struktur Target ke Repo Saat Ini

Repo target di dokumen awal memakai `src/`, tetapi repo aktif saat ini masih memakai `app/`. Untuk MVP, mapping-nya:

```text
src/api/v1/endpoints/chat.py      -> app/api/v1/endpoints/chat.py
src/api/v1/endpoints/tools.py     -> app/api/v1/endpoints/tools.py
src/api/v1/endpoints/sessions.py  -> app/api/v1/endpoints/sessions.py
src/core/database.py              -> app/database.py
src/core/celery_app.py            -> app/core/celery_app.py
src/models/*                      -> app/models.py
src/services/agent/*              -> app/services/agent/*
src/services/rag/*                -> sebagian masih di scripts/ingest_pdfs.py dan app/services/agent/streaming.py
src/services/tools/*              -> app/tools/*
src/services/uploads/*            -> belum ada
src/utils/validators.py           -> belum ada
main.py                           -> app/main.py
```

Keputusan MVP: jangan refactor besar dari `app/` ke `src/` sebelum disepakati tim, karena akan menyentuh ownership M1/M2 dan berisiko konflik merge.

## Boundary Agar Tidak Konflik

Ownership utama M3:

```text
src/core/
src/models/
src/services/tools/
src/api/v1/endpoints/tools.py
src/utils/validators.py
alembic/
docker/
tests/tools/
tests/core/
```

Hindari edit langsung area ini tanpa koordinasi:

```text
src/services/agent/        # M1
src/api/v1/endpoints/chat.py
src/api/v1/endpoints/sessions.py
src/services/rag/          # M2
src/services/uploads/      # M2
app/static/index.html      # frontend/session UX
```

Kalau repo belum dipindah ke `src/`, M3 sebaiknya tetap menulis dokumen kontrak dan modul baru yang isolated. Jangan mengubah `app/agent.py` atau `app/main.py` kecuali sudah ada agreement dari M1.

## Flow Kerja M3

### 1. Sepakati Kontrak Internal

M3 perlu menetapkan kontrak data supaya M1 dan M2 bisa coding paralel.

Kontrak minimal untuk child context:

```json
{
  "session_id": "string",
  "child": {
    "name": "string | null",
    "birth_date": "YYYY-MM-DD | null",
    "age_months": 6,
    "gender": "male | female | unknown",
    "weight_kg": 7.2,
    "height_cm": 65.0
  }
}
```

Kontrak tool result:

```json
{
  "tool_name": "calculate_vaccine_schedule",
  "status": "ok | needs_more_input | error",
  "data": {},
  "warnings": [],
  "sources": []
}
```

Kontrak error:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "birth_date is required",
    "details": {}
  }
}
```

### 2. Database Foundation

Target schema awal:

```text
users
sessions
child_profiles
chat_messages
documents
vaccine_records
tool_calls
```

Untuk MVP tanpa auth, `users` boleh nullable atau diganti anonymous user. Yang penting semua data punya `session_id`.

Relasi minimum:

```text
sessions.id
  -> child_profiles.session_id
  -> chat_messages.session_id
  -> vaccine_records.session_id
  -> tool_calls.session_id
```

Index minimum:

```text
sessions.created_at
chat_messages.session_id + created_at
child_profiles.session_id
vaccine_records.session_id
tool_calls.session_id + created_at
```

Keputusan yang perlu dikunci sebelum migration:

- Pakai PostgreSQL langsung atau tetap SQLite sementara.
- Pakai SQLModel seperti repo saat ini atau pindah SQLAlchemy declarative.
- Apakah migration Alembic dibuat dari awal atau setelah struktur `src/` siap.

Rekomendasi: kalau teman lain masih mengubah foundation, M3 jangan migration besar dulu. Buat draft model dan migration plan dulu, lalu implement setelah struktur final disepakati.

### 3. Vaccine Schedule Tool

Tool ini bisa dikerjakan sekarang karena bisa dibuat sebagai pure function tanpa dependency ke agent/RAG.

Sumber data awal yang sudah tersedia:

```text
data/buku_kia_2024.pdf
```

PDF Buku KIA 2024 bisa diekstrak teksnya dan memuat bagian imunisasi dasar bayi/baduta. Untuk RAG, file ini bisa langsung ikut pipeline `scripts/ingest_pdfs.py`. Untuk tool `calculate_vaccine_schedule()`, jadwal dari Buku KIA sebaiknya diturunkan menjadi data terstruktur manual/JSON terlebih dahulu, bukan diparse dari PDF setiap request.

Input minimal:

```json
{
  "birth_date": "2025-11-08",
  "as_of_date": "2026-05-08",
  "country": "ID",
  "completed_vaccines": [
    {
      "vaccine_code": "BCG",
      "date_given": "2025-12-01"
    }
  ]
}
```

Output minimal:

```json
{
  "age_months": 6,
  "due_now": [],
  "upcoming": [],
  "overdue": [],
  "completed": [],
  "notes": [],
  "sources": []
}
```

Flow:

```text
validate input
  -> calculate child age at as_of_date
  -> load schedule table for country
  -> compare age window vs completed records
  -> group result: due_now / upcoming / overdue / completed
  -> attach caveats and source metadata
  -> return structured result
```

Rules MVP:

- Jangan memberi diagnosis.
- Jangan mengklaim anak pasti sudah/kurang vaksin kalau riwayat vaksin tidak lengkap.
- Jika `birth_date` tidak ada, return `needs_more_input`.
- Jika anak punya kondisi khusus, arahkan konsultasi dokter.
- Jadwal harus punya sumber eksplisit dan tanggal versi.

### 4. API Tools Endpoint

Endpoint yang aman dibuat sebagai kontrak:

```http
POST /api/v1/tools/vaccine-schedule
```

Request:

```json
{
  "session_id": "string | null",
  "birth_date": "YYYY-MM-DD",
  "as_of_date": "YYYY-MM-DD",
  "gender": "male | female | unknown",
  "completed_vaccines": []
}
```

Response:

```json
{
  "result": {
    "age_months": 6,
    "due_now": [],
    "upcoming": [],
    "overdue": [],
    "completed": []
  },
  "sources": [],
  "warnings": []
}
```

M1 bisa memanggil endpoint ini dari agent loop. Frontend tidak wajib memanggil langsung untuk MVP.

### 5. MCP Server Flow

MCP exposure bisa dipisahkan dari FastAPI endpoint agar tidak memblokir MVP.

Tool yang diekspos:

```text
calculate_vaccine_schedule
```

MCP input schema sama dengan API tools endpoint. M1 hanya perlu tahu nama tool, input schema, dan response schema.

Flow:

```text
M1 agent detects vaccine intent
  -> M1 calls MCP tool calculate_vaccine_schedule
  -> M3 tool validates input
  -> if missing input, return needs_more_input
  -> if valid, return vaccine schedule result
  -> M1 turns structured result into user-facing answer
```

Fallback kalau MCP belum siap:

```text
M1 calls internal Python function or HTTP endpoint
```

Jadi implementasi tool jangan terlalu tergantung pada MCP. Core logic harus berada di service pure function.

### 6. Redis + Celery Flow

Untuk MVP aktif, Redis + Celery belum wajib di chat/upload flow. Skeleton M3 sekarang sudah tersedia agar M2 bisa menyambungkan async upload processing tanpa mengubah foundation lagi.

Implementasi saat ini:

```text
docker-compose.yml       -> service redis
app/core/celery_app.py   -> Celery instance + health task
Makefile                 -> redis, services, worker, celery-health
.env.example             -> REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND
```

Command:

```bash
make redis
make worker
make celery-health
```

Flow upload async nantinya:

```text
M2 receives upload
  -> create document row status=queued
  -> enqueue Celery task
  -> worker processes file
  -> update document status=processing / completed / failed
  -> M2 writes vectors
```

M3 tidak perlu mengerjakan parsing, chunking, embedding, atau vector write. Itu M2.

### 7. Validation and Middleware

M3 bisa menyiapkan shared validation:

- Date format validation.
- Age range validation.
- Gender enum normalization.
- Weight/height positive number validation.
- Standard API error format.
- Basic rate-limit design.
- Request ID middleware.

Untuk menghindari konflik, middleware app bootstrap sebaiknya menunggu struktur `main.py` final. Yang bisa dikerjakan sekarang adalah utility dan test untuk validator.

## Apa Yang Bisa Dikerjakan Sekarang

Bisa dikerjakan sekarang tanpa menunggu M1/M2:

- Dokumen kontrak API/tool.
- Pure function `calculate_vaccine_schedule()` beserta test table-driven.
- Draft Pydantic schemas untuk tool request/response.
- Draft DB schema dan migration plan.
- Redis/Celery docker design, tanpa integrasi upload.
- Error response standard.
- Validator util.

Sebaiknya menunggu foundation:

- Refactor repo dari `app/` ke `src/`.
- Alembic migration final.
- App bootstrap/middleware final.
- Integrasi MCP ke agent loop.
- Celery task upload/ingestion end-to-end.
- Perubahan langsung ke chat/session endpoint.

## Risiko Utama

- Struktur repo target belum ada, sehingga file ownership di gambar belum bisa diterapkan apa adanya.
- Model database lama masih sangat tipis dan belum punya `session_id`.
- Belum ada PostgreSQL config.
- Belum ada Alembic.
- Belum ada source resmi jadwal vaksin di repo.
- MCP belum jelas akan memakai transport apa: stdio, SSE, atau HTTP JSON-RPC.
- Kalau M3 langsung refactor `main.py` dan `models.py`, besar kemungkinan konflik dengan M1/M2.

## Rencana Eksekusi Aman

### Hari 1

- Finalisasi dokumen kontrak M3.
- Sepakati dengan M1/M2:
  - struktur folder final,
  - schema session/profile,
  - response format tool,
  - transport MCP sementara.
- Buat pure function vaccine schedule di folder isolated.

### Hari 2

- Tambah unit test vaccine schedule.
- Tambah Pydantic schemas.
- Draft DB model dan Alembic migration plan.
- Siapkan docker compose PostgreSQL/Redis jika disetujui.

### Hari 3

- Integrasi endpoint `/api/v1/tools/vaccine-schedule`.
- Expose MCP wrapper jika agent contract M1 sudah siap.
- Integrasi Celery healthcheck jika M2 butuh upload async.

## Definition of Done M3 MVP

- `calculate_vaccine_schedule()` punya input/output structured dan test.
- Tool mengembalikan `needs_more_input` saat data anak kurang.
- Jadwal vaksin punya source metadata.
- Endpoint tool tersedia atau minimal service function siap dipanggil M1.
- DB schema untuk session, child profile, vaccine record, dan tool call sudah disepakati.
- Tidak ada perubahan yang memblokir M1 streaming/session atau M2 RAG/upload.

## Kesimpulan

M3 bisa mulai sekarang, tapi jangan mulai dari refactor foundation besar. Jalur paling aman adalah membuat kontrak, schema draft, validator, dan vaccine tool sebagai pure service. Integrasi penuh ke FastAPI, Alembic, Celery, dan MCP sebaiknya dilakukan setelah struktur `src/` dan kontrak M1/M2 sudah dikunci.

## Ringkasan Perubahan Yang Sudah Dilakukan

Bagian ini mencatat perubahan yang sudah diterapkan agar status M3 mudah dibaca oleh anggota tim lain.

### Data dan RAG

- Menambahkan Buku KIA 2024 ke folder data:

```text
data/buku_kia_2024.pdf
```

- PDF Buku KIA sudah dicek bisa diekstrak teksnya, sehingga bisa dipakai untuk RAG tanpa OCR.
- Ingest Chroma sudah pernah dijalankan lokal dengan command:

```bash
uv run -m scripts.ingest_pdfs
```

- Hasil ingest lokal:

```text
asi_guidelines.pdf  -> 50 chunks
buku_kia_2024.pdf   -> 384 chunks
total               -> 434 chunks
collection          -> pediatric_guidelines
```

- `chroma_db/` tetap di-ignore oleh git, jadi setiap developer perlu menjalankan ingest sendiri jika ingin punya index lokal.

### Environment

- Menambahkan template environment:

```text
.env.example
```

- Isi variable yang disiapkan:

```env
OPEN_ROUTER_API_KEY=your_openrouter_api_key_here
MISTRAL_API_KEY=your_mistral_api_key_here
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/parentease
```

- Catatan: kode saat ini masih memakai `OPEN_ROUTER_API_KEY` untuk embedding dan chat model melalui OpenRouter. `MISTRAL_API_KEY` sudah disiapkan, tetapi belum dipakai oleh kode existing.
- `DATABASE_URL` default project sekarang mengarah ke PostgreSQL lokal via Docker Compose.

### Vaccine Schedule Tool

- Menambahkan folder tool M3 yang isolated:

```text
app/tools/
  __init__.py
  schemas.py
  vaccine_schedule.py
```

- Menambahkan schema Pydantic untuk request/response:

```text
VaccineScheduleRequest
VaccineScheduleResponse
CompletedVaccine
VaccineScheduleItem
VaccineScheduleSource
```

- Menambahkan pure function:

```python
calculate_vaccine_schedule(request)
```

- Function ini melakukan:

```text
validate input
calculate age_days and age_months
match against VACCINE_SCHEDULE_ID
group result into due_now / upcoming / overdue / completed
return warnings and source metadata
```

- Jadwal vaksin awal diturunkan dari Buku KIA 2024 bagian "Imunisasi Dasar Bayi dan Baduta" / "Pelayanan Imunisasi" halaman cetak 124-125.
- Jadwal yang dikunci dalam `VACCINE_SCHEDULE_ID`:

```text
0-24 jam : HB0
1 bulan  : BCG, OPV1
2 bulan  : DPT-HB-Hib 1, OPV2, RV1, PCV1
3 bulan  : DPT-HB-Hib 2, OPV3, RV2, PCV2
4 bulan  : DPT-HB-Hib 3, OPV4, IPV1, RV3
9 bulan  : MR1, IPV2
10 bulan : JE, optional regional
12 bulan : PCV3
18 bulan : DPT-HB-Hib lanjutan, MR lanjutan
```

- Vaksin regional `JE` dibuat opt-in melalui:

```json
{
  "include_regional_vaccines": true
}
```

### API Endpoint

- Menambahkan endpoint FastAPI untuk vaccine tool, mengikuti routing baru backend:

```http
POST /api/v1/tools/vaccine-schedule
```

- Contoh request:

```json
{
  "birth_date": "2026-03-08",
  "as_of_date": "2026-05-08",
  "completed_vaccines": []
}
```

- Contoh expected `due_now` untuk anak usia 2 bulan:

```text
DPT-HB-HIB1
OPV2
RV1
PCV1
```

- Endpoint ini tetap bisa dipanggil langsung untuk test/debug. Selain itu, chat agent sekarang sudah bisa memakai hasil tool secara otomatis ketika intent vaksin terdeteksi dan profil anak punya `birth_date`.

### Tests

- Menambahkan test untuk service vaccine schedule:

```text
tests/test_vaccine_schedule.py
```

- Menambahkan test untuk endpoint:

```text
tests/test_tools_endpoint.py
```

- Test yang sudah diverifikasi:

```bash
.venv/bin/python -m unittest tests/test_vaccine_schedule.py tests/test_tools_endpoint.py tests/test_red_flags.py
```

- Hasil terakhir:

```text
Ran 14 tests
OK
```

### Cleanup Repo

- Membersihkan `__pycache__` dari tracking git.
- Menambahkan ignore rule:

```gitignore
__pycache__/
*.py[cod]
```

### Status Saat Ini

```text
RAG PDF umum            : siap secara lokal setelah ingest
Chroma collection       : pediatric_guidelines, 434 chunks lokal
Document metadata       : tersedia via tabel document setelah ingest
Vaccine schedule tool   : siap dan tested
Vaccine endpoint        : siap dan tested
Agent chat              : pre-retrieve RAG, auto vaccine schedule, red flag handler
calculate_z_score       : masih placeholder
Session/history         : tersedia dari merge M1, dipakai untuk profil/chat
Vaccine history         : tersedia via endpoint profile vaccines
Tool call audit         : tersedia via tabel toolcall
MCP server              : belum dibuat
Redis/Celery            : skeleton tersedia, belum dipakai flow aktif
Alembic migration       : initial schema tersedia
PostgreSQL              : tersedia via Docker Compose
```

## M3 MVP Specs Lengkap

Bagian ini adalah spec operasional terbaru setelah merge frontend/backend dan implementasi M3 yang sudah masuk di working tree. Pakai bagian ini sebagai acuan demo dan handoff ke M1/M2.

### Tujuan MVP M3

M3 menyediakan fondasi backend yang membuat chat parenting bisa memakai data terstruktur dan knowledge base lokal:

```text
child profile
  -> chat context
  -> red flag guardrail
  -> Chroma guideline retrieval
  -> deterministic vaccine schedule
  -> response streaming + sources
```

Scope MVP M3 yang sudah dikerjakan:

- Tool deterministic `calculate_vaccine_schedule()`.
- Endpoint tool `/api/v1/tools/vaccine-schedule`.
- Endpoint riwayat vaksin per profile.
- Integrasi chat agar pertanyaan vaksin otomatis memakai tool.
- Pre-retrieve Chroma untuk pertanyaan ASI/MPASI/vaksin/tumbuh kembang.
- Basic medical red flag handler.
- Date/number normalization untuk form frontend lokal Indonesia.

Scope yang sengaja belum menjadi MVP:

- Redis/Celery worker untuk flow upload/chat aktif.
- MCP server transport.
- Growth chart/z-score valid WHO.
- Intent classifier berbasis model khusus.

### Runtime Lokal

Urutan jalan lokal:

```bash
uv sync
cp .env.example .env
docker compose up -d postgres
docker compose up -d redis
uv run alembic upgrade head
uv run -m scripts.ingest_pdfs
make dev
```

Frontend React dijalankan dari folder frontend:

```bash
cd frontend
npm install
npm run dev
```

Environment yang dibutuhkan:

```env
OPEN_ROUTER_API_KEY=...
MISTRAL_API_KEY=...
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/parentease
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

Catatan saat ini:

- `OPEN_ROUTER_API_KEY` dipakai untuk chat model dan embedding melalui OpenRouter.
- `MISTRAL_API_KEY` sudah disiapkan, tetapi belum dipakai oleh kode saat ini.
- `DATABASE_URL` dibaca oleh app dan Alembic. Untuk local MVP default-nya PostgreSQL Docker.
- `REDIS_URL` disiapkan untuk Redis session/cache usage.
- `CELERY_BROKER_URL` dan `CELERY_RESULT_BACKEND` dipakai oleh `app/core/celery_app.py`.
- `chroma_db/` tidak di-commit, jadi setiap developer perlu ingest PDF sendiri.
- `parentease.db` adalah sisa SQLite lokal lama dan tidak dipakai jika `DATABASE_URL` mengarah ke PostgreSQL.

### Alembic Migration

Alembic sudah tersedia untuk mengelola schema database.

File yang ditambahkan:

```text
alembic.ini
alembic/env.py
alembic/script.py.mako
alembic/versions/20260512_0001_initial_schema.py
alembic/versions/20260513_0002_add_tool_call_audit.py
alembic/versions/20260513_0003_add_document_metadata.py
```

Dependency:

```text
alembic>=1.18.4
```

Command migration:

```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run alembic current
```

`Makefile` sekarang menjalankan migration sebelum dev server:

```bash
make dev
```

Flow `make dev`:

```text
uv run alembic upgrade head
  -> uv run uvicorn app.main:app --reload
```

Initial migration dibuat defensif. Kalau developer sudah punya `parentease.db` dari `create_all`, migration tidak gagal karena tabel sudah ada; Alembic tetap mencatat revision `20260512_0001`.

Migration kedua menambahkan tabel audit:

```text
toolcall
```

Tabel ini dipakai untuk proof/debugging pemanggilan tool dari chat, terutama `calculate_vaccine_schedule`.

Migration ketiga menambahkan tabel metadata dokumen:

```text
document
```

Tabel ini dipakai untuk proof/debugging ingest PDF lokal. `scripts.ingest_pdfs` akan menulis status `processing`, `completed`, `skipped`, atau `failed`.

PostgreSQL local disediakan lewat:

```text
docker-compose.yml
service: postgres
image  : postgres:16-alpine
db     : parentease
user   : postgres
pass   : postgres
port   : 5432
```

### Data Sources

Knowledge base lokal:

```text
data/asi_guidelines.pdf
data/buku_kia_2024.pdf
```

Chroma collection:

```text
path       : ./chroma_db
collection : pediatric_guidelines
total      : 434 chunks lokal
```

PostgreSQL document metadata:

```text
table      : document
writer     : scripts.ingest_pdfs
status     : processing | completed | skipped | failed
purpose    : proof file PDF mana yang sudah masuk Chroma lokal
```

RAG source rule:

- PDF dipakai untuk jawaban edukasi umum seperti ASI, MPASI, posisi menyusui, dan guideline KIA.
- Vaccine schedule tidak dihitung dari Chroma setiap request. Jadwal vaksin dibuat deterministic dari tabel terstruktur di `app/tools/vaccine_schedule.py`.
- Response frontend menerima marker `[SOURCES]` untuk menampilkan dokumen sumber.

### Database Model MVP

Model yang relevan sekarang ada di `app/models.py`.

```text
ChildProfile
  id
  session_id
  birth_date
  gender
  name
  weight_kg
  height_cm
  topic
  created_at

ChatMessage
  id
  session_id
  role
  content
  created_at

VaccineRecord
  id
  session_id
  vaccine_code
  date_given
  notes
  created_at

ToolCall
  id
  session_id
  tool_name
  status
  input_payload
  output_payload
  sources
  created_at

Document
  id
  filename
  source_type
  status
  collection_name
  chunk_count
  error_message
  ingested_at
  created_at
  updated_at
```

Relasi MVP masih berbasis `session_id`, bukan foreign key database ketat. Ini cukup untuk local MVP, tetapi untuk production perlu migration dan constraint.

`ToolCall` dipakai sebagai audit trail untuk membuktikan tool deterministic benar-benar terpanggil dari chat. Saat user bertanya jadwal vaksin dan profil anak punya `birth_date`, `stream_chat_response()` menjalankan `calculate_vaccine_schedule()` lalu endpoint chat menyimpan audit row berisi input, output, status, dan source tool.

Cara cek di TablePlus:

```sql
select
  id,
  session_id,
  tool_name,
  status,
  input_payload,
  sources,
  created_at
from toolcall
order by created_at desc
limit 20;
```

`Document` dipakai untuk tracking metadata PDF yang di-ingest ke Chroma. Vector tetap disimpan di `chroma_db/`, sedangkan PostgreSQL menyimpan bukti operasional file mana yang sudah masuk, jumlah chunk, status ingest, dan collection target.

Cara cek dokumen RAG di TablePlus:

```sql
select
  id,
  filename,
  status,
  collection_name,
  chunk_count,
  ingested_at,
  updated_at
from document
order by updated_at desc;
```

### Child Profile Contract

Create profile:

```http
POST /api/v1/profiles/
```

Request:

```json
{
  "tanggal_lahir": "2026-03-08",
  "gender": "P",
  "nama_anak": "Gee",
  "berat_badan_kg": 5.8,
  "tinggi_badan_cm": 59
}
```

Update profile:

```http
PATCH /api/v1/profiles/{session_id}
```

Tanggal diterima dalam dua format:

```text
YYYY-MM-DD
DD/MM/YYYY
```

Frontend juga menormalisasi:

```text
08/03/2026 -> 2026-03-08
5,8        -> 5.8
```

Get profile:

```http
GET /api/v1/profiles/{session_id}
```

### Vaccine History Contract

List riwayat vaksin:

```http
GET /api/v1/profiles/{session_id}/vaccines
```

Tambah riwayat vaksin:

```http
POST /api/v1/profiles/{session_id}/vaccines
```

Request:

```json
{
  "vaccine_code": "BCG",
  "date_given": "2026-04-08",
  "notes": "Diberikan di puskesmas"
}
```

Delete riwayat vaksin:

```http
DELETE /api/v1/profiles/{session_id}/vaccines/{record_id}
```

Riwayat ini dipakai otomatis oleh chat. Saat user bertanya jadwal vaksin, `chat.py` mengambil `VaccineRecord` dan mengirimnya sebagai `completed_vaccines` ke streaming agent.

### Vaccine Schedule Tool Spec

Endpoint:

```http
POST /api/v1/tools/vaccine-schedule
```

Request schema:

```json
{
  "session_id": "optional-session-id-for-audit",
  "birth_date": "2026-03-08",
  "as_of_date": "2026-05-12",
  "country": "ID",
  "completed_vaccines": [
    {
      "vaccine_code": "BCG",
      "date_given": "2026-04-08"
    }
  ],
  "include_regional_vaccines": false
}
```

Response schema:

```json
{
  "tool_name": "calculate_vaccine_schedule",
  "status": "ok",
  "age_days": 65,
  "age_months": 2,
  "due_now": [],
  "upcoming": [],
  "overdue": [],
  "completed": [],
  "warnings": [],
  "sources": [
    {
      "title": "Buku Kesehatan Ibu dan Anak 2024",
      "page": 124,
      "year": 2024
    }
  ]
}
```

Status:

```text
ok               -> birth_date valid dan hasil dihitung
needs_more_input -> birth_date kosong
error            -> reserved untuk error terstruktur
```

Jadwal ID yang dimodelkan:

```text
0-24 jam : HB0
1 bulan  : BCG, OPV1
2 bulan  : DPT-HB-Hib 1, OPV2, RV1, PCV1
3 bulan  : DPT-HB-Hib 2, OPV3, RV2, PCV2
4 bulan  : DPT-HB-Hib 3, OPV4, IPV1, RV3
9 bulan  : MR1, IPV2
10 bulan : JE, optional regional
12 bulan : PCV3
18 bulan : DPT-HB-Hib lanjutan, MR lanjutan
```

Business rules:

- Jika `completed_vaccines` berisi kode vaksin, item tersebut masuk `completed` dan tidak muncul di `due_now`.
- `JE` hanya muncul kalau `include_regional_vaccines=true`.
- Jika request membawa `session_id`, endpoint menyimpan audit row ke tabel `toolcall`.
- Tool memberi warning untuk batas usia rotavirus dan catatan konsultasi tenaga kesehatan.
- Tool tidak membuat diagnosis dan tidak menggantikan keputusan dokter.

### Chat Agent Integration Spec

Endpoint chat:

```http
POST /api/v1/chat/
Header: X-Session-ID: {session_id}
```

Request:

```json
{
  "message": "Jadwal vaksinasi bayi saya apa?"
}
```

Flow backend:

```text
receive message
  -> save user ChatMessage
  -> fetch ChildProfile by X-Session-ID
  -> fetch VaccineRecord by session_id
  -> build child_context
  -> stream_chat_response()
```

Flow di `stream_chat_response()`:

```text
build base prompt
  -> inject child profile if available
  -> detect red flag
  -> if red flag: return urgent safety response
  -> if medical keyword: pre-retrieve Chroma
  -> if vaccine keyword + birth_date: calculate vaccine schedule
  -> call LLM streaming
  -> if LLM function-call search_medical_guidelines: execute it
  -> append [SOURCES]
  -> save assistant ChatMessage
```

Log yang diharapkan:

```text
ChromaDB has 434 documents
Pre-retrieved 3 source(s)
Calculated vaccine schedule from child profile
No tool calls detected - direct response
Sending ... pre-retrieved source(s) to frontend
```

Catatan: `No tool calls detected` hanya berarti LLM tidak memanggil function tool tambahan. Chroma tetap bisa sudah dipakai lewat pre-retrieve.

### Red Flag Guardrail Spec

File:

```text
app/tools/red_flags.py
```

Deteksi tanda bahaya MVP:

```text
kejang
sesak / sulit napas / napas cepat
bibir biru / kebiruan
tidak mau minum / tidak mau menyusu
dehidrasi
lemas sekali
tidak sadar
muntah terus
demam pada bayi di bawah 3 bulan
suhu >= 40 C
```

Jika red flag terdeteksi, chat langsung mengembalikan safety response dan tidak lanjut ke RAG/LLM biasa.

### Frontend Contract

Frontend tidak perlu memanggil vaccine tool langsung untuk flow chat. Yang wajib:

- Simpan `session_id` setelah welcome form.
- Kirim `X-Session-ID` setiap chat.
- Kirim tanggal lahir dalam `YYYY-MM-DD` jika memungkinkan.
- Tampilkan `[SOURCES]` sebagai daftar sumber di bawah jawaban.

Endpoint tool tetap tersedia untuk debug/admin/test manual.

### Test Plan

Backend tests:

```bash
.venv/bin/python -m unittest tests/test_vaccine_schedule.py tests/test_tools_endpoint.py tests/test_red_flags.py
```

Type check spot check:

```bash
uvx ty check app/services/agent/streaming.py app/api/v1/endpoints/child_profiles.py
```

Frontend build:

```bash
cd frontend
npm run build
```

Manual test cases:

```text
ASI eksklusif sampai kapan?
  -> source dari asi_guidelines / Buku KIA muncul

Kapan mulai MPASI?
  -> RAG Chroma terpanggil dan source muncul

Jadwal vaksinasi bayi
  -> jika X-Session-ID punya profile birth_date, vaccine schedule dihitung

Bayi saya demam 39 dan usianya 2 bulan
  -> red flag response, arahkan ke fasilitas kesehatan

Tambah BCG ke /profiles/{session_id}/vaccines
  -> BCG tidak lagi muncul sebagai due_now
```

### Batasan dan Next Step M3

Yang masih perlu diselesaikan setelah MVP:

- Production/staging PostgreSQL credential management.
- MCP server wrapper untuk `calculate_vaccine_schedule`.
- Redis/Celery kalau ingestion/upload dibuat async.
- Z-score/growth chart berbasis WHO, bukan placeholder.
- Intent classifier yang lebih robust daripada keyword.
- Pemisahan source type:
  - guideline edukasi dari RAG,
  - source rule jadwal vaksin,
  - source dari tool calculation.
- Chat history beberapa pesan terakhir perlu dimasukkan ke prompt untuk follow-up yang lebih kuat.
