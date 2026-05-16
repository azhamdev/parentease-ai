import logging
import os
import uuid
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class MCPClientError(Exception):
    """Structured error raised when MCP communication or JSON-RPC fails."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str = "mcp_error",
        tool_name: str | None = None,
        retryable: bool = False,
        details: Any | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.tool_name = tool_name
        self.retryable = retryable
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.error_type,
            "message": self.message,
            "tool_name": self.tool_name,
            "retryable": self.retryable,
            "details": self.details,
        }


class MCPClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._connected = False

    async def connect(self) -> None:
        if self._connected:
            return
        try:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
            response = await self._client.get("/health", timeout=5.0)
            response.raise_for_status()
            self._connected = True
            logger.info(f"✅ Connected to MCP server at {self.base_url}")
        except httpx.TimeoutException as exc:
            logger.error(f"❌ MCP Connection timed out: {exc}")
            self._connected = False
            raise MCPClientError(
                "MCP server health check timed out.",
                error_type="mcp_timeout",
                retryable=True,
                details={"base_url": self.base_url},
            ) from exc
        except httpx.HTTPError as exc:
            logger.error(f"❌ MCP Connection failed: {exc}")
            self._connected = False
            raise MCPClientError(
                "MCP server is unavailable.",
                error_type="mcp_connection_error",
                retryable=True,
                details={"base_url": self.base_url, "error": str(exc)},
            ) from exc

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            self._connected = False
            logger.info("🔌 MCP Client disconnected")

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool via JSON-RPC."""
        if not self._connected:
            await self.connect()

        if self._client is None:
            raise MCPClientError(
                "MCP HTTP client is not initialized.",
                error_type="mcp_connection_error",
                tool_name=tool_name,
                retryable=True,
                details={"base_url": self.base_url},
            )

        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        try:
            response = await self._client.post("/rpc", json=payload)
            response.raise_for_status()
            result = response.json()
        except httpx.TimeoutException as exc:
            raise MCPClientError(
                f"MCP tool '{tool_name}' timed out.",
                error_type="mcp_timeout",
                tool_name=tool_name,
                retryable=True,
                details={"base_url": self.base_url},
            ) from exc
        except httpx.HTTPError as exc:
            self._connected = False
            raise MCPClientError(
                f"MCP tool '{tool_name}' request failed.",
                error_type="mcp_http_error",
                tool_name=tool_name,
                retryable=True,
                details={"base_url": self.base_url, "error": str(exc)},
            ) from exc
        except ValueError as exc:
            raise MCPClientError(
                f"MCP tool '{tool_name}' returned invalid JSON.",
                error_type="mcp_invalid_response",
                tool_name=tool_name,
                retryable=False,
                details={"base_url": self.base_url},
            ) from exc

        if "error" in result:
            error = result["error"]
            data = error.get("data") if isinstance(error, dict) else None
            message = error.get("message", "Tool execution failed")
            error_type = "mcp_jsonrpc_error"
            retryable = False
            if isinstance(data, dict):
                error_type = data.get("type", error_type)
                retryable = bool(data.get("retryable", False))
            raise MCPClientError(
                message,
                error_type=error_type,
                tool_name=tool_name,
                retryable=retryable,
                details=data,
            )

        return result.get("result", {})

# --- Global Instance & Public Functions ---
_mcp_client: Optional[MCPClient] = None

async def get_mcp_client() -> MCPClient:
    global _mcp_client
    if _mcp_client is None:
        url = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
        timeout = float(os.getenv("MCP_TIMEOUT_SECONDS", "30"))
        _mcp_client = MCPClient(base_url=url, timeout=timeout)
    return _mcp_client

async def disconnect_mcp_client() -> None:
    """Fungsi publik untuk memutus koneksi saat app shutdown."""
    global _mcp_client
    if _mcp_client:
        await _mcp_client.disconnect()
        _mcp_client = None
