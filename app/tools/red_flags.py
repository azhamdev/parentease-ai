from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class RedFlagResult:
    is_red_flag: bool
    reasons: list[str] = field(default_factory=list)
    action: str = ""


URGENT_ACTION = (
    "Segera bawa anak ke IGD atau fasilitas kesehatan terdekat. "
    "Jika gejala berat, hubungi layanan darurat setempat."
)


RED_FLAG_PATTERNS: tuple[tuple[str, str], ...] = (
    ("kejang", "Kejang pada anak perlu evaluasi medis segera."),
    ("sesak", "Sesak napas adalah tanda bahaya."),
    ("sulit napas", "Sulit bernapas adalah tanda bahaya."),
    ("napas cepat", "Napas cepat dapat menjadi tanda gangguan pernapasan."),
    ("bibir biru", "Bibir atau tubuh kebiruan adalah tanda kekurangan oksigen."),
    ("kebiruan", "Warna tubuh kebiruan adalah tanda bahaya."),
    ("tidak mau minum", "Tidak mau minum berisiko dehidrasi dan perlu dinilai segera."),
    ("tidak mau menyusu", "Tidak mau menyusu pada bayi adalah tanda bahaya."),
    ("dehidrasi", "Dehidrasi pada bayi/anak perlu penanganan segera."),
    ("lemas sekali", "Anak sangat lemas adalah tanda bahaya."),
    ("tidak sadar", "Penurunan kesadaran adalah kondisi gawat darurat."),
    ("muntah terus", "Muntah terus-menerus berisiko dehidrasi."),
)


def detect_red_flags(message: str, child_context: dict | None = None) -> RedFlagResult:
    text = message.lower()
    reasons: list[str] = []

    for pattern, reason in RED_FLAG_PATTERNS:
        if pattern in text:
            reasons.append(reason)

    age_months = _age_months(child_context)
    temperature = _extract_temperature(text)
    mentions_fever = "demam" in text or "panas" in text

    if mentions_fever and age_months is not None and age_months < 3:
        if temperature is None or temperature >= 38:
            reasons.append("Demam pada bayi usia di bawah 3 bulan perlu diperiksa segera.")

    if temperature is not None and temperature >= 40:
        reasons.append("Demam 40°C atau lebih adalah tanda bahaya.")

    unique_reasons = list(dict.fromkeys(reasons))
    return RedFlagResult(
        is_red_flag=bool(unique_reasons),
        reasons=unique_reasons,
        action=URGENT_ACTION if unique_reasons else "",
    )


def _age_months(child_context: dict | None) -> int | None:
    if not child_context:
        return None

    explicit_age = child_context.get("age_months")
    if isinstance(explicit_age, int):
        return explicit_age

    birth = child_context.get("birth_date")
    if not birth:
        return None

    try:
        birth_date = birth if isinstance(birth, date) else date.fromisoformat(str(birth))
    except ValueError:
        return None

    today = date.today()
    months = (today.year - birth_date.year) * 12 + (today.month - birth_date.month)
    if today.day < birth_date.day:
        months -= 1
    return max(months, 0)


def _extract_temperature(text: str) -> float | None:
    match = re.search(r"(\d{2}(?:[,.]\d)?)\s*(?:°|derajat|c\b|celcius|celsius)?", text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))
