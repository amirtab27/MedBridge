from __future__ import annotations
import re, unicodedata
from .emotion import _load
from .models import Flag, Message


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s.lower()).replace("\u200d", "").replace("\u200c", "")
    return re.sub(r"[^\w\s\u0900-\u097F]", "", s).strip()


def check_culture(msg: Message) -> list[Flag]:
    t, flags = _norm(msg.text), []
    for e in _load("culture.json"):
        if e["lang"] != msg.src_lang:
            continue
        for v in [e["expression"], *e["variants"]]:
            if _norm(v) in t:
                flags.append(Flag("culture", "amber", f"Ambiguous expression: could mean {', '.join(e['possible_meanings'])}",
                                  e["expression"], e["question"]["en"]))
                break
    return flags


def question_for(span: str, lang: str) -> str | None:
    for e in _load("culture.json"):
        if e["lang"] == lang and _norm(e["expression"]) == _norm(span):
            return e["question"].get(lang)
    return None
