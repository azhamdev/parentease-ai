from datetime import date
import unittest

from app.tools.vaccine_schedule import VACCINE_SCHEDULE_ID, calculate_vaccine_schedule


class VaccineScheduleTest(unittest.TestCase):
    def test_schedule_matches_buku_kia_2024_recommended_ages(self):
        reviewed_schedule = [
            ("HB0", "0-24 jam"),
            ("BCG", "1 bulan"),
            ("OPV1", "1 bulan"),
            ("DPT-HB-HIB1", "2 bulan"),
            ("OPV2", "2 bulan"),
            ("RV1", "2 bulan"),
            ("PCV1", "2 bulan"),
            ("DPT-HB-HIB2", "3 bulan"),
            ("OPV3", "3 bulan"),
            ("RV2", "3 bulan"),
            ("PCV2", "3 bulan"),
            ("DPT-HB-HIB3", "4 bulan"),
            ("OPV4", "4 bulan"),
            ("IPV1", "4 bulan"),
            ("RV3", "4 bulan"),
            ("MR1", "9 bulan"),
            ("IPV2", "9 bulan"),
            ("JE", "10 bulan"),
            ("PCV3", "12 bulan"),
            ("DPT-HB-HIB4", "18 bulan"),
            ("MR2", "18 bulan"),
        ]

        actual = [
            (rule.code, "0-24 jam" if rule.due_age_days == 0 else f"{rule.due_age_months} bulan")
            for rule in VACCINE_SCHEDULE_ID
        ]

        self.assertEqual(actual, reviewed_schedule)

    def test_needs_birth_date(self):
        result = calculate_vaccine_schedule({"birth_date": None})

        self.assertEqual(result.status, "needs_more_input")
        self.assertIn("birth_date", result.warnings[0])

    def test_newborn_due_for_hb0(self):
        result = calculate_vaccine_schedule(
            {
                "birth_date": "2026-05-08",
                "as_of_date": "2026-05-08",
                "completed_vaccines": [],
            }
        )

        self.assertEqual(result.age_days, 0)
        self.assertIn("HB0", [item.vaccine_code for item in result.due_now])
        self.assertEqual(result.due_now[0].due_age_label, "0-24 jam")

    def test_two_month_old_due_for_primary_series(self):
        result = calculate_vaccine_schedule(
            {
                "birth_date": "2026-03-08",
                "as_of_date": "2026-05-08",
                "completed_vaccines": [],
            }
        )

        due_codes = {item.vaccine_code for item in result.due_now}
        self.assertTrue({"DPT-HB-HIB1", "OPV2", "RV1", "PCV1"} <= due_codes)

    def test_completed_vaccine_is_not_due(self):
        result = calculate_vaccine_schedule(
            {
                "birth_date": "2026-03-08",
                "as_of_date": "2026-05-08",
                "completed_vaccines": [
                    {"vaccine_code": "DPT-HB-Hib 1", "date_given": "2026-05-08"}
                ],
            }
        )

        due_codes = {item.vaccine_code for item in result.due_now}
        completed_codes = {item.vaccine_code for item in result.completed}
        self.assertNotIn("DPT-HB-HIB1", due_codes)
        self.assertIn("DPT-HB-HIB1", completed_codes)

    def test_eighteen_month_old_due_for_boosters(self):
        result = calculate_vaccine_schedule(
            {
                "birth_date": "2024-11-08",
                "as_of_date": "2026-05-08",
                "completed_vaccines": [],
            }
        )

        due_codes = {item.vaccine_code for item in result.due_now}
        self.assertTrue({"DPT-HB-HIB4", "MR2"} <= due_codes)

    def test_regional_je_is_opt_in(self):
        base = {
            "birth_date": "2025-07-08",
            "as_of_date": "2026-05-08",
            "completed_vaccines": [],
        }

        without_regional = calculate_vaccine_schedule(base)
        with_regional = calculate_vaccine_schedule(
            {**base, "include_regional_vaccines": True}
        )

        self.assertNotIn("JE", {item.vaccine_code for item in without_regional.due_now})
        self.assertIn("JE", {item.vaccine_code for item in with_regional.due_now})

    def test_rejects_as_of_date_before_birth_date(self):
        result = calculate_vaccine_schedule(
            {
                "birth_date": date(2026, 5, 8),
                "as_of_date": date(2026, 5, 7),
            }
        )

        self.assertEqual(result.status, "error")


if __name__ == "__main__":
    unittest.main()
