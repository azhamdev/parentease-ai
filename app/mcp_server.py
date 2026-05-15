from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field, ValidationError

from app.tools.schemas import VaccineScheduleRequest
from app.tools.vaccine_schedule import calculate_vaccine_schedule


app = FastAPI(title="ParentEase MCP Tool Server")


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


def _jsonrpc_result(request_id: str | int | None, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(
    request_id: str | int | None,
    *,
    code: int,
    message: str,
    data: Any | None = None,
) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "parentease-mcp-server"}


@app.post("/rpc")
def rpc(payload: JsonRpcRequest) -> dict:
    if payload.jsonrpc != "2.0":
        return _jsonrpc_error(
            payload.id,
            code=-32600,
            message="Invalid JSON-RPC version.",
        )

    if payload.method == "tools/list":
        return _jsonrpc_result(payload.id, {"tools": [_vaccine_schedule_tool_schema()]})

    if payload.method == "tools/call":
        return _handle_tool_call(payload)

    return _jsonrpc_error(
        payload.id,
        code=-32601,
        message=f"Method '{payload.method}' is not supported.",
    )


def _handle_tool_call(payload: JsonRpcRequest) -> dict:
    tool_name = payload.params.get("name")
    arguments = payload.params.get("arguments") or {}

    if tool_name != "calculate_vaccine_schedule":
        return _jsonrpc_error(
            payload.id,
            code=-32601,
            message=f"Tool '{tool_name}' is not supported.",
        )

    try:
        request = VaccineScheduleRequest.model_validate(
            _normalize_vaccine_arguments(arguments)
        )
        result = calculate_vaccine_schedule(request)
    except ValidationError as exc:
        return _jsonrpc_error(
            payload.id,
            code=-32602,
            message="Invalid tool arguments.",
            data=exc.errors(),
        )

    return _jsonrpc_result(payload.id, result.model_dump(mode="json"))


def _normalize_vaccine_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(arguments)
    completed = normalized.get("completed_vaccines")
    if completed and all(isinstance(item, str) for item in completed):
        normalized["completed_vaccines"] = [
            {"vaccine_code": item} for item in completed
        ]
    return normalized


def _vaccine_schedule_tool_schema() -> dict:
    return {
        "name": "calculate_vaccine_schedule",
        "description": "Hitung jadwal vaksin anak Indonesia berdasarkan tanggal lahir dan riwayat vaksin.",
        "input_schema": {
            "type": "object",
            "properties": {
                "birth_date": {
                    "type": "string",
                    "description": "Tanggal lahir anak dalam format YYYY-MM-DD.",
                },
                "as_of_date": {
                    "type": "string",
                    "description": "Tanggal acuan perhitungan dalam format YYYY-MM-DD.",
                },
                "country": {
                    "type": "string",
                    "default": "ID",
                },
                "completed_vaccines": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "vaccine_code": {"type": "string"},
                                    "date_given": {"type": "string"},
                                },
                                "required": ["vaccine_code"],
                            },
                        ]
                    },
                },
                "include_regional_vaccines": {
                    "type": "boolean",
                    "default": False,
                },
            },
            "required": ["birth_date"],
        },
    }
