# Database Reset and End-to-End Proof

Dokumen ini dipakai kalau ingin mulai dari database kosong, menjalankan flow dari awal, lalu membuktikan data benar-benar masuk ke PostgreSQL dan fitur M3 berjalan.

## Scope

Yang dibersihkan:

```text
PostgreSQL Docker volume
Redis Docker volume
```

Yang tidak otomatis dibersihkan:

```text
chroma_db/
.env
data/*.pdf
```

Catatan: `docker compose down -v` akan menghapus data PostgreSQL dan Redis lokal. Jalankan hanya kalau memang ingin reset total service lokal.

## 1. Reset PostgreSQL Lokal

Stop container dan hapus volume database:

```bash
docker compose down -v
```

Start PostgreSQL dan Redis baru:

```bash
docker compose up -d postgres redis
```

Cek container sehat:

```bash
docker compose ps postgres redis
```

Expected:

```text
parentease-postgres   ...   Up ... (healthy)   0.0.0.0:5432->5432/tcp
parentease-redis      ...   Up ... (healthy)   0.0.0.0:6379->6379/tcp
```

## 2. Run Migration

Pastikan `.env` memakai PostgreSQL:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/parentease
```

Run migration:

```bash
uv run alembic upgrade head
```

Cek revision:

```bash
uv run alembic current
```

Expected:

```text
20260516_0005 (head)
```

Proof via `psql`:

```bash
docker exec -it parentease-postgres psql -U postgres -d parentease
```

Di dalam `psql`:

```sql
\dt
select * from alembic_version;
```

Expected tables:

```text
alembic_version
chatmessage
childprofile
document
growthrecord
toolcall
uploadjob
vaccinerecord
```

Redis/Celery proof:

```bash
docker compose exec -T redis redis-cli ping
uv run celery -A app.core.celery_app.celery_app report
```

Expected:

```text
PONG
transport: redis://localhost:6379/1
results: redis://localhost:6379/2
```

Async upload worker proof:

```bash
make worker
```

Expected worker task list contains:

```text
uploads.process_growth_pdf
```

## 3. Ingest Chroma Knowledge Base

Kalau `chroma_db/` belum ada atau ingin rebuild index lokal:

```bash
uv run -m scripts.ingest_pdfs
```

Expected current local collection:

```text
pediatric_guidelines
434 chunks
```

Chunking method:

```text
library       : Chonkie TokenChunker
chunk type    : token-based, bukan character-based
chunk size    : 512 tokens
overlap       : 64 tokens
embedding     : openai/text-embedding-3-small via OpenRouter
vector store  : ChromaDB collection pediatric_guidelines
metadata      : source filename, chunk_index, page
```

Flow ingest PDF:

```text
data/*.pdf
  -> pypdf extracts text per page
  -> pages joined with separators
  -> Chonkie TokenChunker splits into 512-token chunks with 64-token overlap
  -> each chunk embedded with OpenRouter embedding model
  -> chunk + embedding + metadata stored in ChromaDB
  -> document ingest metadata stored in PostgreSQL document table
```

Catatan: Chroma bukan PostgreSQL. Chroma menyimpan vector index PDF lokal di `chroma_db/`. PostgreSQL hanya menyimpan metadata dokumen untuk proof/debugging.

PostgreSQL proof setelah ingest:

```sql
select
  filename,
  status,
  collection_name,
  chunk_count,
  ingested_at
from document
order by filename;
```

Expected:

```text
asi_guidelines.pdf | completed | pediatric_guidelines | 50
buku_kia_2024.pdf  | completed | pediatric_guidelines | 384
```

## 4. Start Local Stack

```bash
make dev
```

Expected services:

```text
Backend API : http://127.0.0.1:8000
MCP Server  : http://127.0.0.1:8001
React UI    : http://localhost:5173
```

API docs:

```text
http://127.0.0.1:8000/scalar
```

MCP health proof:

```bash
curl http://127.0.0.1:8001/health
```

Expected:

```text
status = ok
tools contains calculate_vaccine_schedule, detect_red_flags, search_medical_guidelines, verify_url_source
```

## UI Proof Flow

Bagian ini dipakai kalau app sudah jalan dan ingin mengecek dari sisi user, bukan dari `curl`.

Yang perlu dibuka:

```text
Terminal backend  : tempat menjalankan make dev
Frontend browser  : http://localhost:5173
Browser DevTools  : tab Network
PostgreSQL proof  : psql / DBeaver / TablePlus
```

### UI Step 1: Welcome Form

Di UI, isi data anak:

```text
Tanggal lahir : 08/03/2026 atau 2026-03-08
Gender        : Perempuan
Nama anak     : Aira
Berat         : 5,8 atau 5.8
Tinggi        : 59
```

Klik submit / simpan.

Network tab expected:

```text
POST http://localhost:8000/api/v1/profiles/
Status: 200
```

Request payload expected:

```json
{
  "tanggal_lahir": "2026-03-08",
  "gender": "P",
  "nama_anak": "Aira",
  "berat_badan_kg": 5.8,
  "tinggi_badan_cm": 59
}
```

Response expected:

```json
{
  "session_id": "...",
  "message": "Profil anak berhasil dibuat",
  "child_data": {
    "nama": "Aira",
    "usia_bulan": 2,
    "gender": "P",
    "berat_kg": 5.8,
    "tinggi_cm": 59
  }
}
```

Proof in PostgreSQL:

```sql
select session_id, name, birth_date, gender, weight_kg, height_cm
from childprofile
order by created_at desc
limit 1;
```

Expected:

```text
Aira | 2026-03-08 | P | 5.8 | 59
```

### UI Step 2: General RAG Question

From the chat UI, ask:

```text
ASI eksklusif sampai kapan?
```

Network tab expected:

```text
POST http://localhost:8000/api/v1/chat
Status: 200
Request header: X-Session-ID: {session_id}
Response type: text/event-stream
```

Backend terminal expected:

```text
Intent scores: medical=...
ChromaDB has 434 documents
Pre-retrieved ... source(s)
No tool calls detected - direct response
Sending ... source(s) to frontend
```

UI expected:

```text
Jawaban muncul streaming.
Bagian sumber muncul di bawah jawaban.
Source bisa berisi Asi Guidelines atau Buku Kia 2024.
```

Proof in PostgreSQL:

```sql
select role, content
from chatmessage
where session_id = '{SESSION_ID}'
order by created_at asc;
```

Expected:

```text
user      | ASI eksklusif sampai kapan?
assistant | ...
```

Interpretasi:

```text
Kalau backend log menunjukkan Intent scores + Pre-retrieved ... source(s), berarti intent classifier mendeteksi medical/RAG dan Chroma dipakai.
Kalau UI menampilkan sources, berarti marker [SOURCES] berhasil diparse frontend.
```

### UI Step 3: Vaccine Question

From the chat UI, ask:

```text
Anak saya perlu suntikan bulan ini apa?
```

Network tab expected:

```text
POST http://localhost:8000/api/v1/chat
Status: 200
Request header: X-Session-ID: {session_id}
```

Backend terminal expected:

```text
Intent scores: medical=..., vaccine=...
ChromaDB has 434 documents
Pre-retrieved ... source(s)
Calculated vaccine schedule via MCP
No tool calls detected - direct response
```

UI expected:

```text
Jawaban menyebut jadwal vaksin sesuai tanggal lahir anak.
Untuk bayi lahir 2026-03-08 dan tanggal sekitar 2026-05-13, usia sekitar 2 bulan.
Vaksin yang relevan: DPT-HB-Hib 1, OPV2, RV1, PCV1.
Sumber Buku Kesehatan Ibu dan Anak 2024 muncul.
```

Proof:

```text
Kalau log "Calculated vaccine schedule via MCP" muncul, berarti chat otomatis memakai MCP vaccine tool.
Kalau tidak muncul, cek apakah X-Session-ID terkirim dan child profile punya birth_date.
```

PostgreSQL/TablePlus proof:

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
where session_id = '{SESSION_ID}'
order by created_at desc;
```

Expected:

```text
tool_name = calculate_vaccine_schedule
status    = ok
input_payload.birth_date terisi
sources berisi Buku Kesehatan Ibu dan Anak 2024
```

Intent classifier proof:

```text
Kalimat eksplisit:
  "Jadwal vaksinasi bayi saya apa?"

Kalimat implisit:
  "Anak saya perlu suntikan bulan ini apa?"
  "Anakku perlu yang tetes kapan?"
  "Suntikan bulan ini apa?"

Semua harus menghasilkan log vaccine score tinggi dan route ke calculate_vaccine_schedule.
```

### UI Step 4: Red Flag Question

From the chat UI, ask:

```text
Bayi saya demam 39 dan usianya 2 bulan
```

Backend terminal expected:

```text
Tidak perlu menunggu RAG/LLM biasa.
Response langsung safety-first dari MCP detect_red_flags.
```

UI expected:

```text
Jawaban menyebut tanda bahaya dan menyarankan segera ke IGD/fasilitas kesehatan.
```

Proof in PostgreSQL:

```sql
select role, content
from chatmessage
where session_id = '{SESSION_ID}'
order by created_at desc
limit 2;
```

Expected:

```text
assistant response berisi arahan fasilitas kesehatan/IGD.
```

Tambahan red flag yang perlu ikut dites manual:

```text
Bayi saya sesak dan dada tertarik
Anak saya kejang
Bayi saya muntah hijau
Anak saya tidak pipis dan mulutnya kering
Bayi 4 bulan demam 39
```

Expected:

```text
Chat berhenti di safety response, tidak lanjut ke RAG/LLM biasa.
```

### UI Step 5: Edit Profile

Open edit profile in UI and change:

```text
Berat : 6,0
Tinggi: 60
```

Network tab expected:

```text
PATCH http://localhost:8000/api/v1/profiles/{session_id}
Status: 200
```

Request payload expected:

```json
{
  "tanggal_lahir": "2026-03-08",
  "gender": "P",
  "nama_anak": "Aira",
  "berat_badan_kg": 6,
  "tinggi_badan_cm": 60
}
```

Proof in PostgreSQL:

```sql
select name, birth_date, gender, weight_kg, height_cm
from childprofile
where session_id = '{SESSION_ID}';
```

Expected:

```text
weight_kg = 6
height_cm = 60
```

### UI Debug Checklist

Jika source kosong:

```text
1. Cek backend log: apakah ada "Pre-retrieved ... source(s)"?
2. Cek Chroma: apakah "ChromaDB has 434 documents" muncul?
3. Cek backend log "Intent scores"; medical/vaccine/growth harus melewati threshold.
4. Cek frontend Network response: apakah ada marker [SOURCES]?
```

Jika vaccine tool tidak terpanggil:

```text
1. Cek request chat punya header X-Session-ID.
2. Cek table childprofile punya row untuk session_id itu.
3. Cek birth_date tidak null.
4. Cek backend log: harus ada "Intent scores" dengan vaccine score tinggi.
5. Cek backend log: harus ada "Calculated vaccine schedule via MCP".
6. Cek MCP server hidup di http://127.0.0.1:8001/health.
```

Jika MCP error:

```text
1. Cek make dev menjalankan uvicorn app.mcp_server:app --port 8001.
2. Cek /health status ok.
3. Cek toolcall table: output_payload.error harus berbentuk structured error, bukan string mentah.
4. Cek field error.type, error.retryable, error.tool_name.
```

Jika data tidak muncul saat balik ke app:

```text
1. Cek localStorage/session state frontend menyimpan session_id.
2. Cek Network GET /api/v1/profiles/{session_id}.
3. Cek PostgreSQL childprofile masih punya row session_id itu.
4. Cek GET /api/v1/sessions dan /api/v1/sessions/{session_id}/messages.
```

## 5. Scenario A: Create Child Profile

Request:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/profiles/ \
  -H "Content-Type: application/json" \
  -d '{
    "tanggal_lahir": "2026-03-08",
    "gender": "P",
    "nama_anak": "Aira",
    "berat_badan_kg": 5.8,
    "tinggi_badan_cm": 59
  }'
```

Expected response:

```json
{
  "session_id": "...",
  "message": "Profil anak berhasil dibuat",
  "child_data": {
    "nama": "Aira",
    "usia_bulan": 2,
    "gender": "P",
    "berat_kg": 5.8,
    "tinggi_cm": 59
  }
}
```

Save `session_id` for next steps.

Proof in PostgreSQL:

```sql
select session_id, name, birth_date, gender, weight_kg, height_cm
from childprofile;
```

Expected:

```text
Aira | 2026-03-08 | P | 5.8 | 59
```

## 6. Scenario B: Get Child Profile

Request:

```bash
curl -s http://127.0.0.1:8000/api/v1/profiles/{SESSION_ID}
```

Expected:

```json
{
  "session_id": "...",
  "nama_anak": "Aira",
  "tanggal_lahir": "2026-03-08",
  "gender": "P",
  "berat_badan_kg": 5.8,
  "tinggi_badan_cm": 59,
  "usia_bulan": 2
}
```

## 7. Scenario C: Vaccine Tool Direct Endpoint

Request:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/tools/vaccine-schedule \
  -H "Content-Type: application/json" \
  -d '{
    "birth_date": "2026-03-08",
    "as_of_date": "2026-05-13",
    "completed_vaccines": []
  }'
```

Expected:

```text
status = ok
age_months = 2
due_now contains DPT-HB-HIB1, OPV2, RV1, PCV1
sources contains Buku Kesehatan Ibu dan Anak 2024
```

## 8. Scenario D: Vaccine History

Create vaccine record:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/profiles/{SESSION_ID}/vaccines \
  -H "Content-Type: application/json" \
  -d '{
    "vaccine_code": "BCG",
    "date_given": "08/04/2026",
    "notes": "Diberikan di puskesmas"
  }'
```

Expected:

```json
{
  "vaccine_code": "BCG",
  "date_given": "2026-04-08"
}
```

List records:

```bash
curl -s http://127.0.0.1:8000/api/v1/profiles/{SESSION_ID}/vaccines
```

Proof in PostgreSQL:

```sql
select session_id, vaccine_code, date_given, notes
from vaccinerecord;
```

Expected:

```text
BCG | 2026-04-08 | Diberikan di puskesmas
```

## 9. Scenario E: Chat With RAG Source

Request:

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: {SESSION_ID}" \
  -d '{"message": "ASI eksklusif sampai kapan?"}'
```

Expected backend log:

```text
Intent scores: medical=...
ChromaDB has 434 documents
Pre-retrieved ... source(s)
No tool calls detected - direct response
Sending ... source(s) to frontend
```

Expected stream includes:

```text
[SOURCES] [...]
```

Proof in PostgreSQL:

```sql
select role, content
from chatmessage
where session_id = '{SESSION_ID}'
order by created_at asc;
```

Expected:

```text
user      | ASI eksklusif sampai kapan?
assistant | ...
```

## 10. Scenario F: Chat Auto Vaccine Tool

Request:

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: {SESSION_ID}" \
  -d '{"message": "Jadwal vaksinasi bayi saya apa?"}'
```

Expected backend log:

```text
Intent scores: medical=..., vaccine=...
Calculated vaccine schedule via MCP
```

Expected answer:

```text
Menjawab jadwal vaksin berdasarkan tanggal lahir anak dan riwayat vaksin yang tercatat.
```

Expected sources:

```text
Buku Kesehatan Ibu dan Anak 2024
```

## 11. Scenario G: Red Flag Guardrail

Request:

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: {SESSION_ID}" \
  -d '{"message": "Bayi saya demam 39 dan usianya 2 bulan"}'
```

Expected:

```text
Ada tanda bahaya.
Segera bawa anak ke IGD atau fasilitas kesehatan terdekat.
```

## 12. Scenario H: Intent Classifier Spot Check

Run:

```bash
.venv/bin/python - <<'PY'
from app.services.agent.intent_classifier import classify_intent

samples = [
    "Anak saya perlu suntikan bulan ini apa?",
    "Anakku perlu yang tetes kapan?",
    "Kapan mulai MPASI?",
    "Posisi menyusui yang benar",
    "Berat anak saya normal nggak?",
    "Anak saya suka main bola",
    "Apa itu JavaScript?",
]

for sample in samples:
    result = classify_intent(sample)
    print(sample)
    print({
        "guidelines": result.needs_guidelines,
        "vaccine": result.needs_vaccine_schedule,
        "growth": result.needs_growth_context,
        "scores": {
            "medical": result.medical.score,
            "vaccine": result.vaccine.score,
            "growth": result.growth.score,
        },
    })
PY
```

Expected:

```text
Suntikan/tetes/vaksin implicit question -> vaccine = True
MPASI/menyusui -> guidelines = True
Berat normal -> guidelines = True, growth = True
Main bola / JavaScript -> all false
```

## 13. Scenario I: Async PDF Upload Job

Frontend upload PDF sekarang memakai jalur async job. Run the full async stack:

```bash
make dev-async
```

Or run manually in separate terminals:

```bash
make dev
make worker
```

Create async upload job from UI or curl:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/chat/upload-pdf/jobs \
  -H "X-Session-ID: {SESSION_ID}" \
  -F "file=@test_assets/sample_kia_growth_filled.pdf" \
  -F "message=Tolong proses data tumbuh kembang ini"
```

Expected response:

```json
{
  "job_id": "...",
  "celery_task_id": "...",
  "status": "queued",
  "message": "PDF sudah diterima dan masuk antrean pemrosesan.",
  "filename": "growth-document.pdf"
}
```

Poll status:

```bash
curl -s http://127.0.0.1:8000/api/v1/chat/upload-pdf/jobs/{JOB_ID} \
  -H "X-Session-ID: {SESSION_ID}"
```

Expected status flow:

```text
queued -> processing -> completed
```

Frontend expected:

```text
Saat upload, chat menampilkan Job ID dan status.
Setelah completed, chat menampilkan jumlah data pertumbuhan dan catatan imunisasi yang tersimpan.
```

PostgreSQL proof:

```sql
select job_id, session_id, celery_task_id, filename, status, result_payload, error_message
from uploadjob
order by created_at desc
limit 5;

select session_id, source_filename, age_months, weight_kg, height_cm, head_circumference_cm
from growthrecord
where session_id = '{SESSION_ID}'
order by created_at desc;

select session_id, tool_name, status, input_payload, output_payload
from toolcall
where session_id = '{SESSION_ID}' and tool_name = 'pdf_growth_extract'
order by created_at desc;
```

Expected:

```text
uploadjob.status = completed
toolcall.tool_name = pdf_growth_extract
growthrecord has extracted measurements if OCR found growth data
vaccinerecord has dated immunization records if OCR found vaccine notes
```

If status becomes `failed`, check:

```text
uploadjob.error_message
worker terminal traceback
MISTRAL_API_KEY in .env
```

Sample PDF:

```text
test_assets/sample_kia_growth_filled.pdf
test_assets/sample_buku_kia_filled_pages.pdf
```

These files are synthetic and contain filled KIA-style growth rows plus dated
immunization notes. They are safe for local testing because they are not real
patient data. Use `sample_buku_kia_filled_pages.pdf` for the closest multi-page
Buku KIA scenario.

Relevant Buku KIA source pages used as reference for real-life uploads:

```text
PDF page 62 : Catatan Pelayanan Kesehatan Anak
PDF page 63 : Pelayanan Kesehatan Bayi 0-28 Hari, including HB notes
PDF page 64 : Pelayanan Imunisasi / Imunisasi Dasar Bayi dan Baduta
PDF page 65 : Pemantauan Pertumbuhan & Perkembangan
PDF page 67 : Tabel Pertumbuhan Anak 0-2 Tahun
PDF page 73 : KMS Perempuan 0-2 Tahun
PDF page 74 : KMS Perempuan 2-5 Tahun
```

## 14. Automated Verification

Run backend tests:

```bash
.venv/bin/python -m unittest tests/test_intent_detection.py tests/test_red_flags.py tests/test_mcp_server.py tests/test_mcp_client.py tests/test_tools_endpoint.py tests/test_upload_jobs.py tests/test_pdf_extraction.py
```

Expected:

```text
Ran 43 tests
OK
```

Check Alembic:

```bash
uv run alembic current
```

Expected:

```text
20260516_0005 (head)
```

## 15. Cleanup After Testing

Stop services without deleting data:

```bash
docker compose down
```

Stop services and delete PostgreSQL data:

```bash
docker compose down -v
```
