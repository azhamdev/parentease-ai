from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.tools.verify_url import extract_urls


@dataclass(frozen=True)
class IntentScore:
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IntentClassification:
    text: str
    has_url: bool
    medical: IntentScore
    vaccine: IntentScore
    growth: IntentScore

    @property
    def needs_guidelines(self) -> bool:
        return (
            self.medical.score >= 3
            or self.vaccine.score >= 3
            or self.growth.score >= 2.5
        )

    @property
    def needs_vaccine_schedule(self) -> bool:
        return self.vaccine.score >= 3

    @property
    def needs_growth_context(self) -> bool:
        return self.growth.score >= 2.5


MEDICAL_TERMS: tuple[tuple[str, float], ...] = (
    ("mpasi", 3),
    ("makanan pendamping", 3),
    ("asi", 3),
    ("menyusui", 3),
    ("susu", 2),
    ("makan pertama", 3),
    ("boleh makan", 3),
    ("tekstur", 2),
    ("porsi", 2),
    ("gtm", 2),
    ("gerakan tutup mulut", 2),
    ("latch", 2),
    ("pelekatan", 2),
    ("posisi menyusui", 3),
    ("sendawa", 2),
    ("kolostrum", 2),
    ("pompa asi", 2),
    ("dbf", 2),
    ("direct breastfeeding", 2),
    ("demam", 2),
    ("panas", 1.5),
    ("batuk", 2),
    ("diare", 2),
    ("muntah", 2),
    ("ruam", 1.5),
    ("pilek", 1.5),
    ("sesak", 2),
)

VACCINE_TERMS: tuple[tuple[str, float], ...] = (
    ("vaksin", 3),
    ("vaksinasi", 3),
    ("imunisasi", 3),
    ("suntik", 2.5),
    ("suntikan", 2.5),
    ("disuntik", 2.5),
    ("tetes", 2),
    ("booster", 2.5),
    ("bcg", 3),
    ("dpt", 3),
    ("polio", 3),
    ("pcv", 3),
    ("rotavirus", 3),
    ("campak", 3),
    ("rubella", 3),
    ("mr", 2),
    ("hb0", 3),
    ("hepatitis", 2),
)

GROWTH_TERMS: tuple[tuple[str, float], ...] = (
    ("tumbuh", 2),
    ("kembang", 2),
    ("pertumbuhan", 2.5),
    ("perkembangan", 2.5),
    ("berat", 2),
    ("berat badan", 2.5),
    ("tinggi", 2),
    ("tinggi badan", 2.5),
    ("lingkar kepala", 2.5),
    ("gizi", 2),
    ("nutrisi", 2),
    ("stunting", 3),
    ("z-score", 3),
    ("z score", 3),
    ("growth", 2),
    ("kms", 2),
    ("posyandu", 2),
    ("grafik", 1.5),
    ("kurva", 1.5),
    ("normal", 1),
    ("pdf", 1),
    ("upload", 1),
)

CHILD_CONTEXT_TERMS = ("bayi", "anak", "balita", "baduta", "newborn", "anak saya")
SCHEDULE_TERMS = (
    "jadwal",
    "kapan",
    "bulan ini",
    "minggu ini",
    "hari ini",
    "sekarang",
    "berikutnya",
    "lanjutan",
    "perlu",
    "butuh",
    "dapat",
    "dapet",
    "apa",
)

MEDICAL_PATTERNS: tuple[tuple[str, float, str], ...] = (
    (r"\b(kapan|umur|usia|usia berapa)\b.*\b(mpasi|makan|makanan pendamping)\b", 4, "age-to-feed"),
    (r"\b(posisi|pelekatan|latch)\b.*\b(menyusui|asi|dbf)\b", 4, "breastfeeding-technique"),
    (r"\b(berapa|normal|ideal)\b.*\b(berat|tinggi|gizi)\b", 3, "growth-question"),
    (r"\b(bayi|anak)\b.*\b(demam|batuk|diare|muntah|ruam|sesak)\b", 3, "child-symptom"),
)

