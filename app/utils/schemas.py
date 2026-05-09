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