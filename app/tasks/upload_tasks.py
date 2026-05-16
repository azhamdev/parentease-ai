from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select

from app.core.celery_app import celery_app
from app.database import engine
from app.models import ChatMessage, GrowthRecord, ToolCall, UploadJob, VaccineRecord
from app.tools.pdf_growth_extract import extract_growth_from_pdf


@celery_app.task(
    name="uploads.process_growth_pdf",
    bind=True,
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_growth_pdf_upload(
    self,
    *,
    job_id: str,
    file_path: str,
    filename: str,
    session_id: str | None = None,
    message: str | None = None,
) -> dict:
    """Process an uploaded growth PDF in the background.

    The task persists the same core artifacts as the synchronous upload flow:
    user chat message, pdf extraction tool audit, growth records, and job status.
    """
    task_id = getattr(self.request, "id", None)
    _update_job(
        job_id,
        status="processing",
        celery_task_id=task_id,
        message="PDF sedang diproses.",
    )

    path = Path(file_path)
    try:
        pdf_bytes = path.read_bytes()
        user_text = message or f"[Upload PDF: {filename}]"

        with Session(engine) as db:
            db.add(ChatMessage(role="user", content=user_text, session_id=session_id))
            db.commit()

        result = extract_growth_from_pdf(pdf_bytes, filename)
        saved_growth_count, saved_vaccine_count = _persist_extraction_result(
            session_id=session_id,
            filename=filename,
            file_size=len(pdf_bytes),
            result=result,
        )

        payload = {
            "success": result.success,
            "child_name": result.child_name,
            "measurement_count": len(result.measurements),
            "saved_growth_count": saved_growth_count,
            "vaccine_count": len(result.vaccinations),
            "saved_vaccine_count": saved_vaccine_count,
            "summary": result.summary,
            "error": result.error,
        }
        _update_job(
            job_id,
            status="completed" if result.success else "failed",
            result_payload=jsonable_encoder(payload),
            error_message=result.error,
            completed_at=datetime.utcnow(),
            message=(
                "PDF selesai diproses."
                if result.success
                else "PDF gagal diproses."
            ),
        )
        return payload
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            error_message=str(exc),
            completed_at=datetime.utcnow(),
            message="PDF gagal diproses.",
        )
        raise


def _persist_extraction_result(
    *,
    session_id: str | None,
    filename: str,
    file_size: int,
    result,
) -> tuple[int, int]:
    with Session(engine) as db:
        db.add(
            ToolCall(
                session_id=session_id,
                tool_name="pdf_growth_extract",
                status="ok" if result.success else "error",
                input_payload=jsonable_encoder(
                    {"filename": filename, "size_bytes": file_size, "async": True}
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
        )

        saved_records = 0
        if result.success and result.measurements:
            for measurement in result.measurements:
                db.add(
                    GrowthRecord(
                        session_id=session_id or "",
                        source_filename=filename,
                        measurement_date=_parse_date_safe(
                            measurement.measurement_date
                        ),
                        age_months=measurement.age_months,
                        weight_kg=measurement.weight_kg,
                        height_cm=measurement.height_cm,
                        head_circumference_cm=measurement.head_circumference_cm,
                        notes=measurement.notes,
                        raw_ocr_text=(
                            result.raw_ocr_text[:5000]
                            if result.raw_ocr_text
                            else None
                        ),
                    )
                )
                saved_records += 1

        saved_vaccines = _persist_vaccine_records(
            db=db,
            session_id=session_id,
            filename=filename,
            result=result,
        )

        db.commit()
        return saved_records, saved_vaccines


def _persist_vaccine_records(
    *,
    db: Session,
    session_id: str | None,
    filename: str,
    result,
) -> int:
    if not session_id or not result.success or not result.vaccinations:
        return 0

    saved = 0
    for vaccine in result.vaccinations:
        date_given = _parse_date_safe(vaccine.date_given)
        existing = db.exec(
            select(VaccineRecord).where(
                VaccineRecord.session_id == session_id,
                VaccineRecord.vaccine_code == vaccine.vaccine_code,
                VaccineRecord.date_given == date_given,
            )
        ).first()
        if existing:
            continue
        db.add(
            VaccineRecord(
                session_id=session_id,
                vaccine_code=vaccine.vaccine_code,
                date_given=date_given,
                notes=vaccine.notes or f"Extracted from {filename}",
            )
        )
        saved += 1
    return saved


def _update_job(
    job_id: str,
    *,
    status: str,
    celery_task_id: str | None = None,
    message: str | None = None,
    result_payload: dict | None = None,
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> None:
    with Session(engine) as db:
        job = db.exec(select(UploadJob).where(UploadJob.job_id == job_id)).first()
        if job is None:
            return
        job.status = status
        if celery_task_id:
            job.celery_task_id = celery_task_id
        if message is not None:
            job.message = message
        if result_payload is not None:
            job.result_payload = result_payload
        if error_message is not None:
            job.error_message = error_message
        if completed_at is not None:
            job.completed_at = completed_at
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()


def _parse_date_safe(date_str: str | None):
    if not date_str:
        return None
    try:
        from datetime import date

        return date.fromisoformat(date_str)
    except (TypeError, ValueError):
        return None
