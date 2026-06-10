import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from generate_and_post import JST, crosses, sign_of, slot_for


class AstrologyHelperTests(unittest.TestCase):
    def test_sign_of_longitude_boundaries(self):
        self.assertEqual(sign_of(0), "牡羊座")
        self.assertEqual(sign_of(29.999), "牡羊座")
        self.assertEqual(sign_of(30), "牡牛座")
        self.assertEqual(sign_of(359.999), "魚座")
        self.assertEqual(sign_of(360), "牡羊座")
        self.assertEqual(sign_of(-1), "魚座")

    def test_crosses_handles_zero_degree_wrap(self):
        self.assertTrue(crosses(350, 10, 0))
        self.assertFalse(crosses(350, 10, 180))
        self.assertFalse(crosses(10, 350, 0))
        self.assertTrue(crosses(10, 350, 180))

    def test_slot_for_midnight_window(self):
        self.assertEqual(slot_for(datetime(2026, 6, 10, 0, 0, tzinfo=JST)), "midnight")
        self.assertEqual(slot_for(datetime(2026, 6, 10, 1, 59, tzinfo=JST)), "midnight")
        self.assertEqual(slot_for(datetime(2026, 6, 10, 2, 0, tzinfo=JST)), "morning")

    def test_slot_for_converts_to_jst(self):
        utc = timezone(timedelta(0))
        self.assertEqual(slot_for(datetime(2026, 6, 9, 15, 0, tzinfo=utc)), "midnight")


if __name__ == "__main__":
    unittest.main()
