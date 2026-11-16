"""Rule-based clinical-safety comparison between source and translation."""
from __future__ import annotations
import re, unicodedata
from .models import Flag, Message

DEV = str.maketrans("०१२३४५६७८९", "0123456789")
WORDS = {
    "en": "zero one two three four five six seven eight nine ten fifteen twenty fifty hundred".split(),
    "es": "cero uno dos tres cuatro cinco seis siete ocho nueve diez quince veinte cincuenta cien".split(),
    "hi": "शून्य एक दो तीन चार पाँच पांच छह सात आठ नौ दस पंद्रह बीस पचास सौ".split(),
    "zh": [],
}
VALS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 50, 100]
NUMWORDS: dict[str, dict[str, int]] = {}
for lg, ws in WORDS.items():
    d = {}
    for w in ws:
        i = ws.index(w)
        d[w] = VALS[i] if i < len(VALS) else 0
    NUMWORDS[lg] = d
NUMWORDS["hi"]["पांच"] = 5
NUMWORDS["hi"]["छः"] = 6
NUMWORDS["es"].update({"una": 1, "un": 1})
NUMWORDS["en"].update({"a": 0})
NUMWORDS["en"].pop("a")
ZH = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

UNITS = {
    "mg": ["mg", "milligram", "milligrams", "miligramos", "miligramo", "मिलीग्राम", "毫克"],
    "g": ["grams", "gramos", "ग्राम", "克"],
    "ml": ["ml", "milliliters", "mililitros", "मिलीलीटर", "毫升"],
    "mcg": ["mcg", "micrograms", "microgramos", "माइक्रोग्राम", "微克"],
    "tablet": ["tablet", "tablets", "pill", "pills", "tableta", "tabletas", "pastilla", "pastillas", "comprimido", "comprimidos",
               "गोली", "गोलियां", "गोलियाँ", "टैबलेट", "片", "粒", "颗"],
}
UNIT_LOOKUP = {w: u for u, ws in UNITS.items() for w in ws}
NEG = {
    "en": ["not", "don't", "didn't", "doesn't", "can't", "won't", "cannot", "do not", "never", "no", "avoid"],
    "es": ["no", "nunca", "jamás", "evite", "evitar"],
    "hi": ["नहीं", "मत", "न", "nahi", "mat", "बचें"],
    "zh": ["不", "别", "不要", "勿", "禁止"],
}
FREQ_PATTERNS = {
    "en": [(r"\bonce (a|per) day\b|\bdaily\b", "1/day"), (r"\btwice (a|per) day\b", "2/day"),
           (r"\b(three times|thrice) (a|per) day\b", "3/day"), (r"\bevery (\d+) hours\b", "q{0}h"),
           (r"\bat night\b|\bbedtime\b", "night")],
    "es": [(r"una vez al día|diariamente", "1/day"), (r"dos veces (al|por) día", "2/day"),
           (r"tres veces (al|por) día", "3/day"), (r"cada (\d+) horas", "q{0}h"), (r"por la noche|al acostarse", "night")],
    "hi": [(r"दिन में एक बार|रोज़ एक बार|रोज एक बार", "1/day"), (r"दिन में दो बार", "2/day"),
           (r"दिन में तीन बार", "3/day"), (r"हर (\d+) घंटे", "q{0}h"), (r"रात (को|में)|सोते समय", "night")],
    "zh": [(r"每天一次|一天一次", "1/day"), (r"每天两次|一天两次|每天二次", "2/day"),
           (r"每天三次|一天三次", "3/day"), (r"每(\d+)小时", "q{0}h"), (r"晚上|睡前", "night")],
}


TIMES = {"1/day": ("once", "one time", "1 time"), }


