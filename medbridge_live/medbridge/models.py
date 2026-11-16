from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class Flag:
    kind: str  # "safety" | "culture" | "emotion" | "tone"
    level: str  # "red" | "amber" | "info"
    reason: str
    span: str
    suggestion: str | None = None


@dataclass
class Message:
    id: str
    speaker: str  # "doctor" | "patient"
    src_lang: str  # "en" | "es" | "hi" | "zh"
    tgt_lang: str
    text: str
    translation: str
    is_final: bool
    flags: list[Flag] = field(default_factory=list)
    emotions: list[dict] = field(default_factory=list)
    status: str = "live"  # live | checking | ok | amber | red | confirmed

    def to_dict(self) -> dict:
        return asdict(self)
