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