def _generic_freq(low: str, lang: str) -> list[str]:
    out = []
    n = lambda tok: _num(tok, lang)
    pats = {"en": [r"(\w+) times? (?:a|per|each) day", r"(\w+) times? daily"],
            "es": [r"(\w+) veces (?:al|por|cada) día"],
            "hi": [r"(?:दिन में|रोज़|रोज|प्रतिदिन)\s+(\S+)\s+बार", r"(\S+)\s+बार\s+(?:प्रतिदिन|रोज़|रोज|दैनिक)"],
            "zh": []}
    for pat in pats.get(lang, []):
        for m in re.finditer(pat, low):
            v = n(m.group(1)) if lang != "en" else (n(m.group(1)) or {"twice": 2, "thrice": 3}.get(m.group(1)))
            if v:
                out.append(f"{int(v)}/day")
    if lang == "hi":
        for m in re.finditer(r"हर\s+(\S+)\s+घंटे", low):
            v = n(m.group(1))
            if v:
                out.append(f"q{int(v)}h")
    return out


# A "no"/"नहीं"/"不" that stands alone at the start of a clause is an answer or interjection ("No.. I feel bad"),
# not a negated instruction, so it must not count as a negation.
INTERJ = {
    "en": r"(^|[.!?…,;]\s*)(?:no|nope|nah)(?:[\s,]+(?:no|nope))*\s*(?:[,.…!?;:\-]+|$)",
    "es": r"(^|[.!?…,;¿¡]\s*)(?:no|nop)(?:[\s,]+no)*\s*(?:[,.…!?;:\-]+|$)",
    "hi": r"(^|[।.!?…,;]\s*)(?:नहीं|नही|ना|नहिं)(?:[\s,]+(?:नहीं|नही))*\s*(?:[,।.…!?;:\-]+|$)",
    "zh": r"(^|[，。！？…,.!?]\s*)不(?:是|对)?\s*(?:[，。！？…,.!?]+|$)",
}
# Words that make a sentence a medical directive (medication, food, drink, activity), where a lost "not" is dangerous.
DIRECTIVE = re.compile(
    r"\b(take|taking|drink|eat|use|avoid|stop|dose|doses|medicine|medication|tablet|pill|pills|alcohol|food|stomach|mg|ml|"
    r"tomar|tome|beba|beber|coma|comer|use|evite|medicina|medicamento|pastilla|alcohol|dosis)\b|"
    r"दवा|लें|पिएं|पीएं|खाएं|शराब|गोली|खुराक|药|吃|喝|酒|片|服用|毫克|मिलीग्राम|miligramos|milligram", re.I)


def _strip_interjections(low: str, lang: str) -> str:
    pat = INTERJ.get(lang)
    if not pat:
        return low
    prev = None
    while prev != low:
        prev = low
        low = re.sub(pat, r"\1 ", low)
    return low


def _num(tok: str, lang: str) -> float | None:
    tok = tok.translate(DEV)
    if re.fullmatch(r"\d+(\.\d+)?", tok):
        return float(tok)
    return NUMWORDS.get(lang, {}).get(tok.lower())


def extract_facts(text: str, lang: str) -> dict:
    t = unicodedata.normalize("NFC", text).translate(DEV).replace("\u200d", "").replace("\u200c", "")
    low = t.lower().replace("’", "'")
    doses, numbers = [], []
    unit_words = sorted(UNIT_LOOKUP, key=len, reverse=True)
    uni = "|".join(re.escape(u) for u in unit_words)
    numtok = r"(\d+(?:\.\d+)?|[\u0900-\u0963\u0966-\u097F]+|[^\W\d_]+|[零一二两三四五六七八九十]+)"
    for m in re.finditer(rf"{numtok}\s*({uni})", low):
        raw = m.group(1)
        n = _num(raw, lang)
        if n is None and lang == "zh" and all(c in ZH for c in raw):
            n = float(ZH[raw[-1]]) if len(raw) == 1 else (10.0 if raw == "十" else None)
        if n is not None:
            doses.append((n, UNIT_LOOKUP[m.group(2)]))
    for m in re.finditer(r"\d+(?:\.\d+)?", low):
        numbers.append(float(m.group()))
    freqs = []
    for pat, norm in FREQ_PATTERNS.get(lang, []):
        for m in re.finditer(pat, low):
            freqs.append(norm.format(*m.groups()[-1:]) if "{0}" in norm else norm)
    low = _strip_interjections(low, lang)
    freqs += _generic_freq(low, lang)
    freqs = sorted(set(freqs))
    negs = 0
    if lang == "zh":
        negs = len(re.findall(r"不要|禁止|勿|别|不", low))
    elif lang == "hi":
        toks = re.split(r"[\s,.;:!?।]+", low)
        negs = sum(1 for t in toks if t in NEG["hi"])
    else:
        for w in sorted(NEG.get(lang, []), key=len, reverse=True):
            c = len(re.findall(rf"(?<!\w){re.escape(w)}(?!\w)", low))
            if c:
                low = re.sub(rf"(?<!\w){re.escape(w)}(?!\w)", " ", low)
                negs += c
    return {"doses": doses, "frequencies": sorted(freqs), "negations": negs, "numbers": numbers}


