from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .schemas import (
    CompletedVaccine,
    VaccineScheduleItem,
    VaccineScheduleRequest,
    VaccineScheduleResponse,
    VaccineScheduleSource,
    VaccineTiming,
)


@dataclass(frozen=True)
class VaccineRule:
    code: str
    label: str
    due_age_months: int | None = None
    due_age_days: int | None = None
    latest_age_months: int | None = None
    latest_age_days: int | None = None
    diseases_prevented: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    regional: bool = False
    aliases: tuple[str, ...] = field(default_factory=tuple)


SCHEDULE_DATA_PATH = Path(__file__).with_name("data") / "vaccine_schedule_id.json"


def _load_schedule_data() -> dict:
    with SCHEDULE_DATA_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def _load_source(data: dict) -> VaccineScheduleSource:
    return VaccineScheduleSource.model_validate(data["source"])


def _load_rules(data: dict) -> tuple[VaccineRule, ...]:
    return tuple(
        VaccineRule(
            code=rule["code"],
            label=rule["label"],
            due_age_months=rule.get("due_age_months"),
            due_age_days=rule.get("due_age_days"),
            latest_age_months=rule.get("latest_age_months"),
            latest_age_days=rule.get("latest_age_days"),
            diseases_prevented=tuple(rule.get("diseases_prevented", [])),
            notes=tuple(rule.get("notes", [])),
            regional=rule.get("regional", False),
            aliases=tuple(rule.get("aliases", [])),
        )
        for rule in data["rules"]
    )


# Initial ID schedule reviewed against Buku KIA 2024, section "Imunisasi Dasar
# Bayi dan Baduta" / "Pelayanan Imunisasi" on printed pages 124-125.
# Recommended age columns in the source table:
# 0-24 jam, 1, 2, 3, 4, 9, 10, 12, and 18 months.
# Keep this deterministic; do not parse the PDF at request time.
_SCHEDULE_DATA = _load_schedule_data()
SOURCE = _load_source(_SCHEDULE_DATA)
VACCINE_SCHEDULE_ID = _load_rules(_SCHEDULE_DATA)


def calculate_vaccine_schedule(
    request: VaccineScheduleRequest | dict,
) -> VaccineScheduleResponse:
    """Calculate an Indonesian child vaccine schedule from structured input."""
    if isinstance(request, dict):
        request = VaccineScheduleRequest.model_validate(request)

    warnings: list[str] = []
    if request.country.upper() != "ID":
        return VaccineScheduleResponse(
            status="error",
            warnings=["Saat ini jadwal vaksin hanya tersedia untuk country='ID'."],
            sources=[SOURCE],
        )

    if request.birth_date is None:
        return VaccineScheduleResponse(
            status="needs_more_input",
            warnings=["birth_date diperlukan untuk menghitung jadwal imunisasi."],
            sources=[SOURCE],
        )

    if request.as_of_date < request.birth_date:
        return VaccineScheduleResponse(
            status="error",
            warnings=["as_of_date tidak boleh lebih awal dari birth_date."],
            sources=[SOURCE],
        )

    age_days = (request.as_of_date - request.birth_date).days
    age_months = _age_in_months(request.birth_date, request.as_of_date)
    completed_codes = _normalize_completed_codes(request.completed_vaccines)

    due_now: list[VaccineScheduleItem] = []
    upcoming: list[VaccineScheduleItem] = []
    overdue: list[VaccineScheduleItem] = []
    completed: list[VaccineScheduleItem] = []

    for rule in VACCINE_SCHEDULE_ID:
        if rule.regional and not request.include_regional_vaccines:
            continue

        timing = _classify_timing(rule, request.birth_date, request.as_of_date)
        item = _to_item(rule, timing)

        if _is_completed(rule, completed_codes):
            completed.append(_to_item(rule, "completed"))
        elif timing == "due_now":
            due_now.append(item)
        elif timing == "overdue":
            overdue.append(item)
        else:
            upcoming.append(item)

    if any(item.vaccine_code.startswith("RV") for item in overdue):
        warnings.append(
            "Rotavirus memiliki batas usia pemberian. Konfirmasi ke tenaga kesehatan bila sudah melewati usia yang dianjurkan."
        )

    warnings.append(
        "Hasil ini adalah bantuan penjadwalan berdasarkan Buku KIA 2024, bukan pengganti konsultasi tenaga kesehatan."
    )

    return VaccineScheduleResponse(
        status="ok",
        age_days=age_days,
        age_months=age_months,
        due_now=due_now,
        upcoming=upcoming,
        overdue=overdue,
        completed=completed,
        warnings=warnings,
        sources=[SOURCE],
    )


def _classify_timing(
    rule: VaccineRule, birth_date: date, as_of_date: date
) -> VaccineTiming:
    due_date = _due_date(rule, birth_date)
    if as_of_date < due_date:
        return "upcoming"

    latest_date = _latest_date(rule, birth_date)
    if as_of_date > latest_date:
        return "overdue"

    return "due_now"


def _due_date(rule: VaccineRule, birth_date: date) -> date:
    if rule.due_age_days is not None:
        return birth_date + timedelta(days=rule.due_age_days)
    if rule.due_age_months is None:
        raise ValueError(f"Vaccine rule {rule.code} has no due age")
    return _add_months(birth_date, rule.due_age_months)


def _latest_date(rule: VaccineRule, birth_date: date) -> date:
    if rule.latest_age_days is not None:
        return birth_date + timedelta(days=rule.latest_age_days)
    if rule.latest_age_months is not None:
        return _add_months(birth_date, rule.latest_age_months)
    if rule.due_age_days is not None:
        return birth_date + timedelta(days=rule.due_age_days + 1)
    if rule.due_age_months is None:
        raise ValueError(f"Vaccine rule {rule.code} has no due age")
    return _add_months(birth_date, rule.due_age_months + 1) - timedelta(days=1)


def _to_item(rule: VaccineRule, timing: VaccineTiming) -> VaccineScheduleItem:
    return VaccineScheduleItem(
        vaccine_code=rule.code,
        label=rule.label,
        due_age_label=_age_label(rule),
        timing=timing,
        diseases_prevented=list(rule.diseases_prevented),
        notes=list(rule.notes),
    )


def _age_label(rule: VaccineRule) -> str:
    if rule.due_age_days is not None:
        if rule.latest_age_days == 1:
            return "0-24 jam"
        return f"{rule.due_age_days} hari"
    return f"{rule.due_age_months} bulan"


def _normalize_completed_codes(
    completed_vaccines: list[CompletedVaccine],
) -> set[str]:
    return {_normalize_code(item.vaccine_code) for item in completed_vaccines}


def _is_completed(rule: VaccineRule, completed_codes: set[str]) -> bool:
    candidates = {rule.code, *rule.aliases}
    return any(_normalize_code(code) in completed_codes for code in candidates)


def _normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _age_in_months(birth_date: date, as_of_date: date) -> int:
    months = (as_of_date.year - birth_date.year) * 12
    months += as_of_date.month - birth_date.month
    if as_of_date.day < birth_date.day:
        months -= 1
    return max(months, 0)


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day
