import unittest

import httpx

from app.services.agent.mcp_client import MCPClient, MCPClientError


class McpClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_call_tool_raises_structured_jsonrpc_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "error": {
                        "code": -32602,
                        "message": "Invalid tool arguments.",
                        "data": {
                            "type": "validation_error",
                            "tool_name": "calculate_vaccine_schedule",
                            "retryable": False,
                            "details": {"field": "birth_date"},
                        },
                    },
                },
            )

        client = MCPClient("http://mcp.test")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://mcp.test",
        )
        client._connected = True

        with self.assertRaises(MCPClientError) as ctx:
            await client.call_tool("calculate_vaccine_schedule", {})

        self.assertEqual(ctx.exception.error_type, "validation_error")
        self.assertEqual(ctx.exception.tool_name, "calculate_vaccine_schedule")
        self.assertFalse(ctx.exception.retryable)
        await client.disconnect()

    async def test_call_tool_timeout_is_retryable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout")

        client = MCPClient("http://mcp.test")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://mcp.test",
        )
        client._connected = True

        with self.assertRaises(MCPClientError) as ctx:
            await client.call_tool("search_medical_guidelines", {"query": "mpasi"})

        self.assertEqual(ctx.exception.error_type, "mcp_timeout")
        self.assertEqual(ctx.exception.tool_name, "search_medical_guidelines")
        self.assertTrue(ctx.exception.retryable)
        await client.disconnect()


if __name__ == "__main__":
    unittest.main()
