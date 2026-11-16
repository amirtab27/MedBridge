"""MedBridge live server: FastAPI + WebSockets. Run: uvicorn medbridge.server:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations
import asyncio, json, os, time, uuid, urllib.request, urllib.error, hashlib
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

from .models import Message, Flag
from . import translate as T, safety, culture, emotion
from . import plain_language, cultural_insights
from .present import present

ROOT = Path(__file__).resolve().parent.parent
_env = ROOT / ".env"
if _env.exists():  # KEY=value lines; never committed (see .gitignore)
    for _l in _env.read_text().splitlines():
        if "=" in _l and not _l.strip().startswith("#"):
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
app = FastAPI(title="MedBridge")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
POOL = ThreadPoolExecutor(max_workers=2)
THROTTLE = 1.0
EMPATHY_LEADS = ["here_to_help", "take_your_time", "worrying"]


class Session:
    def __init__(self):
        self.ws: dict[str, WebSocket] = {}
        self.patient_lang = "es"
        self.prefs = {"tone": "empathetic", "length": "detailed", "mode": "interactive"}
        self.inject = False
        self.history: dict[str, dict] = {}
        self.order: list[str] = []
        self.interim_state: dict[str, dict] = {}
        self.lead_next = True
        self.lead_i = 0
        self.finalized: set[str] = set()


SESSIONS: dict[str, Session] = {}


def sess(name: str) -> Session:
    return SESSIONS.setdefault(name, Session())


async def run(fn, *a):
    return await asyncio.get_running_loop().run_in_executor(POOL, fn, *a)


async def send(s: Session, role: str, payload: dict):
    ws = s.ws.get(role)
    if ws:
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            s.ws.pop(role, None)


async def both(s: Session, payload: dict):
    for r in ("doctor", "patient"):
        await send(s, r, payload)


def langs(s: Session, speaker: str) -> tuple[str, str]:
    return ("en", s.patient_lang) if speaker == "doctor" else (s.patient_lang, "en")


def status_of(flags: list[Flag]) -> str:
    if any(f.level == "red" for f in flags):
        return "red"
    if any(f.level == "amber" for f in flags):
        return "amber"
    return "ok"


def pack(m: Message, extra: dict | None = None) -> dict:
    d = m.to_dict()
    d["facts"] = safety.extract_facts(m.text, m.src_lang)["doses"]
    d["plain_explanations"] = getattr(m, "plain_explanations", [])
    d["cultural_insights"] = getattr(m, "cultural_insights", [])
    d.update(extra or {})
    return d


async def handle_interim(s: Session, speaker: str, mid: str, text: str):
    st = s.interim_state.setdefault(speaker, {"latest": None, "busy": False, "last": 0.0})
    st["latest"] = (mid, text)
    if st["busy"]:
        return
    st["busy"] = True
    try:
        while st["latest"]:
            wait = THROTTLE - (time.time() - st["last"])
            if wait > 0:
                await asyncio.sleep(wait)
            if not st["latest"]:  # a final message cleared it while we were waiting
                break
            mid_, txt = st["latest"]
            st["latest"] = None
            st["last"] = time.time()
            src, tgt = langs(s, speaker)
            tr = await run(T.translate, txt, src, tgt)
            if mid_ in s.finalized:
                continue
            other = "patient" if speaker == "doctor" else "doctor"
            await send(s, other, {"type": "interim", "id": mid_, "speaker": speaker, "text": txt, "translation": tr})
    finally:
        st["busy"] = False


async def handle_final(s: Session, speaker: str, mid: str, text: str):
    text = text.strip()
    if not text:
        return
    s.interim_state.get(speaker, {})["latest"] = None
    s.finalized.add(mid)
    src, tgt = langs(s, speaker)
    m = Message(mid, speaker, src, tgt, text, "", True, status="checking")
    await both(s, {"type": "checking", "id": mid, "speaker": speaker, "text": text})
    clean = await run(T.translate, text, src, tgt)
    shown = clean
    if speaker == "doctor" and s.inject:
        shown = safety.inject_error(clean, tgt)
    m.translation = shown
    m.flags = safety.check_safety(m) + culture.check_culture(m)
    if speaker == "doctor":
        m.flags += emotion.check_register(m)
    else:
        m.emotions, ef = emotion.check_emotion(m, "")
        m.flags += ef
    m.status = status_of(m.flags)
    # Supplemental information only: never alters translated clinical text or TTS.
    m.plain_explanations = plain_language.explain(text, tgt) if speaker == "doctor" else []
    m.cultural_insights = cultural_insights.insights(text) if speaker == "patient" else []
    extra = {"clean_translation": clean} if speaker == "doctor" else {}
    s.history[mid] = {**pack(m), "clean": clean}
    s.order.append(mid)
    lead = ""
    if speaker == "patient":
        s.lead_next = True
    elif m.status != "red" and s.prefs.get("tone") == "empathetic" and s.lead_next:
        key = EMPATHY_LEADS[s.lead_i % len(EMPATHY_LEADS)]
        lead = emotion.empathy_line(key, s.patient_lang)
        s.lead_i += 1
        s.lead_next = False
    s.history[mid]["lead"] = lead
    payload = {"type": "final", "message": pack(m), "lead": lead}
    await both(s, payload)
    asyncio.create_task(back_check(s, m, lead))


async def back_check(s: Session, m: Message, lead: str):
    """Background back-translation; may refine the caption's dot a beat later."""
    if m.speaker != "doctor":
        return
    back = await run(T.back_translate, m.translation, m.tgt_lang)
    s.history[m.id]["back"] = back
    await send(s, "doctor", {"type": "back", "id": m.id, "back": back})


