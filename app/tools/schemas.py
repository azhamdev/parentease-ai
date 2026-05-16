from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


ToolStatus = Literal["ok", "needs_more_input", "error"]
VaccineTiming = Literal["due_now", "upcoming", "overdue", "completed"]


class CompletedVaccine(BaseModel):
    vaccine_code: str = Field(..., min_length=1)
    date_given: date | None = None


class VaccineScheduleRequest(BaseModel):
    session_id: str | None = None
    birth_date: date | None = None
    as_of_date: date = Field(default_factory=date.today)
    country: str = "ID"
    completed_vaccines: list[CompletedVaccine] = Field(default_factory=list)
    include_regional_vaccines: bool = False


class VaccineScheduleItem(BaseModel):
    vaccine_code: str
    label: str
    due_age_label: str
    timing: VaccineTiming
    diseases_prevented: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class VaccineScheduleSource(BaseModel):
    title: str
    page: int | None = None
    year: int | None = None


class VaccineScheduleResponse(BaseModel):
    tool_name: str = "calculate_vaccine_schedule"
    status: ToolStatus
    age_days: int | None = None
    age_months: int | None = None
    due_now: list[VaccineScheduleItem] = Field(default_factory=list)
    upcoming: list[VaccineScheduleItem] = Field(default_factory=list)
    overdue: list[VaccineScheduleItem] = Field(default_factory=list)
    completed: list[VaccineScheduleItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sources: list[VaccineScheduleSource] = Field(default_factory=list)
