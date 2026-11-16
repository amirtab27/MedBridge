from __future__ import annotations
import functools, json, re, unicodedata
from pathlib import Path
from .models import Flag, Message

DATA = Path(__file__).resolve().parent.parent / "data"


@functools.lru_cache(maxsize=None)
def _load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def detect(text: str, lang: str) -> list[dict]:
    n = lambda x: unicodedata.normalize("NFC", x).replace("\u200d", "").replace("\u200c", "").replace("’", "'")
    d, out = _load("emotion.json"), []
    text = n(text); low = text.lower()
    inten = d["intensifiers"].get(lang, [])
    for cat, langs in d["categories"].items():
        for ph in langs.get(lang, []):
            i = low.find(n(ph).lower())
            if i < 0:
                continue
            before = low[:i]
            has_int = any(n(w).lower() in n(ph).lower() for w in inten)
            if lang == "zh":
                strong = any(w in before[-2:] for w in inten)
            else:
                w3 = " ".join(before.split()[-4:])
                strong = any(re.search(rf"(?<!\w){re.escape(n(w).lower())}(?!\w)", w3) for w in inten)
            out.append({"category": cat, "intensity": "strong" if (strong or has_int) else "normal", "span": text[i:i + len(ph)]})
            break
    return out


def check_emotion(msg: Message, back_translation: str) -> tuple[list[dict], list[Flag]]:
    src = detect(msg.text, msg.src_lang)
    tgt = {e["category"]: e for e in detect(msg.translation, msg.tgt_lang)}
    back = {e["category"]: e for e in detect(back_translation, "en")} if back_translation else {}
    flags = []
    for e in src:
        c = e["category"]
        if c not in tgt and c not in back:
            flags.append(Flag("emotion", "amber", f"Emotion may be lost: {c} ({e['intensity']}); translation reads neutral", e["span"]))
        elif e["intensity"] == "strong" and tgt.get(c, back.get(c))["intensity"] == "normal":
            flags.append(Flag("emotion", "amber", f"Emotion weakened: {c}", e["span"]))
    return src, flags


def check_register(msg: Message) -> list[Flag]:
    if msg.speaker != "doctor":
        return []
    t = msg.translation.lower()
    if msg.tgt_lang == "es" and re.search(r"\b(tienes|debes|puedes|sientes|tu|tú|te duele)\b", t):
        return [Flag("tone", "amber", "Informal register; use usted/आप", "tú")]
    if msg.tgt_lang == "hi" and re.search(r"तुम|तू\b|तुम्हारा|(?<![\u0900-\u0963\u0966-\u097F])(?:पीओ|खाओ|करो|लो|जाओ|आओ|बताओ)(?![\u0900-\u0963\u0966-\u097F])", t):
        return [Flag("tone", "amber", "Informal register; use usted/आप", "तुम")]
    return []


def empathy_line(key: str, lang: str) -> str:
    return _load("empathy.json")[key][lang]
