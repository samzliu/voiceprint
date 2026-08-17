"""voiceprint — train a model on your writing, then draft in your voice."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from voiceprint import corpus, engine, prep, registry, remote, scorers, stylometry, train
from voiceprint.scaffold import DEFAULT_N, DEFAULT_TEMPERATURE, LENGTHS


def main() -> int:
    parser = argparse.ArgumentParser(prog="voiceprint", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_deploy = sub.add_parser("deploy", help="deploy the GPU app to your own Modal workspace")
    p_deploy.set_defaults(run=cmd_deploy)

    p_train = sub.add_parser("train", help="train a voice on a file or folder of your writing")
    p_train.add_argument("path", help="file or folder of .md/.txt you wrote")
    p_train.add_argument("--name", required=True, help="what to call this voice")
    p_train.add_argument("--model", default="14b", choices=["14b", "7b"])
    p_train.set_defaults(run=cmd_train)

    p_resume = sub.add_parser("resume", help="finish collecting a training job")
    p_resume.add_argument("job_id", nargs="?", help="defaults to the most recent unfinished job")
    p_resume.set_defaults(run=cmd_resume)

    p_write = sub.add_parser("write", help="draft in your voice")
    p_write.add_argument("notes", nargs="*", help="a bullet of the brief; repeat for more")
    p_write.add_argument("--notes-file", help="file of bullets, or - for stdin")
    p_write.add_argument("--continue-from", help="file whose text the draft should continue")
    p_write.add_argument("--length", default="medium", choices=list(LENGTHS))
    p_write.add_argument("--candidates", type=int, default=DEFAULT_N)
    p_write.add_argument("--temp", type=float, default=DEFAULT_TEMPERATURE)
    p_write.add_argument("--voice")
    p_write.add_argument("--scorer", default="stylometry", choices=["stylometry", "pangram"])
    p_write.add_argument("--all", action="store_true", help="show every candidate with its score")
    p_write.set_defaults(run=cmd_write)

    p_rewrite = sub.add_parser("rewrite", help="say this in my voice (stdin or a file)")
    p_rewrite.add_argument("path", nargs="?", help="file to rewrite; omit to read stdin")
    p_rewrite.add_argument("--candidates", type=int, default=4)
    p_rewrite.add_argument("--temp", type=float, default=DEFAULT_TEMPERATURE)
    p_rewrite.add_argument("--voice")
    p_rewrite.add_argument("--scorer", default="stylometry", choices=["stylometry", "pangram"])
    p_rewrite.set_defaults(run=cmd_rewrite)

    p_voices = sub.add_parser("voices", help="list trained voices")
    p_voices.set_defaults(run=cmd_voices)

    p_eval = sub.add_parser("eval", help="does it sound like you, and is it reciting?")
    p_eval.add_argument("voice", nargs="?")
    p_eval.add_argument("--samples", type=int, default=5)
    p_eval.add_argument("--scorer", default="stylometry", choices=["stylometry", "pangram"])
    p_eval.set_defaults(run=cmd_eval)

    p_mcp = sub.add_parser("mcp", help="run the MCP server on stdio")
    p_mcp.set_defaults(run=cmd_mcp)

    args = parser.parse_args()
    try:
        return args.run(args)
    except (
        corpus.CorpusTooSmall,
        registry.VoiceNotFound,
        remote.NotDeployed,
        FileNotFoundError,
        ValueError,
        RuntimeError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def cmd_deploy(_args) -> int:
    return remote.deploy()


def cmd_train(args) -> int:
    chunks, warning = train.prepare(args.path)
    words = sum(c.words for c in chunks)
    print(f"{words} words, {len(chunks)} chunks from {args.path}")
    if warning:
        print(f"warning: {warning}")

    job_id = train.start(chunks, args.name, args.model)
    print(f"training '{args.name}' on {args.model} — a few minutes. job {job_id}")
    print(f"safe to interrupt; pick it back up with:  voiceprint resume {job_id}")
    return _await_training(job_id)


def cmd_resume(args) -> int:
    job_id = args.job_id
    if not job_id:
        jobs = train.pending_jobs()
        if not jobs:
            print("no training jobs waiting to be collected")
            return 0
        job_id, name = jobs[-1]
        print(f"resuming '{name}' (job {job_id})")
    return _await_training(job_id)


def _await_training(job_id: str) -> int:
    voice = train.wait(job_id, on_tick=lambda: print(".", end="", flush=True))
    print(f"\ndone: {voice.pairs} pairs from {voice.words} words -> {voice.adapter_path}")
    print(f'\nwrite with:  voiceprint write --voice {voice.name} "your first bullet"')
    return 0


def cmd_write(args) -> int:
    notes = list(args.notes)
    if args.notes_file:
        notes += _read_bullets(args.notes_file)
    preceding = Path(args.continue_from).read_text(encoding="utf-8") if args.continue_from else ""
    if not notes and not preceding and not sys.stdin.isatty():
        notes += _read_bullets("-")

    draft = engine.write(
        notes=notes or None,
        preceding_text=preceding,
        length=args.length,
        voice_name=args.voice,
        n=args.candidates,
        temperature=args.temp,
        scorer_name=args.scorer,
    )

    if args.all:
        for rank, (text, score) in enumerate([(draft.text, draft.score)] + draft.alternates, 1):
            print(f"--- candidate {rank}  {args.scorer}={score:.3f}\n{text}\n")
        return 0

    print(draft.text)
    print(f"\n[{args.scorer} {draft.score:.3f}, best of {len(draft.alternates) + 1}]", file=sys.stderr)
    return 0


def cmd_rewrite(args) -> int:
    text = Path(args.path).read_text(encoding="utf-8") if args.path else sys.stdin.read()
    if not text.strip():
        raise ValueError("nothing to rewrite")
    print(
        engine.rewrite(
            text,
            voice_name=args.voice,
            n=args.candidates,
            temperature=args.temp,
            scorer_name=args.scorer,
        )
    )
    return 0


def cmd_voices(_args) -> int:
    voices = registry.load_all()
    if not voices:
        print("no voices yet — voiceprint train <path-to-your-writing> --name me")
        return 0
    for voice in voices:
        print(
            f"{voice.name:<16} {voice.base:<5} {voice.words:>6} words  "
            f"{voice.pairs:>3} pairs  {voice.trained_at}"
        )
    return 0


def cmd_eval(args) -> int:
    """Continue held-out passages the model never saw, then ask three questions:
    does it sound like the author, is it reciting, and how does that compare to
    the author's own unseen writing."""
    voice = engine.resolve(args.voice)
    if not voice.holdout:
        raise RuntimeError(f"'{voice.name}' has no held-out corpus to evaluate against")

    scorer = scorers.build(args.scorer, voice.profile)
    drafts = []
    for chunk in voice.holdout[: args.samples]:
        head, tail = prep.continuation_split(chunk)
        if not head or not tail:
            continue
        draft = engine.write(
            preceding_text=head + " ",
            length="medium",
            voice_name=voice.name,
            n=1,
            scorer_name=args.scorer,
        )
        drafts.append(draft.text)
        print(".", end="", flush=True)
    print()

    if not drafts:
        raise RuntimeError("held-out passages were too short to continue")

    generated = sum(scorer.score(d) for d in drafts) / len(drafts)
    human = sum(scorer.score(h) for h in voice.holdout) / len(voice.holdout)
    novel = sum(stylometry.novelty(d, voice.training) for d in drafts) / len(drafts)

    print(f"\nvoice: {voice.name}  ({len(drafts)} drafts continuing held-out passages)")
    print(f"  {args.scorer:<12} {generated:.3f}   (your own unseen writing: {human:.3f})")
    print(f"  novelty      {novel:.3f}   (1.000 = nothing lifted from the training text)")
    if novel < 0.95:
        print("  ^ that is low: it is reciting your corpus, not writing in your voice")
    return 0


def cmd_mcp(_args) -> int:
    from voiceprint.mcp_server import run

    run()
    return 0


def _read_bullets(source: str) -> list[str]:
    """A notes file is one bullet per line. A leading -, * or 1. is optional."""
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    lines = (re.sub(r"^[-*•]\s*|^\d+[.)]\s*", "", line.strip()) for line in raw.splitlines())
    return [line for line in lines if line]


if __name__ == "__main__":
    raise SystemExit(main())
