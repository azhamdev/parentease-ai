import unittest
import uuid

from sqlmodel import Session, select

from app.database import engine
from app.models import VaccineRecord
from app.tasks.upload_tasks import _persist_extraction_result
from app.tools.pdf_growth_extract import (
    GrowthExtractionResult,
    GrowthMeasurement,
    VaccineExtractionRecord,
    extract_vaccine_records_from_text,
)


class PdfExtractionTest(unittest.TestCase):
    def test_extracts_dated_vaccine_records_from_ocr_text(self):
        text = """
        HB0: 2026-03-08 di Klinik Sehat
        BCG: 08/04/2026 di Puskesmas Melati
        OPV1: 08-04-2026 di Puskesmas Melati
        DPT-HB-Hib 1: 2026-05-08 di Puskesmas Melati
        Halaman jadwal kosong: PCV 2
        """

        records = extract_vaccine_records_from_text(text)
        by_code = {record.vaccine_code: record.date_given for record in records}

        self.assertEqual(by_code["HB0"], "2026-03-08")
        self.assertEqual(by_code["BCG"], "2026-04-08")
        self.assertEqual(by_code["OPV1"], "2026-04-08")
        self.assertEqual(by_code["DPT-HB-HIB1"], "2026-05-08")
        self.assertNotIn("PCV2", by_code)

    def test_persists_vaccine_records_from_async_upload_result(self):
        session_id = f"pdf-extraction-vaccine-session-{uuid.uuid4()}"
        result = GrowthExtractionResult(
            success=True,
            filename="sample.pdf",
            raw_ocr_text="sample",
            measurements=[
                GrowthMeasurement(
                    measurement_date="2026-05-08",
                    age_months=2,
                    weight_kg=5.8,
                    height_cm=59,
                )
            ],
            vaccinations=[
                VaccineExtractionRecord(
                    vaccine_code="BCG",
                    date_given="2026-04-08",
                    notes="BCG: 2026-04-08 di Puskesmas Melati",
                )
            ],
        )

        saved_growth, saved_vaccines = _persist_extraction_result(
            session_id=session_id,
            filename="sample.pdf",
            file_size=123,
            result=result,
        )

        self.assertEqual(saved_growth, 1)
        self.assertEqual(saved_vaccines, 1)
        with Session(engine) as db:
            vaccine = db.exec(
                select(VaccineRecord).where(
                    VaccineRecord.session_id == session_id,
                    VaccineRecord.vaccine_code == "BCG",
                )
            ).first()

        self.assertIsNotNone(vaccine)
        assert vaccine is not None
        self.assertEqual(vaccine.date_given.isoformat(), "2026-04-08")


if __name__ == "__main__":
    unittest.main()
