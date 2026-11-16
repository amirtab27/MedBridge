"""MedBridge live server: FastAPI + WebSockets. Run: uvicorn medbridge.server:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations
import asyncio, json, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import Message, Flag
from . import translate as T, safety, culture, emotion
from .present import present

ROOT = Path(__file__).resolve().parent.parent
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
    await ws.send_text(json.dumps({"type": "hello", "lang": s.patient_lang, "prefs": s.prefs, "inject": s.inject,
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
