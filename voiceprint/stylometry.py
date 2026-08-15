"""Does this text read like the author? A local, key-free ranker.

Ported from the research repo's verifier, trimmed to the parts that are cheap
and serializable. Three established signals, no neural model and no API:

  1. Function-word distance (Mosteller-Wallace / Burrows's-Delta family) — how
     someone uses closed-class words is the classic author-discriminative signal,
     and it is independent of what they are writing about.
  2. Character n-gram divergence against the corpus distribution.
  3. Slop markers — cheap interpretable penalties for the AI tells the first two
     don't catch ("not X, but Y", "let's dive in", summary endings).

The fitted profile is a few hundred floats, so it lives in the local registry.
That is what lets ranking happen on the user's machine with the corpus gone.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np

# ~150 closed-class English words, the standard Burrows's-Delta range.
FUNCTION_WORDS: tuple[str, ...] = tuple(
    (
        "the of and to a in that it is was for as with his he be not by but have you "
        "this had at on i they from she which or we an were her would their there been "
        "has when who will more no if out so up said what its about into than them can "
        "only other new some could time these two may then do first any my now such "
        "like our over man me even most made after also did many before must through "
        "back years where much your way well down should because each just those people "
        "how too little state good very make world still see own men work long here "
        "between both life being under never same another while last us off might great "
        "go come since against right came take three states himself few house use during "
        "without again place around however home small found thought went say part once "
        "general high upon school every don does got united left number course war until "
        "always away something fact though water less public put think almost hand enough "
        "far took head yet government system better set told nothing night end why called "
        "didn eyes find going look asked later knew"
    ).split()
)

SLOP_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\bnot\b[^.,;:!?]{1,40},?\s+but\b", re.IGNORECASE),
    re.compile(r"\bit'?s\s+(?:worth|important)\s+(?:noting|to note)\b", re.IGNORECASE),
    re.compile(r"\blet'?s\s+(?:dive|delve)\b", re.IGNORECASE),
    re.compile(r"\b(?:in\s+conclusion|ultimately|at\s+the\s+end\s+of\s+the\s+day)\b", re.IGNORECASE),
    re.compile(r"\b(?:in\s+today'?s|in\s+the\s+world\s+of)\b", re.IGNORECASE),
)

_WORD = re.compile(r"[a-z']+")
NGRAM_VOCAB = 500
NOVELTY_N = 8


@dataclass
class Profile:
    """A fitted author profile. JSON-serializable by construction."""

    fw_mean: list[float]
    fw_std: list[float]
    tau: float
    ngram_keys: list[str]
    ngram_dist: list[float]

    def to_dict(self) -> dict:
        return {
            "fw_mean": self.fw_mean,
            "fw_std": self.fw_std,
            "tau": self.tau,
            "ngram_keys": self.ngram_keys,
            "ngram_dist": self.ngram_dist,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        return cls(**data)


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _function_word_freq(text: str) -> np.ndarray:
    toks = _tokens(text)
    counts = Counter(toks)
    n = max(len(toks), 1)
    return np.array([counts.get(w, 0) / n for w in FUNCTION_WORDS], dtype=float)


def _char_ngrams(text: str, n: int = 3) -> Counter:
    flat = re.sub(r"\s+", " ", text.lower())
    return Counter(flat[i : i + n] for i in range(max(len(flat) - n + 1, 0)))


def _dist_over(counter: Counter, keys: list[str]) -> np.ndarray:
    total = sum(counter.values()) or 1
    return np.array([counter.get(k, 0) / total for k in keys], dtype=float)


def _js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    p = p + 1e-12
    q = q + 1e-12
    p = p / p.sum()
    q = q / q.sum()
    m = 0.5 * (p + q)
    kl = lambda a, b: float(np.sum(a * np.log(a / b)))  # noqa: E731
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def slop_penalty(text: str) -> float:
    hits = sum(len(p.findall(text)) for p in SLOP_PATTERNS)
    return 1.0 - math.exp(-0.6 * hits)


def fit(texts: list[str]) -> Profile:
    if not texts:
        raise ValueError("cannot fit a style profile on an empty corpus")

    freqs = np.stack([_function_word_freq(t) for t in texts])
    fw_mean = freqs.mean(0)
    fw_std = freqs.std(0) + 1e-6

    # tau is calibrated to the corpus's own internal spread, so a genuine sample
    # of the author's writing scores mid-high rather than saturating at 1.0.
    intra = [float(np.mean(np.abs((_function_word_freq(t) - fw_mean) / fw_std))) for t in texts]
    tau = max(float(np.median(intra)), 1e-3)

    all_ngrams: Counter = Counter()
    for text in texts:
        all_ngrams.update(_char_ngrams(text))
    keys = [k for k, _ in all_ngrams.most_common(NGRAM_VOCAB)]

    return Profile(
        fw_mean=fw_mean.tolist(),
        fw_std=fw_std.tolist(),
        tau=tau,
        ngram_keys=keys,
        ngram_dist=_dist_over(all_ngrams, keys).tolist(),
    )


def score(profile: Profile, text: str) -> float:
    """[0,1] — higher means it reads more like the author."""
    if not text.strip():
        return 0.0

    z = (_function_word_freq(text) - np.array(profile.fw_mean)) / np.array(profile.fw_std)
    distance = float(np.mean(np.abs(z)))
    fw = math.exp(-(distance**2) / (2.0 * profile.tau**2))

    js = _js_divergence(np.array(profile.ngram_dist), _dist_over(_char_ngrams(text), profile.ngram_keys))
    ngram = max(0.0, 1.0 - js / math.log(2))

    markers = max(0.0, 1.0 - slop_penalty(text))
    return float(min(1.0, max(0.0, 0.5 * fw + 0.3 * ngram + 0.2 * markers)))


def novelty(text: str, corpus_texts: list[str], n: int = NOVELTY_N) -> float:
    """1.0 means nothing in the text is an n-gram lifted from the corpus.

    The memorization guard. A voice adapter that scores well here is supplying
    style; one that scores badly is reciting.
    """
    words = _tokens(text)
    if len(words) < n:
        return 1.0

    seen = set()
    for source in corpus_texts:
        source_words = _tokens(source)
        seen.update(
            tuple(source_words[i : i + n]) for i in range(max(len(source_words) - n + 1, 0))
        )

    grams = [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]
    overlap = sum(g in seen for g in grams) / len(grams)
    return 1.0 - overlap
