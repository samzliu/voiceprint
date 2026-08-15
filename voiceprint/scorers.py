"""Ranking the best-of-N candidates.

The default scorer is local and free, which is the point: nothing about the
default path requires an account, a key, or sending someone's drafts to a third
party. An AI-detector scorer is available for people who want to reproduce the
research numbers, and it is strictly opt-in.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol

from voiceprint import stylometry
from voiceprint.stylometry import Profile


class Scorer(Protocol):
    name: str

    def score(self, text: str) -> float: ...


class StylometryScorer:
    """Ranks by how close the text sits to the author's own style profile."""

    name = "stylometry"

    def __init__(self, profile: Profile):
        self.profile = profile

    def score(self, text: str) -> float:
        return stylometry.score(self.profile, text)


class PangramScorer:
    """Ranks by P(human) from Pangram. Opt-in, needs PANGRAM_API_KEY."""

    name = "pangram"
    url = "https://text.api.pangramlabs.com"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("PANGRAM_API_KEY")
        if not self.api_key:
            raise RuntimeError("--scorer pangram needs PANGRAM_API_KEY in the environment")

    def score(self, text: str) -> float:
        request = urllib.request.Request(
            self.url,
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json", "x-api-key": self.api_key},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        return 1.0 - float(payload["ai_likelihood"])


def build(name: str, profile: Profile) -> Scorer:
    if name == "stylometry":
        return StylometryScorer(profile)
    if name == "pangram":
        return PangramScorer()
    raise ValueError(f"unknown scorer {name!r} — use 'stylometry' or 'pangram'")
