import logging
import uuid
from datetime import date, datetime

from app.database import get_session
from app.models import ChildProfile, VaccineRecord
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import asc
from sqlmodel import Session, select

router = APIRouter(prefix="/profiles", tags=["child-profiles"])


def parse_birth_date(value: str) -> date:
    """Parse browser/API date input into a date.

    Native date inputs should submit YYYY-MM-DD, but some browsers/locales or
    manual edits can still send DD/MM/YYYY. Accept both to keep profile editing
    resilient.
    """
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise HTTPException(
        status_code=400,
        detail="Format tanggal lahir tidak valid. Gunakan YYYY-MM-DD",
    )


def calculate_age_months(birth_date: date) -> int:
    today = date.today()
    age = (today.year - birth_date.year) * 12 + (today.month - birth_date.month)
    return max(0, age)


class GetProfileResponse(BaseModel):
    """Response untuk get child profile."""

    session_id: str
    nama_anak: str | None
    tanggal_lahir: str
    gender: str
    berat_badan_kg: float | None
    tinggi_badan_cm: float | None
    usia_bulan: int


class ChildContext(BaseModel):
    """Model untuk data anak yang dikirim dari frontend."""

    tanggal_lahir: str = Field(..., description="YYYY-MM-DD format")
    gender: str = Field(..., description="L or P")
    nama_anak: str | None = Field(None, max_length=100)
    berat_badan_kg: float | None = Field(None, ge=0, le=100)
    tinggi_badan_cm: float | None = Field(None, ge=20, le=200)
    topik: str | None = Field(None, max_length=500)

    class Config:
        extra = "ignore"


class CreateProfileResponse(BaseModel):
    """Response setelah create profile."""

    session_id: str
    message: str
    child_data: dict


class UpdateProfileResponse(BaseModel):
    """Response setelah update profile."""

    message: str
    data: dict


class VaccineRecordRequest(BaseModel):
    vaccine_code: str = Field(..., min_length=1, max_length=50)
    date_given: str | None = Field(None, description="YYYY-MM-DD or DD/MM/YYYY")
    notes: str | None = Field(None, max_length=500)


@router.post("/", response_model=CreateProfileResponse)
async def create_child_profile(
    context: ChildContext,
    db_session: Session = Depends(get_session),
):
    """
    Create session + child profile baru.
    Dipanggil saat user pertama kali mengisi form welcome.
    """
    birth_date = parse_birth_date(context.tanggal_lahir)
    age_months = calculate_age_months(birth_date)
    session_id = str(uuid.uuid4())

    profile = ChildProfile(
        session_id=session_id,
        name=context.nama_anak,
        birth_date=birth_date,
        gender=context.gender.upper(),
        weight_kg=context.berat_badan_kg,
        height_cm=context.tinggi_badan_cm,
    )

    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    return {
        "session_id": session_id,
        "message": "Profil anak berhasil dibuat",
        "child_data": {
            "nama": profile.name,
            "usia_bulan": age_months,
            "gender": profile.gender,
            "berat_kg": profile.weight_kg,
            "tinggi_cm": profile.height_cm,
        },
    }


