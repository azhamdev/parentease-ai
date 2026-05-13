from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.models import ChatMessage, ChildProfile, ToolCall, VaccineRecord
from app.database import get_session
from app.services.agent.streaming import stream_chat_response
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


@router.post("/", response_class=StreamingResponse)
async def chat_endpoint_streaming(
    request: ChatRequest,
    session: Session = Depends(get_session),
    x_session_id: str | None = Header(None, alias="X-Session-ID")
):
    """
    Chat endpoint dengan streaming response (SSE).
    
    - **message**: Pesan dari user
    - **x_session_id**: Session ID dari header
    """
    # Save user message
    user_msg = ChatMessage(role="user", content=request.message, session_id=x_session_id)
    session.add(user_msg)
    session.commit()

    # Fetch child data
    child_data = None
    if x_session_id:
        stmt = select(ChildProfile).where(ChildProfile.session_id == x_session_id)
        profile = session.exec(stmt).first()
        if profile:
            child_data = profile.model_dump()
            vaccine_stmt = select(VaccineRecord).where(
                VaccineRecord.session_id == x_session_id
            )
            vaccine_records = session.exec(vaccine_stmt).all()
            child_data["completed_vaccines"] = [
                {
                    "vaccine_code": record.vaccine_code,
                    "date_given": record.date_given.isoformat() if record.date_given else None,
                }
                for record in vaccine_records
            ]

    # Streaming generator
    async def event_generator():
        full_response = ""

        def audit_tool_call(payload: dict) -> None:
            tool_call = ToolCall(
                session_id=x_session_id,
                tool_name=payload["tool_name"],
                status=payload["status"],
                input_payload=payload.get("input_payload", {}),
                output_payload=payload.get("output_payload", {}),
                sources=payload.get("sources", []),
            )
            session.add(tool_call)
            session.commit()

        try:
            async for token in stream_chat_response(
                user_message=request.message,
                child_context=child_data,
                tool_audit_callback=audit_tool_call,
            ):
                # Skip empty tokens
                if not token or token.strip() == "":
                    continue
                    
                full_response += token
                yield f"data: {token}\n\n"
                
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            # Save AI response if not empty
            if full_response and full_response.strip():
                ai_msg = ChatMessage(
                    role="assistant",
                    content=full_response,
                    session_id=x_session_id
                )
                session.add(ai_msg)
                session.commit()
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
