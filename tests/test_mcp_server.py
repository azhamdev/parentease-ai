import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.mcp_server import app
from app.tools.medical_guidelines import MedicalGuidelinesResult


class McpServerTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertIn("calculate_vaccine_schedule", response.json()["tools"])

    def test_tools_list(self):
        response = self.client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("result", data)
        tool_names = {tool["name"] for tool in data["result"]["tools"]}
        self.assertIn("calculate_vaccine_schedule", tool_names)
        self.assertIn("detect_red_flags", tool_names)
        self.assertIn("search_medical_guidelines", tool_names)
        self.assertIn("verify_url_source", tool_names)

    def test_calculate_vaccine_schedule_tool_call(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tools/call",
                "params": {
                    "name": "calculate_vaccine_schedule",
                    "arguments": {
                        "birth_date": "2026-03-08",
                        "as_of_date": "2026-05-08",
                        "completed_vaccines": [],
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["tool_name"], "calculate_vaccine_schedule")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["age_months"], 2)

    def test_calculate_vaccine_schedule_accepts_string_completed_vaccines(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "3",
                "method": "tools/call",
                "params": {
                    "name": "calculate_vaccine_schedule",
                    "arguments": {
                        "birth_date": "2026-03-08",
                        "as_of_date": "2026-05-08",
                        "completed_vaccines": ["DPT-HB-Hib 1"],
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        completed_codes = {item["vaccine_code"] for item in result["completed"]}
        self.assertIn("DPT-HB-HIB1", completed_codes)

    def test_unknown_tool_returns_jsonrpc_error(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "4",
                "method": "tools/call",
                "params": {"name": "unknown_tool", "arguments": {}},
            },
        )

        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(error["code"], -32601)
        self.assertEqual(error["data"]["type"], "tool_not_found")
        self.assertEqual(error["data"]["tool_name"], "unknown_tool")
        self.assertFalse(error["data"]["retryable"])

    def test_unknown_method_returns_jsonrpc_error(self):
        response = self.client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "id": "5", "method": "unknown/method"},
        )

        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(error["code"], -32601)
        self.assertEqual(error["data"]["type"], "method_not_found")

    def test_invalid_tool_arguments_return_jsonrpc_error(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "6",
                "method": "tools/call",
                "params": {
                    "name": "calculate_vaccine_schedule",
                    "arguments": {"birth_date": "not-a-date"},
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(error["code"], -32602)
        self.assertEqual(error["data"]["type"], "validation_error")
        self.assertEqual(error["data"]["tool_name"], "calculate_vaccine_schedule")

    def test_missing_tool_name_returns_jsonrpc_error(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "7",
                "method": "tools/call",
                "params": {"arguments": {}},
            },
        )

        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(error["code"], -32602)
        self.assertEqual(error["data"]["type"], "invalid_params")

    def test_detect_red_flags_tool_call(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "8",
                "method": "tools/call",
                "params": {
                    "name": "detect_red_flags",
                    "arguments": {
                        "message": "Bayi saya demam 39 dan usianya 2 bulan",
                        "child_context": {"age_months": 2},
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["tool_name"], "detect_red_flags")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["is_red_flag"])
        self.assertTrue(result["reasons"])
        self.assertEqual(result["sources"][0]["type"], "red_flag_rule")

    def test_detect_red_flags_requires_message(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "9",
                "method": "tools/call",
                "params": {
                    "name": "detect_red_flags",
                    "arguments": {"child_context": {"age_months": 2}},
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(error["code"], -32602)
        self.assertEqual(error["data"]["type"], "validation_error")
        self.assertEqual(error["data"]["tool_name"], "detect_red_flags")

    def test_search_medical_guidelines_tool_call(self):
        with patch(
            "app.mcp_server.search_medical_guidelines",
            return_value=MedicalGuidelinesResult(
                status="ok",
                query="mpasi",
                content="MPASI dimulai saat bayi berusia 6 bulan.",
                sources=[
                    {
                        "type": "rag_document",
                        "title": "Buku Kia 2024",
                        "page": 88,
                    }
                ],
            ),
        ):
            response = self.client.post(
                "/rpc",
                json={
                    "jsonrpc": "2.0",
                    "id": "10",
                    "method": "tools/call",
                    "params": {
                        "name": "search_medical_guidelines",
                        "arguments": {"query": "kapan mulai mpasi"},
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["tool_name"], "search_medical_guidelines")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sources"][0]["type"], "rag_document")

    def test_search_medical_guidelines_requires_query(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "11",
                "method": "tools/call",
                "params": {"name": "search_medical_guidelines", "arguments": {}},
            },
        )

        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(error["code"], -32602)
        self.assertEqual(error["data"]["type"], "validation_error")
        self.assertEqual(error["data"]["tool_name"], "search_medical_guidelines")

    @patch.dict("os.environ", {"TAVILY_API_KEY": ""})
    def test_verify_url_source_tool_call_without_api_key_returns_no_match(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "12",
                "method": "tools/call",
                "params": {
                    "name": "verify_url_source",
                    "arguments": {"url": "https://example.com/article"},
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["tool_name"], "verify_url_source")
        self.assertEqual(result["status"], "no_match")
        self.assertEqual(result["url"], "https://example.com/article")

    def test_verify_url_source_requires_url(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "13",
                "method": "tools/call",
                "params": {"name": "verify_url_source", "arguments": {}},
            },
        )

        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(error["code"], -32602)
        self.assertEqual(error["data"]["type"], "validation_error")
        self.assertEqual(error["data"]["tool_name"], "verify_url_source")

    def test_verify_url_source_rejects_non_http_url(self):
        response = self.client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "id": "14",
                "method": "tools/call",
                "params": {
                    "name": "verify_url_source",
                    "arguments": {"url": "example.com/article"},
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(error["code"], -32602)
        self.assertEqual(error["data"]["type"], "validation_error")
        self.assertEqual(error["data"]["tool_name"], "verify_url_source")

    def test_tool_execution_error_is_structured(self):
        with patch(
            "app.mcp_server.search_medical_guidelines",
            side_effect=RuntimeError("chroma unavailable"),
        ):
            response = self.client.post(
                "/rpc",
                json={
                    "jsonrpc": "2.0",
                    "id": "15",
                    "method": "tools/call",
                    "params": {
                        "name": "search_medical_guidelines",
                        "arguments": {"query": "mpasi"},
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        error = response.json()["error"]
        self.assertEqual(error["code"], -32603)
        self.assertEqual(error["data"]["type"], "tool_execution_error")
        self.assertEqual(error["data"]["tool_name"], "search_medical_guidelines")
        self.assertTrue(error["data"]["retryable"])


if __name__ == "__main__":
    unittest.main()