def _fmt(d): return " ".join(f"{n:g} {u}" for n, u in d)


def check_safety(msg: Message) -> list[Flag]:
    a, b = extract_facts(msg.text, msg.src_lang), extract_facts(msg.translation, msg.tgt_lang)
    flags: list[Flag] = []
    if a["doses"]:
        na = sorted(n for n, _ in a["doses"]); nb = sorted(n for n, _ in b["doses"])
        ua = sorted(u for _, u in a["doses"]); ub = sorted(u for _, u in b["doses"])
        if not nb and set(na) <= set(b["numbers"]):
            flags.append(Flag("safety", "amber", "Dose unit missing in the translation", _fmt(a["doses"])))
        elif na != nb:
            flags.append(Flag("safety", "red", f"Dose changed: {_fmt(a['doses'])} → {_fmt(b['doses']) or 'missing'}", _fmt(a["doses"]),
                              "Repeat the dose and confirm it with the patient."))
        elif ua != ub:
            flags.append(Flag("safety", "amber", "Dose unit missing or different in the translation", _fmt(a["doses"])))
    if a["frequencies"] != b["frequencies"] and a["frequencies"]:
        flags.append(Flag("safety", "red", f"Frequency changed: {', '.join(a['frequencies'])} → {', '.join(b['frequencies']) or 'missing'}",
                          ", ".join(a["frequencies"]), "Repeat how often the medicine is taken."))
    if a["negations"] != b["negations"]:
        directive = bool(DIRECTIVE.search(msg.text) or DIRECTIVE.search(msg.translation))
        if msg.speaker == "doctor" and directive:
            flags.append(Flag("safety", "red", "A 'do not' may have been dropped or added in an instruction", "negation",
                              "Rephrase the instruction and confirm it."))
        else:  # conversational negation (e.g. a patient describing how they feel): worth a glance, never a safety alarm
            flags.append(Flag("safety", "info", "Negation may differ between original and translation — check the meaning", "negation"))
    big = [n for n in a["numbers"] if n >= 10]
    if big:
        flags.append(Flag("safety", "info", f"Confirm number: {big[0]:g} (speech recognition confuses 15/50)", f"{big[0]:g}"))
    return flags


def inject_error(translation: str, lang: str) -> str:
    """Demo helper: multiply the first number by 10 and drop the first negation."""
    t = translation.translate(DEV)
    m = re.search(r"\d+(?:\.\d+)?", t)
    if m:
        v = float(m.group()) * 10
        t = t[:m.start()] + (f"{v:g}") + t[m.end():]
    if lang == "zh":
        t = re.sub(r"不要|禁止|勿|别|不", "", t, count=1)
    elif lang == "hi":
        t = re.sub(r"(?:(?<=\s)|^)(?:नहीं|मत|न)(?=[\s,.।!?]|$)\s*", "", t, count=1)
    else:
        for w in sorted(NEG.get(lang, []), key=len, reverse=True):
            n = re.sub(rf"(?<!\w){re.escape(w)}(?!\w)\s*", "", t, count=1, flags=re.I)
            if n != t:
                t = n; break
    return t
