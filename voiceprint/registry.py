"""Local record of trained voices: ~/.voiceprint/voices/<name>.json

Holds the metadata, the fitted style profile, and a held-out slice of the corpus
for `voiceprint eval`. One file per voice, so two concurrent trainings can never
clobber each other's record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from voiceprint.stylometry import Profile

HOME = Path.home() / ".voiceprint"
VOICES_DIR = HOME / "voices"
CONFIG = HOME / "config.json"


@dataclass
class Voice:
    name: str
    model: str
    adapter_path: str
    profile: Profile
    words: int
    chunks: int
    pairs: int
    # Kept for `voiceprint eval`: `training` is what novelty is measured against
    # (did it recite?), `holdout` is unseen real writing by the author and gives
    # the style score something honest to be compared to.
    training: list[str] = field(default_factory=list)
    holdout: list[str] = field(default_factory=list)
    trained_at: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "adapter_path": self.adapter_path,
            "profile": self.profile.to_dict(),
            "words": self.words,
            "chunks": self.chunks,
            "pairs": self.pairs,
            "training": self.training,
            "holdout": self.holdout,
            "trained_at": self.trained_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Voice":
        return cls(**{**data, "profile": Profile.from_dict(data["profile"])})


class VoiceNotFound(Exception):
    pass


def path_for(name: str) -> Path:
    return VOICES_DIR / f"{name}.json"


def save(voice: Voice) -> Path:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    voice.trained_at = voice.trained_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    target = path_for(voice.name)
    target.write_text(json.dumps(voice.to_dict()), encoding="utf-8")
    return target


def load(name: str) -> Voice:
    target = path_for(name)
    if not target.exists():
        known = ", ".join(n for n in list_names()) or "none yet"
        raise VoiceNotFound(f"no voice named {name!r}. Trained voices: {known}")
    return Voice.from_dict(json.loads(target.read_text(encoding="utf-8")))


def list_names() -> list[str]:
    if not VOICES_DIR.exists():
        return []
    return sorted(p.stem for p in VOICES_DIR.glob("*.json"))


def load_all() -> list[Voice]:
    return [load(name) for name in list_names()]


def set_default(name: str) -> None:
    load(name)  # refuse to point the default at a voice that isn't there
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"default_voice": name}), encoding="utf-8")


def get_default() -> str | None:
    if not CONFIG.exists():
        return None
    name = json.loads(CONFIG.read_text(encoding="utf-8")).get("default_voice")
    return name if name in list_names() else None


def default_name() -> str:
    """The voice used when the user doesn't name one.

    An explicit `voiceprint use` wins; otherwise a single trained voice is
    unambiguous. With several and no default set, refuse rather than guess —
    picking the wrong voice wastes a generation and reads as a bug.
    """
    chosen = get_default()
    if chosen:
        return chosen

    names = list_names()
    if not names:
        raise VoiceNotFound("no voices trained yet — run `voiceprint train <path-to-your-writing>`")
    if len(names) > 1:
        raise VoiceNotFound(
            f"several voices exist ({', '.join(names)}) — pass --voice, "
            f"or pick a default with `voiceprint use <name>`"
        )
    return names[0]


def delete(name: str, drop_adapter: bool = True) -> str:
    """Forget a voice locally, and remove its adapter from the Modal volume."""
    voice = load(name)
    path_for(name).unlink()
    if get_default() == name:
        CONFIG.unlink(missing_ok=True)

    if not drop_adapter:
        return f"removed '{name}' locally; adapter left at {voice.adapter_path}"

    import modal

    from voiceprint.modal_app import voices_volume

    try:
        voices_volume.remove_file(f"/{name}", recursive=True)
    except (FileNotFoundError, modal.exception.NotFoundError):
        return f"removed '{name}'; no adapter was stored for it"
    return f"removed '{name}' and its adapter"
