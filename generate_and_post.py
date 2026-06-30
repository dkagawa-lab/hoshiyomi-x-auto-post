"""
HOSHIYOMI X auto post script.

Calculates the current day's astrology events in JST, creates a short post,
and publishes it to X. Designed to run on GitHub Actions without a server.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import swisseph as swe
from PIL import Image, ImageDraw, ImageFont
from requests_oauthlib import OAuth1

JST = timezone(timedelta(hours=9))
SITE_URL = os.environ.get("SITE_URL", "https://hoshiyomi4u.com/m")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_VERSION = "2023-06-01"
VALID_SLOTS = ("midnight", "morning", "noon", "night")
MAX_TWEET_CHARS = 280
X_POST_RETRIES = int(os.environ.get("X_POST_RETRIES", "3"))
X_POST_RETRY_SECONDS = int(os.environ.get("X_POST_RETRY_SECONDS", "30"))
RANKING_CARD_SIZE = (1080, 1350)
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "out"))
MIDNIGHT_GRACE_HOUR = int(os.environ.get("MIDNIGHT_GRACE_HOUR", "1"))

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

GUIDANCE_VARIANTS = {
    0: [("主役運", "自分の感覚を最優先に"), ("始動運", "朝のうちに小さく一歩だけ動く"), ("自分軸の日", "人に合わせる前に本音を確認する")],
    1: [("準備運", "予定を詰めず余白を作る"), ("温存運", "急ぐ用事ほど一呼吸置く"), ("整備運", "持ち物や予定を一つ軽くする")],
    2: [("対話運", "短い連絡を一つ返す"), ("情報運", "気になったことを一つ調べる"), ("言葉の運", "曖昧な返事をひとつ整える")],
    3: [("整え運", "家や仕事場を一か所整える"), ("土台運", "落ち着ける場所を先に作る"), ("生活運", "食事や睡眠の予定を崩しすぎない")],
    4: [("追い風運", "好きなことに少し時間を使う"), ("表現運", "気分が上がる選択を一つ入れる"), ("遊び心の日", "正しさより楽しさを少し選ぶ")],
    5: [("調整運", "抱えすぎた役目を一つ軽くする"), ("整理運", "細かいタスクを一つ終わらせる"), ("見直し運", "無理している約束を確認する")],
    6: [("対人運", "相手の言葉を最後まで聞く"), ("関係運", "大事な人に柔らかく伝える"), ("バランス運", "譲る所と守る所を分ける")],
    7: [("深掘り運", "本音を紙に書き出す"), ("集中運", "一人で考える時間を少し取る"), ("洞察運", "違和感を急いで消さず観察する")],
    8: [("展開運", "いつもと違う選択を一つ試す"), ("冒険運", "知らない情報に触れてみる"), ("拡張運", "行きたい方向を言葉にする")],
    9: [("仕事運", "先に結論を決めて動く"), ("達成運", "今日の優先順位を一つに絞る"), ("現実運", "数字や期限を先に確認する")],
    10: [("仲間運", "相談できる人に声をかける"), ("つながり運", "一人で抱えず小さく共有する"), ("未来運", "理想に近い人の動きを見る")],
    11: [("休息運", "無理に答えを出さず深呼吸を"), ("回復運", "静かな時間を先に確保する"), ("浄化運", "気が散るものを一つ手放す")],
}

REFLECTION_VARIANTS = {
    0: [("自分の本音が見えた日", "迷ったなら、最初に浮かんだ気持ちを否定しないで"), ("自分に戻る夜", "うまく言えなかった思いも、今夜はそのまま置いて"), ("輪郭が戻る日", "選べなかったことより、感じたことを覚えていて")],
    1: [("無理の量に気づく日", "進まなくても、余白を作れたなら十分"), ("ペースを戻す夜", "急げなかった分、体は何かを守っていたのかも"), ("抱え方を見直す日", "できなかった所に、減らすヒントがあります")],
    2: [("言葉の温度を見直す日", "返せなかった連絡は、明日短く整えれば大丈夫"), ("伝え方を選ぶ夜", "飲み込んだ言葉は、少しやわらかくして明日へ"), ("情報をほどく日", "考えすぎたなら、結論を一晩寝かせて")],
    3: [("居場所を整える日", "片づかなくても、安心できる場所を一つ思い出して"), ("心の帰り道を探す夜", "疲れたなら、誰かの期待から少し離れて"), ("土台を感じる日", "完璧でなくても、休める場所があれば十分")],
    4: [("好きなものに救われる日", "楽しめなかったなら、疲れを先に認めて"), ("ときめきを拾う夜", "気分が乗らなかった自分も責めないで"), ("光を思い出す日", "小さく笑えた瞬間があれば、それを残して")],
    5: [("抱えすぎに気づく日", "完璧にできなくても、減らしたい役目が見えたなら前進"), ("整える前の夜", "散らかったままでも、優先順位が見えれば十分"), ("細部をほどく日", "気になった所を全部直さなくていい")],
    6: [("人との距離を測る日", "合わせすぎたなら、今夜は自分の気持ちへ戻って"), ("関係を眺める夜", "誰かを思った時間も、あなたのやさしさです"), ("バランスを学ぶ日", "うまく譲れなくても、境界線を知れたなら十分")],
    7: [("心の奥をのぞく日", "重く感じたなら、答えより感情の名前を置いて"), ("深いところに触れる夜", "言葉にならない気持ちを急がせないで"), ("静かな洞察の日", "不安の奥にある願いだけ拾って")],
    8: [("次の可能性を見る日", "動けなかったなら、行きたい方向だけ残して"), ("遠くを見る夜", "今すぐ行けなくても、望みは消さなくていい"), ("視野が開く日", "知らなかった選択肢に気づけたなら前進")],
    9: [("現実的な判断をする日", "成果が薄くても、優先順位が見えたなら十分"), ("積み上げを確かめる夜", "進みが遅くても、向き合った時間は残ります"), ("責任をほどく日", "背負いすぎたなら、明日は一つだけ軽くして")],
    10: [("誰かとのつながりを感じる日", "頼れなかったなら、明日ひとことだけ声をかけて"), ("未来を共有する夜", "一人で考えすぎたなら、明日は小さく相談を"), ("仲間を思い出す日", "孤独に見えた時間にも、次の縁の種があります")],
    11: [("静かに回復する日", "何もできなくても、心を責めない夜にして"), ("眠る前にほどく夜", "答えが出ないことは、今夜の荷物にしないで"), ("休む勇気の日", "止まった時間も、明日のあなたを守っています")],
}

TEXT_VARIANTS = {
    "midnight": [
        "{date}({weekday})、今日の月は{moon_sign}。{moon_phase}の入口です。{event_line}急がず、星の流れを一つだけ意識して。 #星読み",
        "{date}({weekday})の空。月は{moon_sign}、{moon_phase}。{event_line}今日の始まりに、心の向きをそっと整えて。 #星読み",
        "新しい日が始まりました。月は{moon_sign}、{moon_phase}。{event_line}今日は小さな違和感を見逃さずに。 #星読み",
    ],
    "noon": [
        "いまの月は{moon_sign}。月は約2.5日で星座を移り、心の反応の出方を少しずつ変えていきます。 #占星術",
        "昼の星読みメモ。月は{moon_sign}にあります。今日の気分の揺れも、空のリズムを知る手がかりです。 #占星術",
        "月がいる星座は、その日の受け取り方に表れます。いまは{moon_sign}。焦らず自分の反応を観察して。 #占星術",
    ],
    "night": [
        "{date}({weekday})の星を振り返る夜。月は{moon_sign}、{moon_phase}。{event_line}できたことも、できなかったことも、明日の選び方につながります。 #星読み",
        "今日の空を閉じる前に。月は{moon_sign}、{moon_phase}。{event_line}進めなかった部分は、責めるより整えるための合図に。 #星読み",
        "夜の星読み。月は{moon_sign}、{moon_phase}。{event_line}今日残った気持ちを、明日の自分へのメモにして。 #星読み",
    ],
}

STYLE_PROFILES = [
    "観察メモ調。感情を押しつけず、星の事実から静かに読む",
    "問いかけ調。読者が自分の一日を思い出せる余白を残す",
    "短い宣言調。冒頭を強くし、同じ語尾を続けない",
    "余韻のある助言調。抽象と具体を一文ずつ混ぜる",
    "実用寄り。今日やることを具体的にし、詩的表現を控えめにする",
]

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

    planet_signs: dict[str, dict[str, str | float | bool]] = {}
    for planet, name in PLANETS.items():
        lon, speed = calc(jd_now, planet)
        planet_signs[name] = {
            "sign": sign_of(lon),
            "longitude": round(lon, 2),
            "retrograde": speed < 0 and planet in RETROGRADE_PLANETS,
        }

    return {
        "date": now.strftime("%Y年%m月%d日"),
        "weekday": f"{WEEKDAYS[now.weekday()]}曜日",
        "moon_sign": current_moon_sign,
        "moon_phase": phase_name(moon_phase_angle(jd_now)),
        "events": events,
        "retrogrades": retrogrades,
        "planet_signs": planet_signs,
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
    "morning": "朝8時の投稿。星の位置から総合運・恋愛運・金運・仕事運を独立したランキングスレッドで伝える。",
    "noon": "昼の投稿。月星座や天体イベントを短い星読みメモとして伝える。",
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


def variation_index(sky: dict[str, Any], slot: str, salt: str, size: int) -> int:
    if size <= 0:
        return 0
    key = f"{sky.get('date', '')}-{sky.get('moon_sign', '')}-{slot}-{salt}"
    return sum((index + 1) * ord(char) for index, char in enumerate(key)) % size


def style_profile(sky: dict[str, Any], slot: str) -> str:
    return STYLE_PROFILES[variation_index(sky, slot, "style", len(STYLE_PROFILES))]


def choose_by_sky(options: list[tuple[str, str]], sky: dict[str, Any], slot: str, salt: str) -> tuple[str, str]:
    return options[variation_index(sky, slot, salt, len(options))]


def sign_guidance_line(sign: str, moon_sign: str) -> str:
    diff = (SIGN_INDEX[sign] - SIGN_INDEX[moon_sign]) % 12
    tone, action = RELATION_GUIDANCE[diff]
    return f"{sign}: {tone}。{action}。"


def varied_sign_guidance_line(sign: str, sky: dict[str, Any], slot: str = "morning") -> str:
    diff = (SIGN_INDEX[sign] - SIGN_INDEX[sky["moon_sign"]]) % 12
    tone, action = choose_by_sky(GUIDANCE_VARIANTS[diff], sky, slot, sign)
    return f"{sign}: {tone}。{action}。"


def sign_reflection_line(sign: str, moon_sign: str) -> str:
    diff = (SIGN_INDEX[sign] - SIGN_INDEX[moon_sign]) % 12
    tone, reflection = REFLECTION_GUIDANCE[diff]
    return f"{sign}: {tone}。{reflection}。"


def varied_sign_reflection_line(sign: str, sky: dict[str, Any], slot: str = "night") -> str:
    diff = (SIGN_INDEX[sign] - SIGN_INDEX[sky["moon_sign"]]) % 12
    tone, reflection = choose_by_sky(REFLECTION_VARIANTS[diff], sky, slot, sign)
    return f"{sign}: {tone}。{reflection}。"


FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

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

RANKING_RELATION_ORDER = [0, 4, 8, 2, 6, 10, 1, 5, 9, 3, 7, 11]

FORTUNE_DOMAINS = [
    {"key": "love", "label": "恋愛運", "planet": "金星", "short": "恋愛", "symbol": "恋"},
    {"key": "money", "label": "金運", "planet": "木星", "short": "金運", "symbol": "金"},
    {"key": "work", "label": "仕事運", "planet": "水星", "short": "仕事", "symbol": "仕"},
]

FORTUNE_DOMAIN_BY_KEY = {domain["key"]: domain for domain in FORTUNE_DOMAINS}
NOON_SECTION_ORDER = ("overall", "love", "money", "work")
NOON_TWEETS_PER_SECTION = 5

FORTUNE_SECTION_META = {
    "overall": {
        "label": "総合運",
        "title": "総合運ランキング",
        "subtitle": "恋愛・金運・仕事を合わせた今日の流れ",
        "color": (232, 199, 121),
        "english": "TOTAL FORTUNE",
        "badge": "今日の総合バランス",
        "index_label": "総合指数",
    },
    "love": {
        "label": "恋愛運",
        "title": "恋愛運ランキング",
        "subtitle": "金星の位置から見る、恋の動き方",
        "color": (225, 151, 180),
        "english": "LOVE FORTUNE",
        "badge": "恋の動き方",
        "index_label": "恋愛指数",
    },
    "money": {
        "label": "金運",
        "title": "金運ランキング",
        "subtitle": "木星の位置から見る、お金の流れ",
        "color": (232, 199, 121),
        "english": "MONEY FORTUNE",
        "badge": "お金の流れ",
        "index_label": "金運指数",
    },
    "work": {
        "label": "仕事運",
        "title": "仕事運ランキング",
        "subtitle": "水星の位置から見る、仕事の進め方",
        "color": (144, 192, 233),
        "english": "WORK FORTUNE",
        "badge": "仕事の進め方",
        "index_label": "仕事指数",
    },
}

FORTUNE_SCORE_BY_DIFF = {
    0: 5,
    4: 5,
    8: 5,
    2: 4,
    6: 4,
    10: 4,
    1: 3,
    5: 3,
    9: 3,
    3: 2,
    7: 2,
    11: 2,
}

FORTUNE_COPY = {
    "love": {
        0: ("本命運", "素直な好意が伝わりやすい"),
        1: ("温め運", "急がず距離を縮める"),
        2: ("会話運", "短い連絡がきっかけになる"),
        3: ("安心運", "弱さを見せるほど近づく"),
        4: ("ときめき運", "楽しい誘いが流れを作る"),
        5: ("調整運", "相手に合わせすぎない"),
        6: ("対人運", "相手の反応をよく見る"),
        7: ("本音運", "嫉妬や不安の奥を読む"),
        8: ("進展運", "いつもと違う誘い方が効く"),
        9: ("現実運", "将来の話を軽く出してみる"),
        10: ("縁運", "友人経由の出会いに目を向ける"),
        11: ("余白運", "追いすぎず相手の余地を残す"),
    },
    "money": {
        0: ("入る運", "得意なことで価値を受け取る"),
        1: ("管理運", "小さな固定費を見直す"),
        2: ("情報運", "買う前に比較すると残る"),
        3: ("守り運", "生活費の安心ラインを整える"),
        4: ("楽しみ運", "好きなことへの投資が活きる"),
        5: ("整理運", "使途不明の出費を一つ止める"),
        6: ("交渉運", "条件を確認してから動く"),
        7: ("共有運", "借り貸しや共同管理を明確に"),
        8: ("拡大運", "学びや移動にお金を回す"),
        9: ("堅実運", "長く使うものを選ぶ"),
        10: ("紹介運", "人からの情報に収穫あり"),
        11: ("節約運", "気分買いを一晩寝かせる"),
    },
    "work": {
        0: ("主役運", "自分の案を先に出す"),
        1: ("準備運", "資料や段取りを整える"),
        2: ("発信運", "確認や共有を早めにする"),
        3: ("基盤運", "作業環境を一つ整える"),
        4: ("評価運", "得意な役割で前に出る"),
        5: ("実務運", "細かいタスクから片づける"),
        6: ("協力運", "相手の目的を聞いて動く"),
        7: ("集中運", "深い作業を先に確保する"),
        8: ("挑戦運", "新しいやり方を試してみる"),
        9: ("達成運", "期限と数字を先に確認する"),
        10: ("チーム運", "相談先を一つ増やす"),
        11: ("調整運", "詰め込みすぎを減らす"),
    },
}

FORTUNE_COPY_VARIANTS = {
    "love": {
        0: [
            ("本命運", "気持ちは濁さず短く伝える", "返事を急かさず、言葉の余韻を残して。"),
            ("直球運", "好意を隠しすぎない", "軽い誘いより、会いたい理由を一つ添えて。"),
            ("主役運", "あなたから空気を温める", "待つより一言。素直さが印象に残ります。"),
        ],
        1: [
            ("温め運", "急がず距離を縮める", "長文より、相手が返しやすい一言を。"),
            ("育てる運", "小さな接点を重ねる", "今日決め切らず、次の会話の種を残して。"),
            ("観察運", "反応の温度を見ながら進む", "押すより合わせる方が、自然に近づけます。"),
        ],
        2: [
            ("会話運", "短い連絡がきっかけになる", "近況を聞くより、具体的な話題を一つ。"),
            ("言葉運", "やわらかな質問が効く", "答えやすい聞き方にすると会話が続きます。"),
            ("接点運", "偶然を会話に変える", "スタンプだけで終わらせず、ひと言添えて。"),
        ],
        3: [
            ("安心運", "弱さを見せるほど近づく", "完璧に見せるより、素の温度を少しだけ。"),
            ("受容運", "甘え方を選ぶ日", "頼るなら重くせず、具体的にお願いして。"),
            ("心ほどき運", "本音の入口が開く", "不安をぶつけず、感じた理由を言葉に。"),
        ],
        4: [
            ("ときめき運", "楽しい誘いが流れを作る", "予定は軽めに。笑える要素を入れると強い日。"),
            ("華やぎ運", "恋の温度を上げやすい", "少しだけ見た目や香りに気を配って。"),
            ("魅力運", "明るい提案が響く", "悩み相談より、楽しい未来を見せると進みます。"),
        ],
        5: [
            ("調整運", "相手に合わせすぎない", "譲る前に、自分がどうしたいかを確認して。"),
            ("整え運", "気遣いの量を見直す", "尽くしすぎるより、心地よい距離を守って。"),
            ("丁寧運", "細かな違和感を流さない", "小さな不満ほど、穏やかに早めに整えて。"),
        ],
        6: [
            ("対人運", "相手の反応をよく見る", "答えを決めつけず、今日は聞き役が効きます。"),
            ("鏡運", "相手の態度から自分も見える", "期待を押しつけず、温度差を観察して。"),
            ("バランス運", "歩幅を合わせるほど安定", "先回りせず、相手の言葉を待つ余白を。"),
        ],
        7: [
            ("本音運", "嫉妬や不安の奥を読む", "責めるより、欲しかった安心を言葉にして。"),
            ("深まり運", "曖昧な感情を見つめる", "極端な結論を出す前に、理由を一つ掘って。"),
            ("核心運", "隠していた望みが出やすい", "重い話は短く、逃げ道を残して伝えて。"),
        ],
        8: [
            ("進展運", "いつもと違う誘い方が効く", "少し遠出や新しい店など、変化を足して。"),
            ("冒険運", "恋の景色を変える日", "普段言わない褒め言葉が流れを動かします。"),
            ("広がり運", "距離を越える提案が吉", "会えない相手にも、未来形の話題を出して。"),
        ],
        9: [
            ("現実運", "将来の話を軽く出してみる", "重く迫らず、生活感のある話題を少しだけ。"),
            ("信頼運", "約束の扱いが印象を決める", "小さな時間厳守が、安心感につながります。"),
            ("地固め運", "関係の土台を整える", "勢いより誠実さ。返事は遅れても丁寧に。"),
        ],
        10: [
            ("縁運", "友人経由の出会いに目を向ける", "一人で探すより、周囲の誘いに乗って。"),
            ("紹介運", "人の輪から恋が動く", "集まりでは聞き役から入ると印象が残ります。"),
            ("未来運", "価値観の近い人に気づく", "肩書きより、会話のテンポを見て。"),
        ],
        11: [
            ("余白運", "追いすぎず相手の余地を残す", "返信待ちは別の予定で心を逃がして。"),
            ("夢見運", "理想を膨らませすぎない", "相手の現実の行動を一つ見て判断して。"),
            ("静かな運", "想いを寝かせるほど整う", "今日は詰めず、やさしい距離感を保って。"),
        ],
    },
    "money": {
        0: [
            ("入る運", "得意なことで価値を受け取る", "遠慮せず、できることを価格や条件に反映して。"),
            ("収穫運", "積み上げた力がお金に近づく", "無料で引き受けすぎていないか見直して。"),
            ("価値運", "自分の強みを出すほど巡る", "得意分野の発信や提案が次の収入種に。"),
        ],
        1: [
            ("管理運", "小さな固定費を見直す", "使っていない契約を一つ切るだけで流れが軽く。"),
            ("整財運", "残す仕組みを作る", "節約より自動で残る形を一つ増やして。"),
            ("所有運", "持ち物と支出を揃える", "安いから買うより、長く使う基準で選んで。"),
        ],
        2: [
            ("情報運", "買う前に比較すると残る", "口コミを二つ以上見てから決めると失敗減。"),
            ("選別運", "情報の取り方で差が出る", "限定や急かし文句には一拍置いて。"),
            ("交渉運", "聞くだけで条件が変わる", "値段だけでなく、保証や期間も確認して。"),
        ],
        3: [
            ("守り運", "生活費の安心ラインを整える", "不安な出費ほど、先に上限を決めて。"),
            ("家計運", "暮らしの土台を見直す", "食費や日用品の買い方に改善余地あり。"),
            ("安心運", "備えが心を落ち着かせる", "小さな予備費を作ると判断がぶれません。"),
        ],
        4: [
            ("楽しみ運", "好きなことへの投資が活きる", "ただの浪費にせず、経験が残る使い方を。"),
            ("喜び運", "気分が上がる支出は厳選して", "一点豪華より、満足が続くものを選んで。"),
            ("創造運", "趣味がお金のヒントに変わる", "好きなものを人に説明すると需要が見えます。"),
        ],
        5: [
            ("整理運", "使途不明の出費を一つ止める", "履歴を見て、記憶にない支払いから確認を。"),
            ("改善運", "細かい支出に答えがある", "完璧な節約より、毎日減らせる一つを。"),
            ("点検運", "数字を見るほど安心が戻る", "怖くても残高と予定支出を並べてみて。"),
        ],
        6: [
            ("交渉運", "条件を確認してから動く", "曖昧な約束は、金額と期限を文字で残して。"),
            ("契約運", "人とのお金を明確にする", "借り貸しや割り勘は早めに線引きを。"),
            ("均衡運", "損得より納得を整える", "相手に合わせる前に、自分の上限を決めて。"),
        ],
        7: [
            ("共有運", "借り貸しや共同管理を明確に", "感情で曖昧にしたお金ほど、今日整理を。"),
            ("深掘り運", "隠れた支出を見つける", "サブスクや手数料に小さな漏れがありそう。"),
            ("再生運", "過去の損を学びに変える", "同じ買い方を繰り返さないルールを一つ。"),
        ],
        8: [
            ("拡大運", "学びや移動にお金を回す", "短期の得より、経験値が増える使い方を。"),
            ("投資運", "視野を広げる支出が吉", "本や講座は、今の悩みに直結するものから。"),
            ("遠方運", "外の情報が金運を広げる", "普段見ない市場やサービスを調べてみて。"),
        ],
        9: [
            ("堅実運", "長く使うものを選ぶ", "安さより修理しやすさ、続けやすさを基準に。"),
            ("積立運", "小さく続けるほど強い", "今日の一回より、毎月の仕組みを整えて。"),
            ("責任運", "数字を締めるほど残る", "支払い期限と優先順位を先に固めて。"),
        ],
        10: [
            ("紹介運", "人からの情報に収穫あり", "信頼できる人のおすすめだけ一つ試して。"),
            ("仲間運", "共同の知恵が金運を動かす", "一人で悩まず、詳しい人に聞くと近道。"),
            ("未来運", "新しい収入口を考える", "副業や発信は、小さく試す案から始めて。"),
        ],
        11: [
            ("節約運", "気分買いを一晩寝かせる", "欲しい理由が曖昧なら、今日は保留が正解。"),
            ("浄化運", "お金の不安をほどく", "買う前に、今あるもので代用できるか確認を。"),
            ("見送り運", "買わない選択が流れを守る", "判断に迷う支出は、明日の自分に渡して。"),
        ],
    },
    "work": {
        0: [
            ("主役運", "自分の案を先に出す", "完璧な資料より、最初の方向性を早めに共有して。"),
            ("先導運", "声を上げるほど進む", "遠慮して後回しにした提案を一つ出して。"),
            ("突破運", "自分発信が場を動かす", "小さな決断を待たずに投げると流れが速い日。"),
        ],
        1: [
            ("準備運", "資料や段取りを整える", "表に出る前の確認が、後の評価を支えます。"),
            ("仕込み運", "見えない作業に価値がある", "明日の自分が楽になる下準備を一つ。"),
            ("安定運", "急がず土台を固める", "新規より、手元の抜け漏れを潰すと強い日。"),
        ],
        2: [
            ("発信運", "確認や共有を早めにする", "迷ったら抱えず、短く状況を出して。"),
            ("連絡運", "言葉の速さが成果になる", "結論を先に置くと、相手が動きやすくなります。"),
            ("調整運", "情報の橋渡しが効く", "自分だけ知っていることは今日共有して。"),
        ],
        3: [
            ("基盤運", "作業環境を一つ整える", "机・通知・予定表のどれかを軽くして。"),
            ("保守運", "足元の仕事を守る", "派手な成果より、ミスを減らす工夫が評価に。"),
            ("安心運", "慣れた手順を整える", "毎回迷う作業は、テンプレ化すると楽です。"),
        ],
        4: [
            ("評価運", "得意な役割で前に出る", "遠慮せず、あなたらしい見せ場を取りにいって。"),
            ("表現運", "魅せ方で印象が変わる", "成果は数字だけでなく、背景も一言添えて。"),
            ("創造運", "遊び心が突破口になる", "堅い場面ほど、わかりやすい例えが効きます。"),
        ],
        5: [
            ("実務運", "細かいタスクから片づける", "五分で終わるものを先に消すと集中が戻ります。"),
            ("精度運", "細部の修正が信頼になる", "見直しは一回多めに。小さな穴を塞いで。"),
            ("改善運", "手順を磨くほど進む", "面倒な作業ほど、一つだけ自動化や短縮を。"),
        ],
        6: [
            ("協力運", "相手の目的を聞いて動く", "自分の正しさより、相手の優先順位を確認して。"),
            ("対話運", "すり合わせで成果が出る", "依頼を受ける前に、完成形を言葉にして。"),
            ("均衡運", "役割分担を整える", "引き受けすぎは禁物。境界線を静かに引いて。"),
        ],
        7: [
            ("集中運", "深い作業を先に確保する", "通知を切る時間を作ると、一気に進みます。"),
            ("核心運", "問題の根に触れやすい", "表面の修正より、原因を一つ特定して。"),
            ("探究運", "難所に向き合うほど強い", "避けていたタスクを、短時間だけ開いてみて。"),
        ],
        8: [
            ("挑戦運", "新しいやり方を試してみる", "成功前提でなく、検証として小さく始めて。"),
            ("拡張運", "視野を広げるほど進む", "他業界のやり方にヒントが見つかります。"),
            ("前進運", "少し背伸びした選択が吉", "不安でも、学びながら進む余地があります。"),
        ],
        9: [
            ("達成運", "期限と数字を先に確認する", "ゴールを曖昧にしないほど成果が出ます。"),
            ("責任運", "約束の精度が評価になる", "納期・範囲・優先度を一度言語化して。"),
            ("実績運", "積み重ねが見える日", "終わったことも記録し、成果として残して。"),
        ],
        10: [
            ("チーム運", "相談先を一つ増やす", "一人で抱える前に、視点の違う人へ投げて。"),
            ("連携運", "人の力を借りるほど進む", "相談は弱さではなく、速度を上げる選択です。"),
            ("構想運", "先の流れを共有する", "今だけでなく、次の一手まで話すと味方が増えます。"),
        ],
        11: [
            ("調整運", "詰め込みすぎを減らす", "今日やらないことを決めるほど大事な仕事が残ります。"),
            ("休ませ運", "余白が判断力を戻す", "無理な集中より、区切りを作って回復して。"),
            ("手放し運", "完璧主義を少し緩める", "七割で出して、反応を見ながら磨くと進みます。"),
        ],
    },
}

OVERALL_DETAIL_TEMPLATES = [
    "{topic}から動くと、他のテーマも整いやすい日。",
    "迷ったらまず{topic}を優先すると、流れをつかみやすい日。",
    "{topic}の一歩が、今日全体の手応えにつながります。",
    "午前中は{topic}を先に片づけると、午後の判断が軽くなります。",
    "{topic}で小さく勝ち筋を作ると、他の運気にも弾みが出ます。",
    "今日は{topic}を広げすぎず、一点集中にすると成果が残ります。",
    "{topic}に関する迷いを一つ減らすだけで、全体の流れが澄みます。",
    "人に合わせすぎず、{topic}の優先順位を先に決めて動いて。",
    "{topic}は勢いより整え方。焦らず順番を決めると安定します。",
    "今日の突破口は{topic}。小さな行動を早めに置くのが鍵です。",
    "{topic}を後回しにしないほど、夕方の満足感が変わります。",
    "まず{topic}の不要な迷いを削ると、一日全体が扱いやすくなります。",
]

OVERALL_TONE_VARIANTS = [
    "主役級の流れ",
    "一日を動かす軸",
    "流れをつかむ星回り",
    "使いどころが多い日",
    "追い風を拾う日",
    "得意分野を活かす日",
    "テーマを絞る日",
    "整えて伸ばす日",
    "小さく勝ちに行く日",
    "無理せず整える日",
    "余白を守る日",
    "立て直しが効く日",
]


def find_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            if current:
                lines.append(current)
                current = ""
            continue
        candidate = f"{current}{char}"
        if current and text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = char.lstrip()
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def line_height(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, line_gap: int = 5) -> int:
    box = draw.textbbox((0, 0), "星", font=font)
    return box[3] - box[1] + line_gap


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_gap: int = 5,
) -> int:
    step = line_height(draw, font, line_gap)
    for line in wrap_text(draw, text, font, max_width):
        draw.text((x, y), line, font=font, fill=fill)
        y += step
    return y


def draw_centered_wrapped(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_gap: int = 5,
) -> int:
    step = line_height(draw, font, line_gap)
    for line in wrap_text(draw, text, font, max_width):
        width = text_width(draw, line, font)
        draw.text(((RANKING_CARD_SIZE[0] - width) // 2, y), line, font=font, fill=fill)
        y += step
    return y


def draw_centered(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    width = text_width(draw, text, font)
    draw.text(((RANKING_CARD_SIZE[0] - width) // 2, y), text, font=font, fill=fill)


def blend_color(
    color: tuple[int, int, int],
    base: tuple[int, int, int] = (9, 13, 34),
    ratio: float = 0.5,
) -> tuple[int, int, int]:
    return tuple(int(base[index] * (1 - ratio) + color[index] * ratio) for index in range(3))


def draw_theme_motif(
    draw: ImageDraw.ImageDraw,
    section_key: str,
    accent: tuple[int, int, int],
) -> None:
    color = blend_color(accent, ratio=0.62)
    faint = blend_color(accent, ratio=0.28)
    if section_key == "love":
        cx, cy = 915, 178
        draw.ellipse((cx - 52, cy - 42, cx + 8, cy + 18), fill=faint, outline=color, width=2)
        draw.ellipse((cx - 8, cy - 42, cx + 52, cy + 18), fill=faint, outline=color, width=2)
        draw.polygon([(cx - 60, cy - 4), (cx + 60, cy - 4), (cx, cy + 76)], fill=faint, outline=color)
        return
    if section_key == "money":
        for offset, radius in ((0, 56), (-44, 42), (46, 38)):
            cx, cy = 902 + offset, 188 + abs(offset) // 4
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=faint, outline=color, width=3)
            draw.arc((cx - radius + 14, cy - radius + 14, cx + radius - 14, cy + radius - 14), 35, 325, fill=color, width=3)
        return
    if section_key == "work":
        base_y = 242
        xs = [824, 872, 922, 976]
        ys = [226, 192, 210, 154]
        for index in range(len(xs) - 1):
            draw.line((xs[index], ys[index], xs[index + 1], ys[index + 1]), fill=color, width=6)
        for x, y in zip(xs, ys):
            draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=accent)
        for index, x in enumerate(xs):
            draw.rounded_rectangle((x - 13, base_y - index * 18, x + 13, base_y + 52), radius=7, fill=faint, outline=color, width=2)
        return

    cx, cy = 905, 190
    for radius in (74, 48, 22):
        draw.ellipse((cx - radius, cy - radius // 2, cx + radius, cy + radius // 2), outline=color, width=2)
    draw.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=accent)
    draw.ellipse((cx + 54, cy - 18, cx + 68, cy - 4), fill=color)


def parse_sign_reading_line(line: str) -> tuple[str, str, str]:
    normalized = line.replace(":", "：", 1).strip()
    sign, _, rest = normalized.partition("：")
    parts = [part.strip() for part in rest.split("。") if part.strip()]
    tone = parts[0] if parts else ""
    action = parts[1] if len(parts) > 1 else ""
    return sign, tone, action


def ranking_signs_for_sky(sky: dict[str, Any], slot: str) -> list[str]:
    moon_index = SIGN_INDEX[sky["moon_sign"]]

    def rank_key(sign: str) -> tuple[int, int]:
        diff = (SIGN_INDEX[sign] - moon_index) % 12
        return (RANKING_RELATION_ORDER.index(diff), variation_index(sky, slot, sign, 3))

    return sorted(SIGNS, key=rank_key)


def zodiac_ranking_items(sky: dict[str, Any], slot: str) -> list[dict[str, str | int]]:
    mode = "night" if slot == "night" else "morning"
    items: list[dict[str, str | int]] = []
    for rank, sign in enumerate(ranking_signs_for_sky(sky, mode), start=1):
        line = (
            varied_sign_reflection_line(sign, sky, "night")
            if mode == "night"
            else varied_sign_guidance_line(sign, sky, "morning")
        )
        _, tone, action = parse_sign_reading_line(line)
        items.append(
            {
                "rank": rank,
                "sign": sign,
                "short": SIGN_SHORT_LABELS.get(sign, sign.replace("座", "")),
                "tone": tone,
                "comment": action,
            }
        )
    return items


def planet_sign_from_sky(sky: dict[str, Any], planet_name: str) -> str:
    planet_signs = sky.get("planet_signs", {})
    if isinstance(planet_signs, dict):
        value = planet_signs.get(planet_name)
        if isinstance(value, dict) and isinstance(value.get("sign"), str):
            return str(value["sign"])
        if isinstance(value, str):
            return value
    return str(sky.get("moon_sign", "牡羊座"))


def fortune_detail_for_sign(sky: dict[str, Any], sign: str, domain: dict[str, str]) -> dict[str, str | int]:
    planet_sign = planet_sign_from_sky(sky, domain["planet"])
    diff = (SIGN_INDEX[sign] - SIGN_INDEX[planet_sign]) % 12
    variants = FORTUNE_COPY_VARIANTS.get(domain["key"], {}).get(diff)
    if variants:
        tone, comment, detail = variants[
            variation_index(sky, domain["key"], f"{sign}-{diff}-copy", len(variants))
        ]
    else:
        tone, comment = FORTUNE_COPY[domain["key"]][diff]
        detail = "今日の流れに合わせ、無理なく一つだけ動いて。"
    return {
        "domain": domain["key"],
        "label": domain["label"],
        "short": domain["short"],
        "planet": domain["planet"],
        "planet_sign": planet_sign,
        "tone": tone,
        "comment": comment,
        "detail": detail,
        "score": FORTUNE_SCORE_BY_DIFF[diff],
        "order": RANKING_RELATION_ORDER.index(diff),
    }


def three_fortune_items(sky: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for sign in SIGNS:
        fortunes = {domain["key"]: fortune_detail_for_sign(sky, sign, domain) for domain in FORTUNE_DOMAINS}
        dominant = max(fortunes.values(), key=lambda item: (int(item["score"]), -int(item["order"])))
        items.append({"sign": sign, "fortunes": fortunes, "dominant": dominant})
    return items


def fortune_domain_rankings(sky: dict[str, Any], domain_key: str) -> list[dict[str, Any]]:
    items = three_fortune_items(sky)

    def rank_key(item: dict[str, Any]) -> tuple[int, int, int]:
        fortune = item["fortunes"][domain_key]
        return (-int(fortune["score"]), int(fortune["order"]), SIGN_INDEX[item["sign"]])

    return sorted(items, key=rank_key)


def overall_fortune_rankings(sky: dict[str, Any]) -> list[dict[str, Any]]:
    items = three_fortune_items(sky)

    def rank_key(item: dict[str, Any]) -> tuple[int, int, int, int]:
        fortunes = item["fortunes"]
        total_score = sum(int(fortune["score"]) for fortune in fortunes.values())
        total_order = sum(int(fortune["order"]) for fortune in fortunes.values())
        dominant_order = int(item["dominant"]["order"])
        return (-total_score, total_order, dominant_order, SIGN_INDEX[item["sign"]])

    return sorted(items, key=rank_key)


def fortune_index_score(sky: dict[str, Any], section_key: str, item: dict[str, Any], rank: int) -> int:
    """Return a visible 100-point index derived from rank with deterministic variation."""
    offset = variation_index(sky, section_key, str(item["sign"]), 2)
    return max(60, 98 - (rank - 1) * 3 - offset)


def fortune_ranking_items(sky: dict[str, Any], section_key: str) -> list[dict[str, Any]]:
    if section_key == "overall":
        ranked = overall_fortune_rankings(sky)
    elif section_key in FORTUNE_DOMAIN_BY_KEY:
        ranked = fortune_domain_rankings(sky, section_key)
    else:
        raise ValueError(f"unknown fortune section: {section_key}")

    items: list[dict[str, Any]] = []
    for rank, item in enumerate(ranked, start=1):
        visible_score = fortune_index_score(sky, section_key, item, rank)
        if section_key == "overall":
            fortunes = item["fortunes"]
            raw_score = sum(int(fortune["score"]) for fortune in fortunes.values())
            tone_offset = variation_index(sky, "overall", "tone-order", len(OVERALL_TONE_VARIANTS))
            tone = OVERALL_TONE_VARIANTS[(rank - 1 + tone_offset) % len(OVERALL_TONE_VARIANTS)]
            comment = (
                f"恋愛{fortunes['love']['tone']}・"
                f"金運{fortunes['money']['tone']}・"
                f"仕事{fortunes['work']['tone']}"
            )
            dominant = item["dominant"]
            detail_offset = variation_index(sky, "overall", "detail-order", len(OVERALL_DETAIL_TEMPLATES))
            detail_template = OVERALL_DETAIL_TEMPLATES[(rank - 1 + detail_offset) % len(OVERALL_DETAIL_TEMPLATES)]
            detail = detail_template.format(topic=dominant["short"])
        else:
            fortune = item["fortunes"][section_key]
            raw_score = int(fortune["score"])
            tone = str(fortune["tone"])
            comment = str(fortune["comment"])
            detail = str(fortune["detail"])

        items.append(
            {
                **item,
                "rank": rank,
                "short": SIGN_SHORT_LABELS.get(item["sign"], item["sign"].replace("座", "")),
                "score": visible_score,
                "raw_score": raw_score,
                "tone": tone,
                "comment": comment,
                "detail": detail,
            }
        )
    return items


def three_fortune_overview(sky: dict[str, Any]) -> str:
    parts = []
    for domain in FORTUNE_DOMAINS:
        parts.append(f"{domain['short']}={domain['planet']}{planet_sign_from_sky(sky, domain['planet'])}")
    return " / ".join(parts)


def format_three_fortune_line(item: dict[str, Any]) -> str:
    sign = item["sign"]
    fortunes = item["fortunes"]
    dominant = item["dominant"]
    return (
        f"{sign}: "
        f"恋愛{fortunes['love']['tone']}・"
        f"金運{fortunes['money']['tone']}・"
        f"仕事{fortunes['work']['tone']}。"
        f"{dominant['short']}は{dominant['comment']}。{dominant['detail']}"
    )


def format_fortune_ranking_line(item: dict[str, Any], section_key: str, include_detail: bool = True) -> str:
    rank = item["rank"]
    sign = item["sign"]
    index_label = FORTUNE_SECTION_META[section_key]["index_label"]
    index_text = f"{index_label}{item['score']}/100"
    if section_key == "overall":
        dominant = item["dominant"]
        if include_detail:
            return f"{rank}位 {sign}: {index_text}。{item['comment']}。{item['detail']}"
        return f"{rank}位 {sign}: {index_text}。{item['tone']}。{item['comment']}。{dominant['short']}を先に。"
    if include_detail:
        return f"{rank}位 {sign}: {index_text}。{item['tone']}。{item['comment']}。{item['detail']}"
    return f"{rank}位 {sign}: {index_text}。{item['tone']}。{item['comment']}。"


def noon_section_header(sky: dict[str, Any], section_key: str) -> str:
    if section_key == "overall":
        variants = [
            f"朝の星読み。まずは総合運ランキング。{three_fortune_overview(sky)}。恋愛・金運・仕事を合わせて、今日の流れが強い順に見ます。#星読み",
            f"今日の総合運ランキング。{three_fortune_overview(sky)}。3つの運気を合わせ、動きやすい星座から順に読みます。#占星術",
            f"12星座別、今日の総合運。{three_fortune_overview(sky)}。恋愛・お金・仕事の重なりから順位を出しました。#星読み",
        ]
        text = variants[variation_index(sky, "morning", "overall-header", len(variants))]
        return append_link_to_tweet(text)

    domain = FORTUNE_DOMAIN_BY_KEY[section_key]
    planet_sign = planet_sign_from_sky(sky, domain["planet"])
    variants = [
        f"{domain['label']}ランキング。{domain['planet']}は{planet_sign}。太陽星座を目安に、今日の{domain['short']}の動き方を見ていきます。#星読み",
        f"今日の{domain['label']}。{domain['planet']}が{planet_sign}にある今日、流れに乗りやすい星座から順に読みます。#占星術",
        f"今日の{domain['label']}。鍵になる天体は{domain['planet']}、位置は{planet_sign}。12星座別に使いどころを見ます。#星読み",
    ]
    return trim_tweet(variants[variation_index(sky, "morning", f"{section_key}-header", len(variants))])


def build_noon_thread(sky: dict[str, Any]) -> list[str]:
    posts: list[str] = []
    for section_key in NOON_SECTION_ORDER:
        posts.append(noon_section_header(sky, section_key))
        ranked_items = fortune_ranking_items(sky, section_key)
        for offset in range(0, len(ranked_items), 3):
            lines = [format_fortune_ranking_line(item, section_key) for item in ranked_items[offset : offset + 3]]
            posts.append(trim_tweet("\n".join(lines)))
    return posts


def three_fortunes_caption(sky: dict[str, Any]) -> str:
    sections: list[str] = []
    for section_key in NOON_SECTION_ORDER:
        meta = FORTUNE_SECTION_META[section_key]
        ranked_lines = [
            format_fortune_ranking_line(item, section_key, include_detail=False).replace(":", "：", 1)
            for item in fortune_ranking_items(sky, section_key)
        ]
        sections.append(f"{meta['label']}\n" + "\n".join(ranked_lines))
    return (
        f"{sky['date']}の星座別ランキング。\n"
        f"{three_fortune_overview(sky)}。\n\n"
        "総合運、恋愛運、金運、仕事運をそれぞれ独立して読みます。\n"
        "太陽星座を目安に、気になるテーマから見てください。\n\n"
        + "\n\n".join(sections)
        + f"\n\n出生図から深く読むならプロフィールへ。\n{SITE_URL}\n\n#星読み #占星術 #HOSHIYOMI"
    )


def create_ranking_background(seed: str) -> Image.Image:
    width, height = RANKING_CARD_SIZE
    image = Image.new("RGB", RANKING_CARD_SIZE, (9, 13, 34))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = int(9 + 17 * ratio)
        g = int(13 + 13 * ratio)
        b = int(34 + 28 * ratio)
        draw.line((0, y, width, y), fill=(r, g, b))

    seed_value = sum((index + 1) * ord(char) for index, char in enumerate(seed))
    for index in range(130):
        x = (seed_value * (index + 13) * 37) % width
        y = (seed_value * (index + 29) * 19) % height
        brightness = 110 + ((seed_value + index * 23) % 110)
        radius = 1 if index % 7 else 2
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(brightness, brightness, min(255, brightness + 28)))

    return image


def generate_ranking_card(
    sky: dict[str, Any],
    slot: str,
    output_path: Path,
    now: datetime | None = None,
) -> Path:
    now = now or datetime.now(JST)
    mode = "night" if slot == "night" else "morning"
    image = create_ranking_background(f"{sky['date']}-{mode}-ranking")
    draw = ImageDraw.Draw(image)

    brand_font = find_font(48)
    small_font = find_font(24)
    title_font = find_font(52)
    rank_font = find_font(34)
    sign_font = find_font(31)
    top_body_font = find_font(19)
    list_font = find_font(20)

    gold = (232, 199, 121)
    pale = (248, 236, 192)
    white = (248, 246, 235)
    muted = (187, 181, 206)
    border = (88, 80, 132)
    panel = (17, 20, 52)
    accent = (178, 135, 79)

    draw_centered(draw, 48, "HOSHIYOMI", brand_font, gold)
    subtitle = "12星座ランキング / 今日の使い方" if mode == "morning" else "12星座ランキング / 夜の振り返り"
    draw_centered(draw, 108, f"{subtitle}", small_font, muted)
    draw_centered(draw, 154, f"{sky['date']} {sky['moon_sign']}の月", title_font, pale)
    focus = sky_focus_sentence(sky) or f"今日の鍵は「{moon_theme(sky)}」。"
    draw_centered_wrapped(draw, 218, focus, small_font, gold, 920)

    items = zodiac_ranking_items(sky, mode)
    top_items = items[:3]
    top_y = 286
    top_w = 298
    gap = 22
    start_x = (RANKING_CARD_SIZE[0] - top_w * 3 - gap * 2) // 2
    for index, item in enumerate(top_items):
        x = start_x + index * (top_w + gap)
        h = 240
        draw.rounded_rectangle((x, top_y, x + top_w, top_y + h), radius=28, fill=panel, outline=gold, width=3)
        draw.text((x + 22, top_y + 20), f"{item['rank']}位", font=rank_font, fill=gold)
        draw.text((x + 22, top_y + 68), str(item["sign"]), font=sign_font, fill=white)
        next_y = draw_wrapped_text(draw, x + 22, top_y + 112, str(item["tone"]), top_body_font, pale, top_w - 44, 4)
        draw_wrapped_text(draw, x + 22, next_y + 6, str(item["comment"]), top_body_font, muted, top_w - 44, 4)

    list_y = 560
    row_h = 112
    col_gap = 20
    col_w = 462
    left_x = 58
    right_x = left_x + col_w + col_gap
    for index, item in enumerate(items[3:]):
        column = 0 if index < 5 else 1
        row = index if index < 5 else index - 5
        x = left_x if column == 0 else right_x
        y = list_y + row * (row_h + 12)
        draw.rounded_rectangle((x, y, x + col_w, y + row_h), radius=18, fill=panel, outline=border, width=1)
        draw.rectangle((x, y, x + 5, y + row_h), fill=accent)
        draw.text((x + 18, y + 16), f"{item['rank']}位", font=list_font, fill=gold)
        draw.text((x + 92, y + 16), str(item["sign"]), font=list_font, fill=white)
        comment = f"{item['tone']}。{item['comment']}"
        draw_wrapped_text(draw, x + 18, y + 52, comment, list_font, muted, col_w - 36, 4)

    note = "詳しい星座別コメントは、この投稿のスレッドへ。"
    if mode == "night":
        note = "詳しい星座別の振り返りは、この投稿のスレッドへ。"
    draw_centered(draw, 1236, note, small_font, pale)
    draw_centered(draw, 1280, "hoshiyomi4u.com", small_font, gold)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=92, optimize=True)
    return output_path


def generate_three_fortunes_card(
    sky: dict[str, Any],
    output_path: Path,
    now: datetime | None = None,
) -> Path:
    now = now or datetime.now(JST)
    image = create_ranking_background(f"{sky['date']}-three-fortunes")
    draw = ImageDraw.Draw(image)

    brand_font = find_font(46)
    small_font = find_font(23)
    title_font = find_font(55)
    domain_font = find_font(31)
    rank_font = find_font(23)
    sign_font = find_font(26)
    body_font = find_font(18)
    foot_font = find_font(24)

    gold = (232, 199, 121)
    pale = (248, 236, 192)
    white = (248, 246, 235)
    muted = (187, 181, 206)
    border = (88, 80, 132)
    panel = (17, 20, 52)
    accent = (178, 135, 79)

    draw_centered(draw, 48, "HOSHIYOMI", brand_font, gold)
    draw_centered(draw, 104, f"{sky['date']} / 星で見るテーマ別運勢", small_font, muted)
    draw_centered(draw, 154, "恋愛運・金運・仕事運", title_font, pale)
    draw_centered_wrapped(draw, 222, three_fortune_overview(sky), small_font, gold, 940)

    column_w = 304
    gap = 26
    start_x = (RANKING_CARD_SIZE[0] - column_w * 3 - gap * 2) // 2
    top_y = 306
    domain_colors = {
        "love": (225, 151, 180),
        "money": (232, 199, 121),
        "work": (144, 192, 233),
    }

    for index, domain in enumerate(FORTUNE_DOMAINS):
        x = start_x + index * (column_w + gap)
        domain_key = domain["key"]
        color = domain_colors[domain_key]
        draw.rounded_rectangle((x, top_y, x + column_w, 1100), radius=30, fill=panel, outline=border, width=2)
        draw.rounded_rectangle((x + 18, top_y + 18, x + column_w - 18, top_y + 86), radius=22, fill=(24, 28, 67), outline=color, width=2)
        draw.text((x + 36, top_y + 33), str(domain["label"]), font=domain_font, fill=color)
        draw.text(
            (x + 36, top_y + 92),
            f"{domain['planet']}が{planet_sign_from_sky(sky, domain['planet'])}",
            font=small_font,
            fill=muted,
        )

        for rank, item in enumerate(fortune_domain_rankings(sky, domain_key)[:4], start=1):
            fortune = item["fortunes"][domain_key]
            y = top_y + 146 + (rank - 1) * 148
            draw.rounded_rectangle((x + 18, y, x + column_w - 18, y + 126), radius=20, fill=(13, 17, 45), outline=(58, 56, 98), width=1)
            draw.rectangle((x + 18, y, x + 23, y + 126), fill=color)
            draw.text((x + 36, y + 18), f"{rank}位", font=rank_font, fill=gold)
            draw.text((x + 92, y + 16), str(item["sign"]), font=sign_font, fill=white)
            draw.text((x + 36, y + 54), str(fortune["tone"]), font=rank_font, fill=pale)
            draw_wrapped_text(draw, x + 36, y + 84, str(fortune["comment"]), body_font, muted, column_w - 72, 4)

    draw.rounded_rectangle((104, 1140, 976, 1218), radius=26, fill=(12, 16, 42), outline=border, width=1)
    draw_centered(draw, 1162, "全12星座の詳しい運勢は、この投稿のスレッドへ。", foot_font, pale)
    draw_centered(draw, 1278, "hoshiyomi4u.com", foot_font, gold)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=92, optimize=True)
    return output_path


def generate_fortune_ranking_card(
    sky: dict[str, Any],
    section_key: str,
    output_path: Path,
    now: datetime | None = None,
) -> Path:
    now = now or datetime.now(JST)
    if section_key not in FORTUNE_SECTION_META:
        raise ValueError(f"unknown fortune section: {section_key}")

    meta = FORTUNE_SECTION_META[section_key]
    accent_color = tuple(meta["color"])
    image = create_ranking_background(f"{sky['date']}-{section_key}-fortune-ranking")
    draw = ImageDraw.Draw(image)

    brand_font = find_font(46)
    small_font = find_font(23)
    title_font = find_font(54)
    badge_font = find_font(22)
    rank_font = find_font(34)
    sign_font = find_font(31)
    top_body_font = find_font(17)
    list_font = find_font(20)
    list_comment_font = find_font(17)

    gold = (232, 199, 121)
    pale = (248, 236, 192)
    white = (248, 246, 235)
    muted = (187, 181, 206)
    border = (88, 80, 132)
    panel = (17, 20, 52)

    draw_theme_motif(draw, section_key, accent_color)
    draw_centered(draw, 48, "HOSHIYOMI", brand_font, gold)
    draw_centered(draw, 104, f"{sky['date']} / 太陽星座別", small_font, muted)
    draw_centered(draw, 154, str(meta["title"]), title_font, pale)
    badge_text = f"{meta['english']}  |  {meta['badge']}"
    badge_w = min(820, text_width(draw, badge_text, badge_font) + 72)
    badge_x1 = (RANKING_CARD_SIZE[0] - badge_w) // 2
    draw.rounded_rectangle((badge_x1, 214, badge_x1 + badge_w, 258), radius=22, fill=(18, 22, 56), outline=accent_color, width=2)
    draw_centered(draw, 224, badge_text, badge_font, accent_color)
    if section_key == "overall":
        subtitle = f"{meta['subtitle']}。{three_fortune_overview(sky)}。"
    else:
        domain = FORTUNE_DOMAIN_BY_KEY[section_key]
        subtitle = f"{meta['subtitle']}。{domain['planet']}は{planet_sign_from_sky(sky, domain['planet'])}。"
    draw_centered_wrapped(draw, 268, subtitle, small_font, accent_color, 920)

    items = fortune_ranking_items(sky, section_key)
    top_items = items[:3]
    top_y = 326
    top_w = 298
    gap = 22
    start_x = (RANKING_CARD_SIZE[0] - top_w * 3 - gap * 2) // 2
    for index, item in enumerate(top_items):
        x = start_x + index * (top_w + gap)
        h = 260
        draw.rounded_rectangle((x, top_y, x + top_w, top_y + h), radius=28, fill=panel, outline=accent_color, width=3)
        draw.text((x + 22, top_y + 20), f"{item['rank']}位", font=rank_font, fill=gold)
        draw.text((x + 22, top_y + 68), str(item["sign"]), font=sign_font, fill=white)
        score_text = f"{meta['index_label']} {item['score']}/100"
        draw.rounded_rectangle((x + 22, top_y + 108, x + top_w - 22, top_y + 143), radius=17, fill=(24, 28, 67), outline=accent_color, width=1)
        draw_center_x = x + top_w // 2
        score_w = text_width(draw, score_text, top_body_font)
        draw.text((draw_center_x - score_w // 2, top_y + 115), score_text, font=top_body_font, fill=accent_color)
        next_y = draw_wrapped_text(draw, x + 22, top_y + 154, str(item["tone"]), top_body_font, pale, top_w - 44, 4)
        top_comment = f"{item['comment']}。{item['detail']}"
        draw_wrapped_text(draw, x + 22, next_y + 4, top_comment, top_body_font, muted, top_w - 44, 4)

    list_y = 608
    row_h = 112
    col_gap = 20
    col_w = 462
    left_x = 58
    right_x = left_x + col_w + col_gap
    for index, item in enumerate(items[3:]):
        column = 0 if index < 5 else 1
        row = index if index < 5 else index - 5
        x = left_x if column == 0 else right_x
        y = list_y + row * (row_h + 10)
        draw.rounded_rectangle((x, y, x + col_w, y + row_h), radius=18, fill=panel, outline=border, width=1)
        draw.rectangle((x, y, x + 5, y + row_h), fill=accent_color)
        draw.text((x + 18, y + 16), f"{item['rank']}位", font=list_font, fill=gold)
        draw.text((x + 92, y + 16), str(item["sign"]), font=list_font, fill=white)
        score_text = f"{item['score']}/100"
        score_w = text_width(draw, score_text, list_font)
        draw.text((x + col_w - score_w - 20, y + 16), score_text, font=list_font, fill=accent_color)
        comment = f"{item['tone']}。{item['comment']}。{item['detail']}"
        draw_wrapped_text(draw, x + 18, y + 50, comment, list_comment_font, muted, col_w - 36, 3)

    draw_centered(draw, 1236, "詳しい星座別コメントは、この投稿のスレッドへ。", small_font, pale)
    draw_centered(draw, 1280, "hoshiyomi4u.com", small_font, gold)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=92, optimize=True)
    return output_path


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
    overview_variants = [
        f"{sky['date']}({sky['weekday']})の星。月は{sky['moon_sign']}、{sky['moon_phase']}。{focus}今日は「{theme}」が鍵。12星座別は太陽星座を目安に。#星読み",
        f"朝の星読み。月は{sky['moon_sign']}、{sky['moon_phase']}。{focus}今日のテーマは「{theme}」。太陽星座別に見ていきます。#星読み",
        f"{sky['date']}の空は、月が{sky['moon_sign']}に滞在中。{focus}今日は{theme}ことから始めて。12星座別の流れです。#星読み",
    ]
    overview = overview_variants[variation_index(sky, "morning", "overview", len(overview_variants))]
    posts = [append_link_to_tweet(overview)]
    for group in SIGN_GROUPS:
        lines = [varied_sign_guidance_line(sign, sky) for sign in group]
        posts.append(trim_tweet("\n".join(lines)))
    return posts


def build_night_thread(sky: dict[str, Any]) -> list[str]:
    focus = sky_focus_sentence(sky)
    overview_variants = [
        f"{sky['date']}({sky['weekday']})の星の振り返り。月は{sky['moon_sign']}、{sky['moon_phase']}。{focus}できたことも、できなかったことも、明日の選び方につながります。#星読み",
        f"夜の星読み。月は{sky['moon_sign']}、{sky['moon_phase']}。{focus}今日残った気持ちは、明日の自分へのメモにして。#星読み",
        f"一日を閉じる前に。月は{sky['moon_sign']}、{sky['moon_phase']}。{focus}うまくいかなかった所にも、次のヒントがあります。#星読み",
    ]
    overview = overview_variants[variation_index(sky, "night", "overview", len(overview_variants))]
    posts = [trim_tweet(overview)]
    for group in SIGN_GROUPS:
        lines = [varied_sign_reflection_line(sign, sky) for sign in group]
        posts.append(trim_tweet("\n".join(lines)))
    return posts


def should_include_link(slot: str, sky: dict[str, Any]) -> bool:
    return slot == "morning" or bool(sky["events"])


def append_required_link(text: str, slot: str, sky: dict[str, Any]) -> str:
    if should_include_link(slot, sky) and SITE_URL not in text:
        return f"{text.rstrip()}\n{SITE_URL}"
    return text.rstrip()


def fallback_text(sky: dict[str, Any], slot: str) -> str:
    templates = TEXT_VARIANTS.get(slot, [TEMPLATES[slot]])
    template = templates[variation_index(sky, slot, "fallback", len(templates))]
    text = template.format(event_line=primary_event_sentence(sky), **sky)
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

今日の文体指定:
{style_profile(sky, slot)}

制約:
- 全角120字以内。リンクは字数に含めない
- ハッシュタグは #星読み または #占星術 を1つだけ入れる
- 「絶対」「必ず当たる」などの断定・効果保証表現は禁止
- 不安を煽らない。逆行は「見直しに向く時期」のような前向きな整理にする
- 天体イベント(新月・満月・星座移動・逆行)がある日はそれを最優先で扱う
- 直近投稿と同じように見える定型文を避ける。「今日の星」「整える」「鍵」「明日へ」の同時多用は禁止
- 導入文、語尾、文のリズムを前回と変える。毎回「月は〜」で始めない
- 抽象表現だけにせず、ひとつだけ具体的な行動や視点を入れる
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

今日の文体指定:
{style_profile(sky, "morning")}

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
- 前回と同じ型に見える投稿は禁止。各星座の「運気名」と「やること」は、似た言い回しを連続させない
- 「整える」「見直す」「余白」「気づく」を全投稿で繰り返しすぎない
- 天体イベント(新月・満月・星座移動・逆行)がある日は1件目で最優先に扱う
- 3星座ごとの投稿は、各行の語尾をできるだけ変える"""


