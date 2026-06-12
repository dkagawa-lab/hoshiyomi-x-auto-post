"""
HOSHIYOMI X auto post script.

Calculates the current day's astrology events in JST, creates a short post,
and publishes it to X. Designed to run on GitHub Actions without a server.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
import swisseph as swe
from requests_oauthlib import OAuth1

JST = timezone(timedelta(hours=9))
SITE_URL = os.environ.get("SITE_URL", "https://hoshiyomi4u.com/m")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_VERSION = "2023-06-01"
VALID_SLOTS = ("midnight", "morning", "noon", "night")
MAX_TWEET_CHARS = 280

SIGNS = [
    "牡羊座",
    "牡牛座",
    "双子座",
    "蟹座",
    "獅子座",
    "乙女座",
    "天秤座",
    "蠍座",
    "射手座",
    "山羊座",
    "水瓶座",
    "魚座",
]

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

SIGN_INDEX = {sign: index for index, sign in enumerate(SIGNS)}

SIGN_GROUPS = [
    ["牡羊座", "牡牛座", "双子座"],
    ["蟹座", "獅子座", "乙女座"],
    ["天秤座", "蠍座", "射手座"],
    ["山羊座", "水瓶座", "魚座"],
]

SIGN_ELEMENTS = {
    "牡羊座": "火",
    "獅子座": "火",
    "射手座": "火",
    "牡牛座": "地",
    "乙女座": "地",
    "山羊座": "地",
    "双子座": "風",
    "天秤座": "風",
    "水瓶座": "風",
    "蟹座": "水",
    "蠍座": "水",
    "魚座": "水",
}

MOON_THEMES = {
    "火": "熱量を小さく動かす",
    "地": "体と現実を整える",
    "風": "言葉と情報を整理する",
    "水": "心の本音に寄り添う",
}

RELATION_GUIDANCE = {
    0: ("主役運", "自分の感覚を最優先に"),
    1: ("準備運", "予定を詰めず余白を作る"),
    2: ("対話運", "短い連絡を一つ返す"),
    3: ("整え運", "家や仕事場を一か所整える"),
    4: ("追い風運", "好きなことに少し時間を使う"),
    5: ("調整運", "抱えすぎた役目を一つ軽くする"),
    6: ("対人運", "相手の言葉を最後まで聞く"),
    7: ("深掘り運", "本音を紙に書き出す"),
    8: ("展開運", "いつもと違う選択を一つ試す"),
    9: ("仕事運", "先に結論を決めて動く"),
    10: ("仲間運", "相談できる人に声をかける"),
    11: ("休息運", "無理に答えを出さず深呼吸を"),
}

REFLECTION_GUIDANCE = {
    0: ("自分の本音が見えた日", "迷ったなら、最初に浮かんだ気持ちを否定しないで"),
    1: ("無理の量に気づく日", "進まなくても、余白を作れたなら十分"),
    2: ("言葉の温度を見直す日", "返せなかった連絡は、明日短く整えれば大丈夫"),
    3: ("居場所を整える日", "片づかなくても、安心できる場所を一つ思い出して"),
    4: ("好きなものに救われる日", "楽しめなかったなら、疲れを先に認めて"),
    5: ("抱えすぎに気づく日", "完璧にできなくても、減らしたい役目が見えたなら前進"),
    6: ("人との距離を測る日", "合わせすぎたなら、今夜は自分の気持ちへ戻って"),
    7: ("心の奥をのぞく日", "重く感じたなら、答えより感情の名前を置いて"),
    8: ("次の可能性を見る日", "動けなかったなら、行きたい方向だけ残して"),
    9: ("現実的な判断をする日", "成果が薄くても、優先順位が見えたなら十分"),
    10: ("誰かとのつながりを感じる日", "頼れなかったなら、明日ひとことだけ声をかけて"),
    11: ("静かに回復する日", "何もできなくても、心を責めない夜にして"),
}

PLANETS = {
    swe.SUN: "太陽",
    swe.MOON: "月",
    swe.MERCURY: "水星",
    swe.VENUS: "金星",
    swe.MARS: "火星",
    swe.JUPITER: "木星",
    swe.SATURN: "土星",
    swe.URANUS: "天王星",
    swe.NEPTUNE: "海王星",
    swe.PLUTO: "冥王星",
}

RETROGRADE_PLANETS = {
    key: name for key, name in PLANETS.items() if key not in (swe.SUN, swe.MOON)
}

# Moshier ephemeris avoids external ephemeris files. SPEED is required for retrograde checks.
FLAG = swe.FLG_MOSEPH | swe.FLG_SPEED


def jd_from(dt_jst: datetime) -> float:
    """Convert a JST datetime to Julian day in UT."""
    ut = dt_jst.astimezone(timezone.utc)
    hour = ut.hour + ut.minute / 60 + ut.second / 3600 + ut.microsecond / 3_600_000_000
    return swe.julday(ut.year, ut.month, ut.day, hour)


def calc(jd: float, planet: int) -> tuple[float, float]:
    """Return ecliptic longitude and daily speed for a planet."""
    pos, _ = swe.calc_ut(jd, planet, FLAG)
    return pos[0] % 360.0, pos[3]


def sign_of(lon: float) -> str:
    """Return the Japanese zodiac sign name for an ecliptic longitude."""
    return SIGNS[int((lon % 360.0) // 30) % 12]


def moon_phase_angle(jd: float) -> float:
    """Return Moon-Sun elongation. 0 means new moon, 180 means full moon."""
    sun_lon, _ = calc(jd, swe.SUN)
    moon_lon, _ = calc(jd, swe.MOON)
    return (moon_lon - sun_lon) % 360.0


def crosses(start: float, end: float, target: float) -> bool:
    """
    Return whether a forward angular sweep from start to end crosses target.

    The sweep is normalized through 360 degrees, so 350 -> 10 crosses 0.
    The start point itself is excluded, while the end point is included.
    """
    start = start % 360.0
    end = end % 360.0
    target = target % 360.0
    distance = (end - start) % 360.0
    if distance == 0:
        return False
    relative_target = (target - start) % 360.0
    return 0 < relative_target <= distance


def phase_name(angle: float) -> str:
    angle = angle % 360.0
    if angle < 45:
        return "新月期"
    if angle < 90:
        return "上弦に向かう月"
    if angle < 135:
        return "満ちていく月"
    if angle < 180:
        return "満月前"
    if angle < 225:
        return "満月直後"
    if angle < 270:
        return "欠けていく月"
    if angle < 315:
        return "下弦の月"
    return "新月前の月"


def todays_sky(now: datetime | None = None) -> dict[str, Any]:
    """Collect today's sky data in JST."""
    now = now.astimezone(JST) if now else datetime.now(JST)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    jd0 = jd_from(day_start)
    jd1 = jd_from(day_end)
    jd_now = jd_from(now)

    events: list[str] = []

    start_phase = moon_phase_angle(jd0)
    end_phase = moon_phase_angle(jd1)
    current_moon_lon, _ = calc(jd_now, swe.MOON)
    current_moon_sign = sign_of(current_moon_lon)

    if crosses(start_phase, end_phase, 0.0):
        events.append(f"今日は{current_moon_sign}の新月")
    if crosses(start_phase, end_phase, 180.0):
        events.append(f"今日は{current_moon_sign}の満月")

    for planet, name in PLANETS.items():
        lon0, speed0 = calc(jd0, planet)
        lon1, speed1 = calc(jd1, planet)
        sign0 = sign_of(lon0)
        sign1 = sign_of(lon1)
        if sign0 != sign1:
            events.append(f"{name}が{sign0}から{sign1}へ移動")
        if planet in RETROGRADE_PLANETS:
            if speed0 >= 0 > speed1:
                events.append(f"{name}が{sign1}で逆行を開始")
            elif speed0 < 0 <= speed1:
                events.append(f"{name}の逆行が{sign1}で終了")

    retrogrades: list[str] = []
    for planet, name in RETROGRADE_PLANETS.items():
        lon, speed = calc(jd_now, planet)
        if speed < 0:
            retrogrades.append(f"{name}({sign_of(lon)})")

    return {
        "date": now.strftime("%Y年%m月%d日"),
        "weekday": f"{WEEKDAYS[now.weekday()]}曜日",
        "moon_sign": current_moon_sign,
        "moon_phase": phase_name(moon_phase_angle(jd_now)),
        "events": events,
        "retrogrades": retrogrades,
    }