async def handle(s: Session, role: str, d: dict):
    t = d.get("type")
    other = "patient" if role == "doctor" else "doctor"
    if t == "speech":
        if d.get("is_final"):
            await handle_final(s, role, d["id"], d["text"])
        else:
            asyncio.create_task(handle_interim(s, role, d["id"], d["text"]))
    elif t == "floor":
        await send(s, other, {"type": "peer_floor", "state": d.get("state")})
    elif t == "prefs" and role == "patient":
        s.prefs.update(d.get("prefs", {}))
        if d.get("lang") in ("es", "hi", "zh"):
            s.patient_lang = d["lang"]
        await both(s, {"type": "config", "lang": s.patient_lang, "prefs": s.prefs, "inject": s.inject})
    elif t == "inject" and role == "doctor":
        s.inject = bool(d.get("on"))
        await both(s, {"type": "config", "lang": s.patient_lang, "prefs": s.prefs, "inject": s.inject})
    elif t == "confirm" and role == "doctor":
        h = s.history.get(d["id"])
        if h:
            h["translation"] = h["clean"]
            h["status"] = "confirmed"
            await both(s, {"type": "confirmed", "id": d["id"], "translation": h["clean"]})
    elif t == "rephrase" and role == "doctor":
        await both(s, {"type": "retract", "id": d["id"]})
    elif t == "empathy" and role == "doctor":
        key = d["key"]
        mid = uuid.uuid4().hex[:8]
        en, tr = emotion.empathy_line(key, "en"), emotion.empathy_line(key, s.patient_lang)
        m = Message(mid, "doctor", "en", s.patient_lang, en, tr, True, status="ok")
        s.history[mid] = {**pack(m), "clean": tr, "lead": ""}
        s.lead_next = False
        await both(s, {"type": "final", "message": pack(m), "lead": "", "stored": True})
    elif t == "clarify" and role == "doctor":
        q = culture.question_for(d["span"], s.patient_lang)
        if q:
            mid = uuid.uuid4().hex[:8]
            m = Message(mid, "doctor", "en", s.patient_lang, d.get("en", ""), q, True, status="ok")
            s.history[mid] = {**pack(m), "clean": q, "lead": ""}
            await both(s, {"type": "final", "message": pack(m), "lead": "", "stored": True})
    elif t == "resolve" and role == "doctor":
        await send(s, "doctor", {"type": "resolved", "id": d["id"]})
    elif t == "interpreter":
        await both(s, {"type": "interpreter", "from": role})


@app.websocket("/ws/{session}/{role}")
async def ws_endpoint(ws: WebSocket, session: str, role: str):
    await ws.accept()
    s = sess(session)
    s.ws[role] = ws
    await ws.send_text(json.dumps({"type": "hello", "lang": s.patient_lang, "prefs": s.prefs, "inject": s.inject, "cloud_tts": tts_enabled(),
                                   "history": [s.history[i] for i in s.order if i in s.history]}, ensure_ascii=False))
    await send(s, "patient" if role == "doctor" else "doctor", {"type": "peer", "online": True})
    for r in s.ws:
        if r != role:
            await ws.send_text(json.dumps({"type": "peer", "online": True}))
    try:
        while True:
            await handle(s, role, json.loads(await ws.receive_text()))
    except WebSocketDisconnect:
        pass
    finally:
        if s.ws.get(role) is ws:
            s.ws.pop(role, None)
        await send(s, "patient" if role == "doctor" else "doctor", {"type": "peer", "online": False})


