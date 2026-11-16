"""Presentation layer: wraps approved text for the patient. Never alters medical content."""
from __future__ import annotations
from .emotion import empathy_line


def present(translation: str, prefs: dict, lang: str, first: bool = False) -> dict:
    """Returns {text, lead, tail}. The approved translation is untouched; only framing is added."""
    lead = ""
    if prefs.get("tone") == "empathetic" and first:
        lead = empathy_line("here_to_help", lang)
    return {"text": translation, "lead": lead, "style": prefs.get("length", "detailed")}