def slot_for(now: datetime | None = None) -> str:
    now = now.astimezone(JST) if now else datetime.now(JST)
    if now.hour < 2:
        return "midnight"
    if now.hour < 11:
        return "morning"
    if now.hour < 17:
        return "noon"
    return "night"


SLOT_BRIEF = {
    "midnight": "日付が変わった直後の投稿。今日の星の入口として、日付・月星座・月相・あれば天体イベントを静かに告げる。",
    "morning": "朝8時の投稿。今日の星の動きから、12星座別の運気とやるべきことをスレッドで伝える。",
    "noon": "昼の投稿。占星術の豆知識を、初心者にも分かる言葉で伝える。",
    "night": "夜22時の投稿。今日の星をふり返り、できた人にもできなかった人にも明日へつながる言葉を伝える。",
}

TEMPLATES = {
    "midnight": "日が変わりました。{date}({weekday})の月は{moon_sign}、{moon_phase}。{event_line}今日の星の流れを、静かに受け取って。 #星読み",
    "morning": "{date}({weekday})の月は{moon_sign}。{moon_phase}の流れです。{event_line}今日は気持ちの反応を急がず、自分のペースを整えて。 #星読み",
    "noon": "月は約2.5日ごとに星座を移ります。いまは{moon_sign}。同じ日でも、生まれた時刻と場所で星の地図は変わります。 #占星術",
    "night": "{date}({weekday})の星の振り返り。月は{moon_sign}、{moon_phase}。{event_line}思うように動けなかった人も、気づけたことを一つ残せば十分です。明日はまた違う流れへ。 #星読み",
}


