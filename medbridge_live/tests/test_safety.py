import json, pathlib
from medbridge.models import Message
from medbridge.safety import check_safety, inject_error


def mk(src, tgt, text, tr):
    return Message("t", "doctor", src, tgt, text, tr, True)


def levels(m): return [f.level for f in check_safety(m)]


def test_dose_and_negation():
    m = mk("en", "es", "Take 5 mg twice a day. Do not drink alcohol.", "Tome 50 mg dos veces al día. Beba alcohol.")
    assert levels(m).count("red") == 2

def test_clean_spanish():
    m = mk("en", "es", "Take 5 mg twice a day. Do not drink alcohol.", "Tome 5 mg dos veces al día. No beba alcohol.")
    assert "red" not in levels(m)

def test_clean_hindi():
    m = mk("en", "hi", "Take 5 mg twice a day.", "दिन में दो बार 5 मिलीग्राम लें।")
    assert "red" not in levels(m)

def test_frequency():
    m = mk("en", "es", "Take it twice a day.", "Tómelo tres veces al día.")
    assert "red" in levels(m)

def test_inject_roundtrip():
    bad = inject_error("Tome 5 mg dos veces al día. No beba alcohol.", "es")
    assert "50" in bad and "No" not in bad


def test_hindi_digits_and_words():
    from medbridge.safety import extract_facts
    assert extract_facts("दिन में दो बार ५ मिलीग्राम लें।", "hi")["doses"] == [(5.0, "mg")]
    assert extract_facts("पाँच मिलीग्राम", "hi")["doses"] == [(5.0, "mg")]
    assert extract_facts("दिन में 3 बार", "hi")["frequencies"] == ["3/day"]
    assert extract_facts("दिन में दिन", "hi")["negations"] == 0  # 'न' inside दिन is not a negation
    assert extract_facts("इस दवा को खाली पेट न लें।", "hi")["negations"] == 1

def test_hindi_negation_drop_and_contraction():
    m = mk("en", "hi", "Do not drink alcohol.", "शराब पिएं।")
    assert "red" in levels(m)
    m = Message("t", "patient", "hi", "en", "मुझे समझ नहीं आया", "I didn't understand.", True)
    assert "red" not in levels(m)

def test_hindi_register_and_emotion():
    from medbridge.emotion import check_register, detect
    from medbridge.translate import fix_hi_register
    assert fix_hi_register("शराब मत पीओ।") == "शराब न पिएं।"
    assert check_register(mk("en", "hi", "x", "शराब मत पीओ।"))
    assert detect("मुझे बहुत डर लग रहा है", "hi")[0]["intensity"] == "strong"
    assert detect("मुझे समझ नहीं आया", "hi")[0]["category"] == "confusion"


def test_interjection_no_is_not_a_negation():
    from medbridge.safety import extract_facts
    assert extract_facts("No.. I feel bad", "en")["negations"] == 0
    assert extract_facts("No, me siento mal", "es")["negations"] == 0
    assert extract_facts("नहीं, मुझे बुरा लग रहा है", "hi")["negations"] == 0
    assert extract_facts("Do not drink alcohol.", "en")["negations"] == 1
    assert extract_facts("I have no pain", "en")["negations"] == 1

def test_patient_conversation_never_red():
    m = Message("t", "patient", "en", "es", "No.. I feel bad", "Me siento mal", True)
    assert levels(m) == []
    m = Message("t", "patient", "hi", "en", "मुझे दर्द नहीं है", "I have pain.", True)
    assert "red" not in levels(m)

def test_doctor_chat_negation_is_not_red_but_directive_is():
    m = Message("t", "doctor", "en", "es", "I don't think it is serious.", "Creo que es grave.", True)
    assert "red" not in levels(m)
    m = Message("t", "doctor", "en", "es", "Do not take it on an empty stomach.", "Tómelo con el estómago vacío.", True)
    assert "red" in levels(m)
