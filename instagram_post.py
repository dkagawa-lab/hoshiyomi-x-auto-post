"""
HOSHIYOMI Instagram auto post script.

Creates a 1080x1350 astrology card image, uploads it to Supabase Storage,
and publishes it to Instagram via the Instagram Graph API.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

from generate_and_post import (
    ANTHROPIC_MODEL,
    ANTHROPIC_VERSION,
    JST,
    PLANETS,
    SITE_URL,
    SIGNS,
    SIGN_ELEMENTS,
    SIGN_GROUPS,
    SIGN_INDEX,
    calc,
    jd_from,
    moon_theme,
    VALID_SLOTS,
    primary_event_sentence,
    retrograde_sentence,
    slot_for,
    style_profile,
    sky_focus_sentence,
    todays_sky,
    varied_sign_guidance_line,
    varied_sign_reflection_line,
)

GRAPH_API_VERSION = os.environ.get("META_GRAPH_API_VERSION", "v23.0")
CARD_SIZE = (1080, 1350)
OUTPUT_DIR = Path("out")

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

CAPTION_BRIEF = {
    "midnight": "日付が変わった直後の投稿。今日の星の入口として、日付・月星座・月相を静かに伝える。",
    "morning": "朝の投稿。今日の星の動きから、12星座別の運気とやるべきことを伝える。",
    "noon": "昼の投稿。占星術の豆知識を今日の星と絡めて伝える。",
    "night": "夜の投稿。今日の星をふり返り、12星座別にできたこと・できなかった時の受け止め方を伝える。",
}

CAPTION_TEMPLATES = {
    "midnight": "{date}。日が変わりました。\n月は{moon_sign}、{moon_phase}。\n{event_line}今日の鍵は「{theme}」。予定を増やす前に、心の向きを一つ決めておくと流れを受け取りやすい日です。\n\n#星読み #占星術 #HOSHIYOMI",
    "morning": "{date}の月は{moon_sign}。{moon_phase}の流れです。\n{event_line}今日は「{theme}」を意識して、反応を急がず、自分のペースに戻ることから始めてください。\n\n#星読み #占星術 #HOSHIYOMI",
    "noon": "いま月は{moon_sign}にあります。\n月は約2.5日ごとに星座を移り、同じ出来事への反応の出方を少しずつ変えていきます。今日は「{theme}」を観察すると、午後の選び方が整いやすくなります。\n\n#星読み #占星術 #HOSHIYOMI",
    "night": "今日もおつかれさまでした。\n月は{moon_sign}、{moon_phase}。\n{event_line}うまくできたことだけでなく、引っかかった感情にも明日のヒントがあります。\n\n#星読み #占星術 #HOSHIYOMI",
}

IMAGE_MESSAGES = {
    "midnight": "今日の星の入口。\n月のサインと天体の動きから、一日の質感を読みます。",
    "morning": "朝の星読み。\n今日の空から、12星座別の使い方まで落とし込みます。",
    "noon": "昼の星読みメモ。\n月の位置は、反応の出方と選び方をそっと映します。",
    "night": "夜の振り返り。\n今日の星を、明日の選び方へつなげます。",
}

PLANET_MARKS = {
    "太陽": "太",
    "月": "月",
    "水星": "水",
    "金星": "金",
    "火星": "火",
    "木星": "木",
    "土星": "土",
    "天王星": "天",
    "海王星": "海",
    "冥王星": "冥",
}

SLOT_TITLES = {
    "midnight": "今日の星図",
    "morning": "朝の星読み",
    "noon": "星読みメモ",
    "night": "夜の振り返り",
}

SIGN_SHORT_LABELS = {
    "牡羊座": "牡羊",
    "牡牛座": "牡牛",
    "双子座": "双子",
    "蟹座": "蟹",
    "獅子座": "獅子",
    "乙女座": "乙女",
    "天秤座": "天秤",
    "蠍座": "蠍",
    "射手座": "射手",
    "山羊座": "山羊",
    "水瓶座": "水瓶",
    "魚座": "魚",
}

ELEMENT_TRAITS = {
    "火": ("熱量", "動きながら気持ちに火を入れる"),
    "地": ("現実", "体感と予定を具体的に整える"),
    "風": ("言葉", "情報を選び、伝え方を軽くする"),
    "水": ("本音", "感情の揺れを無理に急がせない"),
}

IMAGE_GUIDANCE_ACTIONS = {
    0: "本音を先に確認",
    1: "急ぐ前に一呼吸",
    2: "返事を一つ整える",
    3: "居場所を整える",
    4: "好きなものを選ぶ",
    5: "抱えすぎを減らす",
    6: "相手の言葉を聞く",
    7: "違和感を書き出す",
    8: "行きたい方を言葉に",
    9: "優先順位を一つに",
    10: "小さく相談する",
    11: "静かな時間を確保",
}

IMAGE_REFLECTION_ACTIONS = {
    0: "最初の本音を残す",
    1: "減らすヒントを見る",
    2: "言葉を明日へほどく",
    3: "安心できる場所へ",
    4: "笑えた瞬間を残す",
    5: "完璧より優先順位",
    6: "境界線を思い出す",
    7: "感情の名前を置く",
    8: "望みだけ残す",
    9: "背負いすぎを軽く",
    10: "ひとこと頼ってみる",
    11: "責めずに休む",
}


def find_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        current = ""
        for char in raw_line:
            candidate = current + char
            if current and text_width(draw, candidate, font) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_gap: int,
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width)
    line_height = draw.textbbox((0, 0), "星", font=font)[3] + line_gap
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def draw_centered(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    width = text_width(draw, text, font)
    draw.text(((CARD_SIZE[0] - width) // 2, y), text, font=font, fill=fill)


def clean_event_line(text: str) -> str:
    return " ".join(text.strip().rstrip("。").split())


def event_or_retrograde_line(sky: dict[str, Any]) -> str:
    event = primary_event_sentence(sky)
    if event:
        return clean_event_line(event)
    retrograde = retrograde_sentence(sky)
    if retrograde:
        return clean_event_line(retrograde)
    return "大きな天体イベントは控えめ。月のサインが一日の肌触りを作ります"


def image_headline(sky: dict[str, Any], slot: str) -> str:
    if sky.get("events"):
        return clean_event_line(str(sky["events"][0]))
    if slot == "morning":
        return f"月{sky['moon_sign']}の日は、{moon_theme(sky)}"
    if slot == "night":
        return "今日の反応を、明日の選び方へ"
    if slot == "noon":
        return f"月{sky['moon_sign']}で読む、心の動き"
    return f"{sky['date']}の星が動き出します"


def reading_points(sky: dict[str, Any], slot: str) -> list[str]:
    element = SIGN_ELEMENTS.get(sky["moon_sign"], "地")
    element_label, element_action = ELEMENT_TRAITS[element]
    focus = event_or_retrograde_line(sky)
    retrogrades = sky.get("retrogrades", [])
    retro = f"逆行中: {' / '.join(retrogrades[:3])}。急ぐより再確認へ。" if retrogrades else ""

    if slot == "night":
        points = [
            focus,
            f"月{sky['moon_sign']}の{element_label}が、今日の反応の跡を残します。",
            "できた/できないより、何に心が動いたかを拾う夜。",
        ]
    elif slot == "noon":
        points = [
            focus,
            f"月{sky['moon_sign']}は、{element_action}流れ。",
            "午後は予定より、反応の癖を観察すると読みやすい日。",
        ]
    elif slot == "midnight":
        points = [
            focus,
            f"今日の鍵は「{moon_theme(sky)}」。",
            "一日の始まりに、無理なく意識するテーマを一つだけ。",
        ]
    else:
        points = [
            focus,
            f"月{sky['moon_sign']}は、{element_action}日。",
            f"今日の鍵は「{moon_theme(sky)}」。太陽星座別に使い方を確認して。",
        ]

    if retro and retro not in points:
        points.append(retro)
    return points[:3]


def parse_sign_line(line: str) -> tuple[str, str, str]:
    normalized = line.replace(":", "：", 1).strip()
    sign, _, rest = normalized.partition("：")
    parts = [part.strip() for part in rest.split("。") if part.strip()]
    tone = parts[0] if parts else ""
    action = parts[1] if len(parts) > 1 else ""
    return sign, tone, action


def sign_digest_items(sky: dict[str, Any], slot: str) -> list[tuple[str, str, str]]:
    if slot == "night":
        lines = [varied_sign_reflection_line(sign, sky, "night") for sign in SIGNS]
        action_map = IMAGE_REFLECTION_ACTIONS
    else:
        lines = [varied_sign_guidance_line(sign, sky, "morning") for sign in SIGNS]
        action_map = IMAGE_GUIDANCE_ACTIONS
    items: list[tuple[str, str, str]] = []
    for line in lines:
        sign, tone, _action = parse_sign_line(line)
        diff = (SIGN_INDEX[sign] - SIGN_INDEX[sky["moon_sign"]]) % 12
        items.append((sign, tone, action_map[diff]))
    return items


def zodiac_lines(sky: dict[str, Any], mode: str) -> list[str]:
    if mode == "night":
        return [varied_sign_reflection_line(sign, sky, "night").replace(":", "：", 1) for sign in SIGNS]
    return [varied_sign_guidance_line(sign, sky, "morning").replace(":", "：", 1) for sign in SIGNS]


def zodiac_caption(sky: dict[str, Any], slot: str) -> str:
    points = "\n".join(f"・{point}" for point in reading_points(sky, slot))
    if slot == "morning":
        lead = (
            f"{sky['date']}の星読み。\n"
            f"月は{sky['moon_sign']}、{sky['moon_phase']}。\n"
            f"{sky_focus_sentence(sky)}\n\n"
            "今日の読み筋\n"
            f"{points}\n\n"
            "12星座別の運気と、今日やるといいこと。\n"
            "太陽星座を目安に読んでください。\n"
        )
        body = "\n".join(zodiac_lines(sky, "morning"))
    elif slot == "night":
        lead = (
            f"{sky['date']}の星の振り返り。\n"
            f"月は{sky['moon_sign']}、{sky['moon_phase']}。\n"
            f"{sky_focus_sentence(sky)}\n\n"
            "今夜の読み筋\n"
            f"{points}\n\n"
            "12星座別の振り返り。\n"
            "できたことも、できなかったことも、明日の選び方につなげてください。\n"
            "太陽星座を目安に読んでください。\n"
        )
        body = "\n".join(zodiac_lines(sky, "night"))
    else:
        raise ValueError(f"zodiac caption is not supported for slot: {slot}")
    return f"{lead}\n{body}\n\n出生図から読むならプロフィールへ。\n{SITE_URL}\n\n#星読み #占星術 #HOSHIYOMI"


def create_background(seed: str) -> Image.Image:
    width, height = CARD_SIZE
    image = Image.new("RGB", CARD_SIZE, (9, 13, 34))
    pixels = image.load()
    top = (8, 13, 35)
    bottom = (25, 29, 66)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        for x in range(width):
            vignette = 1 - min(((x - width / 2) ** 2 / (width / 1.15) ** 2) + ((y - height / 2) ** 2 / (height / 1.05) ** 2), 0.55)
            r = int((top[0] * (1 - ratio) + bottom[0] * ratio) * vignette)
            g = int((top[1] * (1 - ratio) + bottom[1] * ratio) * vignette)
            b = int((top[2] * (1 - ratio) + bottom[2] * ratio) * vignette)
            pixels[x, y] = (r, g, b)

    draw = ImageDraw.Draw(image)
    rng = random.Random(seed)
    for _ in range(110):
        x = rng.randint(40, width - 40)
        y = rng.randint(40, height - 40)
        alpha = rng.randint(80, 190)
        color = (min(255, 180 + alpha // 3), min(255, 160 + alpha // 4), min(255, 100 + alpha // 5))
        radius = rng.choice([1, 1, 2])
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    return image


def planet_positions(now: datetime) -> list[dict[str, Any]]:
    jd = jd_from(now)
    positions: list[dict[str, Any]] = []
    for planet, name in PLANETS.items():
        lon, speed = calc(jd, planet)
        positions.append(
            {
                "name": name,
                "mark": PLANET_MARKS.get(name, name[:1]),
                "longitude": lon,
                "retrograde": speed < 0 and name not in ("太陽", "月"),
            }
        )
    return positions


def point_on_wheel(center: tuple[int, int], radius: int, longitude: float) -> tuple[int, int]:
    angle = math.radians(longitude - 90)
    return (
        int(center[0] + math.cos(angle) * radius),
        int(center[1] + math.sin(angle) * radius),
    )


def draw_star_chart(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    positions: list[dict[str, Any]],
    font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
    scale: float = 1.0,
) -> None:
    gold = (226, 195, 118)
    pale_gold = (249, 229, 160)
    line = (83, 80, 132)
    muted = (158, 154, 188)
    dark = (16, 18, 45)

    outer = int(372 * scale)
    middle = int(302 * scale)
    inner = int(205 * scale)
    label_offset = int(38 * scale)
    sign_radius = max(15, int(24 * scale))

    for radius, color, width in ((outer, line, 3), (middle, (63, 61, 112), 2), (inner, (52, 51, 98), 2)):
        draw.ellipse(
            (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
            outline=color,
            width=width,
        )

    for index, sign in enumerate(SIGN_GROUPS[0] + SIGN_GROUPS[1] + SIGN_GROUPS[2] + SIGN_GROUPS[3]):
        degree = index * 30
        x1, y1 = point_on_wheel(center, inner, degree)
        x2, y2 = point_on_wheel(center, outer, degree)
        draw.line((x1, y1, x2, y2), fill=(58, 56, 104), width=1)

        label_degree = degree + 15
        lx, ly = point_on_wheel(center, outer - label_offset, label_degree)
        label = sign.replace("座", "")
        box = draw.textbbox((0, 0), label, font=small_font)
        draw.text((lx - (box[2] - box[0]) // 2, ly - (box[3] - box[1]) // 2), label, font=small_font, fill=muted)

    for position in positions:
        radius = int((248 if position["name"] in ("太陽", "月") else 276) * scale)
        x, y = point_on_wheel(center, radius, position["longitude"])
        color = pale_gold if position["name"] in ("太陽", "月") else gold
        draw.ellipse((x - sign_radius, y - sign_radius, x + sign_radius, y + sign_radius), fill=dark, outline=color, width=2)
        label = position["mark"]
        box = draw.textbbox((0, 0), label, font=font)
        draw.text((x - (box[2] - box[0]) // 2, y - (box[3] - box[1]) // 2 - 2), label, font=font, fill=color)
        if position["retrograde"]:
            draw.text((x + int(18 * scale), y - int(32 * scale)), "R", font=small_font, fill=(244, 206, 132))


def moon_phase_fraction(phase: str) -> float:
    if "新月" in phase:
        return 0.1
    if "上弦" in phase:
        return 0.5
    if "満月" in phase:
        return 1.0
    if "下弦" in phase:
        return 0.5
    if "満ち" in phase:
        return 0.7
    if "欠け" in phase:
        return 0.35
    return 0.55


def draw_moon_disc(draw: ImageDraw.ImageDraw, center: tuple[int, int], phase: str) -> None:
    fraction = moon_phase_fraction(phase)
    radius = 58
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(234, 224, 187), outline=(239, 205, 127), width=2)
    shadow_width = int(radius * 2 * (1 - fraction))
    if shadow_width > 0:
        draw.ellipse((x - radius, y - radius, x + shadow_width - radius, y + radius), fill=(19, 22, 52))


def truncate_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if text_width(draw, text, font) <= max_width:
        return text
    clipped = text
    while clipped and text_width(draw, f"{clipped}…", font) > max_width:
        clipped = clipped[:-1]
    return f"{clipped}…" if clipped else ""


def draw_reading_panel(
    draw: ImageDraw.ImageDraw,
    y: int,
    sky: dict[str, Any],
    slot: str,
    title_font: ImageFont.ImageFont,
    body_font: ImageFont.ImageFont,
) -> int:
    gold = (229, 199, 121)
    white = (247, 244, 232)
    panel = (17, 20, 49)
    border = (88, 82, 132)
    x1, x2 = 82, 998
    height = 178
    draw.rounded_rectangle((x1, y, x2, y + height), radius=24, fill=panel, outline=border, width=2)
    title = "今夜の読み筋" if slot == "night" else "今日の読み筋"
    draw.text((116, y + 24), title, font=title_font, fill=gold)
    line_y = y + 72
    for point in reading_points(sky, slot):
        line = truncate_to_width(draw, f"・{point}", body_font, 830)
        draw.text((116, line_y), line, font=body_font, fill=white)
        line_y += 32
    return y + height


def draw_zodiac_digest(
    draw: ImageDraw.ImageDraw,
    y: int,
    sky: dict[str, Any],
    slot: str,
    header_font: ImageFont.ImageFont,
    sign_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> int:
    gold = (229, 199, 121)
    pale = (248, 235, 186)
    white = (247, 244, 232)
    muted = (178, 174, 200)
    cell_fill = (18, 22, 56)
    cell_border = (69, 66, 112)
    accent = (183, 136, 74)

    items = sign_digest_items(sky, slot)
    grid_y = y + 60
    margin_x = 58
    gap = 8
    columns = 4
    cell_w = (CARD_SIZE[0] - margin_x * 2 - gap * (columns - 1)) // columns
    cell_h = 58
    row_gap = 8
    rows = math.ceil(len(items) / columns)
    area_bottom = grid_y + rows * cell_h + max(rows - 1, 0) * row_gap
    draw.rounded_rectangle((58, y - 12, 1022, area_bottom + 12), radius=24, fill=(12, 16, 42), outline=(58, 56, 98), width=1)

    title = "十二星座別 今夜の振り返り" if slot == "night" else "十二星座別 今日の使い方"
    draw.text((82, y), title, font=header_font, fill=gold)
    draw.text((82, y + 34), "太陽星座を目安に読んでください", font=small_font, fill=muted)

    for index, (sign, tone, action) in enumerate(items):
        col = index % columns
        row = index // columns
        x = margin_x + col * (cell_w + gap)
        cy = grid_y + row * (cell_h + row_gap)
        draw.rounded_rectangle((x, cy, x + cell_w, cy + cell_h), radius=16, fill=cell_fill, outline=cell_border, width=1)
        draw.rectangle((x, cy, x + 4, cy + cell_h), fill=accent)
        label = SIGN_SHORT_LABELS.get(sign, sign.replace("座", ""))
        draw.text((x + 14, cy + 9), label, font=sign_font, fill=pale)
        draw.text((x + 70, cy + 9), truncate_to_width(draw, tone, sign_font, cell_w - 88), font=sign_font, fill=white)
        draw.text((x + 14, cy + 34), truncate_to_width(draw, action, small_font, cell_w - 28), font=small_font, fill=muted)
    return area_bottom


def generate_card(sky: dict[str, Any], slot: str, output_path: Path, now: datetime | None = None) -> Path:
    now = now or datetime.now(JST)
    image = create_background(f"{sky['date']}-{slot}")
    draw = ImageDraw.Draw(image)

    brand_font = find_font(50)
    small_font = find_font(24)
    title_font = find_font(46)
    body_font = find_font(25)
    panel_title_font = find_font(29)
    sign_font = find_font(23)
    zodiac_note_font = find_font(20)
    planet_font = find_font(22)
    foot_font = find_font(25)

    gold = (229, 199, 121)
    pale_gold = (246, 226, 162)
    muted = (189, 184, 205)

    draw_centered(draw, 54, "HOSHIYOMI", brand_font, gold)
    draw_centered(draw, 112, f"{SLOT_TITLES[slot]} / {sky['date']}", small_font, muted)
    draw_centered(draw, 158, image_headline(sky, slot), title_font, pale_gold)

    chart_center = (540, 500)
    draw_star_chart(draw, chart_center, planet_positions(now), planet_font, small_font, scale=0.72)
    draw_moon_disc(draw, chart_center, sky["moon_phase"])

    draw_centered(draw, 782, f"月は{sky['moon_sign']}、{sky['moon_phase']}", find_font(38), pale_gold)
    draw_centered(draw, 832, IMAGE_MESSAGES[slot].splitlines()[0], body_font, muted)
    y = draw_reading_panel(draw, 860, sky, slot, panel_title_font, body_font)
    draw_zodiac_digest(draw, y + 12, sky, slot, panel_title_font, sign_font, zodiac_note_font)

    draw_centered(draw, 1314, "hoshiyomi4u.com", foot_font, gold)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=92, optimize=True)
    return output_path


def fallback_caption(sky: dict[str, Any], slot: str) -> str:
    if slot in ("morning", "night"):
        return zodiac_caption(sky, slot)
    return CAPTION_TEMPLATES[slot].format(
        event_line=primary_event_sentence(sky),
        theme=moon_theme(sky),
        **sky,
    )


def instagram_prompt(sky: dict[str, Any], slot: str) -> str:
    if slot in ("morning", "night"):
        mode_detail = (
            "朝の投稿なので、今日の星の動きから12星座別の運気と今日やるといいことを全星座分書く。各星座の行は、運気名と具体的な行動を必ず変える。"
            if slot == "morning"
            else "夜の投稿なので、今日の星の振り返りと、できなかった時の受け止め方を12星座分書く。各星座の行は、振り返りの視点と明日への持ち越し方を必ず変える。"
        )
        return f"""Instagramに投稿するHOSHIYOMIの星読みキャプションを1つだけ書いてください。