def primary_event_sentence(sky: dict[str, Any]) -> str:
    if not sky["events"]:
        return ""
    return f"{sky['events'][0]}。"


def retrograde_sentence(sky: dict[str, Any]) -> str:
    retrogrades = sky.get("retrogrades", [])
    if not retrogrades:
        return ""
    names = "、".join(retrogrades[:3])
    suffix = "ほか" if len(retrogrades) > 3 else ""
    return f"{names}{suffix}が逆行中。見直しに向く流れ。"


def sky_focus_sentence(sky: dict[str, Any]) -> str:
    if sky.get("events"):
        return primary_event_sentence(sky)
    return retrograde_sentence(sky)


def moon_theme(sky: dict[str, Any]) -> str:
    element = SIGN_ELEMENTS.get(sky["moon_sign"], "地")
    return MOON_THEMES[element]


def sign_guidance_line(sign: str, moon_sign: str) -> str:
    diff = (SIGN_INDEX[sign] - SIGN_INDEX[moon_sign]) % 12
    tone, action = RELATION_GUIDANCE[diff]
    return f"{sign}: {tone}。{action}。"


def sign_reflection_line(sign: str, moon_sign: str) -> str:
    diff = (SIGN_INDEX[sign] - SIGN_INDEX[moon_sign]) % 12
    tone, reflection = REFLECTION_GUIDANCE[diff]
    return f"{sign}: {tone}。{reflection}。"


def trim_tweet(text: str) -> str:
    lines = [" ".join(line.strip().split()) for line in text.strip().splitlines() if line.strip()]
    text = "\n".join(lines)
    if len(text) <= MAX_TWEET_CHARS:
        return text
    return f"{text[: MAX_TWEET_CHARS - 1].rstrip()}…"


def append_link_to_tweet(text: str) -> str:
    text = trim_tweet(text)
    if SITE_URL in text:
        return text
    candidate = f"{text.rstrip()}\n{SITE_URL}"
    if len(candidate) <= MAX_TWEET_CHARS:
        return candidate
    available = MAX_TWEET_CHARS - len(SITE_URL) - 2
    return f"{text[:available].rstrip()}…\n{SITE_URL}"


def build_morning_thread(sky: dict[str, Any]) -> list[str]:
    focus = sky_focus_sentence(sky)
    theme = moon_theme(sky)
    overview = (
        f"{sky['date']}({sky['weekday']})の星。月は{sky['moon_sign']}、{sky['moon_phase']}。"
        f"{focus}今日は「{theme}」が鍵。12星座別は太陽星座を目安に。#星読み"
    )
    posts = [append_link_to_tweet(overview)]
    for group in SIGN_GROUPS:
        lines = [sign_guidance_line(sign, sky["moon_sign"]) for sign in group]
        posts.append(trim_tweet("\n".join(lines)))
    return posts


def build_night_thread(sky: dict[str, Any]) -> list[str]:
    focus = sky_focus_sentence(sky)
    overview = (
        f"{sky['date']}({sky['weekday']})の星の振り返り。月は{sky['moon_sign']}、{sky['moon_phase']}。"
        f"{focus}できたことも、できなかったことも、明日の選び方につながります。#星読み"
    )
    posts = [trim_tweet(overview)]
    for group in SIGN_GROUPS:
        lines = [sign_reflection_line(sign, sky["moon_sign"]) for sign in group]
        posts.append(trim_tweet("\n".join(lines)))
    return posts


def should_include_link(slot: str, sky: dict[str, Any]) -> bool:
    return slot == "morning" or bool(sky["events"])


