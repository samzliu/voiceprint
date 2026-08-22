"""Which base model a voice is trained on.

Any Hugging Face causal LM with a chat template works. The presets are shorthands
for ones worth starting from; anything else is passed straight through as a repo
id.
"""

from __future__ import annotations

# Shorthands for the two bases the technique has been measured on. Both are
# instruct-tuned, which is not a detail: the adapter is trained and served
# through the base model's own chat template, so a model without one cannot be
# used at all. See `voiceprint/scaffold.py` for why.
#
#   qwen14b     the cheapest base that passes. Quality ~6.9 on held-out topics.
#   mistral24b  better prose (~7.1) for the same single-GPU footprint, and
#               Apache-2.0, which is the cleaner licence for a paid product.
#
# Deliberately plain data with no Modal import: choosing a base model shouldn't
# require a cloud account to be configured.
MODEL_PRESETS = {
    "qwen14b": "Qwen/Qwen2.5-14B-Instruct",
    "mistral24b": "mistralai/Mistral-Small-24B-Instruct-2501",
}
DEFAULT_MODEL = "qwen14b"

INSTRUCT_MARKERS = ("instruct", "-it", "chat", "-sft", "-dpo", "zephyr", "tulu")


class NotAnInstructModel(Exception):
    """Raised GPU-side when a base model turns out to have no chat template."""


def resolve(name: str) -> str:
    """A preset key or a Hugging Face repo id -> a repo id."""
    model = MODEL_PRESETS.get(name, name)
    if "/" not in model:
        raise ValueError(
            f"unknown model {name!r}. Use a preset ({', '.join(MODEL_PRESETS)}) "
            f"or any Hugging Face id, e.g. 'Qwen/Qwen2.5-14B-Instruct'."
        )
    return model


def looks_like_base(model: str) -> bool:
    """A cheap name-shaped guess at whether this is a pretrained-only model.

    Only a guess, and deliberately not enforced here. Plenty of instruct-tuned
    models are named in ways no keyword list will catch, and refusing those
    would be worse than the mistake it prevents. The authoritative check is
    whether the tokenizer actually carries a chat template, which needs the
    tokenizer — so `train_voice` makes it, first thing, before any GPU time is
    spent. This exists only so the CLI can say something useful up front.
    """
    tail = model.rsplit("/", 1)[-1].lower()
    return not any(marker in tail for marker in INSTRUCT_MARKERS)


def base_model_warning(model: str) -> str | None:
    if not looks_like_base(model):
        return None
    return (
        f"{model} looks like a pretrained base model, not an instruct/chat one. "
        f"Voiceprint trains and generates through the chat template, so the base "
        f"needs one — training will stop early if it has none. Did you mean "
        f"'{model}-Instruct'?"
    )


def label(model: str) -> str:
    """The short name for a model id, for listings."""
    for preset, full in MODEL_PRESETS.items():
        if full == model:
            return preset
    return model


__all__ = [
    "DEFAULT_MODEL",
    "MODEL_PRESETS",
    "NotAnInstructModel",
    "base_model_warning",
    "label",
    "looks_like_base",
    "resolve",
]
