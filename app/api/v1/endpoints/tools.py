from fastapi import APIRouter

from app.tools.schemas import VaccineScheduleRequest, VaccineScheduleResponse
from app.tools.vaccine_schedule import calculate_vaccine_schedule

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/vaccine-schedule", response_model=VaccineScheduleResponse)
def vaccine_schedule_endpoint(request: VaccineScheduleRequest):
    return calculate_vaccine_schedule(request)