@app.on_event("startup")
async def _warm():
    asyncio.get_running_loop().run_in_executor(POOL, T.warm_up)


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "landing.html")


@app.get("/doctor")
@app.get("/patient")
def page():
    return FileResponse(ROOT / "static" / "app.html")


# ---------- natural voice (OpenAI text-to-speech). Key stays on the server; browsers never see it. ----------
TTS_MODEL = os.environ.get("MEDBRIDGE_TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.environ.get("MEDBRIDGE_TTS_VOICE", "marin")
LANG_NAME = {"en": "English", "es": "Spanish", "hi": "Hindi", "zh": "Mandarin Chinese"}
_tts_cache: dict[str, bytes] = {}
_tts_hits: deque = deque()


EDGE_VOICES = {"en": "en-US-JennyNeural", "es": "es-MX-DaliaNeural", "hi": "hi-IN-SwaraNeural", "zh": "zh-CN-XiaoxiaoNeural"}
try:
    import edge_tts
except ImportError:  # optional dependency
    edge_tts = None


EL_MODEL = os.environ.get("MEDBRIDGE_EL_MODEL", "eleven_multilingual_v2")  # closest to a cloned voice; Hindi/Spanish/Mandarin
EL_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "QqPyu24rMjzzVxXJrpH8")   # "Sia" cloned voice (needs the owner's ELEVENLABS_API_KEY; else falls back to free voice)
EL_BUDGET = int(os.environ.get("MEDBRIDGE_EL_BUDGET", "8000"))             # characters; then falls back to the free voice
_el_used = 0


def tts_enabled() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("OPENAI_API_KEY")) or edge_tts is not None


def _el_synthesize(text: str, lang: str) -> bytes:
    body = json.dumps({"text": text, "model_id": EL_MODEL, "language_code": lang,
                       "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True}}).encode()
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE}?output_format=mp3_44100_128", data=body,
                                 method="POST", headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


async def _edge_synthesize(text: str, lang: str) -> bytes:
    out = b""
    async for ch in edge_tts.Communicate(text, EDGE_VOICES[lang], rate="-4%").stream():
        if ch["type"] == "audio":
            out += ch["data"]
    return out


class TTSReq(BaseModel):
    session: str
    text: str
    lang: str


def _synthesize(text: str, lang: str) -> bytes:
    body = json.dumps({
        "model": TTS_MODEL, "voice": TTS_VOICE, "input": text, "response_format": "mp3",
        "instructions": (f"Speak {LANG_NAME.get(lang, 'the language of the text')} like a warm, calm, caring clinician talking "
                         "to a patient one-to-one. Natural conversational pace, gentle and reassuring, clear pronunciation "
                         "of numbers and medicine doses. Respectful, formal register."),
    }).encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body, method="POST", headers={
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


@app.post("/api/tts")
async def api_tts(req: TTSReq):
    if not tts_enabled():
        return Response(status_code=503)
    text = req.text.strip()[:500]
    if req.session not in SESSIONS or req.lang not in LANG_NAME or not text:  # only live sessions may spend the key
        return Response(status_code=400)
    key = hashlib.sha1(f"{req.lang}|{text}".encode()).hexdigest()
    if key not in _tts_cache:
        now = time.time()
        while _tts_hits and now - _tts_hits[0] > 60:
            _tts_hits.popleft()
        if len(_tts_hits) >= 40:  # crude global cap: 40 new syntheses per minute
            return Response(status_code=429)
        _tts_hits.append(now)
        try:
            global _el_used
            audio = b""
            if os.environ.get("ELEVENLABS_API_KEY") and _el_used + len(text) <= EL_BUDGET:
                try:
                    audio = await run(_el_synthesize, text, req.lang)
                    _el_used += len(text)
                except Exception:
                    audio = b""  # bad key / out of credits / network -> free voice below
            if audio:
                _tts_cache[key] = audio
            elif os.environ.get("OPENAI_API_KEY"):
                _tts_cache[key] = await run(_synthesize, text, req.lang)
            else:
                _tts_cache[key] = await asyncio.wait_for(_edge_synthesize(text, req.lang), 15)
            if not _tts_cache[key]:
                _tts_cache.pop(key, None)
                return Response(status_code=502)
        except Exception:
            return Response(status_code=502)
        if len(_tts_cache) > 300:
            _tts_cache.pop(next(iter(_tts_cache)))
    return Response(_tts_cache[key], media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})
