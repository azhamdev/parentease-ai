from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import date

class WelcomeContext(BaseModel):
    tanggal_lahir: date  # ✅ WAJIB
    gender: Literal["L", "P"]  # ✅ WAJIB
    
    nama_anak: Optional[str] = None
    berat_badan_kg: Optional[float] = Field(default=None, gt=0)
    tinggi_badan_cm: Optional[float] = Field(default=None, gt=0)
    topik: Optional[Literal["ASI", "MPASI", "Vaksin", "Tidur", "TumbuhKembang", "Umum"]] = None

class SessionCreate(BaseModel):
    context: WelcomeContext