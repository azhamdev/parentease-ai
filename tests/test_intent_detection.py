import unittest

from app.services.agent.intent_classifier import (
    classify_intent,
    should_calculate_vaccine_schedule,
    should_include_growth_data,
    should_retrieve_guidelines,
)


class IntentDetectionTest(unittest.TestCase):
    def test_detects_implicit_vaccine_intent(self):
        message = "Anak saya perlu suntikan bulan ini apa?"
        result = classify_intent(message)

        self.assertTrue(result.needs_vaccine_schedule)
        self.assertTrue(should_calculate_vaccine_schedule(message))
        self.assertGreaterEqual(result.vaccine.score, 3)
        self.assertTrue(any("suntikan" in reason for reason in result.vaccine.reasons))

    def test_detects_vaccine_drop_intent(self):
        self.assertTrue(should_calculate_vaccine_schedule("Polio tetes berikutnya kapan?"))

    def test_detects_implicit_drop_vaccine_intent(self):
        self.assertTrue(should_calculate_vaccine_schedule("Anakku perlu yang tetes kapan?"))

    def test_detects_implicit_monthly_injection_intent(self):
        self.assertTrue(should_calculate_vaccine_schedule("Suntikan bulan ini apa?"))

    def test_detects_immunization_without_explicit_vaccine_word(self):
        self.assertTrue(
            should_calculate_vaccine_schedule("Bulan ini anakku harus disuntik apa?")
        )

    def test_detects_mpasi_guideline_intent(self):
        self.assertTrue(should_retrieve_guidelines("Umur berapa bayi boleh makan?"))

    def test_detects_breastfeeding_position_intent(self):
        self.assertTrue(should_retrieve_guidelines("Posisi menyusui yang benar gimana?"))

    def test_non_medical_question_does_not_trigger_vaccine_tool(self):
        self.assertFalse(should_calculate_vaccine_schedule("Apa itu JavaScript?"))

    def test_child_word_alone_does_not_trigger_guideline_retrieval(self):
        self.assertFalse(should_retrieve_guidelines("Anak saya suka main bola"))

    def test_detects_growth_context(self):
        self.assertTrue(should_include_growth_data("Berat anak saya normal nggak?"))


if __name__ == "__main__":
    unittest.main()
