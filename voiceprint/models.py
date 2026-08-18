"""Which base model a voice is trained on.

Any Hugging Face causal LM works. The presets are shorthands for ones worth
starting from; anything else is passed straight through as a repo id.
"""

from __future__ import annotations

# Shorthands for the two bases that have actually been trained and measured. Any
# other Hugging Face base model can be passed by id — it just hasn't been tried,
# and a preset that nobody has run is a recommendation you can't stand behind.
# Deliberately plain data with no Modal import: choosing a base model shouldn't
# require a cloud account to be configured.
MODEL_PRESETS = {
    "qwen14b": "Qwen/Qwen2.5-14B",
    "qwen7b": "Qwen/Qwen2.5-7B",
}
DEFAULT_MODEL = "qwen14b"

INSTRUCT_SUFFIXES = ("-instruct", "-it", "-chat", "-chat-hf")


class NotABaseModel(Exception):
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
            f"{model} is an instruct/chat model. Voiceprint trains on base models — "
            f"instruct-tuned ones already have a voice, and it isn't yours. "
            f"Try the base version (e.g. 'Qwen/Qwen2.5-14B', not '-Instruct')."
        )


def label(model: str) -> str:
    """The short name for a model id, for listings."""
    for preset, full in MODEL_PRESETS.items():
        if full == model:
            return preset
    return model


__all__ = ["DEFAULT_MODEL", "MODEL_PRESETS", "NotABaseModel", "label", "reject_instruct", "resolve"]
