from app.database import get_session
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from pydantic import BaseModel, Field
from datetime import date, datetime
import uuid
from app.models import ChildProfile

router = APIRouter(prefix="/profiles", tags=["child-profiles"])

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

@router.post("/", response_model=CreateProfileResponse)
async def create_child_profile(
    context: ChildContext,
    db_session: Session = Depends(get_session)
):
    """
    Create session + child profile baru.
    Dipanggil saat user pertama kali mengisi form welcome.
    """
    # 1. Validasi & parse tanggal lahir
    try:
        birth_date = datetime.strptime(context.tanggal_lahir, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail="Format tanggal lahir tidak valid. Gunakan YYYY-MM-DD"
        )
    
    # 2. Generate session ID unik
    session_id = str(uuid.uuid4())
    
    # 3. Hitung usia dalam bulan
    today = date.today()
    age_months = (today.year - birth_date.year) * 12 + (today.month - birth_date.month)
    if age_months < 0:
        age_months = 0
    
    # 4. Buat ChildProfile
    profile = ChildProfile(
        session_id=session_id,
        name=context.nama_anak,
        birth_date=birth_date,
        gender=context.gender.upper(),
        weight_kg=context.berat_badan_kg,
        height_cm=context.tinggi_badan_cm,
    )
    
    # 5. Simpan ke database
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    
    # 6. Return response
    return {
        "session_id": session_id,
        "message": "Profil anak berhasil dibuat",
        "child_data": {
            "nama": profile.name,
            "usia_bulan": age_months,
            "gender": profile.gender,
            "berat_kg": profile.weight_kg,
            "tinggi_cm": profile.height_cm
        }
    }

class UpdateProfileResponse(BaseModel):
    """Response setelah update profile."""
    message: str
    data: dict

@router.patch("/{session_id}", response_model=UpdateProfileResponse)
async def update_child_profile(
    session_id: str,
    update_data: ChildContext,
    db_session: Session = Depends(get_session)
):
    """
    Update data anak untuk session tertentu.
    Hanya field yang dikirim yang akan diupdate (partial update).
    """
    # 1. Cari profile existing
    stmt = select(ChildProfile).where(ChildProfile.session_id == session_id)
    profile = db_session.exec(stmt).first()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan")
    
    # 2. Apply update hanya pada field yang dikirim (exclude_unset=True)
    update_dict = update_data.model_dump(exclude_unset=True)  # ✅ Sekarang update_data sudah valid
    
    # 3. Validasi & konversi field khusus
    if "tanggal_lahir" in update_dict:
        try:
            birth_date = datetime.strptime(update_dict["tanggal_lahir"], "%Y-%m-%d").date()
            profile.birth_date = birth_date
            
            # Recalculate age
            today = date.today()
            profile.age_months = (today.year - birth_date.year) * 12 + (today.month - birth_date.month)
            if profile.age_months < 0:  # ty:ignore[unresolved-attribute]
                profile.age_months = 0
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Format tanggal lahir tidak valid"
            )
    
    if "nama_anak" in update_dict:
        profile.name = update_dict["nama_anak"]
    
    if "gender" in update_dict:
        profile.gender = update_dict["gender"].upper()
    
    if "berat_badan_kg" in update_dict:
        profile.weight_kg = update_dict["berat_badan_kg"]
    
    if "tinggi_badan_cm" in update_dict:
        profile.height_cm = update_dict["tinggi_badan_cm"]
    
    # 4. Commit perubahan
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    
    return {
        "message": "Data anak berhasil diperbarui",
        "data": profile.model_dump()
    }

@router.get("/{session_id}", response_model=dict)
async def get_child_profile(
    session_id: str,
    db_session: Session = Depends(get_session)
):
    """
    Get child profile data untuk auto-fill form edit.
    
    - **session_id**: ID session yang ingin diambil datanya
    """
    # 1. Cari profile
    stmt = select(ChildProfile).where(ChildProfile.session_id == session_id)
    profile = db_session.exec(stmt).first()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan")
    
    # 2. Return data yang sudah diformat untuk frontend
    return {
        "session_id": profile.session_id,
        "nama_anak": profile.name,
        "tanggal_lahir": profile.birth_date.isoformat() if profile.birth_date else None,
        "gender": profile.gender,
        "berat_badan_kg": profile.weight_kg,
        "tinggi_badan_cm": profile.height_cm,
    }