@router.patch("/{session_id}", response_model=UpdateProfileResponse)
async def update_child_profile(
    session_id: str,
    update_data: ChildContext,
    db_session: Session = Depends(get_session),
):
    logging.info(f"Update profile for session: {session_id}")
    logging.info(f"Received {update_data.model_dump()}")

    stmt = select(ChildProfile).where(ChildProfile.session_id == session_id)
    profile = db_session.exec(stmt).first()

    if not profile:
        logging.error(f"Session not found: {session_id}")
        raise HTTPException(status_code=404, detail="Session tidak ditemukan")

    update_dict = update_data.model_dump(exclude_unset=True, exclude_none=True)
    logging.info(f"Fields to update: {update_dict.keys()}")

    if "tanggal_lahir" in update_dict and update_dict["tanggal_lahir"]:
        profile.birth_date = parse_birth_date(update_dict["tanggal_lahir"])

    if "nama_anak" in update_dict and update_dict["nama_anak"]:
        profile.name = update_dict["nama_anak"]
    if "gender" in update_dict and update_dict["gender"]:
        profile.gender = update_dict["gender"].upper()
    if "berat_badan_kg" in update_dict and update_dict["berat_badan_kg"] is not None:
        profile.weight_kg = update_dict["berat_badan_kg"]
    if "tinggi_badan_cm" in update_dict and update_dict["tinggi_badan_cm"] is not None:
        profile.height_cm = update_dict["tinggi_badan_cm"]

    try:
        db_session.commit()
        db_session.refresh(profile)
        logging.info("Profile updated successfully")
    except Exception as e:
        logging.error(f"Failed to commit: {e}", exc_info=True)
        db_session.rollback()
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan perubahan: {str(e)}")

    profile_dict = profile.model_dump()
    profile_dict["usia_bulan"] = calculate_age_months(profile.birth_date)

    return {
        "message": "Data anak berhasil diperbarui",
        "data": profile_dict,
    }


@router.get("/{session_id}", response_model=GetProfileResponse)
async def get_child_profile(
    session_id: str,
    db_session: Session = Depends(get_session),
):
    """
    Get child profile data untuk auto-fill form edit.

    - **session_id**: ID session yang ingin diambil datanya
    """
    logging.info(f"Get profile for session: {session_id}")

    profile = _get_profile_or_404(session_id, db_session)

    response_data = {
        "session_id": profile.session_id,
        "nama_anak": profile.name,
        "tanggal_lahir": profile.birth_date.isoformat() if profile.birth_date else None,
        "gender": profile.gender,
        "berat_badan_kg": profile.weight_kg,
        "tinggi_badan_cm": profile.height_cm,
        "usia_bulan": calculate_age_months(profile.birth_date),
    }

    logging.info(f"Profile retrieved successfully for session: {session_id}")
    return response_data


@router.get("/{session_id}/vaccines", response_model=list[dict])
async def list_vaccine_records(
    session_id: str,
    db_session: Session = Depends(get_session),
):
    _get_profile_or_404(session_id, db_session)
    stmt = select(VaccineRecord).where(
        VaccineRecord.session_id == session_id
    ).order_by(asc("date_given"))
    records = db_session.exec(stmt).all()
    return [_serialize_vaccine_record(record) for record in records]


@router.post("/{session_id}/vaccines", response_model=dict)
async def create_vaccine_record(
    session_id: str,
    request: VaccineRecordRequest,
    db_session: Session = Depends(get_session),
):
    _get_profile_or_404(session_id, db_session)
    record = VaccineRecord(
        session_id=session_id,
        vaccine_code=request.vaccine_code.strip().upper(),
        date_given=parse_birth_date(request.date_given) if request.date_given else None,
        notes=request.notes,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return _serialize_vaccine_record(record)


@router.delete("/{session_id}/vaccines/{record_id}", response_model=dict)
async def delete_vaccine_record(
    session_id: str,
    record_id: int,
    db_session: Session = Depends(get_session),
):
    _get_profile_or_404(session_id, db_session)
    stmt = select(VaccineRecord).where(
        VaccineRecord.id == record_id,
        VaccineRecord.session_id == session_id,
    )
    record = db_session.exec(stmt).first()
    if not record:
        raise HTTPException(status_code=404, detail="Riwayat vaksin tidak ditemukan")
    db_session.delete(record)
    db_session.commit()
    return {"message": "Riwayat vaksin berhasil dihapus"}


def _get_profile_or_404(session_id: str, db_session: Session) -> ChildProfile:
    stmt = select(ChildProfile).where(ChildProfile.session_id == session_id)
    profile = db_session.exec(stmt).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan")
    return profile


def _serialize_vaccine_record(record: VaccineRecord) -> dict:
    return {
        "id": record.id,
        "session_id": record.session_id,
        "vaccine_code": record.vaccine_code,
        "date_given": record.date_given.isoformat() if record.date_given else None,
        "notes": record.notes,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
