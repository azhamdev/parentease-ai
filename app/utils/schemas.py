from pydantic import BaseModel, Field, field_validator
from datetime import date

class WelcomeContext(BaseModel):
    tanggal_lahir: date  # ✅ WAJIB - type date
    gender: str          # ✅ WAJIB - "L" atau "P"
    nama_anak: str | None = None
    berat_badan_kg: float | None = Field(default=None, gt=0)
    tinggi_badan_cm: float | None = Field(default=None, gt=0)
    topik: str | None = None

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        if v not in ("L", "P"):
            raise ValueError("Gender harus 'L' atau 'P'")
        return v.upper()  # Auto-uppercase untuk konsistensi

    @field_validator("topik")
    @classmethod
    def validate_topik(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid_topics = ["ASI", "MPASI", "Vaksin", "Tidur", "TumbuhKembang", "Umum"]
        if v not in valid_topics:
            raise ValueError(f"Topik harus salah satu dari: {', '.join(valid_topics)}")
        return v.upper()

class SessionCreate(BaseModel):
    context: WelcomeContext

class SessionListItem(BaseModel):
    session_id: str
    child_name: str | None
    last_message_preview: str
    created_at: str | None

class ChildContext(BaseModel):
    """Model untuk data anak yang dikirim dari frontend."""
    tanggal_lahir: str = Field(..., description="YYYY-MM-DD format")
    gender: str = Field(..., description="L or P")
    nama_anak: str | None = Field(None, max_length=100)
    berat_badan_kg: float | None = Field(None, ge=0, le=100)
    tinggi_badan_cm: float | None = Field(None, ge=20, le=200)
    topik: str | None = Field(None, max_length=500)

class CreateSessionRequest(BaseModel):
    """Request body untuk create session."""
    context: ChildContext

class CreateSessionResponse(BaseModel):
    """Response setelah create session."""
    session_id: str
    message: str
    child_data: dict