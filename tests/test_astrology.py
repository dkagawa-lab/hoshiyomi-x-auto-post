import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from generate_and_post import (
    JST,
    MAX_TWEET_CHARS,
    SITE_URL,
    build_morning_thread,
    build_night_thread,
    crosses,
    sign_of,
    slot_for,
)
from instagram_post import zodiac_caption


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

    def test_slot_for_morning_and_night_post_times(self):
        self.assertEqual(slot_for(datetime(2026, 6, 10, 8, 0, tzinfo=JST)), "morning")
        self.assertEqual(slot_for(datetime(2026, 6, 10, 22, 0, tzinfo=JST)), "night")

    def test_slot_for_converts_to_jst(self):
        utc = timezone(timedelta(0))
        self.assertEqual(slot_for(datetime(2026, 6, 9, 15, 0, tzinfo=utc)), "midnight")

    def test_build_morning_thread_contains_zodiac_guidance(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "欠けていく月",
            "events": ["金星が牡牛座から双子座へ移動"],
            "retrogrades": ["冥王星(水瓶座)"],
        }
        posts = build_morning_thread(sky)

        self.assertEqual(len(posts), 5)
        self.assertIn(SITE_URL, posts[0])
        self.assertIn("牡羊座", posts[1])
        self.assertIn("魚座", posts[4])
        self.assertTrue(all(len(post) <= MAX_TWEET_CHARS for post in posts))

    def test_build_night_thread_contains_zodiac_reflection(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
        }
        posts = build_night_thread(sky)

        self.assertEqual(len(posts), 5)
        self.assertIn("振り返り", posts[0])
        self.assertIn("牡羊座", posts[1])
        self.assertIn("魚座", posts[4])
        self.assertTrue(all(len(post) <= MAX_TWEET_CHARS for post in posts))

    def test_instagram_zodiac_captions_include_all_signs(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
        }
        morning = zodiac_caption(sky, "morning")
        night = zodiac_caption(sky, "night")

        for sign in ("牡羊座", "牡牛座", "双子座", "蟹座", "獅子座", "乙女座", "天秤座", "蠍座", "射手座", "山羊座", "水瓶座", "魚座"):
            self.assertIn(sign, morning)
            self.assertIn(sign, night)
        self.assertIn("今日やるといいこと", morning)
        self.assertIn("振り返り", night)


if __name__ == "__main__":
    unittest.main()