def night_thread_prompt(sky: dict[str, Any]) -> str:
    return f"""あなたは占星術サービス「HOSHIYOMI」の公式Xアカウントの夜22時投稿スレッドを作成します。

今日の星のデータ:
{json.dumps(sky, ensure_ascii=False, indent=2)}

今日の文体指定:
{style_profile(sky, "night")}

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
- 天体イベント(新月・満月・星座移動・逆行)がある日は1件目で最優先に扱う
- 前回と同じ型に見える投稿は禁止。各星座の「振り返り名」と「受け止め方」は、似た言い回しを連続させない
- 「できなかった」「責めない」「明日」を全行で繰り返しすぎない
- 3星座ごとの投稿は、各行の語尾をできるだけ変える"""


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
        return build_noon_thread(sky)
    if slot == "noon":
        return [generate_text(sky, slot)]
    if slot == "night":
        return generate_night_thread(sky)
    return [generate_text(sky, slot)]


def should_skip_late_midnight(slot: str, now: datetime) -> bool:
    return slot == "midnight" and now.astimezone(JST).hour >= MIDNIGHT_GRACE_HOUR


def is_duplicate_tweet_response(response: requests.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except ValueError:
        return "duplicate content" in response.text.lower()

    detail = str(payload.get("detail", ""))
    title = str(payload.get("title", ""))
    return "duplicate content" in f"{detail} {title}".lower()


def x_auth() -> OAuth1:
    required_envs = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]
    missing = [name for name in required_envs if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing X API environment variables: {', '.join(missing)}")

    return OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )


def upload_media_to_x(image_path: Path) -> str:
    with image_path.open("rb") as image_file:
        response = requests.post(
            "https://upload.twitter.com/1.1/media/upload.json",
            auth=x_auth(),
            files={"media": image_file},
            data={"media_category": "tweet_image"},
            timeout=60,
        )
    if response.status_code == 401:
        raise RuntimeError(
            "X media upload returned 401 Unauthorized. Regenerate OAuth 1.0a Access "
            f"Token and Secret after enabling Read and write. Response: {response.text}"
        )
    if response.status_code == 403:
        raise RuntimeError(
            "X media upload returned 403 Forbidden. Check that the app has media "
            f"upload/post permissions. Response: {response.text}"
        )
    response.raise_for_status()
    payload = response.json()
    media_id = payload.get("media_id_string") or payload.get("media_id")
    if not media_id:
        raise RuntimeError(f"X media upload response did not include media id: {json.dumps(payload, ensure_ascii=False)}")
    return str(media_id)


def post_to_x(
    text: str,
    reply_to_tweet_id: str | None = None,
    media_ids: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"text": text}
    if reply_to_tweet_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}

    response: requests.Response | None = None
    for attempt in range(1, X_POST_RETRIES + 1):
        response = requests.post(
            "https://api.twitter.com/2/tweets",
            auth=x_auth(),
            json=payload,
            timeout=30,
        )
        retryable_cloudflare = response.status_code == 403 and (
            "Just a moment" in response.text or "challenge-platform" in response.text
        )
        retryable_status = response.status_code in (429, 500, 502, 503, 504)
        if not retryable_cloudflare and not retryable_status:
            break
        if attempt >= X_POST_RETRIES:
            break

        wait_seconds = X_POST_RETRY_SECONDS * attempt
        reason = "Cloudflare challenge" if retryable_cloudflare else f"HTTP {response.status_code}"
        print(
            f"[warn] X API returned {reason}; retrying in {wait_seconds}s "
            f"({attempt}/{X_POST_RETRIES})",
            file=sys.stderr,
        )
        time.sleep(wait_seconds)

    if response is None:
        raise RuntimeError("X API request was not sent")

    if is_duplicate_tweet_response(response):
        print(
            "[warn] X API reported duplicate content; treating this tweet as "
            "already posted and stopping the current run safely.",
            file=sys.stderr,
        )
        return {"duplicate": True, "status_code": response.status_code, "response": response.text}

    if response.status_code == 401:
        raise RuntimeError(
            "X API returned 401 Unauthorized. Check that X_API_KEY, X_API_SECRET, "
            "X_ACCESS_TOKEN, and X_ACCESS_SECRET are the OAuth 1.0a values from the "
            "same app, and regenerate the Access Token after setting App permissions "
            f"to Read and write. Response: {response.text}"
        )
    if response.status_code == 403:
        if "Just a moment" in response.text or "challenge-platform" in response.text:
            raise RuntimeError(
                "X API returned 403 Forbidden with a Cloudflare challenge after "
                f"{X_POST_RETRIES} attempts. This is usually a temporary block on "
                f"GitHub Actions runner traffic. Response: {response.text[:800]}"
            )
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
    if should_skip_late_midnight(slot, now):
        print(
            f"[skip] Midnight post started at {now.isoformat()}, "
            "so it is too late to publish a day-change post."
        )
        return

    sky = todays_sky(now)
    print(f"[sky] {json.dumps(sky, ensure_ascii=False)}")

    texts = generate_post_texts(sky, slot)
    for index, text in enumerate(texts, start=1):
        print(f"[post:{slot}:{index}/{len(texts)}]\n{text}\n")

    media_paths_by_post_index: dict[int, Path] = {}
    if slot == "morning":
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        for section_index, section_key in enumerate(NOON_SECTION_ORDER):
            filename = f"{timestamp}-{slot}-{section_key}.jpg"
            path = generate_fortune_ranking_card(sky, section_key, OUTPUT_DIR / filename, now)
            post_index = section_index * NOON_TWEETS_PER_SECTION + 1
            media_paths_by_post_index[post_index] = path
            print(f"[x:{slot}:{section_key}_image:{post_index}] {path}")
    elif slot == "night":
        filename = f"{now.strftime('%Y%m%d-%H%M%S')}-{slot}-ranking.jpg"
        path = generate_ranking_card(sky, slot, OUTPUT_DIR / filename, now)
        media_paths_by_post_index[1] = path
        print(f"[x:{slot}:ranking_image] {path}")

    if os.environ.get("DRY_RUN") == "1":
        print("[dry-run] skipped posting to X")
        return

    media_ids_by_post_index: dict[int, str] = {}
    for post_index, image_path in media_paths_by_post_index.items():
        media_id = upload_media_to_x(image_path)
        media_ids_by_post_index[post_index] = media_id
        print(f"[x:media_id:{post_index}] {media_id}")

    results: list[dict[str, Any]] = []
    reply_to_tweet_id: str | None = None
    for index, text in enumerate(texts, start=1):
        if slot == "morning" and index in media_paths_by_post_index:
            reply_to_tweet_id = None
        media_id = media_ids_by_post_index.get(index)
        media_ids = [media_id] if media_id else None
        result = post_to_x(text, reply_to_tweet_id, media_ids=media_ids)
        results.append(result)
        if result.get("duplicate"):
            print("[duplicate] X already has this content; skipped remaining tweets to avoid duplicates.")
            break

        reply_to_tweet_id = result.get("data", {}).get("id")
        if len(texts) > 1 and not reply_to_tweet_id:
            raise RuntimeError(f"X API response did not include tweet id: {json.dumps(result, ensure_ascii=False)}")

    print(f"[posted] {json.dumps(results, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
