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

    def test_detects_breathing_distress(self):
        result = detect_red_flags(
            "Napas anak saya cepat dan ada tarikan dinding dada",
            {"age_months": 10},
        )

        self.assertTrue(result.is_red_flag)
        self.assertTrue(any("napas" in reason.lower() for reason in result.reasons))

    def test_detects_dehydration_signs(self):
        result = detect_red_flags(
            "Bayi tidak mau menyusu dan pipis sedikit sekali",
            {"age_months": 4},
        )

        self.assertTrue(result.is_red_flag)
        self.assertTrue(any("dehidrasi" in reason.lower() for reason in result.reasons))

    def test_detects_green_vomit(self):
        result = detect_red_flags("Anak muntah hijau sejak tadi", {"age_months": 12})

        self.assertTrue(result.is_red_flag)
        self.assertTrue(any("Muntah hijau" in reason for reason in result.reasons))

    def test_detects_high_fever_under_six_months(self):
        result = detect_red_flags("Bayi panas 39 derajat", {"age_months": 4})

        self.assertTrue(result.is_red_flag)
        self.assertTrue(any("di bawah 6 bulan" in reason for reason in result.reasons))

    def test_non_urgent_question_is_not_red_flag(self):
        result = detect_red_flags("Kapan mulai MPASI?", {"age_months": 6})

        self.assertFalse(result.is_red_flag)
        self.assertEqual(result.reasons, [])


if __name__ == "__main__":
    unittest.main()
