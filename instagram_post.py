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
    SIGN_GROUPS,
    calc,
    jd_from,
    moon_theme,
    VALID_SLOTS,
    primary_event_sentence,
    sign_guidance_line,
    sign_reflection_line,
    slot_for,
    sky_focus_sentence,
    todays_sky,
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
    "midnight": "{date}。日が変わりました。月は{moon_sign}、{moon_phase}。{event_line}今日の星の流れを、静かに受け取ってください。\n\n#星読み #占星術 #HOSHIYOMI",
    "morning": "{date}の月は{moon_sign}。{moon_phase}の流れです。{event_line}今日は反応を急がず、自分の感覚を整えるところから。\n\n#星読み #占星術 #HOSHIYOMI",
    "noon": "月は約2.5日ごとに星座を移ります。いまの月は{moon_sign}。同じ日でも、生まれた時刻と場所で星の地図は変わります。\n\n#星読み #占星術 #HOSHIYOMI",
    "night": "今日もおつかれさまでした。{moon_phase}の夜。{event_line}明日の星は、また少し違う表情を見せます。\n\n#星読み #占星術 #HOSHIYOMI",
}

IMAGE_MESSAGES = {
    "midnight": "日が変わりました。\n今日の星の流れを、静かに受け取って。",
    "morning": "今日の星の流れから、\n12星座別の運気を読みます。",
    "noon": "月の位置は、心の反応の出方をそっと映します。",
    "night": "今日の星を振り返り、\n明日の選び方へつなげます。",
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


def zodiac_lines(sky: dict[str, Any], mode: str) -> list[str]:
    if mode == "night":
        formatter = sign_reflection_line
    else:
        formatter = sign_guidance_line
    lines: list[str] = []
    for group in SIGN_GROUPS:
        for sign in group:
            lines.append(formatter(sign, sky["moon_sign"]).replace(":", "：", 1))
    return lines


def zodiac_caption(sky: dict[str, Any], slot: str) -> str:
    if slot == "morning":
        lead = (
            f"{sky['date']}の星読み。\n"
            f"月は{sky['moon_sign']}、{sky['moon_phase']}。\n"
            f"{sky_focus_sentence(sky)}今日は「{moon_theme(sky)}」が鍵です。\n\n"
            "12星座別の運気と、今日やるといいこと。\n"
            "太陽星座を目安に読んでください。\n"
        )
        body = "\n".join(zodiac_lines(sky, "morning"))
    elif slot == "night":
        lead = (
            f"{sky['date']}の星の振り返り。\n"
            f"月は{sky['moon_sign']}、{sky['moon_phase']}。\n"
            f"{sky_focus_sentence(sky)}できたことも、できなかったことも、明日の選び方につながります。\n\n"
            "12星座別の振り返り。\n"
            "太陽星座を目安に読んでください。\n"
        )
        body = "\n".join(zodiac_lines(sky, "night"))
    else:
        raise ValueError(f"zodiac caption is not supported for slot: {slot}")
    return f"{lead}\n{body}\n\n#星読み #占星術 #HOSHIYOMI"


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
) -> None:
    gold = (226, 195, 118)
    pale_gold = (249, 229, 160)
    line = (83, 80, 132)
    muted = (158, 154, 188)
    dark = (16, 18, 45)

    outer = 372
    middle = 302
    inner = 205

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
        lx, ly = point_on_wheel(center, outer - 38, label_degree)
        label = sign.replace("座", "")
        box = draw.textbbox((0, 0), label, font=small_font)
        draw.text((lx - (box[2] - box[0]) // 2, ly - (box[3] - box[1]) // 2), label, font=small_font, fill=muted)

    for position in positions:
        radius = 248 if position["name"] in ("太陽", "月") else 276
        x, y = point_on_wheel(center, radius, position["longitude"])
        color = pale_gold if position["name"] in ("太陽", "月") else gold
        draw.ellipse((x - 24, y - 24, x + 24, y + 24), fill=dark, outline=color, width=2)
        label = position["mark"]
        box = draw.textbbox((0, 0), label, font=font)
        draw.text((x - (box[2] - box[0]) // 2, y - (box[3] - box[1]) // 2 - 2), label, font=font, fill=color)
        if position["retrograde"]:
            draw.text((x + 18, y - 32), "R", font=small_font, fill=(244, 206, 132))


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


def generate_card(sky: dict[str, Any], slot: str, output_path: Path, now: datetime | None = None) -> Path:
    now = now or datetime.now(JST)
    image = create_background(f"{sky['date']}-{slot}")
    draw = ImageDraw.Draw(image)

    brand_font = find_font(54)
    small_font = find_font(30)
    title_font = find_font(62)
    body_font = find_font(36)
    planet_font = find_font(26)
    foot_font = find_font(28)

    gold = (229, 199, 121)
    pale_gold = (246, 226, 162)
    white = (247, 244, 232)
    muted = (189, 184, 205)

    draw_centered(draw, 78, "HOSHIYOMI", brand_font, gold)
    draw_centered(draw, 145, f"{SLOT_TITLES[slot]} / {sky['date']}", small_font, muted)

    chart_center = (540, 585)
    draw_star_chart(draw, chart_center, planet_positions(now), planet_font, foot_font)
    draw_moon_disc(draw, chart_center, sky["moon_phase"])

    y = 1000
    draw_centered(draw, y, f"月は{sky['moon_sign']}、{sky['moon_phase']}", title_font, pale_gold)
    y += 86
    event = primary_event_sentence(sky) or ("見直しの星: " + " / ".join(sky["retrogrades"][:3]) if sky["retrogrades"] else "")
    if event:
        y = draw_wrapped(draw, (122, y), event, body_font, gold, 836, 14)
        y += 16

    message = IMAGE_MESSAGES[slot]
    draw_wrapped(draw, (122, y), message, body_font, white, 836, 14)

    draw_centered(draw, 1260, "hoshiyomi4u.com", foot_font, gold)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=92, optimize=True)
    return output_path


def fallback_caption(sky: dict[str, Any], slot: str) -> str:
    if slot in ("morning", "night"):
        return zodiac_caption(sky, slot)
    return CAPTION_TEMPLATES[slot].format(event_line=primary_event_sentence(sky), **sky)


def instagram_prompt(sky: dict[str, Any], slot: str) -> str:
    if slot in ("morning", "night"):
        mode_detail = (
            "朝の投稿なので、今日の星の動きから12星座別の運気と今日やるといいことを全星座分書く。"
            if slot == "morning"
            else "夜の投稿なので、今日の星の振り返りと、できなかった時の受け止め方を12星座分書く。"
        )
        return f"""Instagramに投稿するHOSHIYOMIの星読みキャプションを1つだけ書いてください。

今日の星のデータ:
{json.dumps(sky, ensure_ascii=False, indent=2)}

投稿の種類:
{CAPTION_BRIEF[slot]}

制約:
- 1800字以内
- {mode_detail}
- 12星座別は太陽星座を目安にした表現にする
- 「絶対」「必ず当たる」など断定・効果保証は禁止
- 不安を煽らない
- 新月・満月・星座移動・逆行開始/終了がある日は冒頭で優先
- 最後に #星読み #占星術 #HOSHIYOMI を入れる
- キャプション本文のみを出力"""

    return f"""Instagramに投稿するHOSHIYOMIの星読みキャプションを1つだけ書いてください。

今日の星のデータ:
{json.dumps(sky, ensure_ascii=False, indent=2)}

投稿の種類:
{CAPTION_BRIEF[slot]}

制約:
- 160字以内
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
                "max_tokens": 500,
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
