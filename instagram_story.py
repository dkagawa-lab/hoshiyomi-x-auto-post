"""
HOSHIYOMI Instagram Stories auto post script.

Creates a 1080x1920 story image, uploads it to Supabase Storage,
and publishes it to Instagram Stories via the Instagram Graph API.
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from generate_and_post import (
    JST,
    VALID_SLOTS,
    moon_theme,
    primary_event_sentence,
    slot_for,
    sky_focus_sentence,
    todays_sky,
)
from instagram_post import (
    draw_moon_disc,
    draw_star_chart,
    draw_wrapped,
    find_font,
    graph_post,
    planet_positions,
    text_width,
    upload_to_supabase,
    verify_instagram_access,
    wait_for_container,
    required_env,
)

STORY_SIZE = (1080, 1920)
OUTPUT_DIR = Path("out")

STORY_TITLES = {
    "midnight": "今日の星が開く",
    "morning": "今日の星の流れ",
    "noon": "星読みメモ",
    "night": "今日の星を振り返る",
}

STORY_CTA = {
    "midnight": "今日の星読みをチェック",
    "morning": "12星座別の運気はフィード投稿へ",
    "noon": "気になったらプロフィールから星を読む",
    "night": "12星座別の振り返りはフィード投稿へ",
}


def story_centered(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    width = text_width(draw, text, font)
    draw.text(((STORY_SIZE[0] - width) // 2, y), text, font=font, fill=fill)


def create_story_background(seed: str) -> Image.Image:
    width, height = STORY_SIZE
    image = Image.new("RGB", STORY_SIZE, (7, 10, 28))
    pixels = image.load()
    top = (5, 9, 30)
    middle = (17, 20, 52)
    bottom = (8, 12, 34)

    for y in range(height):
        ratio = y / max(height - 1, 1)
        if ratio < 0.55:
            local = ratio / 0.55
            base = tuple(int(top[i] * (1 - local) + middle[i] * local) for i in range(3))
        else:
            local = (ratio - 0.55) / 0.45
            base = tuple(int(middle[i] * (1 - local) + bottom[i] * local) for i in range(3))
        for x in range(width):
            vignette = 1 - min(
                ((x - width / 2) ** 2 / (width / 1.1) ** 2)
                + ((y - height / 2) ** 2 / (height / 1.2) ** 2),
                0.58,
            )
            pixels[x, y] = tuple(int(channel * vignette) for channel in base)

    draw = ImageDraw.Draw(image)
    rng = random.Random(seed)
    for _ in range(170):
        x = rng.randint(36, width - 36)
        y = rng.randint(34, height - 34)
        alpha = rng.randint(70, 190)
        color = (
            min(255, 172 + alpha // 3),
            min(255, 156 + alpha // 4),
            min(255, 98 + alpha // 5),
        )
        radius = rng.choice([1, 1, 2, 2, 3])
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    return image


def story_body(sky: dict[str, Any], slot: str) -> str:
    focus = sky_focus_sentence(sky)
    if slot == "morning":
        return (
            f"{focus}今日は「{moon_theme(sky)}」が鍵。\n"
            "12星座別の詳しい流れは、最新投稿で。"
        )
    if slot == "night":
        return (
            f"{focus}できたことも、できなかったことも、\n"
            "明日の選び方につながります。"
        )
    if slot == "noon":
        return (
            "月は心の反応の出方をそっと映します。\n"
            "今日の自分の揺れ方も、星の流れの一部。"
        )
    event = primary_event_sentence(sky)
    return (
        f"{event}今日の星の流れを、静かに受け取って。"
    )


def draw_cta(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> None:
    gold = (229, 199, 121)
    pale = (248, 235, 186)
    x1, y1, x2, y2 = 116, 1642, 964, 1734
    draw.rounded_rectangle((x1, y1, x2, y2), radius=46, fill=(20, 22, 53), outline=gold, width=3)
    width = text_width(draw, text, font)
    draw.text(((STORY_SIZE[0] - width) // 2, y1 + 24), text, font=font, fill=pale)


def generate_story(sky: dict[str, Any], slot: str, output_path: Path, now: datetime | None = None) -> Path:
    now = now or datetime.now(JST)
    image = create_story_background(f"{sky['date']}-{slot}-story")
    draw = ImageDraw.Draw(image)

    brand_font = find_font(58)
    eyebrow_font = find_font(28)
    title_font = find_font(72)
    body_font = find_font(42)
    planet_font = find_font(26)
    sign_font = find_font(28)
    cta_font = find_font(34)
    foot_font = find_font(28)

    gold = (229, 199, 121)
    pale_gold = (250, 230, 162)
    white = (248, 246, 236)
    muted = (190, 185, 210)

    story_centered(draw, 82, "HOSHIYOMI", brand_font, gold)
    story_centered(draw, 154, f"STORY / {sky['date']}", eyebrow_font, muted)
    story_centered(draw, 226, STORY_TITLES[slot], title_font, pale_gold)

    chart_center = (540, 735)
    draw_star_chart(draw, chart_center, planet_positions(now), planet_font, sign_font)
    draw_moon_disc(draw, chart_center, sky["moon_phase"])

    y = 1190
    story_centered(draw, y, f"月は{sky['moon_sign']}、{sky['moon_phase']}", find_font(54), pale_gold)
    y += 96
    draw_wrapped(draw, (116, y), story_body(sky, slot), body_font, white, 848, 18)

    draw_cta(draw, STORY_CTA[slot], cta_font)
    story_centered(draw, 1794, "hoshiyomi4u.com", foot_font, gold)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=92, optimize=True)
    return output_path


def publish_story(image_url: str) -> dict[str, Any]:
    ig_account_id = required_env("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    create = graph_post(
        f"{ig_account_id}/media",
        {
            "media_type": "STORIES",
            "image_url": image_url,
        },
    )
    creation_id = create.get("id")
    if not creation_id:
        raise RuntimeError(f"Instagram story creation did not return an id: {create}")

    wait_for_container(creation_id)
    return graph_post(f"{ig_account_id}/media_publish", {"creation_id": creation_id})


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    now = datetime.now(JST)
    slot = argv[0] if argv else slot_for(now)
    if slot not in VALID_SLOTS:
        raise SystemExit(f"slot must be one of: {', '.join(VALID_SLOTS)}")

    sky = todays_sky(now)
    filename = f"{now.strftime('%Y%m%d-%H%M%S')}-{slot}-story.jpg"
    local_path = generate_story(sky, slot, OUTPUT_DIR / filename, now)

    print(f"[sky] {json.dumps(sky, ensure_ascii=False)}")
    print(f"[instagram-story:{slot}:image] {local_path}")
    print(f"[instagram-story:{slot}:body]\n{story_body(sky, slot)}\n")

    if os.environ.get("DRY_RUN") == "1":
        print("[dry-run] skipped Supabase upload and Instagram story publish")
        return

    verify_instagram_access()

    object_path = f"stories/{now.strftime('%Y/%m/%d')}/{filename}"
    image_url = upload_to_supabase(local_path, object_path)
    print(f"[supabase:story_image_url] {image_url}")

    result = publish_story(image_url)
    print(f"[instagram-story:posted] {json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