VACCINE_PATTERNS: tuple[tuple[str, float, str], ...] = (
    (r"\b(jadwal|kapan|perlu|butuh|dapat|dapet|apa)\b.*\b(vaksin|imunisasi|suntik|suntikan|tetes)\b", 4, "vaccine-schedule"),
    (r"\b(vaksin|imunisasi|suntik|suntikan|tetes)\b.*\b(bulan ini|minggu ini|sekarang|berikutnya|lanjutan)\b", 4, "vaccine-timing"),
    (r"\b(bcg|dpt|polio|pcv|rotavirus|campak|rubella|hb0)\b.*\b(kapan|berikutnya|jadwal|tetes|suntik)\b", 4, "specific-vaccine"),
)

GROWTH_PATTERNS: tuple[tuple[str, float, str], ...] = (
    (r"\b(berat|tinggi|lingkar kepala)\b.*\b(normal|ideal|kurang|lebih)\b", 3, "growth-status"),
    (r"\b(grafik|kurva|z-score|z score)\b.*\b(berat|tinggi|pertumbuhan)\b", 3, "growth-chart"),
)


def classify_intent(message: str) -> IntentClassification:
    text = _normalize(message)
    has_child_context = any(term in text for term in CHILD_CONTEXT_TERMS)

    medical_score, medical_reasons = _score_terms(text, MEDICAL_TERMS)
    vaccine_score, vaccine_reasons = _score_terms(text, VACCINE_TERMS)
    growth_score, growth_reasons = _score_terms(text, GROWTH_TERMS)

    if has_child_context:
        medical_score += 0.5
        medical_reasons.append("child-context")
        vaccine_score += 0.5
        vaccine_reasons.append("child-context")
        growth_score += 0.5
        growth_reasons.append("child-context")

    schedule_hits = [term for term in SCHEDULE_TERMS if term in text]
    if schedule_hits and vaccine_score >= 2:
        vaccine_score += min(2, len(schedule_hits) * 0.75)
        vaccine_reasons.extend(f"schedule:{term}" for term in schedule_hits[:3])

    medical_pattern_score, medical_pattern_reasons = _score_patterns(text, MEDICAL_PATTERNS)
    vaccine_pattern_score, vaccine_pattern_reasons = _score_patterns(text, VACCINE_PATTERNS)
    growth_pattern_score, growth_pattern_reasons = _score_patterns(text, GROWTH_PATTERNS)

    medical_score += medical_pattern_score
    medical_reasons.extend(medical_pattern_reasons)
    vaccine_score += vaccine_pattern_score
    vaccine_reasons.extend(vaccine_pattern_reasons)
    growth_score += growth_pattern_score
    growth_reasons.extend(growth_pattern_reasons)

    if vaccine_score >= 3:
        medical_score += 1
        medical_reasons.append("vaccine-needs-guideline-context")
    if growth_score >= 2.5:
        medical_score += 1
        medical_reasons.append("growth-needs-guideline-context")

    return IntentClassification(
        text=text,
        has_url=bool(extract_urls(message)),
        medical=IntentScore(score=medical_score, reasons=_unique(medical_reasons)),
        vaccine=IntentScore(score=vaccine_score, reasons=_unique(vaccine_reasons)),
        growth=IntentScore(score=growth_score, reasons=_unique(growth_reasons)),
    )


def should_retrieve_guidelines(message: str) -> bool:
    return classify_intent(message).needs_guidelines


def should_calculate_vaccine_schedule(message: str) -> bool:
    return classify_intent(message).needs_vaccine_schedule


def should_include_growth_data(message: str) -> bool:
    return classify_intent(message).needs_growth_context


def _normalize(message: str) -> str:
    text = message.lower()
    text = text.replace("imunisasi", " imunisasi ")
    text = re.sub(r"[^\w\s\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _score_terms(text: str, terms: tuple[tuple[str, float], ...]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    for term, weight in terms:
        if _contains_term(text, term):
            score += weight
            reasons.append(f"term:{term}")
    return score, reasons


def _score_patterns(
    text: str,
    patterns: tuple[tuple[str, float, str], ...],
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    for pattern, weight, label in patterns:
        if re.search(pattern, text):
            score += weight
            reasons.append(f"pattern:{label}")
    return score, reasons


def _contains_term(text: str, term: str) -> bool:
    if " " in term or "-" in term:
        return term in text
    return bool(re.search(rf"\b{re.escape(term)}\b", text))


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
