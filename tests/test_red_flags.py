from datetime import date
import unittest

from app.tools.red_flags import detect_red_flags


class RedFlagDetectorTest(unittest.TestCase):
    def test_detects_fever_in_baby_under_three_months(self):
        result = detect_red_flags(
            "Bayi saya demam 38,5",
            {"birth_date": date(2026, 4, 1)},
        )

        self.assertTrue(result.is_red_flag)
        self.assertTrue(any("di bawah 3 bulan" in reason for reason in result.reasons))

    def test_detects_seizure(self):
        result = detect_red_flags("Anak saya kejang tadi pagi", {"age_months": 8})

        self.assertTrue(result.is_red_flag)
        self.assertTrue(any("Kejang" in reason for reason in result.reasons))

    def test_non_urgent_question_is_not_red_flag(self):
        result = detect_red_flags("Kapan mulai MPASI?", {"age_months": 6})

        self.assertFalse(result.is_red_flag)
        self.assertEqual(result.reasons, [])


if __name__ == "__main__":
    unittest.main()
