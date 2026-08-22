"""Ranking candidates, and deciding which ones are shippable at all.

Two different jobs, deliberately kept apart:

  Scorer    ranks. "Of these drafts, which sounds most like the author?"
  Detector  gates. "Would this be called machine-written?"

The default scorer is local and free, which is the point: nothing about the
default path requires an account, a key, or sending someone's drafts to a third
party. The default detector runs on the GPU the user is already renting, for the
same reason — a metered API cannot sit in front of every draw of a best-of-N
loop. Pangram is available for both jobs and is strictly opt-in, because it means
posting the user's drafts to somebody else's server.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol

from voiceprint import binoculars, stylometry
from voiceprint.binoculars import Reading
from voiceprint.stylometry import Profile

SCORERS = ("stylometry", "binoculars", "pangram")
DETECTORS = ("binoculars", "pangram", "none")
DEFAULT_DETECTOR = "binoculars"


class Scorer(Protocol):
    name: str

    def score(self, text: str) -> float: ...


class Detector(Protocol):
    name: str

    def read_many(self, texts: list[str]) -> list[Reading]: ...

    def read(self, text: str) -> Reading: ...


class StylometryScorer:
    """Ranks by how close the text sits to the author's own style profile."""

    name = "stylometry"

    def __init__(self, profile: Profile):
        self.profile = profile

    def score(self, text: str) -> float:
        return stylometry.score(self.profile, text)


class BinocularsDetector:
    """P(human) from a self-hosted Binoculars pair. Free per call, so it can gate
    every candidate; see `voiceprint/binoculars.py` for what it measures."""

    name = "binoculars"

    def read_many(self, texts: list[str]) -> list[Reading]:
        from voiceprint import remote

        return [Reading.from_dict(r) for r in remote.detector().read.remote(texts)]

    def read(self, text: str) -> Reading:
        return self.read_many([text])[0]

    def score(self, text: str) -> float:
        return self.read(text).p_human


class PangramDetector:
    """P(human) from Pangram. Opt-in, needs PANGRAM_API_KEY.

    A trained classifier rather than a perplexity ratio, which is exactly why it
    is worth keeping alongside Binoculars: agreeing with two detectors that fail
    in different ways is evidence, agreeing with one is a good chance we learned
    to beat that one.
    """

    name = "pangram"
    url = "https://text.api.pangramlabs.com"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("PANGRAM_API_KEY")
        if not self.api_key:
            raise RuntimeError("the pangram scorer needs PANGRAM_API_KEY in the environment")

    def score(self, text: str) -> float:
        request = urllib.request.Request(
            self.url,
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json", "x-api-key": self.api_key},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        return 1.0 - float(payload["ai_likelihood"])

    def read_many(self, texts: list[str]) -> list[Reading]:
        # No batch endpoint, and each call is metered — another reason this is
        # the QA detector rather than the hot-path one.
        return [self.read(text) for text in texts]

    def read(self, text: str) -> Reading:
        probability = self.score(text)
        words = len(text.split())
        return Reading(
            score=probability,
            p_human=probability,
            tokens=words,
            # Same short-text caveat as Binoculars: under about a paragraph
            # every detector is guessing, and words undercount tokens, so this
            # is the conservative direction.
            reliable=words >= binoculars.MIN_TOKENS,
        )


# Kept under its old name: `voiceprint score --scorer pangram` predates the
# detector split and there is no reason to break it.
PangramScorer = PangramDetector


def build(name: str, profile: Profile) -> Scorer:
    if name == "stylometry":
        return StylometryScorer(profile)
    if name == "binoculars":
        return BinocularsDetector()
    if name == "pangram":
        return PangramDetector()
    raise ValueError(f"unknown scorer {name!r} — use one of {', '.join(SCORERS)}")


def build_detector(name: str) -> Detector | None:
    """None means "ship the first draft ungated", which is a legitimate choice
    when the user is iterating fast and does not want to pay for redraws."""
    if name in (None, "none"):
        return None
    if name == "binoculars":
        return BinocularsDetector()
    if name == "pangram":
        return PangramDetector()
    raise ValueError(f"unknown detector {name!r} — use one of {', '.join(DETECTORS)}")
