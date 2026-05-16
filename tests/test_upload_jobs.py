import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import engine
from app.main import app
from app.models import UploadJob


class FakeAsyncResult:
    id = "fake-celery-task-id"


class UploadJobsTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.v1.endpoints.chat.process_growth_pdf_upload.delay")
    def test_create_upload_pdf_job_enqueues_celery_task(self, delay_mock):
        delay_mock.return_value = FakeAsyncResult()

        response = self.client.post(
            "/api/v1/chat/upload-pdf/jobs",
            headers={"X-Session-ID": "upload-job-session"},
            files={"file": ("growth.pdf", b"%PDF-1.4\nfake", "application/pdf")},
            data={"message": "Tolong proses data tumbuh kembang ini"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["celery_task_id"], "fake-celery-task-id")
        self.assertTrue(data["job_id"])
        delay_mock.assert_called_once()

        with Session(engine) as db:
            job = db.exec(
                select(UploadJob).where(UploadJob.job_id == data["job_id"])
            ).first()

        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(job.session_id, "upload-job-session")
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.celery_task_id, "fake-celery-task-id")

    @patch("app.api.v1.endpoints.chat.process_growth_pdf_upload.delay")
    def test_get_upload_pdf_job_status(self, delay_mock):
        delay_mock.return_value = FakeAsyncResult()

        create_response = self.client.post(
            "/api/v1/chat/upload-pdf/jobs",
            headers={"X-Session-ID": "upload-job-status-session"},
            files={"file": ("growth.pdf", b"%PDF-1.4\nfake", "application/pdf")},
        )
        self.assertEqual(create_response.status_code, 200)
        job_id = create_response.json()["job_id"]

        status_response = self.client.get(
            f"/api/v1/chat/upload-pdf/jobs/{job_id}",
            headers={"X-Session-ID": "upload-job-status-session"},
        )

        self.assertEqual(status_response.status_code, 200)
        data = status_response.json()
        self.assertEqual(data["job_id"], job_id)
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["celery_task_id"], "fake-celery-task-id")


if __name__ == "__main__":
    unittest.main()
