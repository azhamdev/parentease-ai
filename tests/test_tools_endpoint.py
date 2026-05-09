import unittest

from fastapi.testclient import TestClient

from app.main import app


class ToolsEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_vaccine_schedule_endpoint_returns_due_vaccines(self):
        response = self.client.post(
            "/tools/vaccine-schedule",
            json={
                "birth_date": "2026-03-08",
                "as_of_date": "2026-05-08",
                "completed_vaccines": [],
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["tool_name"], "calculate_vaccine_schedule")
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["age_months"], 2)
        self.assertTrue(
            {"DPT-HB-HIB1", "OPV2", "RV1", "PCV1"}
            <= {item["vaccine_code"] for item in data["due_now"]}
        )

    def test_vaccine_schedule_endpoint_handles_missing_birth_date(self):
        response = self.client.post(
            "/tools/vaccine-schedule",
            json={"birth_date": None},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "needs_more_input")


if __name__ == "__main__":
    unittest.main()