def append_required_link(text: str, slot: str, sky: dict[str, Any]) -> str:
    if should_include_link(slot, sky) and SITE_URL not in text:
        return f"{text.rstrip()}\n{SITE_URL}"
    return text.rstrip()


def fallback_text(sky: dict[str, Any], slot: str) -> str:
    text = TEMPLATES[slot].format(event_line=primary_event_sentence(sky), **sky)
    return append_required_link(text, slot, sky)


def claude_prompt(sky: dict[str, Any], slot: str) -> str:
    include_link = should_include_link(slot, sky)
    link_rule = (
        f"朝の投稿またはイベント発生日なので、文末に改行して {SITE_URL} を添える。"
        if include_link
        else "リンクは入れない。"
    )
    return f"""あなたは占星術サービス「HOSHIYOMI」の公式Xアカウントの投稿文を作成します。投稿文を1つだけ書いてください。

今日の星のデータ:
{json.dumps(sky, ensure_ascii=False, indent=2)}

投稿スロット:
{SLOT_BRIEF[slot]}

制約:
- 全角120字以内。リンクは字数に含めない
- ハッシュタグは #星読み または #占星術 を1つだけ入れる
- 「絶対」「必ず当たる」などの断定・効果保証表現は禁止
- 不安を煽らない。逆行は「見直しに向く時期」のような前向きな整理にする
- 天体イベント(新月・満月・星座移動・逆行)がある日はそれを最優先で扱う
- {link_rule}
- 投稿文のみを出力する。前置き、説明、引用符は不要"""


def extract_claude_text(payload: dict[str, Any]) -> str:
    parts = []
    for block in payload.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip().strip("\"'「」")


def morning_thread_prompt(sky: dict[str, Any]) -> str:
    return f"""あなたは占星術サービス「HOSHIYOMI」の公式Xアカウントの朝8時投稿スレッドを作成します。

今日の星のデータ:
{json.dumps(sky, ensure_ascii=False, indent=2)}

作るもの:
- Xのスレッド投稿を5件
- 1件目: 今日の星の動きの概要。月星座、月相、重要イベント、今日の鍵を入れる。最後に #星読み と {SITE_URL} を入れる
- 2件目: 牡羊座・牡牛座・双子座の「運気」と「やること」
- 3件目: 蟹座・獅子座・乙女座の「運気」と「やること」
- 4件目: 天秤座・蠍座・射手座の「運気」と「やること」
- 5件目: 山羊座・水瓶座・魚座の「運気」と「やること」

制約:
- JSON配列だけを出力する。説明、前置き、Markdownは禁止
- 配列の要素は文字列5件だけ
- 各投稿は280字以内
- 12星座別は太陽星座を目安にした表現にする
- 「絶対」「必ず当たる」などの断定・効果保証表現は禁止
- 不安を煽らない。逆行は「見直しに向く時期」のような前向きな整理にする
- 天体イベント(新月・満月・星座移動・逆行)がある日は1件目で最優先に扱う"""


def night_thread_prompt(sky: dict[str, Any]) -> str:
    return f"""あなたは占星術サービス「HOSHIYOMI」の公式Xアカウントの夜22時投稿スレッドを作成します。

今日の星のデータ:
{json.dumps(sky, ensure_ascii=False, indent=2)}

作るもの:
- Xのスレッド投稿を5件
- 1件目: 今日の星の動きの振り返り。月星座、月相、重要イベント、今日をどう受け止めるかを入れる。#星読み を1つ入れる
- 2件目: 牡羊座・牡牛座・双子座の「今日の振り返り」と「できなかった時の受け止め方」
- 3件目: 蟹座・獅子座・乙女座の「今日の振り返り」と「できなかった時の受け止め方」
- 4件目: 天秤座・蠍座・射手座の「今日の振り返り」と「できなかった時の受け止め方」
- 5件目: 山羊座・水瓶座・魚座の「今日の振り返り」と「できなかった時の受け止め方」

制約:
- JSON配列だけを出力する。説明、前置き、Markdownは禁止
- 配列の要素は文字列5件だけ
- 各投稿は280字以内
- 12星座別は太陽星座を目安にした表現にする
- 「絶対」「必ず当たる」などの断定・効果保証表現は禁止
- 不安を煽らない。できなかった人を責めず、明日に向けて静かに整える言葉にする
- 天体イベント(新月・満月・星座移動・逆行)がある日は1件目で最優先に扱う"""


def extract_claude_posts(payload: dict[str, Any]) -> list[str]:
    text = extract_claude_text(payload)
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def normalize_thread(posts: list[str], include_link: bool = False) -> list[str]:
    if len(posts) != 5:
        return []
    normalized = [trim_tweet(post) for post in posts]
    if include_link and SITE_URL not in "\n".join(normalized):
        normalized[0] = append_link_to_tweet(normalized[0])
    return normalized


