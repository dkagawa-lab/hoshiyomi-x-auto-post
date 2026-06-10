import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from generate_and_post import crosses, sign_of


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


if __name__ == "__main__":
    unittest.main()
