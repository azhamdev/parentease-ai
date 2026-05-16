from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.models import ToolCall
from app.tools.schemas import VaccineScheduleRequest, VaccineScheduleResponse
from app.tools.vaccine_schedule import calculate_vaccine_schedule

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/vaccine-schedule", response_model=VaccineScheduleResponse)
def vaccine_schedule_endpoint(
    request: VaccineScheduleRequest,
    db_session: Session = Depends(get_session),
):
    result = calculate_vaccine_schedule(request)
    if request.session_id:
        tool_call = ToolCall(
            session_id=request.session_id,
            tool_name=result.tool_name,
            status=result.status,
            input_payload=request.model_dump(mode="json"),
            output_payload=result.model_dump(mode="json"),
            sources=[source.model_dump(mode="json") for source in result.sources],
        )
        db_session.add(tool_call)
        db_session.commit()
    return result
