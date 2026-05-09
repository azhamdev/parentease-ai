# M3 Flow: BE Core, Database, Tools, and MCP

Dokumen ini merangkum scope M3 berdasarkan kondisi repo saat ini dan pembagian kerja tim. Tujuannya adalah memberi alur kerja yang bisa mulai dikerjakan tanpa menabrak M1 dan M2.

## Kondisi Repo Saat Ini

Repo saat ini masih memakai struktur sederhana:

```text
app/
  main.py
  agent.py
  models.py
  static/index.html
scripts/
  ingest_pdfs.py
data/
  asi_guidelines.pdf
```

Struktur target dari pembagian tim belum ada:

```text
src/
  api/v1/endpoints/
  core/
  models/
  services/
  utils/
alembic/
docker/
tests/
```

Implikasinya: M3 bisa mulai dari desain kontrak, schema, tool logic murni, dan scaffolding yang terisolasi. Hindari refactor besar ke `src/` sebelum disepakati, karena M1/M2 kemungkinan juga akan menyentuh routing, agent, dan RAG.

## Scope M3

M3 bertanggung jawab untuk:

- PostgreSQL + Alembic schema design.
- Redis + Celery setup untuk background jobs.
- Tool medis `calculate_vaccine_schedule()`.
- API routing dan validation layer.
- MCP server / tool exposure agar agent milik M1 bisa consume.
- Shared model contracts yang dipakai M1/M2.

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

Untuk MVP, Redis + Celery belum wajib kecuali upload/ingestion M2 harus async.

Jika tetap dibuat sekarang, scope M3:

```text
src/core/celery_app.py
docker/compose.yml
worker startup command
task retry defaults
healthcheck task
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
```

- Catatan: kode saat ini masih memakai `OPEN_ROUTER_API_KEY` untuk embedding dan chat model melalui OpenRouter. `MISTRAL_API_KEY` sudah disiapkan, tetapi belum dipakai oleh kode existing.

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

- Menambahkan endpoint FastAPI untuk vaccine tool:

```http
POST /tools/vaccine-schedule
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

- Endpoint ini sengaja belum disambungkan langsung ke agent/chat agar tidak konflik dengan pekerjaan M1. M1 bisa consume endpoint ini lewat HTTP, atau nanti M3 bisa bungkus sebagai MCP tool.

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
.venv/bin/python -m unittest tests/test_vaccine_schedule.py tests/test_tools_endpoint.py
```

- Hasil terakhir:

```text
Ran 10 tests
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
Vaccine schedule tool   : siap dan tested
Vaccine endpoint        : siap dan tested
Agent chat              : masih memakai search_medical_guidelines dan calculate_z_score lama
calculate_z_score       : masih placeholder
Session/history         : belum dikerjakan di M3
MCP server              : belum dibuat
Redis/Celery            : belum dibuat
PostgreSQL/Alembic      : belum dibuat
```
