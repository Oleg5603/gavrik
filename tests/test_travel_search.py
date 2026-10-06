import json
import tempfile
import unittest
from pathlib import Path

from travel_search import build_travel_search_context


class TravelSearchContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name) / "travel.json"
        self.config.write_text(json.dumps({
            "origin": "Москва",
            "destination": "Благовещенск",
            "departure_month": "май 2027",
            "passengers": 2,
            "stay_days": 10,
            "flight_total_cap_rub": 60000,
            "tour_total_cap_rub": None,
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_injects_exact_trip_and_full_party_price_rules(self):
        result = build_travel_search_context("Найди авиабилеты и туры", self.config)
        self.assertIn("май 2027", result)
        self.assertIn("дата обратного вылета на 10 дней позже", result)
        self.assertIn("строго ниже 60000 ₽", result)
        self.assertIn("не включай в список подходящих билетов", result)
        self.assertIn("Лимит для пакетных туров: не задан", result)

    def test_does_not_inject_trip_profile_into_unrelated_questions(self):
        self.assertEqual("", build_travel_search_context("Посмотри погоду", self.config))


if __name__ == "__main__":
    unittest.main()
