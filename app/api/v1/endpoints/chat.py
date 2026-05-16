import re
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.models import (
    ChatMessage,
    ChildProfile,
    GrowthRecord,
    ToolCall,
    UploadJob,
    VaccineRecord,
)
from app.database import get_session
from app.services.agent.streaming import stream_chat_response
from app.tasks.upload_tasks import process_growth_pdf_upload
from app.tools.pdf_growth_extract import extract_growth_from_pdf
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["chat"])
UPLOADS_DIR = Path("uploads/jobs")


class ChatRequest(BaseModel):
    message: str


@router.post("/", response_class=StreamingResponse)
async def chat_endpoint_streaming(
    request: ChatRequest,
    session: Session = Depends(get_session),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    """
    Chat endpoint dengan streaming response (SSE).

    - **message**: Pesan dari user
    - **x_session_id**: Session ID dari header
    """
    # Save user message
    user_msg = ChatMessage(
        role="user", content=request.message, session_id=x_session_id
    )
    session.add(user_msg)
    session.commit()

    # Fetch child data
    child_data = None
    if x_session_id:
        stmt = select(ChildProfile).where(ChildProfile.session_id == x_session_id)
        profile = session.exec(stmt).first()
        if profile:
            child_data = profile.model_dump(mode="json")
            vaccine_stmt = select(VaccineRecord).where(
                VaccineRecord.session_id == x_session_id
            )
            vaccine_records = session.exec(vaccine_stmt).all()
            child_data["completed_vaccines"] = [
                {
                    "vaccine_code": record.vaccine_code,
                    "date_given": record.date_given.isoformat()
                    if record.date_given
                    else None,
                }
                for record in vaccine_records
            ]

    # Streaming generator
    async def event_generator():
        full_response = ""

        def audit_tool_call(payload: dict) -> None:
            tool_call = ToolCall(
                session_id=x_session_id,
                tool_name=payload["tool_name"],
                status=payload["status"],
                input_payload=jsonable_encoder(payload.get("input_payload", {})),
                output_payload=jsonable_encoder(payload.get("output_payload", {})),
                sources=jsonable_encoder(payload.get("sources", [])),
            )
            session.add(tool_call)
            session.commit()

        try:
            async for token in stream_chat_response(
                user_message=request.message,
                child_context=child_data,
                tool_audit_callback=audit_tool_call,
                session_id=x_session_id,
            ):
                # Skip empty tokens
                if not token or token.strip() == "":
                    continue

                full_response += token
                yield f"data: {token}\n\n"

        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            # Save AI response if not empty
            if full_response and full_response.strip():
                ai_msg = ChatMessage(
                    role="assistant", content=full_response, session_id=x_session_id
                )
                session.add(ai_msg)
                session.commit()
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


MAX_PDF_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/upload-pdf/jobs")
async def create_upload_pdf_job(
    file: UploadFile = File(...),
    message: str | None = None,
    session: Session = Depends(get_session),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    """
    Create an async PDF upload/OCR job.

    This is the production-like flow for heavier PDF work:
    upload -> persist file/job -> enqueue Celery -> frontend polls job status.
    """
    pdf_bytes = await _validate_and_read_pdf(file)
    job_id = str(uuid.uuid4())
    safe_filename = _safe_filename(file.filename or "upload.pdf")
    job_dir = UPLOADS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    file_path = job_dir / safe_filename
    file_path.write_bytes(pdf_bytes)

    job = UploadJob(
        job_id=job_id,
        session_id=x_session_id,
        filename=safe_filename,
        content_type=file.content_type,
        file_path=str(file_path),
        status="queued",
        message="PDF sudah diterima dan masuk antrean pemrosesan.",
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    celery_result = process_growth_pdf_upload.delay(
        job_id=job_id,
        file_path=str(file_path),
        filename=safe_filename,
        session_id=x_session_id,
        message=message,
    )

    job.celery_task_id = celery_result.id
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()

    return {
        "job_id": job_id,
        "celery_task_id": celery_result.id,
        "status": job.status,
        "message": job.message,
        "filename": job.filename,
    }


@router.get("/upload-pdf/jobs/{job_id}")
async def get_upload_pdf_job(
    job_id: str,
    session: Session = Depends(get_session),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    stmt = select(UploadJob).where(UploadJob.job_id == job_id)
    if x_session_id:
        stmt = stmt.where(UploadJob.session_id == x_session_id)
    job = session.exec(stmt).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Upload job not found.")

    return {
        "job_id": job.job_id,
        "session_id": job.session_id,
        "celery_task_id": job.celery_task_id,
        "filename": job.filename,
        "status": job.status,
        "message": job.message,
        "result": job.result_payload,
        "error": job.error_message,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/upload-pdf")
async def upload_pdf_growth(
    file: UploadFile = File(...),
    message: str | None = None,
    session: Session = Depends(get_session),
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    """
    Upload a PDF (KMS, Posyandu card, medical report) to extract child growth data.

    The PDF is processed with Mistral OCR, growth measurements are parsed and
    saved to the database, then the AI responds with an analysis via streaming.

    - **file**: PDF file upload
    - **message**: Optional user message to accompany the upload
    - **x_session_id**: Session ID from header
    """
    pdf_bytes = await _validate_and_read_pdf(file)

    # Save user message about upload
    user_text = message or f"[Upload PDF: {file.filename}]"
    user_msg = ChatMessage(role="user", content=user_text, session_id=x_session_id)
    session.add(user_msg)
    session.commit()

    # Run Mistral OCR + LLM growth extraction
    result = extract_growth_from_pdf(pdf_bytes, file.filename)

    # Save extraction as a ToolCall audit
    tool_call = ToolCall(
        session_id=x_session_id,
        tool_name="pdf_growth_extract",
        status="ok" if result.success else "error",
        input_payload=jsonable_encoder(
            {"filename": file.filename, "size_bytes": len(pdf_bytes)}
        ),
        output_payload=jsonable_encoder(
            {
                "success": result.success,
                "child_name": result.child_name,
                "measurement_count": len(result.measurements),
                "vaccine_count": len(result.vaccinations),
                "summary": result.summary,
                "error": result.error,
            }
        ),
        sources=[],
    )
    session.add(tool_call)
    session.commit()

    # Save growth records to database
    saved_records: list[dict] = []
    if result.success and result.measurements:
        for m in result.measurements:
            record = GrowthRecord(
                session_id=x_session_id or "",
                source_filename=file.filename,
                measurement_date=_parse_date_safe(m.measurement_date),
                age_months=m.age_months,
                weight_kg=m.weight_kg,
                height_cm=m.height_cm,
                head_circumference_cm=m.head_circumference_cm,
                notes=m.notes,
                raw_ocr_text=result.raw_ocr_text[:5000]
                if result.raw_ocr_text
                else None,
            )
            session.add(record)
            saved_records.append(
                {
                    "measurement_date": m.measurement_date,
                    "age_months": m.age_months,
                    "weight_kg": m.weight_kg,
                    "height_cm": m.height_cm,
                    "head_circumference_cm": m.head_circumference_cm,
                    "notes": m.notes,
                }
            )
        session.commit()

    _save_extracted_vaccine_records(
        session=session,
        session_id=x_session_id,
        filename=file.filename,
        result=result,
    )

    # Fetch child data for the streaming response
    child_data = None
    if x_session_id:
        stmt = select(ChildProfile).where(ChildProfile.session_id == x_session_id)
        profile = session.exec(stmt).first()
        if profile:
            child_data = profile.model_dump(mode="json")

    # Build the message for the agent with the extraction context
    agent_message = _build_agent_message(file.filename, user_text, result)

    # Stream AI analysis of the growth data
    async def event_generator():
        full_response = ""

        def audit_tool_call_cb(payload: dict) -> None:
            tc = ToolCall(
                session_id=x_session_id,
                tool_name=payload["tool_name"],
                status=payload["status"],
                input_payload=jsonable_encoder(payload.get("input_payload", {})),
                output_payload=jsonable_encoder(payload.get("output_payload", {})),
                sources=jsonable_encoder(payload.get("sources", [])),
            )
            session.add(tc)
            session.commit()

        try:
            async for token in stream_chat_response(
                user_message=agent_message,
                child_context=child_data,
                tool_audit_callback=audit_tool_call_cb,
                session_id=x_session_id,
                skip_growth_injection=True,
            ):
                if not token or token.strip() == "":
                    continue
                full_response += token
                yield f"data: {token}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            if full_response and full_response.strip():
                ai_msg = ChatMessage(
                    role="assistant",
                    content=full_response,
                    session_id=x_session_id,
                )
                session.add(ai_msg)
                session.commit()
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _build_agent_message(filename: str, user_text: str, result) -> str:
    """Build a composite message with the extraction result for the agent."""
    parts = [f"User mengupload PDF: {filename}"]
    if user_text and not user_text.startswith("[Upload PDF"):
        parts.append(f"Pesan user: {user_text}")

    parts.append(f"\nHasil ekstraksi data tumbuh kembang:\n{result.to_tool_string()}")
    parts.append(
        "\nData di atas telah disimpan ke database dan akan otomatis tersedia "
        "di percakapan selanjutnya. User tidak perlu mengupload ulang."
        "\n\nTolong analisis data tumbuh kembang anak di atas secara menyeluruh:"
        "\n1. Ringkasan data yang berhasil diekstrak"
        "\n2. Analisis tren pertumbuhan (berat badan, tinggi badan, lingkar kepala)"
        "\n3. Bandingkan dengan standar WHO jika memungkinkan"
        "\n4. Berikan insight apakah pertumbuhan anak normal, perlu perhatian, atau ada red flag"
        "\n5. Sampaikan bahwa data ini sudah tersimpan dan bisa ditanyakan kapan saja"
        "\n\nGunakan data dari knowledge base sebagai referensi medis."
    )
    return "\n".join(parts)


def _save_extracted_vaccine_records(
    *,
    session: Session,
    session_id: str | None,
    filename: str | None,
    result,
) -> int:
    if not session_id or not result.success or not result.vaccinations:
        return 0

    saved = 0
    for vaccine in result.vaccinations:
        date_given = _parse_date_safe(vaccine.date_given)
        existing = session.exec(
            select(VaccineRecord).where(
                VaccineRecord.session_id == session_id,
                VaccineRecord.vaccine_code == vaccine.vaccine_code,
                VaccineRecord.date_given == date_given,
            )
        ).first()
        if existing:
            continue
        session.add(
            VaccineRecord(
                session_id=session_id,
                vaccine_code=vaccine.vaccine_code,
                date_given=date_given,
                notes=vaccine.notes or f"Extracted from {filename or 'uploaded PDF'}",
            )
        )
        saved += 1
    if saved:
        session.commit()
    return saved


def _parse_date_safe(date_str: str | None) -> date | None:
    """Parse a date string safely, returning None on failure."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


async def _validate_and_read_pdf(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise HTTPException(status_code=400, detail="PDF exceeds 20 MB limit.")

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    return pdf_bytes


def _safe_filename(filename: str) -> str:
    filename = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
    return cleaned or "upload.pdf"
