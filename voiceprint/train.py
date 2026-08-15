"""Client side of training: corpus in, registered voice out.

The corpus itself never leaves the machine. What goes to the user's Modal
workspace is the chunked prose it derives, and what comes back is an adapter.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from voiceprint import corpus, registry, remote, stylometry
from voiceprint.registry import HOME, Voice

HOLDOUT_EVERY = 7  # ~15%
PENDING_DIR = HOME / "pending"


def prepare(path: str) -> tuple[list[corpus.Chunk], str | None]:
    documents = corpus.read_path(path)
    chunks = corpus.to_chunks(documents)
    return chunks, corpus.check_size(chunks)


def split_holdout(chunks: list[corpus.Chunk]) -> tuple[list[corpus.Chunk], list[corpus.Chunk]]:
    """Deterministic split so a retrain is comparable to the run before it."""
    training = [c for i, c in enumerate(chunks) if i % HOLDOUT_EVERY]
    holdout = [c for i, c in enumerate(chunks) if not i % HOLDOUT_EVERY]
    if not training:
        return chunks, []
    return training, holdout


def _local_record(chunks, training, holdout, name: str, base: str) -> dict:
    """Everything about a voice that is computed on this machine and outlives the
    GPU job: the style profile, and the corpus splits `eval` needs."""
    return {
        "name": name,
        "base": base,
        "profile": stylometry.fit([c.text for c in training]).to_dict(),
        "words": sum(c.words for c in chunks),
        "chunks": len(chunks),
        "training": [c.text for c in training],
        "holdout": [c.text for c in holdout],
    }


def _register(record: dict, result: dict) -> Voice:
    voice = Voice(
        name=record["name"],
        base=record["base"],
        adapter_path=result["adapter_path"],
        profile=registry.Profile.from_dict(record["profile"]),
        words=record["words"],
        chunks=record["chunks"],
        pairs=result["pairs"],
        training=record["training"],
        holdout=record["holdout"],
    )
    registry.save(voice)
    return voice


def run(chunks: list[corpus.Chunk], name: str, base: str = "14b") -> tuple[Voice, dict]:
    """Train on chunks already read, so a caller that showed the user a corpus
    summary doesn't pay to read the folder twice."""
    training, holdout = split_holdout(chunks)
    record = _local_record(chunks, training, holdout, name, base)

    result = remote.trainer().remote(
        name=name,
        chunks=[asdict(c) for c in training],
        base=base,
    )
    return _register(record, result), result


def train(path: str, name: str, base: str = "14b") -> tuple[Voice, dict]:
    chunks, _warning = prepare(path)
    return run(chunks, name, base)


def spawn(path: str, name: str, base: str = "14b") -> str:
    """Start training and return a job id. Used by the MCP server, where a job
    that takes minutes cannot block a tool call."""
    chunks, _warning = prepare(path)
    training, holdout = split_holdout(chunks)

    call = remote.trainer().spawn(name=name, chunks=[asdict(c) for c in training], base=base)

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    record = _local_record(chunks, training, holdout, name, base)
    (PENDING_DIR / f"{call.object_id}.json").write_text(json.dumps(record), encoding="utf-8")
    return call.object_id


def collect(job_id: str) -> Voice | None:
    """None while the job is still running; a registered Voice once it lands."""
    import modal

    pending = PENDING_DIR / f"{job_id}.json"
    if not pending.exists():
        raise FileNotFoundError(f"no training job {job_id!r} started from this machine")

    try:
        result = modal.FunctionCall.from_id(job_id).get(timeout=0)
    except TimeoutError:
        return None

    voice = _register(json.loads(pending.read_text(encoding="utf-8")), result)
    pending.unlink()
    return voice
