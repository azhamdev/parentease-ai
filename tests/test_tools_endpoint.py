import unittest

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import engine
from app.main import app
from app.models import ToolCall


class ToolsEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_vaccine_schedule_endpoint_returns_due_vaccines(self):
        response = self.client.post(
            "/api/v1/tools/vaccine-schedule",
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
            "/api/v1/tools/vaccine-schedule",
            json={"birth_date": None},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "needs_more_input")

    def test_vaccine_schedule_endpoint_audits_tool_call_with_session_id(self):
        session_id = "test-tool-audit-session"
        response = self.client.post(
            "/api/v1/tools/vaccine-schedule",
            json={
                "session_id": session_id,
                "birth_date": "2026-03-08",
                "as_of_date": "2026-05-08",
                "completed_vaccines": [],
            },
        )

        self.assertEqual(response.status_code, 200)
        with Session(engine) as db_session:
            stmt = (
                select(ToolCall)
                .where(ToolCall.session_id == session_id)
                .order_by(ToolCall.created_at.desc())
            )
            tool_call = db_session.exec(stmt).first()

        self.assertIsNotNone(tool_call)
        assert tool_call is not None
        self.assertEqual(tool_call.tool_name, "calculate_vaccine_schedule")
        self.assertEqual(tool_call.status, "ok")
        self.assertEqual(tool_call.input_payload["birth_date"], "2026-03-08")

    def test_vaccine_record_lifecycle(self):
        profile_response = self.client.post(
            "/api/v1/profiles/",
            json={
                "tanggal_lahir": "2026-03-08",
                "gender": "P",
                "nama_anak": "Aira",
            },
        )
        self.assertEqual(profile_response.status_code, 200)
        session_id = profile_response.json()["session_id"]

        create_response = self.client.post(
            f"/api/v1/profiles/{session_id}/vaccines",
            json={
                "vaccine_code": "BCG",
                "date_given": "08/04/2026",
                "notes": "Diberikan di puskesmas",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        record = create_response.json()
        self.assertEqual(record["vaccine_code"], "BCG")
        self.assertEqual(record["date_given"], "2026-04-08")

        list_response = self.client.get(f"/api/v1/profiles/{session_id}/vaccines")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        schedule_response = self.client.post(
            "/api/v1/tools/vaccine-schedule",
            json={
                "birth_date": "2026-03-08",
                "as_of_date": "2026-04-08",
                "completed_vaccines": [
                    {
                        "vaccine_code": record["vaccine_code"],
                        "date_given": record["date_given"],
                    }
                ],
            },
        )
        completed_codes = {
            item["vaccine_code"] for item in schedule_response.json()["completed"]
        }
        self.assertIn("BCG", completed_codes)

        delete_response = self.client.delete(
            f"/api/v1/profiles/{session_id}/vaccines/{record['id']}"
        )
        self.assertEqual(delete_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
