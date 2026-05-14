import json
import logging
import uuid
from typing import Any, Optional
import httpx

logger = logging.getLogger(__name__)

class MCPClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._connected = False

    async def connect(self) -> None:
        if self._connected: return
        try:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
            # Opsional: Health check
            await self._client.get("/health", timeout=5.0)
            self._connected = True
            logger.info(f"✅ Connected to MCP server at {self.base_url}")
        except Exception as e:
            logger.error(f"❌ MCP Connection failed: {e}")
            self._connected = False

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            self._connected = False
            logger.info("🔌 MCP Client disconnected")

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool via JSON-RPC."""
        if not self._connected: await self.connect()
        
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }
        
        response = await self._client.post("/rpc", json=payload)
        response.raise_for_status()
        result = response.json()
        
        if "error" in result:
            raise Exception(result["error"].get("message", "Tool execution failed"))
            
        return result.get("result", {})

# --- Global Instance & Public Functions ---
_mcp_client: Optional[MCPClient] = None

async def get_mcp_client() -> MCPClient:
    global _mcp_client
    if _mcp_client is None:
        # Gunakan URL dari environment variable atau default
        import os
        url = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
        _mcp_client = MCPClient(base_url=url)
    return _mcp_client

async def disconnect_mcp_client() -> None:
    """Fungsi publik untuk memutus koneksi saat app shutdown."""
    global _mcp_client
    if _mcp_client:
        await _mcp_client.disconnect()
        _mcp_client = None