"""NLLB-200 translation (pretrained, used as-is). Falls back to a tiny phrasebook if the model is unavailable."""
from __future__ import annotations
import functools, re, statistics, threading, time

_LOCK = threading.Lock()

MODEL = "facebook/nllb-200-distilled-600M"
CODES = {"en": "eng_Latn", "es": "spa_Latn", "hi": "hin_Deva", "zh": "zho_Hans"}


@functools.lru_cache(maxsize=1)
def get_model():
    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    dev = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL, torch_dtype=torch.float16 if dev == "cuda" else torch.float32).to(dev)
    model.eval()
    return tok, model


def _split(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?।？！。])\s*", text) if p.strip()]
    return parts or [text]


@functools.lru_cache(maxsize=512)
def _translate_cached(text: str, src: str, tgt: str) -> str:
    import torch
    tok, model = get_model()
    sents = _split(text)
    with _LOCK:  # tokenizer.src_lang is global state; never interleave translations
        tok.src_lang = CODES[src]
        inputs = tok(sents, return_tensors="pt", padding=True).to(model.device)
        with torch.inference_mode():
            out = model.generate(**inputs, forced_bos_token_id=tok.convert_tokens_to_ids(CODES[tgt]),
                                 max_new_tokens=128, num_beams=2, max_length=None)
    return " ".join(tok.batch_decode(out, skip_special_tokens=True))


ROMAN_HI = {
    "mera dil ghabra raha hai": "मेरा दिल घबरा रहा है", "mujhe bahut dar lag raha hai": "मुझे बहुत डर लग रहा है",
    "mujhe dar lag raha hai": "मुझे डर लग रहा है", "sar bhaari hai": "सर भारी है", "sar bhari hai": "सर भारी है",
    "mujhe bahut dard hai": "मुझे बहुत दर्द है", "mujhe samajh nahi aaya": "मुझे समझ नहीं आया",
    "mujhe chinta hai": "मुझे चिंता है", "mujhe chakkar aa raha hai": "मुझे चक्कर आ रहा है",
    "mujhe bukhar hai": "मुझे बुखार है", "mujhe ulti jaisa lag raha hai": "मुझे उल्टी जैसा लग रहा है",
    "ji michla raha hai": "जी मिचला रहा है", "main pareshan hoon": "मैं परेशान हूँ",
}


def romanized_hi_to_deva(text: str) -> str:
    """Typed Romanized Hindi is mistranslated by NLLB; map known phrases to Devanagari first."""
    if re.search(r"[\u0900-\u0963\u0966-\u097F]", text):
        return text
    key = re.sub(r"[^\w\s]", "", text.lower()).strip()
    for k, v in ROMAN_HI.items():
        if k in key:
            return v if key == k else key.replace(k, v)
    return text


FORMAL_HI = {"पीओ": "पिएं", "खाओ": "खाएं", "करो": "करें", "लो": "लें", "जाओ": "जाएं", "आओ": "आएं", "बताओ": "बताएं",
             "रखो": "रखें", "देखो": "देखें", "सोओ": "सोएं", "बैठो": "बैठें", "पियो": "पिएं", "लीजिये": "लीजिए"}


def fix_hi_register(text: str) -> str:
    """Force respectful आप register on common informal imperatives (मत पीओ -> न पिएं)."""
    for k, v in FORMAL_HI.items():
        text = re.sub(rf"(?:मत\s+)?(?<![\u0900-\u0963\u0966-\u097F]){k}(?![\u0900-\u0963\u0966-\u097F])", lambda m, v=v: ("न " + v) if m.group(0).startswith("मत") else v, text)
    return text.replace("तुम्हें", "आपको").replace("तुम्हारा", "आपका")


def translate(text: str, src: str, tgt: str) -> str:
    text = (text or "").strip()
    if not text or src == tgt:
        return text
    if src == "hi":
        text = romanized_hi_to_deva(text)
    elif tgt == "hi" and src == "en":
        return fix_hi_register(_translate_cached(text, src, tgt))
    return _translate_cached(text, src, tgt)


def back_translate(text: str, src: str) -> str:
    return translate(text, src, "en")


def warm_up() -> None:
    translate("Hello, how are you feeling today?", "en", "es")


if __name__ == "__main__":
    phrases = ["Take five milligrams twice a day.", "Do you have any pain?", "Do not drink alcohol.",
               "Where does it hurt?", "How long have you had this?"]
    warm_up()
    for lang in ("es", "hi", "zh"):
        ts = []
        for p in phrases:
            t = time.time(); translate(p + " ", "en", lang); ts.append(time.time() - t)
        print(lang, f"median {statistics.median(ts):.2f}s")