今日の星のデータ:
{json.dumps(sky, ensure_ascii=False, indent=2)}

投稿の種類:
{CAPTION_BRIEF[slot]}

今日の文体指定:
{style_profile(sky, slot)}

制約:
- 2200字以内
- 冒頭に「今日の星の読み筋」を2〜3文で書く
- {mode_detail}
- 12星座別は太陽星座を目安にした表現にする
- 似た語尾、似た助言、同じ単語の連続を避ける
- 「整える」「見直す」「大丈夫」「明日」を全星座で繰り返しすぎない
- 「絶対」「必ず当たる」など断定・効果保証は禁止
- 不安を煽らない
- 新月・満月・星座移動・逆行開始/終了がある日は冒頭で優先
- 最後に「出生図から読むならプロフィールへ」と自然に入れる
- 最後に #星読み #占星術 #HOSHIYOMI を入れる
- キャプション本文のみを出力"""

    return f"""Instagramに投稿するHOSHIYOMIの星読みキャプションを1つだけ書いてください。

今日の星のデータ:
{json.dumps(sky, ensure_ascii=False, indent=2)}

投稿の種類:
{CAPTION_BRIEF[slot]}

今日の文体指定:
{style_profile(sky, slot)}

制約:
- 260字以内
- 今日の月星座、月相、重要イベントのうち最低2つを自然に入れる
- 抽象的な一言だけで終わらせず、読者が試せる視点を1つ入れる
- 「絶対」「必ず当たる」など断定・効果保証は禁止
- 不安を煽らない
- 新月・満月・星座移動・逆行開始/終了がある日はそれを優先
- 最後に #星読み #占星術 #HOSHIYOMI を入れる
- キャプション本文のみを出力"""


def extract_claude_text(payload: dict[str, Any]) -> str:
    parts = []
    for block in payload.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip().strip("\"'「」")


def generate_caption(sky: dict[str, Any], slot: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return fallback_caption(sky, slot)

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 1200 if slot in ("morning", "night") else 500,
                "messages": [{"role": "user", "content": instagram_prompt(sky, slot)}],
            },
            timeout=60,
        )
        response.raise_for_status()
        text = extract_claude_text(response.json())
        return text or fallback_caption(sky, slot)
    except requests.RequestException as exc:
        print(f"[warn] Anthropic API failed; using Instagram template mode: {exc}", file=sys.stderr)
        return fallback_caption(sky, slot)


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def upload_to_supabase(image_path: Path, object_path: str) -> str:
    supabase_url = required_env("SUPABASE_URL").rstrip("/")
    service_key = required_env("SUPABASE_SERVICE_ROLE_KEY")
    bucket = required_env("SUPABASE_BUCKET")
    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{object_path}"

    with image_path.open("rb") as image_file:
        response = requests.post(
            upload_url,
            headers={
                "apikey": service_key,
                "authorization": f"Bearer {service_key}",
                "content-type": "image/jpeg",
                "x-upsert": "true",
            },
            data=image_file,
            timeout=60,
        )
    if not response.ok:
        raise RuntimeError(f"Supabase upload failed: {response.status_code} {response.text}")
    return f"{supabase_url}/storage/v1/object/public/{bucket}/{object_path}"


def raise_graph_api_error(response: requests.Response) -> None:
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    code = error.get("code")
    subcode = error.get("error_subcode")
    message = error.get("message", response.text)

    if code == 190 and subcode == 463:
        raise RuntimeError(
            "META_ACCESS_TOKEN has expired. Generate a new long-lived Meta access "
            "token and update the GitHub Repository secret named META_ACCESS_TOKEN. "
            f"Meta response: {message}"
        )
    if code == 190:
        raise RuntimeError(
            "META_ACCESS_TOKEN is invalid or no longer authorized. Reissue the token "
            "with instagram_basic, instagram_content_publish, pages_show_list, and "
            f"pages_read_engagement permissions. Meta response: {message}"
        )

    raise RuntimeError(
        "Instagram Graph API failed: "
        f"{response.status_code} {json.dumps(payload, ensure_ascii=False)}"
    )


def graph_post(path: str, payload: dict[str, str]) -> dict[str, Any]:
    token = required_env("META_ACCESS_TOKEN")
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{path.lstrip('/')}"
    response = requests.post(url, data={**payload, "access_token": token}, timeout=60)
    if not response.ok:
        raise_graph_api_error(response)
    return response.json()


def graph_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    token = required_env("META_ACCESS_TOKEN")
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{path.lstrip('/')}"
    response = requests.get(url, params={**params, "access_token": token}, timeout=30)
    if not response.ok:
        raise_graph_api_error(response)
    return response.json()


def verify_instagram_access() -> None:
    ig_account_id = required_env("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    account = graph_get(ig_account_id, {"fields": "id,username"})
    print(f"[instagram:account] {json.dumps(account, ensure_ascii=False)}")


def wait_for_container(container_id: str) -> None:
    for _ in range(8):
        status = graph_get(container_id, {"fields": "status_code,status"})
        if status.get("status_code") == "FINISHED":
            return
        if status.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram media container failed: {json.dumps(status, ensure_ascii=False)}")
        time.sleep(3)


def publish_to_instagram(image_url: str, caption: str) -> dict[str, Any]:
    ig_account_id = required_env("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    create = graph_post(
        f"{ig_account_id}/media",
        {
            "image_url": image_url,
            "caption": caption,
        },
    )
    creation_id = create.get("id")
    if not creation_id:
        raise RuntimeError(f"Instagram media creation did not return an id: {create}")

    wait_for_container(creation_id)
    return graph_post(f"{ig_account_id}/media_publish", {"creation_id": creation_id})


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    now = datetime.now(JST)
    slot = argv[0] if argv else slot_for(now)
    if slot not in VALID_SLOTS:
        raise SystemExit(f"slot must be one of: {', '.join(VALID_SLOTS)}")

    sky = todays_sky(now)
    caption = generate_caption(sky, slot)
    filename = f"{now.strftime('%Y%m%d-%H%M%S')}-{slot}.jpg"
    local_path = generate_card(sky, slot, OUTPUT_DIR / filename, now)

    print(f"[sky] {json.dumps(sky, ensure_ascii=False)}")
    print(f"[instagram:{slot}:caption]\n{caption}\n")
    print(f"[instagram:{slot}:image] {local_path}")

    if os.environ.get("DRY_RUN") == "1":
        print("[dry-run] skipped Supabase upload and Instagram publish")
        return

    verify_instagram_access()

    object_path = f"cards/{now.strftime('%Y/%m/%d')}/{filename}"
    image_url = upload_to_supabase(local_path, object_path)
    print(f"[supabase:image_url] {image_url}")

    result = publish_to_instagram(image_url, caption)
    print(f"[instagram:posted] {json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
