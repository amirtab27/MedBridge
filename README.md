# MedBridge Live
Hackathon research prototype. No real patient data. Not clinically validated, not a certified interpreter.

## Run
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000 in Chrome (speech recognition needs Chrome on localhost or HTTPS).

## How it works
- Click **Start talking**. Speech is transcribed continuously; the partial sentence is translated (~350 ms debounce) and streamed to the other person while you speak, then finalized and spoken aloud on the listener's side.
- Translation runs locally with Meta NLLB-200 (default `nllb-200-distilled-600M`; set `MEDBRIDGE_NLLB=facebook/nllb-200-distilled-1.3B` or `facebook/nllb-200-3.3B` for more natural output). The model is loaded at startup; the first run downloads it. No API key needed. Optional: `MEDBRIDGE_BACKEND=claude` with `ANTHROPIC_API_KEY` uses Claude instead.
- Rule-based dose/frequency/negation, culture and emotion checks run on each finished sentence and appear as warnings; they never delay delivery and can miss errors.
- Two devices: enter the same room name on both, one as Doctor, one as Patient. With no room, one screen shows both roles.

## Limits
Rooms are unauthenticed and in-memory; browser speech recognition may send audio to its provider (and text goes to Anthropic only if you choose the Claude backend), so use fictional data only. Interim translations of partial sentences may be revised once the sentence finishes. Browser speech synthesis depends on installed voices.

## Speech output
Translations are spoken through the macOS `say` voices (Lekha, Paulina, Tingting, Samantha) via `/api/tts`; on non-macOS servers the browser's own speech synthesis is used.
