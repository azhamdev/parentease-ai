import unittest

from fastapi.testclient import TestClient

from app.mcp_server import app


class McpServerTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

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
        self.assertEqual(response.json()["error"]["code"], -32601)

    def test_unknown_method_returns_jsonrpc_error(self):
        response = self.client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "id": "5", "method": "unknown/method"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"]["code"], -32601)

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
        self.assertEqual(response.json()["error"]["code"], -32602)

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
        self.assertEqual(response.json()["error"]["code"], -32602)

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
        self.assertEqual(response.json()["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
