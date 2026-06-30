import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from generate_and_post import (
    JST,
    MAX_TWEET_CHARS,
    NOON_SECTION_ORDER,
    NOON_TWEETS_PER_SECTION,
    RANKING_CARD_SIZE,
    SITE_URL,
    build_morning_thread,
    build_noon_thread,
    build_night_thread,
    crosses,
    find_font,
    fortune_ranking_items,
    generate_fortune_ranking_card,
    generate_ranking_card,
    generate_three_fortunes_card,
    is_duplicate_tweet_response,
    should_skip_late_midnight,
    sign_of,
    slot_for,
    text_width,
    three_fortune_items,
    three_fortunes_caption,
    wrap_text,
    zodiac_ranking_items,
)
from instagram_post import CARD_SIZE, InstagramGraphAPIError, generate_card, is_instagram_media_download_error, zodiac_caption
from instagram_story import STORY_SIZE, generate_story, story_body


class AstrologyHelperTests(unittest.TestCase):
    def make_response(self, status_code: int, body: str) -> requests.Response:
        response = requests.Response()
        response.status_code = status_code
        response._content = body.encode("utf-8")
        return response

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

    def test_late_midnight_run_is_skipped(self):
        self.assertFalse(should_skip_late_midnight("midnight", datetime(2026, 6, 10, 0, 59, tzinfo=JST)))
        self.assertTrue(should_skip_late_midnight("midnight", datetime(2026, 6, 10, 1, 0, tzinfo=JST)))
        self.assertFalse(should_skip_late_midnight("morning", datetime(2026, 6, 10, 9, 0, tzinfo=JST)))

    def test_duplicate_tweet_response_detection(self):
        response = self.make_response(
            403,
            '{"detail":"You are not allowed to create a Tweet with duplicate content.","title":"Forbidden"}',
        )
        self.assertTrue(is_duplicate_tweet_response(response))

    def test_duplicate_tweet_response_ignores_other_403(self):
        response = self.make_response(403, '{"detail":"Your app is read only.","title":"Forbidden"}')
        self.assertFalse(is_duplicate_tweet_response(response))

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
        self.assertIn("#星読み", posts[0])
        self.assertIn("牡羊座", posts[1])
        self.assertIn("魚座", posts[4])
        self.assertTrue(all(len(post) <= MAX_TWEET_CHARS for post in posts))

    def test_build_noon_thread_contains_independent_rankings(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
            "planet_signs": {
                "金星": {"sign": "牡牛座"},
                "木星": {"sign": "蟹座"},
                "水星": {"sign": "双子座"},
            },
        }
        posts = build_noon_thread(sky)

        self.assertEqual(len(posts), len(NOON_SECTION_ORDER) * NOON_TWEETS_PER_SECTION)
        self.assertIn(SITE_URL, posts[0])
        self.assertIn("総合", posts[0])
        self.assertIn("恋愛", posts[NOON_TWEETS_PER_SECTION])
        self.assertIn("金運", posts[NOON_TWEETS_PER_SECTION * 2])
        self.assertIn("仕事", posts[NOON_TWEETS_PER_SECTION * 3])
        self.assertIn("1位", posts[1])
        self.assertTrue(any("牡羊座" in post for post in posts))
        self.assertTrue(any("魚座" in post for post in posts))
        self.assertTrue(all(len(post) <= MAX_TWEET_CHARS for post in posts))

    def test_x_zodiac_threads_vary_by_date(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
        }
        next_day = {**sky, "date": "2026年06月13日", "weekday": "土曜日"}

        self.assertNotEqual(build_morning_thread(sky)[1], build_morning_thread(next_day)[1])
        self.assertNotEqual(build_night_thread(sky)[1], build_night_thread(next_day)[1])

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
        self.assertIn("今日の読み筋", morning)
        self.assertIn("今夜の読み筋", night)
        self.assertIn("今日やるといいこと", morning)
        self.assertIn("振り返り", night)

    def test_three_fortunes_caption_includes_all_signs(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
            "planet_signs": {
                "金星": {"sign": "牡牛座"},
                "木星": {"sign": "蟹座"},
                "水星": {"sign": "双子座"},
            },
        }
        caption = three_fortunes_caption(sky)

        for sign in ("牡羊座", "牡牛座", "双子座", "蟹座", "獅子座", "乙女座", "天秤座", "蠍座", "射手座", "山羊座", "水瓶座", "魚座"):
            self.assertIn(sign, caption)
        self.assertIn("総合運", caption)
        self.assertIn("恋愛運", caption)
        self.assertIn("金運", caption)
        self.assertIn("仕事運", caption)

    def test_instagram_feed_card_image_size(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
        }
        output = pathlib.Path("/tmp/hoshiyomi-feed-card-test.jpg")
        path = generate_card(sky, "morning", output, datetime(2026, 6, 12, 8, 0, tzinfo=JST))

        from PIL import Image

        with Image.open(path) as image:
            self.assertEqual(image.size, CARD_SIZE)

    def test_instagram_noon_card_image_size(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
            "planet_signs": {
                "金星": {"sign": "牡牛座"},
                "木星": {"sign": "蟹座"},
                "水星": {"sign": "双子座"},
            },
        }
        output = pathlib.Path("/tmp/hoshiyomi-noon-card-test.jpg")
        path = generate_card(sky, "noon", output, datetime(2026, 6, 12, 12, 0, tzinfo=JST))

        from PIL import Image

        with Image.open(path) as image:
            self.assertEqual(image.size, CARD_SIZE)

    def test_zodiac_ranking_items_include_all_signs(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
        }
        items = zodiac_ranking_items(sky, "morning")

        self.assertEqual(len(items), 12)
        self.assertEqual({item["sign"] for item in items}, set(("牡羊座", "牡牛座", "双子座", "蟹座", "獅子座", "乙女座", "天秤座", "蠍座", "射手座", "山羊座", "水瓶座", "魚座")))
        self.assertEqual([item["rank"] for item in items], list(range(1, 13)))

    def test_three_fortune_items_include_all_signs_and_domains(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
            "planet_signs": {
                "金星": {"sign": "牡牛座"},
                "木星": {"sign": "蟹座"},
                "水星": {"sign": "双子座"},
            },
        }
        items = three_fortune_items(sky)

        self.assertEqual(len(items), 12)
        self.assertEqual({item["sign"] for item in items}, set(("牡羊座", "牡牛座", "双子座", "蟹座", "獅子座", "乙女座", "天秤座", "蠍座", "射手座", "山羊座", "水瓶座", "魚座")))
        for item in items:
            self.assertEqual(set(item["fortunes"].keys()), {"love", "money", "work"})

    def test_fortune_ranking_items_include_all_signs_for_each_section(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
            "planet_signs": {
                "金星": {"sign": "牡牛座"},
                "木星": {"sign": "蟹座"},
                "水星": {"sign": "双子座"},
            },
        }
        expected_signs = set(("牡羊座", "牡牛座", "双子座", "蟹座", "獅子座", "乙女座", "天秤座", "蠍座", "射手座", "山羊座", "水瓶座", "魚座"))

        for section_key in NOON_SECTION_ORDER:
            items = fortune_ranking_items(sky, section_key)
            self.assertEqual(len(items), 12)
            self.assertEqual({item["sign"] for item in items}, expected_signs)
            self.assertEqual([item["rank"] for item in items], list(range(1, 13)))

    def test_ranking_text_wraps_without_ellipsis(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (360, 240))
        draw = ImageDraw.Draw(image)
        font = find_font(20)
        lines = wrap_text(draw, "完璧にできなくても、減らしたい役目が見えたなら前進", font, 180)

        self.assertGreater(len(lines), 1)
        self.assertNotIn("…", "".join(lines))
        self.assertEqual("".join(lines), "完璧にできなくても、減らしたい役目が見えたなら前進")
        self.assertTrue(all(text_width(draw, line, font) <= 180 for line in lines))

    def test_ranking_card_image_size(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
        }
        output = pathlib.Path("/tmp/hoshiyomi-ranking-card-test.jpg")
        path = generate_ranking_card(sky, "morning", output, datetime(2026, 6, 12, 8, 0, tzinfo=JST))

        from PIL import Image

        with Image.open(path) as image:
            self.assertEqual(image.size, RANKING_CARD_SIZE)

    def test_three_fortunes_card_image_size(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
            "planet_signs": {
                "金星": {"sign": "牡牛座"},
                "木星": {"sign": "蟹座"},
                "水星": {"sign": "双子座"},
            },
        }
        output = pathlib.Path("/tmp/hoshiyomi-three-fortunes-card-test.jpg")
        path = generate_three_fortunes_card(sky, output, datetime(2026, 6, 12, 12, 0, tzinfo=JST))

        from PIL import Image

        with Image.open(path) as image:
            self.assertEqual(image.size, RANKING_CARD_SIZE)

    def test_fortune_ranking_card_image_size_for_each_section(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
            "planet_signs": {
                "金星": {"sign": "牡牛座"},
                "木星": {"sign": "蟹座"},
                "水星": {"sign": "双子座"},
            },
        }

        from PIL import Image

        for section_key in NOON_SECTION_ORDER:
            output = pathlib.Path(f"/tmp/hoshiyomi-{section_key}-ranking-card-test.jpg")
            path = generate_fortune_ranking_card(sky, section_key, output, datetime(2026, 6, 12, 12, 0, tzinfo=JST))
            with Image.open(path) as image:
                self.assertEqual(image.size, RANKING_CARD_SIZE)

    def test_instagram_media_download_error_detection(self):
        error = InstagramGraphAPIError(
            "failed",
            400,
            {
                "error": {
                    "message": "Only photo or video can be accepted as media type.",
                    "code": 9004,
                    "error_subcode": 2207052,
                }
            },
        )
        self.assertTrue(is_instagram_media_download_error(error))

    def test_instagram_story_image_size_and_body(self):
        sky = {
            "date": "2026年06月12日",
            "weekday": "金曜日",
            "moon_sign": "牡牛座",
            "moon_phase": "新月前の月",
            "events": [],
            "retrogrades": ["冥王星(水瓶座)"],
        }
        output = pathlib.Path("/tmp/hoshiyomi-story-test.jpg")
        path = generate_story(sky, "morning", output)

        from PIL import Image

        with Image.open(path) as image:
            self.assertEqual(image.size, STORY_SIZE)
        self.assertIn("12星座別", story_body(sky, "morning"))


if __name__ == "__main__":
    unittest.main()