def generate_morning_thread(sky: dict[str, Any]) -> list[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return build_morning_thread(sky)

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
                "max_tokens": 1200,
                "messages": [{"role": "user", "content": morning_thread_prompt(sky)}],
            },
            timeout=60,
        )
        response.raise_for_status()
        posts = normalize_thread(extract_claude_posts(response.json()), include_link=True)
        return posts or build_morning_thread(sky)
    except requests.RequestException as exc:
        print(f"[warn] Anthropic API failed; using zodiac template thread: {exc}", file=sys.stderr)
        return build_morning_thread(sky)


def generate_night_thread(sky: dict[str, Any]) -> list[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return build_night_thread(sky)

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
                "max_tokens": 1200,
                "messages": [{"role": "user", "content": night_thread_prompt(sky)}],
            },
            timeout=60,
        )
        response.raise_for_status()
        posts = normalize_thread(extract_claude_posts(response.json()))
        return posts or build_night_thread(sky)
    except requests.RequestException as exc:
        print(f"[warn] Anthropic API failed; using zodiac reflection thread: {exc}", file=sys.stderr)
        return build_night_thread(sky)


def generate_text(sky: dict[str, Any], slot: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return fallback_text(sky, slot)

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
                "max_tokens": 400,
                "messages": [{"role": "user", "content": claude_prompt(sky, slot)}],
            },
            timeout=60,
        )
        response.raise_for_status()
        text = extract_claude_text(response.json())
        return append_required_link(text, slot, sky) if text else fallback_text(sky, slot)
    except requests.RequestException as exc:
        print(f"[warn] Anthropic API failed; using template mode: {exc}", file=sys.stderr)
        return fallback_text(sky, slot)


def generate_post_texts(sky: dict[str, Any], slot: str) -> list[str]:
    if slot == "morning":
        return generate_morning_thread(sky)
    if slot == "night":
        return generate_night_thread(sky)
    return [generate_text(sky, slot)]


def post_to_x(text: str, reply_to_tweet_id: str | None = None) -> dict[str, Any]:
    required_envs = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]
    missing = [name for name in required_envs if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing X API environment variables: {', '.join(missing)}")

    auth = OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )
    payload: dict[str, Any] = {"text": text}
    if reply_to_tweet_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}

    response = requests.post(
        "https://api.twitter.com/2/tweets",
        auth=auth,
        json=payload,
        timeout=30,
    )
    if response.status_code == 401:
        raise RuntimeError(
            "X API returned 401 Unauthorized. Check that X_API_KEY, X_API_SECRET, "
            "X_ACCESS_TOKEN, and X_ACCESS_SECRET are the OAuth 1.0a values from the "
            "same app, and regenerate the Access Token after setting App permissions "
            f"to Read and write. Response: {response.text}"
        )
    if response.status_code == 403:
        raise RuntimeError(
            "X API returned 403 Forbidden. The app may still be Read only, or the "
            f"account/app may not have permission to create posts. Response: {response.text}"
        )
    if response.status_code == 402:
        raise RuntimeError(
            "X API returned 402 Payment Required. Your X Developer account or app "
            "does not appear to have enough API credits/billing access for POST "
            "/2/tweets. Open the X Developer Console, check Billing & credits, "
            f"purchase/enable credits if required, then rerun. Response: {response.text}"
        )
    response.raise_for_status()
    return response.json()


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    now = datetime.now(JST)
    slot = argv[0] if argv else slot_for(now)
    if slot not in VALID_SLOTS:
        raise SystemExit(f"slot must be one of: {', '.join(VALID_SLOTS)}")

    sky = todays_sky(now)
    print(f"[sky] {json.dumps(sky, ensure_ascii=False)}")

    texts = generate_post_texts(sky, slot)
    for index, text in enumerate(texts, start=1):
        print(f"[post:{slot}:{index}/{len(texts)}]\n{text}\n")

    if os.environ.get("DRY_RUN") == "1":
        print("[dry-run] skipped posting to X")
        return

    results: list[dict[str, Any]] = []
    reply_to_tweet_id: str | None = None
    for text in texts:
        result = post_to_x(text, reply_to_tweet_id)
        results.append(result)
        reply_to_tweet_id = result.get("data", {}).get("id")
        if len(texts) > 1 and not reply_to_tweet_id:
            raise RuntimeError(f"X API response did not include tweet id: {json.dumps(result, ensure_ascii=False)}")

    print(f"[posted] {json.dumps(results, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
