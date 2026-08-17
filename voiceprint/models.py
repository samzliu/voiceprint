"""Which base model a voice is trained on.

Any Hugging Face causal LM works. The presets are shorthands for ones worth
starting from; anything else is passed straight through as a repo id.
"""

from __future__ import annotations

# Any Hugging Face causal LM works; these are shorthands for ones worth starting
# from. Deliberately plain data with no Modal import — nothing about choosing a
# base model requires a cloud account to be configured.
MODEL_PRESETS = {
    "qwen14b": "Qwen/Qwen2.5-14B",
    "qwen7b": "Qwen/Qwen2.5-7B",
    "qwen3b": "Qwen/Qwen2.5-3B",
    "llama8b": "meta-llama/Llama-3.1-8B",
    "mistral7b": "mistralai/Mistral-7B-v0.3",
    "gemma9b": "google/gemma-2-9b",
}
DEFAULT_MODEL = "qwen14b"

INSTRUCT_SUFFIXES = ("-instruct", "-it", "-chat", "-chat-hf")


class NotABaseModel(Exception):
    pass


class NeedsToken(Exception):
    pass


def resolve(name: str) -> str:
    """A preset key or a Hugging Face repo id -> a repo id."""
    model = MODEL_PRESETS.get(name, name)
    if "/" not in model:
        raise ValueError(
            f"unknown model {name!r}. Use a preset ({', '.join(MODEL_PRESETS)}) "
            f"or any Hugging Face id, e.g. 'Qwen/Qwen2.5-14B'."
        )
    reject_instruct(model)
    return model


def reject_instruct(model: str) -> None:
    """Instruct models are the one thing that cannot work here.

    The whole technique rests on prompting a *base* model as a plain document.
    An instruct model given the same brief covers the topic perfectly and is
    caught by AI detectors 100% of the time — it has been tuned into a voice of
    its own, and that voice is not the user's. Better to refuse at the CLI than
    to spend the user's GPU minutes learning this the slow way.
    """
    tail = model.rsplit("/", 1)[-1].lower()
    if tail.endswith(INSTRUCT_SUFFIXES) or "instruct" in tail:
        raise NotABaseModel(
            f"{model} is an instruct/chat model. voiceprint trains on base models — "
            f"instruct-tuned ones already have a voice, and it isn't yours. "
            f"Try the base version (e.g. 'Qwen/Qwen2.5-14B', not '-Instruct')."
        )


def check_available(model: str) -> None:
    """Refuse a gated model with no token, here rather than in a GPU log.

    Llama and Gemma need a Hugging Face token and an accepted licence. Without
    this the user waits out a container start and a model download to be told
    401 by a log line they have to go hunting for.
    """
    import json
    import os
    import urllib.error
    import urllib.request

    if os.environ.get("HF_TOKEN"):
        return
    try:
        with urllib.request.urlopen(
            f"https://huggingface.co/api/models/{model}", timeout=10
        ) as response:
            gated = json.load(response).get("gated")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return  # can't reach the hub to check; the training job will report the truth
    if gated:
        raise NeedsToken(
            f"{model} is gated on Hugging Face. Accept its licence on the model page, then:\n"
            f"  export HF_TOKEN=hf_...\n"
            f"  voiceprint deploy        (the token is picked up at deploy time)"
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
    "NeedsToken",
    "NotABaseModel",
    "check_available",
    "label",
    "reject_instruct",
    "resolve",
]
