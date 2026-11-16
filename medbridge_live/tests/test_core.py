import pytest
from medbridge.models import Message
from medbridge.safety import check_safety, inject_error, extract_facts
from medbridge.emotion import detect, check_emotion, check_register
from medbridge.culture import check_culture, question_for


def M(src, tgt, text, tr, speaker="doctor"):
    return Message("x", speaker, src, tgt, text, tr, True)


def levels(fl): return sorted(f.level for f in fl if f.level != "info")


@pytest.mark.parametrize("m,expected", [
    (M("en", "es", "Take 5 mg twice a day. Do not drink alcohol.", "Tome 5 mg dos veces al día. No beba alcohol."), []),
    (M("en", "es", "Take 5 mg twice a day. Do not drink alcohol.", "Tome 50 mg dos veces al día. Beba alcohol."), ["red", "red"]),
    (M("en", "es", "Take 5 mg twice a day.", "Tome 5 mg tres veces al día."), ["red"]),
    (M("en", "hi", "Take 5 milligrams twice a day.", "दिन में दो बार 5 मिलीग्राम लें।"), []),
    (M("en", "hi", "Take 5 milligrams twice a day.", "दिन में दो बार ५० मिलीग्राम लें।"), ["red"]),
    (M("en", "hi", "Do not drink alcohol.", "शराब पिएं।"), ["red"]),
    (M("en", "zh", "Take 5 milligrams twice a day. Do not drink.", "每天两次，每次5毫克。请不要饮酒。"), []),
    (M("en", "zh", "Take 5 milligrams twice a day.", "每天三次，每次5毫克。"), ["red"]),
    (M("en", "es", "Take 5 mg.", "Tome 5."), ["amber"]),
    (M("en", "es", "Take five milligrams twice a day.", "Tome cinco miligramos dos veces al día."), []),
])
def test_safety(m, expected):
    assert levels(check_safety(m)) == expected


def test_inject_roundtrip():
    bad = inject_error("Tome 5 miligramos dos veces al día. No beba alcohol.", "es")
    assert "50" in bad and "No beba" not in bad
    assert len([f for f in check_safety(M("en", "es", "Take 5 mg twice a day. Do not drink alcohol.", bad)) if f.level == "red"]) == 2


def test_fifteen_flag():
    assert any(f.level == "info" and "15" in f.reason for f in check_safety(M("en", "es", "Take 15 mg.", "Tome 15 mg.")))


def test_emotion_zh():
    cats = {e["category"]: e["intensity"] for e in detect("我很害怕，我不明白", "zh")}
    assert cats == {"fear": "strong", "confusion": "normal"}


def test_emotion_lost():
    m = M("es", "en", "Tengo mucho miedo", "I have a problem", "patient")
    _, fl = check_emotion(m, "")
    assert fl and fl[0].level == "amber"
    _, fl = check_emotion(M("es", "en", "Tengo mucho miedo", "I am very scared", "patient"), "")
    assert not fl


def test_culture_hi_roman_and_devanagari():
    for t in ("Mera dil ghabra raha hai", "मेरा दिल घबरा रहा है"):
        fl = check_culture(M("hi", "en", t, "x", "patient"))
        assert len(fl) == 1 and fl[0].kind == "culture"
    assert question_for("Mera dil ghabra raha hai", "hi").startswith("क्या आपको")


def test_register():
    assert check_register(M("en", "es", "x", "¿Tienes dolor?"))
    assert not check_register(M("en", "es", "x", "¿Tiene dolor?"))
    assert check_register(M("en", "hi", "x", "क्या तुम ठीक हो?"))
