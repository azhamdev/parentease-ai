from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field, ValidationError

from app.tools.red_flags import detect_red_flags
from app.tools.schemas import VaccineScheduleRequest
from app.tools.verify_url import verify_url_source
from app.tools.vaccine_schedule import calculate_vaccine_schedule


app = FastAPI(title="ParentEase MCP Tool Server")

JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602


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
            code=JSONRPC_INVALID_REQUEST,
            message="Invalid JSON-RPC version.",
        )

    if payload.method == "tools/list":
        return _jsonrpc_result(
            payload.id,
            {
                "tools": [
                    _vaccine_schedule_tool_schema(),
                    _red_flags_tool_schema(),
                    _verify_url_tool_schema(),
                ]
            },
        )

    if payload.method == "tools/call":
        return _handle_tool_call(payload)

    return _jsonrpc_error(
        payload.id,
        code=JSONRPC_METHOD_NOT_FOUND,
        message=f"Method '{payload.method}' is not supported.",
    )


def _handle_tool_call(payload: JsonRpcRequest) -> dict:
    tool_name = payload.params.get("name")
    arguments = payload.params.get("arguments") or {}

    if not isinstance(tool_name, str) or not tool_name:
        return _jsonrpc_error(
            payload.id,
            code=JSONRPC_INVALID_PARAMS,
            message="Tool name is required.",
        )

    if not isinstance(arguments, dict):
        return _jsonrpc_error(
            payload.id,
            code=JSONRPC_INVALID_PARAMS,
            message="Tool arguments must be an object.",
        )

    if tool_name == "calculate_vaccine_schedule":
        return _handle_vaccine_schedule_tool(payload.id, arguments)

    if tool_name == "detect_red_flags":
        return _handle_red_flags_tool(payload.id, arguments)

    if tool_name == "verify_url_source":
        return _handle_verify_url_tool(payload.id, arguments)

    return _jsonrpc_error(
        payload.id,
        code=JSONRPC_METHOD_NOT_FOUND,
        message=f"Tool '{tool_name}' is not supported.",
    )


def _handle_vaccine_schedule_tool(
    request_id: str | int | None,
    arguments: dict[str, Any],
) -> dict:
    try:
        request = VaccineScheduleRequest.model_validate(
            _normalize_vaccine_arguments(arguments)
        )
        result = calculate_vaccine_schedule(request)
    except ValidationError as exc:
        return _jsonrpc_error(
            request_id,
            code=JSONRPC_INVALID_PARAMS,
            message="Invalid tool arguments.",
            data=exc.errors(),
        )

    return _jsonrpc_result(request_id, result.model_dump(mode="json"))


def _handle_red_flags_tool(
    request_id: str | int | None,
    arguments: dict[str, Any],
) -> dict:
    message = arguments.get("message")
    child_context = arguments.get("child_context")

    if not isinstance(message, str) or not message.strip():
        return _jsonrpc_error(
            request_id,
            code=JSONRPC_INVALID_PARAMS,
            message="Argument 'message' is required.",
        )

    if child_context is not None and not isinstance(child_context, dict):
        return _jsonrpc_error(
            request_id,
            code=JSONRPC_INVALID_PARAMS,
            message="Argument 'child_context' must be an object.",
        )

    result = detect_red_flags(message, child_context)
    sources = []
    if result.is_red_flag:
        sources.append(
            {
                "type": "red_flag_rule",
                "source_id": "PARENTEASE_RED_FLAG_RULES",
                "title": "ParentEase red flag triage rules",
            }
        )

    return _jsonrpc_result(
        request_id,
        {
            "tool_name": "detect_red_flags",
            "status": "ok",
            "is_red_flag": result.is_red_flag,
            "reasons": result.reasons,
            "action": result.action,
            "sources": sources,
        },
    )


def _handle_verify_url_tool(
    request_id: str | int | None,
    arguments: dict[str, Any],
) -> dict:
    url = arguments.get("url")

    if not isinstance(url, str) or not url.strip():
        return _jsonrpc_error(
            request_id,
            code=JSONRPC_INVALID_PARAMS,
            message="Argument 'url' is required.",
        )

    if not url.startswith(("http://", "https://")):
        return _jsonrpc_error(
            request_id,
            code=JSONRPC_INVALID_PARAMS,
            message="Argument 'url' must start with http:// or https://.",
        )

    result = verify_url_source(url)
    return _jsonrpc_result(
        request_id,
        {
            "tool_name": "verify_url_source",
            "status": result.verdict,
            "url": result.url,
            "verdict": result.verdict,
            "web_summary": result.web_summary,
            "matched_rag_excerpts": result.matched_rag_excerpts,
            "sources": result.rag_sources,
            "explanation": result.explanation,
        },
    )


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


def _red_flags_tool_schema() -> dict:
    return {
        "name": "detect_red_flags",
        "description": "Deteksi tanda bahaya medis pada pesan user dan konteks anak.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Pesan user yang perlu dicek tanda bahaya.",
                },
                "child_context": {
                    "type": "object",
                    "description": "Konteks anak opsional, misalnya age_months atau birth_date.",
                    "properties": {
                        "age_months": {"type": "integer"},
                        "birth_date": {"type": "string"},
                    },
                },
            },
            "required": ["message"],
        },
    }


def _verify_url_tool_schema() -> dict:
    return {
        "name": "verify_url_source",
        "description": "Verifikasi apakah artikel URL konsisten dengan knowledge base pediatrik lokal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL artikel yang dimulai dengan http:// atau https://.",
                }
            },
            "required": ["url"],
        },
    }
