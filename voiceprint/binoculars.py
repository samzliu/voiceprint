"""Binoculars: a zero-shot detector we can afford to run on every candidate.

From Hans et al. 2024, "Spotting LLMs With Binoculars". The idea is a ratio
between two closely related models — an *observer* and a *performer*:

    score = perplexity(text | observer) / cross-perplexity(observer, performer)

The numerator asks how surprised the observer is by this text. The denominator
asks how surprised the observer is by what the performer would have predicted at
each position. Dividing one by the other is the whole contribution: raw
perplexity alone flags any human writing about a predictable subject, because
boilerplate is low-perplexity no matter who wrote it. The ratio instead asks
whether the text is unsurprising *in the specific way another language model
finds unsurprising*, which is a much narrower question and the one we actually
care about. Machine text scores low; human text scores high.

Why it is here at all, when `PangramScorer` already exists: Pangram is a metered
API, so it cannot sit in front of every draw of a best-of-N loop. Binoculars is
two small forward passes on hardware we are already renting, so it can. Pangram
stays for periodic QA, and keeping a second detector of a *different kind* around
is deliberate — passing only a perplexity-ratio test might mean we learned to
beat perplexity ratios rather than learned to write like a person.

The maths here is pure and lives apart from the model loading in `modal_app`, so
the thresholding and the token guard can be tested without a GPU.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# The paper's pair. Both are needed and they must share a tokenizer, which in
# practice means a base model and its own instruct sibling.
OBSERVER_MODEL = "tiiuae/falcon-7b"
PERFORMER_MODEL = "tiiuae/falcon-7b-instruct"

# Published operating points for that pair. The low-FPR point is the default:
# a false "this is machine-written" costs us a wasted redraw, while a false
# "this is fine" ships the thing the user is paying us to avoid.
THRESHOLD_ACCURACY = 0.9015310749276843
THRESHOLD_LOW_FPR = 0.8536432310785527
DEFAULT_THRESHOLD = THRESHOLD_LOW_FPR

# Scores for real passages sit in a narrow band either side of the threshold, so
# the logistic that turns one into a probability has to be narrow too. This is a
# monotone remap for interface compatibility — it makes `p_human > 0.5` mean
# exactly `score > threshold` — and not a calibrated probability. Do not read
# 0.73 as "73% likely human".
LOGISTIC_SCALE = 0.02

# Below roughly this many tokens the detector is guessing: there is not enough
# text for either perplexity term to mean anything, and both detectors we use
# get noticeably unreliable. Short drafts are passed through ungated rather than
# gated on noise.
MIN_TOKENS = 40


@dataclass(frozen=True)
class Reading:
    """One detector opinion about one exact piece of text."""

    score: float
    p_human: float
    tokens: int
    reliable: bool

    @property
    def passed(self) -> bool:
        """Unreliable readings pass: a draft too short to judge should not be
        thrown away by a detector that admits it cannot judge it."""
        return not self.reliable or self.p_human > 0.5

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "p_human": self.p_human,
            "tokens": self.tokens,
            "reliable": self.reliable,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Reading":
        return cls(
            score=float(data["score"]),
            p_human=float(data["p_human"]),
            tokens=int(data["tokens"]),
            reliable=bool(data["reliable"]),
        )


def p_human(score: float, threshold: float = DEFAULT_THRESHOLD) -> float:
    """Binoculars score -> a number that crosses 0.5 exactly at the threshold."""
    return 1.0 / (1.0 + math.exp(-(score - threshold) / LOGISTIC_SCALE))


def reading(score: float, tokens: int, threshold: float = DEFAULT_THRESHOLD) -> Reading:
    return Reading(
        score=score,
        p_human=p_human(score, threshold),
        tokens=tokens,
        reliable=tokens >= MIN_TOKENS,
    )


def score_text(text: str, tokenizer, observer, performer, max_len: int = 2048) -> Reading:
    """The two forward passes and the ratio between them.

    Kept here rather than inline in `modal_app` so the shape of the computation
    is readable next to the explanation of it. `tokenizer`, `observer` and
    `performer` are already-loaded Hugging Face objects; see `Detector`.
    """
    import torch

    encoded = tokenizer(
        text, return_tensors="pt", truncation=True, max_length=max_len, return_token_type_ids=False
    )
    encoded = {key: value.to(observer.device) for key, value in encoded.items()}
    tokens = int(encoded["input_ids"].shape[1])
    if tokens < 2:
        return reading(0.0, tokens)

    with torch.no_grad():
        observer_logits = observer(**encoded).logits
        performer_logits = performer(**encoded).logits

    labels = encoded["input_ids"][:, 1:]
    shifted_observer = observer_logits[:, :-1]
    shifted_performer = performer_logits[:, :-1]

    # How surprised the observer is by the text that actually appeared.
    perplexity = torch.nn.functional.cross_entropy(
        shifted_observer.reshape(-1, shifted_observer.shape[-1]),
        labels.reshape(-1),
        reduction="mean",
    )

    # How surprised the observer is by the performer's own predictions. The
    # expectation is taken under the performer, so this is a genuine
    # cross-entropy between two distributions rather than against one sample.
    cross_perplexity = -(
        torch.nn.functional.softmax(shifted_performer, dim=-1)
        * torch.nn.functional.log_softmax(shifted_observer, dim=-1)
    ).sum(dim=-1).mean()

    return reading(float(perplexity / cross_perplexity), tokens)
