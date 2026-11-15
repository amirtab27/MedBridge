# MedBridge Live
Hackathon research prototype. No real patient data. Not clinically validated.

## Run
Python 3.11 recommended. From this directory:
```
python -m venv .venv
source .venv/bin/activate
pip install fastapi 'uvicorn[standard]'
uvicorn server:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000. Offline mode supports only the bundled example phrases, not arbitrary translation. Select a demo scenario, translate, inspect flags, then release only after simulated review. Red flags block release; turn off injection and retry. For two tabs use the same room name and different roles. Rooms are unauthenticated, in-memory, and not appropriate for private information.

## Enable arbitrary translation
```
pip install -r requirements.txt
MEDBRIDGE_MODEL=1 uvicorn server:app --host 0.0.0.0 --port 8000
```
First arbitrary request downloads NLLB-200 distilled 600M; allow several GB and time. GPU recommended. NLLB is noncommercial research software and not intended for medical-domain deployment. Bundled examples are illustrative, not professionally reviewed. Browser speech recognition may send audio to its provider; use Chrome on localhost or HTTPS, and fictional data only. Browser speech synthesis depends on installed voices.

## Scope
Final-phrase translation, not simultaneous streaming; editable interim speech transcript. Rule-based dose/frequency/negation checks are limited and can miss dangerous errors. Teach-back checks dose/frequency only and asks for explicit warning confirmation. Culture and emotion dictionaries are small and unvalidated. No EHR, authentication, clinical validation or professional interpreter integration. Shared room is a demo transport, not a security boundary. Release button represents simulated qualified review. No latency guarantee. Error injection is explicitly labeled.
