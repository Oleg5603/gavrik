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
            "group_total_cap_rub": 60000,
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_applies_one_total_cap_to_both_flights_and_tours(self):
        result = build_travel_search_context("Найди авиабилеты и туры", self.config)
        self.assertIn("май 2027", result)
        self.assertIn("дата обратного вылета на 10 дней позже", result)
        self.assertIn("общую цену для всех 2 пассажиров не выше 60000 ₽", result)
        self.assertIn("бюджет включает поездку туда и обратно", result)
        self.assertIn("для тура — весь пакет на двоих", result)
        self.assertIn("не включай в список подходящих вариантов", result)

    def test_does_not_inject_trip_profile_into_unrelated_questions(self):
        self.assertEqual("", build_travel_search_context("Посмотри погоду", self.config))


if __name__ == "__main__":
    unittest.main()
